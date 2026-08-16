"""Generic read-only governance precheck for raw rows.

This is a preflight adapter, not a business metric calculator. It only emits
defects when the corresponding raw field/schema is present and never writes or
normalizes the source rows.
"""

from __future__ import annotations

import copy
from collections import Counter
from datetime import datetime, timezone
from typing import Any


CONTRACT_NAME = "BIFROST_GOVERNANCE_PRECHECK_v1"
REPORT_CONTRACT_NAME = "BIFROST_DATA_GOVERNANCE_REPORT_v1"
DEFECT_TYPES = {
    "unit_inconsistent",
    "duplicate_key",
    "temporal_gap",
    "referential_broken",
    "business_exception",
}

# The business-facing governance contract has six stable categories.  A
# category may be ``detected``, ``tested_no_anomaly`` or ``not_tested``; the
# latter is important because absence of evidence must not be presented as a
# clean dataset.
GOVERNANCE_CATEGORIES = (
    "missing",
    "duplicate",
    "outlier",
    "format_inconsistent",
    "logic_conflict",
    "stale",
)


def _defect(kind: str, severity: str, field: str, examples: list[Any], impact: str) -> dict:
    return {
        "type": kind,
        "severity": severity,
        "field": field,
        "examples": examples[:5],
        "count": len(examples),
        "impact": impact,
        "source_write_performed": False,
        "actor_can_execute": False,
    }


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
    return None


def _utc_time(value: datetime) -> datetime:
    """Compare timestamps consistently without changing source values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def run_governance_precheck(contract: dict) -> dict:
    if not isinstance(contract, dict):
        raise TypeError("contract must be an object")
    if contract.get("contract_name") != CONTRACT_NAME:
        return {"status": "blocked", "reason": "invalid_contract_name", "defects": [], "source_write_performed": False, "actor_can_execute": False}
    if contract.get("source_write_performed") is not False or contract.get("actor_can_execute") is not False:
        return {"status": "blocked", "reason": "write_boundary_violation", "defects": [], "source_write_performed": False, "actor_can_execute": False}
    rows = contract.get("raw_rows")
    if not isinstance(rows, list) or not rows:
        return {
            "status": "not_run",
            "reason": "raw_rows_missing",
            "defects": [],
            "source_write_performed": False,
            "actor_can_execute": False,
        }
    schema = contract.get("schema") if isinstance(contract.get("schema"), dict) else {}
    defects: list[dict] = []

    key_field = schema.get("primary_key")
    if isinstance(key_field, str) and key_field:
        values = [row.get(key_field) for row in rows if isinstance(row, dict)]
        duplicate_values = [value for value, count in Counter(values).items() if value not in (None, "") and count > 1]
        if duplicate_values:
            defects.append(_defect("duplicate_key", "high", key_field, duplicate_values, "主键重复会导致事件或证据被重复计数"))

    unit_fields = schema.get("unit_fields") if isinstance(schema.get("unit_fields"), dict) else {}
    for field, expected in unit_fields.items():
        if not isinstance(expected, str):
            continue
        observed = {row.get(field) for row in rows if isinstance(row, dict) and row.get(field) not in (None, "")}
        if len(observed) > 1:
            defects.append(_defect("unit_inconsistent", "medium", field, sorted(map(str, observed)), "单位不一致会造成跨记录比较失真"))

    time_field = schema.get("time_field")
    if isinstance(time_field, str) and time_field:
        parsed = [(_parse_time(row.get(time_field)), row.get(time_field)) for row in rows if isinstance(row, dict)]
        invalid = [raw for dt, raw in parsed if raw not in (None, "") and dt is None]
        if invalid:
            defects.append(_defect("temporal_gap", "medium", time_field, invalid, "时间字段无法排序或判断时效"))

    ref_field = schema.get("reference_field")
    allowed = schema.get("allowed_values") if isinstance(schema.get("allowed_values"), list) else None
    if isinstance(ref_field, str) and allowed is not None:
        invalid = [row.get(ref_field) for row in rows if isinstance(row, dict) and row.get(ref_field) not in (None, "") and row.get(ref_field) not in allowed]
        if invalid:
            defects.append(_defect("referential_broken", "high", ref_field, invalid, "引用值不在维表允许集合中，关联分析不可直接使用"))

    exception_rules = schema.get("business_exception_rules") if isinstance(schema.get("business_exception_rules"), list) else []
    for rule in exception_rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("field"), str):
            continue
        field = rule["field"]
        threshold = rule.get("max")
        if isinstance(threshold, (int, float)):
            invalid = [row.get(field) for row in rows if isinstance(row, dict) and isinstance(row.get(field), (int, float)) and row.get(field) > threshold]
            if invalid:
                defects.append(_defect("business_exception", "high", field, invalid, rule.get("impact", "业务值超出规则阈值")))

    return {
        "status": "warning" if defects else "pass",
        "defect_count": len(defects),
        "defects": defects,
        "source_row_count": len(rows),
        "source_write_performed": False,
        "actor_can_execute": False,
        "raw_rows_returned": False,
    }


def validate_governance_result(result: dict) -> list[str]:
    errors: list[str] = []
    if result.get("source_write_performed") is not False or result.get("actor_can_execute") is not False:
        errors.append("write_boundary_violation")
    if result.get("status") not in {"pass", "warning", "not_run", "blocked"}:
        errors.append("invalid_status")
    for item in result.get("defects", []) or []:
        if item.get("type") not in DEFECT_TYPES:
            errors.append("unknown_defect_type")
        if item.get("count", 0) < 1:
            errors.append("empty_defect")
    return errors


def _category_result(category: str, *, status: str, defects: list[dict] | None = None,
                     rule: str = "", data_gap: str | None = None) -> dict:
    items = defects or []
    return {
        "defect_type": category,
        "status": status,
        "issue_count": sum(int(item.get("count", 0) or 0) for item in items),
        "issues": items,
        "rule": rule,
        "data_gap": data_gap,
        "requires_human_confirmation": bool(items),
        "source_write_performed": False,
        "actor_can_execute": False,
    }


def build_governance_report(*, source_profile: dict, rows: list[dict],
                            mapping_status: str, capability_manifest: dict | None = None,
                            freshness_policy: dict | None = None) -> dict:
    """Build one business-readable, read-only governance report.

    This deliberately operates on the canonical rows produced after an
    approved mapping.  Before approval it returns a visible mapping gate and
    six ``not_tested`` categories, so the UI cannot mistake an empty result
    for a healthy source.
    """
    if mapping_status != "approved":
        categories = {
            key: _category_result(key, status="not_tested", data_gap="mapping_not_approved")
            for key in GOVERNANCE_CATEGORIES
        }
        return {
            "contract_name": REPORT_CONTRACT_NAME,
            "status": "blocked",
            "health_score": None,
            "health_score_display": "未完成",
            "source_profile": source_profile,
            "mapping_status": mapping_status,
            "categories": categories,
            "enterprise_defect_types": [
                {
                    "defect_type": key,
                    "status": "not_tested",
                    "status_label": "未检测",
                    "issue_count": 0,
                    "affected_records": 0,
                    "label": key,
                    "proposed_action": "先完成字段映射确认",
                }
                for key in categories
            ],
            "issues": [],
            "data_gaps": ["mapping_not_approved"],
            "tested_category_count": 0,
            "not_tested_category_count": len(categories),
            "source_row_count": 0,
            "source_write_performed": False,
            "actor_can_execute": False,
        }

    rows = [row for row in rows if isinstance(row, dict)]
    issues: list[dict] = []
    category: dict[str, dict] = {}

    # Missing values: only mapped fields that have at least one observed value
    # are tested, preventing an unmapped capability from becoming a fake DQ
    # defect.
    mapped_fields = sorted({key for row in rows for key in row if key not in {"source_table", "source_row", "evidence_ref", "derived_fields", "normalization_notes"}})
    missing_defs = []
    for field in mapped_fields:
        missing_rows = [row.get("evidence_ref") for row in rows if row.get(field) in (None, "")]
        if missing_rows and len(missing_rows) < len(rows):
            missing_defs.append(_defect("missing", "medium", field, missing_rows, "字段部分缺失，相关指标可能不完整"))
    category["missing"] = _category_result("missing", status="detected" if missing_defs else "tested_no_anomaly", defects=missing_defs, rule="已映射字段非空率检查")

    # Duplicate records: use an available business key, never the physical
    # source row itself (which is necessarily unique).
    key_fields = [field for field in ("line_id", "shift_date", "shift_id", "work_order_id") if any(field in row for row in rows)]
    duplicate_defs = []
    if len(key_fields) >= 2:
        seen: dict[tuple, list[str]] = {}
        for row in rows:
            key = tuple(row.get(field) for field in key_fields)
            if all(value not in (None, "") for value in key):
                seen.setdefault(key, []).append(row.get("evidence_ref", ""))
        duplicate_refs = [refs for refs in seen.values() if len(refs) > 1]
        if duplicate_refs:
            duplicate_defs.append(_defect("duplicate", "high", "+".join(key_fields), [ref for refs in duplicate_refs for ref in refs], "同一业务键重复，可能导致指标重复计算"))
        category["duplicate"] = _category_result("duplicate", status="detected" if duplicate_defs else "tested_no_anomaly", defects=duplicate_defs, rule=f"业务键唯一性检查：{'+'.join(key_fields)}")
    else:
        category["duplicate"] = _category_result("duplicate", status="not_tested", data_gap="business_key_missing", rule="需要产线/日期/工单等业务键")

    abnormal_defs = []
    for field in ("availability", "performance_rate_raw", "quality_rate", "oee_source"):
        values = [row.get(field) for row in rows if isinstance(row.get(field), (int, float))]
        bad = [row.get("evidence_ref") for row in rows if isinstance(row.get(field), (int, float)) and not 0 <= row.get(field) <= 1]
        if bad:
            abnormal_defs.append(_defect("outlier", "high", field, bad, "比例字段超出0到1范围，禁止直接参与指标计算"))
    for row in rows:
        total, good = row.get("total_output"), row.get("good_output")
        if isinstance(total, (int, float)) and isinstance(good, (int, float)) and (total < 0 or good < 0 or good > total):
            abnormal_defs.append(_defect("outlier", "high", "total_output/good_output", [row.get("evidence_ref", "")], "产量守恒关系异常"))
    category["outlier"] = _category_result("outlier", status="detected" if abnormal_defs else "tested_no_anomaly", defects=abnormal_defs, rule="比例值域与产量守恒检查")

    format_defs = []
    normalized = [note for row in rows for note in (row.get("normalization_notes") or [])]
    if normalized:
        format_defs.append(_defect("format_inconsistent", "medium", "source_value_format", normalized, "源数据单位或比例格式已被识别并在只读规范化中标记"))
    category["format_inconsistent"] = _category_result("format_inconsistent", status="detected" if format_defs else "tested_no_anomaly", defects=format_defs, rule="单位/比例格式识别")

    logic_defs = []
    for row in rows:
        total, good, quality = row.get("total_output"), row.get("good_output"), row.get("quality_rate")
        if isinstance(total, (int, float)) and total > 0 and isinstance(good, (int, float)) and isinstance(quality, (int, float)):
            if abs(good / total - quality) > 0.01:
                logic_defs.append(_defect("logic_conflict", "high", "quality_rate", [row.get("evidence_ref", "")], "良品数/总产量与质量率不一致"))
    category["logic_conflict"] = _category_result("logic_conflict", status="detected" if logic_defs else "tested_no_anomaly", defects=logic_defs, rule="良品数/总产量/质量率一致性检查")

    category["stale"] = _category_result("stale", status="not_tested", data_gap="freshness_sla_not_provided", rule="需要数据源更新时间和时效阈值")

    # Freshness is only testable when the source supplies both an update
    # timestamp field and an explicit SLA. Business dates are not treated as
    # update timestamps, so historical demo snapshots are not falsely stale.
    policy = freshness_policy if isinstance(freshness_policy, dict) else {}
    timestamp_field = policy.get("timestamp_field")
    sla_hours = policy.get("sla_hours")
    as_of = _parse_time(policy.get("as_of"))
    if isinstance(timestamp_field, str) and timestamp_field.strip() and isinstance(sla_hours, (int, float)) and sla_hours >= 0:
        as_of_utc = _utc_time(as_of or datetime.now(timezone.utc))
        invalid_refs: list[Any] = []
        stale_refs: list[Any] = []
        for row in rows:
            parsed = _parse_time(row.get(timestamp_field))
            ref = row.get("evidence_ref", "")
            if parsed is None:
                invalid_refs.append(ref)
                continue
            age_hours = (as_of_utc - _utc_time(parsed)).total_seconds() / 3600
            if age_hours > float(sla_hours):
                stale_refs.append(ref)
        stale_defs = []
        if stale_refs:
            stale_defs.append(_defect("stale", "high", timestamp_field, stale_refs, "数据更新时间超过配置的时效阈值"))
        category["stale"] = _category_result(
            "stale",
            status="detected" if stale_defs else "tested_no_anomaly",
            defects=stale_defs,
            data_gap="freshness_timestamp_invalid" if invalid_refs else None,
            rule=f"更新时间字段 {timestamp_field}，SLA {sla_hours} 小时",
        )

    for value in category.values():
        issues.extend(value["issues"])
    issue_records = [
        {
            "id": f"DQ-{index:03d}",
            "category": item.get("type"),
            "description": f"字段 {item.get('field')}: {item.get('impact')}",
            "analysis": item.get("impact"),
            "suggested_action": "请核对来源记录并提交人工处理草稿",
            "severity": item.get("severity", "medium"),
            "status": "open",
            "evidence_ref": (item.get("examples") or [None])[0],
            "affected_lines": [],
            "rule": item.get("type"),
            "source_write_performed": False,
            "actor_can_execute": False,
        }
        for index, item in enumerate(issues, start=1)
    ]
    # Health is a category-level signal, not a row-count sum.  Otherwise a
    # large but healthy production file would always collapse to 0/100 merely
    # because the same rule found many affected rows.
    category_weights = {"high": 12, "medium": 6, "low": 2}
    penalty = 0
    for value in category.values():
        if value["status"] == "not_tested":
            penalty += 4
        elif value["status"] == "detected":
            severity = max((item.get("severity", "medium") for item in value["issues"]), key=lambda item: category_weights.get(item, 2), default="medium")
            penalty += category_weights.get(severity, 6)
    score = max(0, 100 - penalty)
    tested = sum(value["status"] != "not_tested" for value in category.values())
    gaps = [value["data_gap"] for value in category.values() if value.get("data_gap")]
    return {
        "contract_name": REPORT_CONTRACT_NAME,
        "status": "warning" if issues or gaps else "pass",
        "health_score": score,
        "health_score_display": f"{score}/100",
        "source_profile": source_profile,
        "mapping_status": mapping_status,
        "categories": category,
        "enterprise_defect_types": [
            {
                "defect_type": key,
                "status": value["status"],
                "status_label": "发现问题" if value["status"] == "detected" else "已检测无异常" if value["status"] == "tested_no_anomaly" else "未检测",
                "issue_count": value["issue_count"],
                "affected_records": value["issue_count"],
                "label": key,
                "proposed_action": "请查看证据并提交人工处理草稿" if value["status"] == "detected" else "当前规则未发现问题" if value["status"] == "tested_no_anomaly" else "补充该类检测所需字段或规则",
                "detected_by": value["rule"],
            }
            for key, value in category.items()
        ],
        "issues": issue_records,
        "raw_issues": issues,
        "data_gaps": gaps,
        "tested_category_count": tested,
        "not_tested_category_count": len(category) - tested,
        "source_row_count": len(rows),
        "source_write_performed": False,
        "actor_can_execute": False,
    }


def validate_governance_report(report: dict) -> list[str]:
    """Validate the public governance contract before a UI consumes it."""
    errors: list[str] = []
    if report.get("contract_name") != REPORT_CONTRACT_NAME:
        errors.append("invalid_contract_name")
    if report.get("status") not in {"pass", "warning", "blocked"}:
        errors.append("invalid_status")
    if set((report.get("categories") or {}).keys()) != set(GOVERNANCE_CATEGORIES):
        errors.append("category_coverage_incomplete")
    if report.get("source_write_performed") is not False or report.get("actor_can_execute") is not False:
        errors.append("write_boundary_violation")
    for item in report.get("issues", []) or []:
        if not item.get("evidence_ref"):
            errors.append("issue_missing_evidence")
        if item.get("status") not in {"open", "resolved", "pending_confirmation"}:
            errors.append("invalid_issue_status")
    return sorted(set(errors))


__all__ = ["CONTRACT_NAME", "REPORT_CONTRACT_NAME", "GOVERNANCE_CATEGORIES", "run_governance_precheck", "validate_governance_result", "build_governance_report", "validate_governance_report"]

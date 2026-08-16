"""
BIFROST 生产诊断只读分析 — 主诊断模块
logical_version: 0.1.2

链路：
  语义消费者
  → BIFROST_DECISION_INPUT_v0.1
  → bifrost-production-diagnosis-readonly（本模块）
  → BIFROST_SPECIALIST_RESULT_v0.1.3
  → BIFROST 决策编排智能体

本 Skill 只承担生产专业的确定性分析（班次/OEE/产量/良率/停机/换产），
不承担字段映射、数据接入、跨源关联、业务写回或最终决策执行。

9 个确定性能力：
1. validate_production_input_contract
2. group_facts_by_semantic_record
3. extract_production_metrics
4. analyze_oee_direct_drivers
5. analyze_downtime_evidence
6. analyze_shift_trend_if_supported
7. classify_production_risks
8. build_production_result
9. validate_specialist_result_contract

v0.1.2 变更（04D.3-PROD）：
- 输出合同升级为 BIFROST-SPECIALIST-RESULT-v0.1.3
- evidence_refs 改用 EVREF-v1:<SHA256>（字段事实级），由共享 build_canonical_evidence_ref 生成
- 删除所有占位证据（EV:no_evidence、EV:*:no_provenance、裸 semantic_record_key 等）
- metrics/causes/actions 每条证据必须通过 validate_specialist_result_against_input
- metrics 字段绑定：每个 metric 的 evidence_refs 解析到的 semantic_field 必须一致
- 高风险动作存在时，非 blocked 结果必须为 needs_confirmation（不得为 warning/completed）
- data_gaps 使用共享 merge_data_gaps 归并，输出 affected_record_count/occurrence_count/sample_source_locators
- 修复真实联调中 321/741 条重复 data_gap 直接输出的问题
- 保留 OEE 三因子、物料风险非直接原因、禁止伪造 MTBF/MTTR、禁止制造趋势等既有规则
"""

import copy
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from . import production_constants as C

# ---- 加载共享验证器函数（build_canonical_evidence_ref / merge_data_gaps）----
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_ROOT = os.path.dirname(_SCRIPTS_DIR)
_VALIDATOR_PATH = os.path.join(_SKILL_ROOT, "validator", "specialist_contract_validator.py")

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("_bifrost_shared_validator", _VALIDATOR_PATH)
_shared_scv = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_shared_scv)

build_canonical_evidence_ref = _shared_scv.build_canonical_evidence_ref
merge_data_gaps = _shared_scv.merge_data_gaps


# =========================================================================
# 1. validate_production_input_contract
# =========================================================================
def validate_production_input_contract(decision_input: dict) -> dict:
    """
    验证 BIFROST_DECISION_INPUT_v0.1 输入合同合规性。

    门控规则：
    - contract_name 必须为 BIFROST_DECISION_INPUT_v0.1
    - source_write_performed 必须为 false
    - actor_can_execute 必须为 false
    - validation.status 不得为 failed/blocked
    - normalized_facts 只能消费 value_consumption_status=usable 的值
    - 每个业务事实必须具有 provenance_ref
    """
    result = {
        "valid": True,
        "blocked_code": None,
        "errors": [],
        "warnings": [],
    }

    if decision_input.get("contract_name") != C.INPUT_CONTRACT_NAME:
        result["valid"] = False
        result["blocked_code"] = "BLOCKED_INPUT_CONTRACT"
        result["errors"].append(
            f"contract_name 不是 {C.INPUT_CONTRACT_NAME}，实际: {decision_input.get('contract_name')!r}"
        )
        return result

    if decision_input.get("source_write_performed") is not False:
        result["valid"] = False
        result["blocked_code"] = "BLOCKED_SOURCE_WRITE_PERFORMED"
        result["errors"].append(
            f"source_write_performed 必须为 false，实际: {decision_input.get('source_write_performed')!r}"
        )
        return result

    if decision_input.get("actor_can_execute") is not False:
        result["valid"] = False
        result["blocked_code"] = "BLOCKED_ACTOR_CAN_EXECUTE"
        result["errors"].append(
            f"actor_can_execute 必须为 false，实际: {decision_input.get('actor_can_execute')!r}"
        )
        return result

    validation = decision_input.get("validation", {}) or {}
    v_status = validation.get("status", "")
    if v_status in C.BLOCKED_VALIDATION_STATUSES:
        result["valid"] = False
        result["blocked_code"] = "BLOCKED_VALIDATION_STATUS"
        result["errors"].append(
            f"validation.status 为 {v_status!r}，不得为 failed/blocked"
        )
        return result

    facts = decision_input.get("normalized_facts", []) or []
    for i, fact in enumerate(facts):
        vcs = fact.get("value_consumption_status", "")
        if vcs != C.USABLE_STATUS:
            result["valid"] = False
            result["blocked_code"] = "BLOCKED_UNUSABLE_FACT"
            result["errors"].append(
                f"normalized_facts[{i}] ({fact.get('semantic_field', '?')}) "
                f"value_consumption_status={vcs!r}，只允许 usable"
            )
            return result

        prov = fact.get("provenance_ref")
        if not prov or not isinstance(prov, dict):
            result["valid"] = False
            result["blocked_code"] = "BLOCKED_MISSING_PROVENANCE"
            result["errors"].append(
                f"normalized_facts[{i}] ({fact.get('semantic_field', '?')}) 缺少 provenance_ref"
            )
            return result

        if not prov.get("evidence_locator"):
            result["valid"] = False
            result["blocked_code"] = "BLOCKED_MISSING_EVIDENCE_LOCATOR"
            result["errors"].append(
                f"normalized_facts[{i}] ({fact.get('semantic_field', '?')}) "
                "provenance_ref 缺少 evidence_locator"
            )
            return result

        if fact.get("normalized_value") is None:
            result["valid"] = False
            result["blocked_code"] = "BLOCKED_NULL_NORMALIZED_VALUE"
            result["errors"].append(
                f"normalized_facts[{i}] ({fact.get('semantic_field', '?')}) normalized_value 为 None"
            )
            return result

    return result


# =========================================================================
# 2. group_facts_by_semantic_record
# =========================================================================
def group_facts_by_semantic_record(normalized_facts: list[dict]) -> dict[str, list[dict]]:
    """按 semantic_record_key 分组事实。不得跨记录、跨实体自行拼接。"""
    groups: dict[str, list[dict]] = {}
    for fact in normalized_facts:
        key = fact.get("semantic_record_key", "")
        if not key:
            continue
        groups.setdefault(key, []).append(fact)
    return groups


def _build_fact_lookup(normalized_facts: list[dict]) -> dict[tuple[str, str], dict]:
    """构建 (record_key, semantic_field) → normalized_fact 索引，用于 EVREF 构建。"""
    lookup: dict[tuple[str, str], dict] = {}
    for fact in normalized_facts:
        rk = fact.get("semantic_record_key", "")
        sf = fact.get("semantic_field", "")
        if rk and sf:
            lookup[(rk, sf)] = fact
    return lookup


# =========================================================================
# 3. extract_production_metrics
# =========================================================================
def extract_production_metrics(grouped_facts: dict[str, list[dict]]) -> dict[str, dict]:
    """从分组事实中提取生产相关指标。只消费 normalized_value。"""
    metrics: dict[str, dict] = {}
    for record_key, facts in grouped_facts.items():
        record_metrics: dict[str, Any] = {
            "semantic_record_key": record_key,
            "source_table": "",
            "source_record_id": "",
            "values": {},
            "display_formats": {},
            "units": {},
            "provenance_refs": {},
        }
        for fact in facts:
            field = fact.get("semantic_field", "")
            value = fact.get("normalized_value")
            record_metrics["values"][field] = value
            if fact.get("display_format"):
                record_metrics["display_formats"][field] = fact["display_format"]
            if fact.get("normalized_unit"):
                record_metrics["units"][field] = fact["normalized_unit"]
            if fact.get("provenance_ref"):
                record_metrics["provenance_refs"][field] = fact["provenance_ref"]
            if not record_metrics["source_table"] and fact.get("source_table"):
                record_metrics["source_table"] = fact["source_table"]
            if not record_metrics["source_record_id"] and fact.get("source_record_id"):
                record_metrics["source_record_id"] = fact["source_record_id"]
        metrics[record_key] = record_metrics
    return metrics


def _build_evref(fact_lookup: dict, record_key: str, field: str) -> str | None:
    """使用共享 build_canonical_evidence_ref 构建字段级 EVREF-v1。

    返回 None 时该事实无法生成合法 EVREF，不得作为业务结论证据。
    """
    fact = fact_lookup.get((record_key, field))
    if fact is None:
        return None
    return build_canonical_evidence_ref(fact)


# =========================================================================
# 4. analyze_oee_direct_drivers
# =========================================================================
def analyze_oee_direct_drivers(record_metrics: dict, fact_lookup: dict, record_key: str) -> dict:
    """分析 OEE 直接驱动因子。"""
    analysis = {
        "direct_drivers": [],
        "oee_source": None,
        "oee_recomputed": None,
        "recompute_performed": False,
        "recompute_blocked_reason": None,
        "data_gaps": [],
    }
    values = record_metrics.get("values", {})

    factors_present = {}
    factors_missing = []
    for factor in C.OEE_RECOMPUTE_REQUIRED_FACTORS:
        if factor in values and values[factor] is not None:
            factors_present[factor] = values[factor]
        else:
            factors_missing.append(factor)

    if len(factors_present) == 3:
        for factor in C.OEE_DIRECT_DRIVERS:
            evref = _build_evref(fact_lookup, record_key, factor)
            analysis["direct_drivers"].append({
                "driver": factor,
                "value": factors_present[factor],
                "display_format": record_metrics.get("display_formats", {}).get(factor, ""),
                "evidence_evref": evref,
                "classification": "OEE直接驱动因子",
            })

    if C.OEE_SOURCE_FIELD in values and values[C.OEE_SOURCE_FIELD] is not None:
        oee_evref = _build_evref(fact_lookup, record_key, C.OEE_SOURCE_FIELD)
        analysis["oee_source"] = {
            "value": values[C.OEE_SOURCE_FIELD],
            "display_format": record_metrics.get("display_formats", {}).get(C.OEE_SOURCE_FIELD, ""),
            "evidence_evref": oee_evref,
        }
    else:
        analysis["data_gaps"].append({
            "semantic_field": C.OEE_SOURCE_FIELD,
            "reason": "source_value_absent",
            "required_resolution": "oee_source 值缺失，无法对比来源值与复算值",
        })

    can_recompute = values.get(C.CAN_RECOMPUTE_OEE_FIELD)
    if can_recompute is True and len(factors_present) == 3:
        a = _to_float(factors_present["availability"])
        p = _to_float(factors_present["performance_rate"])
        q = _to_float(factors_present["quality_factor"])
        if a is not None and p is not None and q is not None:
            recomputed = round(a * p * q, 6)
            analysis["oee_recomputed"] = {
                "value": recomputed,
                "formula": "availability × performance_rate × quality_factor",
                "inputs": {
                    "availability": factors_present["availability"],
                    "performance_rate": factors_present["performance_rate"],
                    "quality_factor": factors_present["quality_factor"],
                },
                "evidence": "deterministic_recompute_from_three_factors",
            }
            analysis["recompute_performed"] = True
        else:
            analysis["recompute_blocked_reason"] = "三因子存在非数值，无法复算"
            analysis["data_gaps"].append({
                "semantic_field": C.OEE_RECOMPUTED_FIELD,
                "reason": "factor_not_numeric",
                "required_resolution": "三因子含非数值，需数据面修正后重新物化",
            })
    else:
        if can_recompute is not True:
            analysis["recompute_blocked_reason"] = "can_recompute_oee 不为 true，不得复算"
            analysis["data_gaps"].append({
                "semantic_field": C.OEE_RECOMPUTED_FIELD,
                "reason": "recompute_not_permitted",
                "required_resolution": "can_recompute_oee 未置 true，不得自行复算 OEE",
            })
        elif factors_missing:
            analysis["recompute_blocked_reason"] = f"三因子不完整，缺失: {factors_missing}"
            analysis["data_gaps"].append({
                "semantic_field": C.OEE_RECOMPUTED_FIELD,
                "reason": "factors_incomplete",
                "missing_factors": factors_missing,
                "required_resolution": "三因子不完整，不得复算 OEE",
            })

    for missing in factors_missing:
        analysis["data_gaps"].append({
            "semantic_field": missing,
            "reason": "factor_absent_for_oee_driver",
            "required_resolution": "缺少 OEE 直接驱动因子，无法识别为直接驱动",
        })

    return analysis


# =========================================================================
# 5. analyze_downtime_evidence
# =========================================================================
def analyze_downtime_evidence(record_metrics: dict, fact_lookup: dict, record_key: str) -> dict:
    """分析停机证据。"""
    analysis = {
        "downtime_evidence": [],
        "material_continuity_risk": None,
        "material_as_oee_cause": False,
        "material_cause_blocked_reason": None,
        "mtbf_mttr": None,
        "mtbf_mttr_blocked_reason": None,
        "data_gaps": [],
    }
    values = record_metrics.get("values", {})

    unplanned = values.get(C.UNPLANNED_DOWNTIME_FIELD)
    if unplanned is not None:
        evref = _build_evref(fact_lookup, record_key, C.UNPLANNED_DOWNTIME_FIELD)
        analysis["downtime_evidence"].append({
            "type": "unplanned_downtime",
            "value": unplanned,
            "unit": record_metrics.get("units", {}).get(C.UNPLANNED_DOWNTIME_FIELD, "minutes"),
            "evidence_evref": evref,
            "impact": "availability_drop_evidence",
        })

    planned = values.get(C.PLANNED_DOWNTIME_FIELD)
    if planned is not None:
        evref = _build_evref(fact_lookup, record_key, C.PLANNED_DOWNTIME_FIELD)
        analysis["downtime_evidence"].append({
            "type": "planned_downtime",
            "value": planned,
            "unit": record_metrics.get("units", {}).get(C.PLANNED_DOWNTIME_FIELD, "minutes"),
            "evidence_evref": evref,
            "impact": "planned_downtime_reference",
        })

    material_gap = values.get(C.MATERIAL_GAP_QTY_FIELD)
    if material_gap is not None:
        mat_evref = _build_evref(fact_lookup, record_key, C.MATERIAL_GAP_QTY_FIELD)
        analysis["material_continuity_risk"] = {
            "type": "material_gap_continuity_risk",
            "value": material_gap,
            "material_code": values.get(C.MATERIAL_GAP_MATERIAL_FIELD),
            "evidence_evref": mat_evref,
            "classification": "后续生产连续性风险（非OEE直接驱动）",
        }
        rel_status = values.get(C.RELATION_MATERIALIZATION_FIELD)
        downtime_group = values.get(C.DOWNTIME_GROUP_FIELD)
        if rel_status != C.MATERIALIZED_STATUS:
            analysis["material_as_oee_cause"] = False
            analysis["material_cause_blocked_reason"] = (
                f"relation_materialization_status={rel_status!r}，未物化，禁止关联查询"
            )
        elif downtime_group != C.MATERIALS_DOWNTIME_GROUP:
            analysis["material_as_oee_cause"] = False
            analysis["material_cause_blocked_reason"] = (
                f"停机组={downtime_group!r}，非 MATERIALS，物料缺口不构成 OEE 直接停机原因"
            )
        else:
            analysis["material_as_oee_cause"] = False
            analysis["material_cause_blocked_reason"] = (
                "存在已物化 MATERIALS 停机关联，但仍仅表述为间接影响，不得称为 OEE 直接原因"
            )

    has_equipment = values.get(C.EQUIPMENT_ID_FIELD) is not None
    has_fault = values.get(C.FAULT_CODE_FIELD) is not None
    has_repair = values.get(C.REPAIR_WORK_ORDER_FIELD) is not None

    if has_equipment and has_fault and has_repair:
        mtbf = values.get(C.MTBF_FIELD)
        mttr = values.get(C.MTTR_FIELD)
        if mtbf is not None or mttr is not None:
            analysis["mtbf_mttr"] = {
                "mtbf": mtbf,
                "mttr": mttr,
                "evidence": "computed_from_equipment_fault_repair",
            }
    else:
        missing = []
        if not has_equipment:
            missing.append(C.EQUIPMENT_ID_FIELD)
        if not has_fault:
            missing.append(C.FAULT_CODE_FIELD)
        if not has_repair:
            missing.append(C.REPAIR_WORK_ORDER_FIELD)
        analysis["mtbf_mttr_blocked_reason"] = (
            f"缺少 MTBF/MTTR 必需证据: {missing}，不得计算"
        )
        analysis["data_gaps"].append({
            "semantic_field": "mtbf_mttr",
            "reason": "missing_equipment_fault_repair_evidence",
            "missing_fields": missing,
            "required_resolution": "缺少 EquipmentID/故障码/维修工单，不得计算 MTBF/MTTR",
        })

    return analysis


# =========================================================================
# 6. analyze_shift_trend_if_supported
# =========================================================================
def analyze_shift_trend_if_supported(all_metrics: dict[str, dict]) -> dict:
    """分析班次趋势（仅在时间字段与记录顺序证据齐全时）。"""
    analysis = {
        "trend_supported": False,
        "trend": None,
        "blocked_reason": None,
        "data_gaps": [],
    }

    ordered_records = []
    for record_key, metrics in all_metrics.items():
        values = metrics.get("values", {})
        shift_date = values.get(C.SHIFT_DATE_FIELD)
        shift_sequence = values.get(C.SHIFT_SEQUENCE_FIELD)
        if shift_date is not None and shift_sequence is not None:
            ordered_records.append({
                "record_key": record_key,
                "shift_date": shift_date,
                "shift_sequence": shift_sequence,
                "oee_source": values.get(C.OEE_SOURCE_FIELD),
            })

    if len(ordered_records) < C.TREND_MIN_RECORDS:
        analysis["blocked_reason"] = (
            f"有序记录数 {len(ordered_records)} < {C.TREND_MIN_RECORDS}，"
            "缺少时间字段或记录顺序证据，不得声称形成趋势"
        )
        analysis["data_gaps"].append({
            "semantic_field": "shift_trend",
            "reason": "insufficient_temporal_evidence",
            "required_resolution": "缺少时间字段或记录顺序证据，不得制造趋势",
        })
        return analysis

    ordered_records.sort(key=lambda r: _to_float(r["shift_sequence"]) or 0)
    oee_values = [r["oee_source"] for r in ordered_records if r["oee_source"] is not None]
    if len(oee_values) != len(ordered_records):
        analysis["blocked_reason"] = "部分记录缺少 oee_source，趋势不完整"
        analysis["data_gaps"].append({
            "semantic_field": "shift_trend",
            "reason": "incomplete_oee_series",
            "required_resolution": "OEE 序列不完整，不得声称形成趋势",
        })
        return analysis

    analysis["trend_supported"] = True
    analysis["trend"] = {
        "type": "shift_oee_sequence",
        "record_count": len(ordered_records),
        "sequence": ordered_records,
        "evidence": "temporal_order_from_shift_date_and_sequence",
    }
    return analysis


# =========================================================================
# 7. classify_production_risks
# =========================================================================
def classify_production_risks(record_metrics: dict, oee_analysis: dict, downtime_analysis: dict) -> dict:
    """分类生产风险并确定严重度。"""
    values = record_metrics.get("values", {})
    risks = []

    for driver in oee_analysis.get("direct_drivers", []):
        risks.append({
            "risk_type": "oee_direct_driver",
            "driver": driver["driver"],
            "value": driver["value"],
            "classification": "OEE直接驱动因子",
            "evidence_evref": driver["evidence_evref"],
        })

    for ev in downtime_analysis.get("downtime_evidence", []):
        if ev["impact"] == "availability_drop_evidence":
            risks.append({
                "risk_type": "unplanned_downtime",
                "value": ev["value"],
                "classification": "开动率下降证据",
                "evidence_evref": ev["evidence_evref"],
            })

    material_risk = downtime_analysis.get("material_continuity_risk")
    if material_risk:
        risks.append({
            "risk_type": "material_gap_continuity_risk",
            "value": material_risk["value"],
            "material_code": material_risk.get("material_code"),
            "classification": "后续生产连续性风险（非OEE直接驱动）",
            "evidence_evref": material_risk["evidence_evref"],
        })

    risk_level = values.get(C.RISK_LEVEL_FIELD)
    severity_rule_id = values.get("severity_rule_id")
    if risk_level is not None and severity_rule_id:
        severity = risk_level
        missing_severity_rule = False
    else:
        severity = C.SEVERITY_UNKNOWN
        missing_severity_rule = True

    return {
        "risks": risks,
        "severity": severity,
        "missing_severity_rule": missing_severity_rule,
        "severity_note": (
            "severity 依据输入中已物化的 risk_level + severity_rule_id；"
            "未提供批准的阈值规则时为 unknown"
        ),
    }


# =========================================================================
# 8. build_production_result
# =========================================================================
def build_production_result(decision_input: dict) -> dict:
    """
    组装 BIFROST_SPECIALIST_RESULT_v0.1.3 输出。

    v0.1.2 变更：
    - evidence_refs 使用 EVREF-v1（字段事实级）
    - data_gaps 使用共享 merge_data_gaps 归并
    - 高风险动作存在时 → needs_confirmation（优先级: blocked > needs_confirmation > warning > completed）
    - 删除所有占位证据
    """
    gate = validate_production_input_contract(decision_input)
    if not gate["valid"]:
        return _build_blocked_result(decision_input, gate)

    facts = decision_input.get("normalized_facts", []) or []
    fact_lookup = _build_fact_lookup(facts)
    grouped = group_facts_by_semantic_record(facts)
    metrics = extract_production_metrics(grouped)

    primary_key = next(iter(metrics), "")
    primary = metrics.get(primary_key, {"values": {}})

    oee_analysis = analyze_oee_direct_drivers(primary, fact_lookup, primary_key)
    downtime_analysis = analyze_downtime_evidence(primary, fact_lookup, primary_key)
    trend_analysis = analyze_shift_trend_if_supported(metrics)
    risk_class = classify_production_risks(primary, oee_analysis, downtime_analysis)

    confidence = _compute_confidence(primary)
    metric_list = _build_metric_list(primary, fact_lookup, primary_key)
    causes = _build_causes(oee_analysis, downtime_analysis, risk_class)
    affected_objects = _build_affected_objects(primary)
    recommended_actions = _build_recommended_actions(oee_analysis, downtime_analysis, risk_class, primary)

    needs_confirmation = any(a.get("is_high_risk") for a in recommended_actions)
    evidence_refs = _collect_evidence_refs(primary, fact_lookup, primary_key, oee_analysis, downtime_analysis, metric_list)

    # data_gaps: 收集原始缺口 → 使用共享 merge_data_gaps 归并
    raw_gaps = _normalize_input_data_gaps(decision_input.get("data_gaps", []) or [])
    for g in oee_analysis.get("data_gaps", []):
        raw_gaps.append(_normalize_gap(g, primary_key, "shift"))
    for g in downtime_analysis.get("data_gaps", []):
        raw_gaps.append(_normalize_gap(g, primary_key, "shift"))
    for g in trend_analysis.get("data_gaps", []):
        raw_gaps.append(_normalize_gap(g, primary_key, "shift"))
    data_gaps = merge_data_gaps(raw_gaps)

    conclusion = _build_conclusion(primary, oee_analysis, downtime_analysis, risk_class, confidence)

    # v0.1.3: 无合法 EVREF 时不产出业务结论（conclusion 需有证据支撑）
    if not evidence_refs:
        conclusion = ""

    # --- status 判定（优先级: blocked > needs_confirmation > warning > completed）---
    # 高风险动作存在时，非 blocked 结果必须为 needs_confirmation
    # 不得为 warning/completed（v0.1.3 状态优先级双向强制）
    if needs_confirmation:
        status = C.STATUS_NEEDS_CONFIRMATION
    elif data_gaps:
        status = C.STATUS_WARNING
    else:
        status = C.STATUS_COMPLETED

    specialist_details = {
        "oee_analysis": {
            "oee_source": oee_analysis.get("oee_source"),
            "oee_recomputed": oee_analysis.get("oee_recomputed"),
            "recompute_performed": oee_analysis.get("recompute_performed"),
            "recompute_blocked_reason": oee_analysis.get("recompute_blocked_reason"),
            "direct_drivers_count": len(oee_analysis.get("direct_drivers", [])),
        },
        "downtime_analysis": {
            "downtime_evidence_count": len(downtime_analysis.get("downtime_evidence", [])),
            "material_continuity_risk": downtime_analysis.get("material_continuity_risk"),
            "material_as_oee_cause": downtime_analysis.get("material_as_oee_cause"),
            "material_cause_blocked_reason": downtime_analysis.get("material_cause_blocked_reason"),
            "mtbf_mttr": downtime_analysis.get("mtbf_mttr"),
            "mtbf_mttr_blocked_reason": downtime_analysis.get("mtbf_mttr_blocked_reason"),
        },
        "trend_analysis": {
            "trend_supported": trend_analysis.get("trend_supported"),
            "trend": trend_analysis.get("trend"),
            "blocked_reason": trend_analysis.get("blocked_reason"),
        },
    }
    if risk_class["missing_severity_rule"]:
        specialist_details["missing_severity_rule"] = True

    # validation 对象
    validation = {
        "status": "passed",
        "issues": [],
        "warnings": [],
        "input_contract_valid": True,
        "evidence_contract_valid": True,
        "output_contract_valid": True,
    }
    if data_gaps:
        validation["status"] = "warning"
        validation["warnings"].append(f"存在 {len(data_gaps)} 个归并后 data_gaps")
    if needs_confirmation:
        validation["status"] = "passed"
        validation["warnings"].append("存在高风险动作，状态为 needs_confirmation")

    result = {
        "contract_name": C.SPECIALIST_CONTRACT_NAME,
        "contract_version": C.SPECIALIST_CONTRACT_VERSION,
        "specialist_type": C.SPECIALIST_TYPE,
        "status": status,
        "request_id": decision_input.get("request_id", ""),
        "source_release_id": decision_input.get("source_release_id", ""),
        "source_snapshot_id": decision_input.get("source_snapshot_id", ""),
        "conclusion": conclusion,
        "severity": risk_class["severity"],
        "confidence": confidence,
        "metrics": metric_list,
        "causes": causes,
        "affected_objects": affected_objects,
        "recommended_actions": recommended_actions,
        "needs_human_confirmation": needs_confirmation,
        "evidence_refs": evidence_refs,
        "data_gaps": data_gaps,
        "actor_can_execute": False,
        "contract_versions": _build_contract_versions(decision_input),
        "validation": validation,
        "local_trace_id": f"PROD-{uuid.uuid4().hex[:16].upper()}",
        "specialist_details": specialist_details,
    }

    return result


# =========================================================================
# 9. validate_specialist_result_contract
# =========================================================================
def validate_specialist_result_contract(result: dict) -> dict:
    """验证 BIFROST_SPECIALIST_RESULT_v0.1.3 输出合同合规性。"""
    validation = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": {},
    }

    required_fields = [
        "contract_name", "contract_version", "specialist_type", "status",
        "request_id", "source_release_id", "source_snapshot_id", "conclusion",
        "severity", "confidence", "metrics", "causes", "affected_objects",
        "recommended_actions", "needs_human_confirmation", "evidence_refs",
        "data_gaps", "actor_can_execute", "contract_versions", "validation",
        "local_trace_id",
    ]
    missing = [f for f in required_fields if f not in result]
    validation["checks"]["required_fields"] = len(missing) == 0
    if missing:
        validation["errors"].append(f"缺少必需字段: {missing}")
        validation["valid"] = False

    if result.get("contract_name") != C.SPECIALIST_CONTRACT_NAME:
        validation["errors"].append(f"contract_name 不是 {C.SPECIALIST_CONTRACT_NAME}")
        validation["valid"] = False
    validation["checks"]["contract_name"] = result.get("contract_name") == C.SPECIALIST_CONTRACT_NAME

    if result.get("contract_version") != C.SPECIALIST_CONTRACT_VERSION:
        validation["errors"].append(f"contract_version 不是 {C.SPECIALIST_CONTRACT_VERSION}")
        validation["valid"] = False
    validation["checks"]["contract_version"] = result.get("contract_version") == C.SPECIALIST_CONTRACT_VERSION

    if result.get("specialist_type") != C.SPECIALIST_TYPE:
        validation["errors"].append(f"specialist_type 不是 {C.SPECIALIST_TYPE}")
        validation["valid"] = False
    validation["checks"]["specialist_type"] = result.get("specialist_type") == C.SPECIALIST_TYPE

    if result.get("actor_can_execute") is not False:
        validation["errors"].append("actor_can_execute 必须为 false")
        validation["valid"] = False
    validation["checks"]["actor_can_execute_false"] = result.get("actor_can_execute") is False

    conf = result.get("confidence")
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        validation["errors"].append(f"confidence 必须为 0-1 浮点数，实际: {conf!r}")
        validation["valid"] = False
    validation["checks"]["confidence_range"] = isinstance(conf, (int, float)) and 0 <= conf <= 1

    sd = result.get("specialist_details", {})
    if result.get("severity") == C.SEVERITY_UNKNOWN and not sd.get("missing_severity_rule"):
        validation["errors"].append("severity=unknown 时 specialist_details 应包含 missing_severity_rule")
        validation["valid"] = False

    # 高风险动作门控
    for action in result.get("recommended_actions", []):
        if action.get("is_high_risk") is True:
            if action.get("needs_human_confirmation") is not True:
                validation["errors"].append(
                    f"高风险动作 {action.get('action_id')} needs_human_confirmation 必须为 true"
                )
                validation["valid"] = False
            if action.get("prohibited_auto_execute") is not True:
                validation["errors"].append(
                    f"高风险动作 {action.get('action_id')} prohibited_auto_execute 必须为 true"
                )
                validation["valid"] = False
            if action.get("actor_can_execute") is not False:
                validation["errors"].append(
                    f"高风险动作 {action.get('action_id')} actor_can_execute 必须为 false"
                )
                validation["valid"] = False
    validation["checks"]["high_risk_gate"] = validation["valid"]

    # v0.1.3: evidence_refs 必须为 EVREF-v1 形式（非占位、非裸记录键）
    ev_prefix = "EVREF-v1:"
    for i, m in enumerate(result.get("metrics", [])):
        for r in m.get("evidence_refs", []):
            if not isinstance(r, str) or not r.startswith(ev_prefix):
                validation["errors"].append(
                    f"metrics[{i}] evidence_ref '{r}' 不是 EVREF-v1 规范形式")
                validation["valid"] = False
    for i, c in enumerate(result.get("causes", [])):
        for r in c.get("evidence_refs", []):
            if not isinstance(r, str) or not r.startswith(ev_prefix):
                validation["errors"].append(
                    f"causes[{i}] evidence_ref '{r}' 不是 EVREF-v1 规范形式")
                validation["valid"] = False
    for i, a in enumerate(result.get("recommended_actions", [])):
        for r in a.get("evidence_refs", []):
            if not isinstance(r, str) or not r.startswith(ev_prefix):
                validation["errors"].append(
                    f"recommended_actions[{i}] evidence_ref '{r}' 不是 EVREF-v1 规范形式")
                validation["valid"] = False
    for r in result.get("evidence_refs", []):
        if not isinstance(r, str) or not r.startswith(ev_prefix):
            validation["errors"].append(
                f"top-level evidence_ref '{r}' 不是 EVREF-v1 规范形式")
            validation["valid"] = False
    validation["checks"]["evidence_refs_evref_v1"] = validation["valid"]

    # 状态语义门控
    status = result.get("status")
    if status == C.STATUS_BLOCKED:
        if result.get("conclusion"):
            validation["errors"].append("blocked 状态不得产生 conclusion")
            validation["valid"] = False
        if result.get("metrics"):
            validation["errors"].append("blocked 状态不得产生 metrics")
            validation["valid"] = False
        if result.get("causes"):
            validation["errors"].append("blocked 状态不得产生 causes")
            validation["valid"] = False
        if result.get("recommended_actions"):
            validation["errors"].append("blocked 状态不得产生 recommended_actions")
            validation["valid"] = False
    elif status == C.STATUS_WARNING:
        if not result.get("data_gaps"):
            validation["errors"].append("warning 状态必须包含 data_gaps")
            validation["valid"] = False
    elif status == C.STATUS_COMPLETED:
        if result.get("data_gaps"):
            validation["errors"].append("completed 状态不得包含 data_gaps")
            validation["valid"] = False
    elif status == C.STATUS_NEEDS_CONFIRMATION:
        has_high = any(a.get("is_high_risk") for a in result.get("recommended_actions", []))
        if not has_high:
            validation["errors"].append("needs_confirmation 状态需要至少一个高风险动作")
            validation["valid"] = False

    # v0.1.3: 高风险动作存在时，非 blocked 结果必须为 needs_confirmation
    has_high_risk = any(a.get("is_high_risk") for a in result.get("recommended_actions", []))
    if has_high_risk and status not in (C.STATUS_BLOCKED, C.STATUS_NEEDS_CONFIRMATION):
        validation["errors"].append(
            f"高风险动作存在但 status={status}，非 blocked 结果必须为 needs_confirmation")
        validation["valid"] = False
    validation["checks"]["high_risk_status_priority"] = validation["valid"]

    # 禁止顶层额外字段
    forbidden_top = {"blocked_code", "missing_severity_rule", "blocked_errors"}
    present_forbidden = [f for f in forbidden_top if f in result]
    if present_forbidden:
        validation["errors"].append(f"禁止的顶层字段（应迁入 specialist_details）: {present_forbidden}")
        validation["valid"] = False

    # 禁止虚构 ID
    for f in ("confirmation_id", "ConfirmationID", "auto_execute_command",
              "executed_action_id", "DecisionID", "RunID"):
        if f in result:
            validation["errors"].append(f"禁止虚构 ID 字段: {f}")
            validation["valid"] = False

    return validation


# =========================================================================
# 内部辅助函数
# =========================================================================

def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _compute_confidence(primary: dict) -> float:
    """按证据覆盖率确定性计算 confidence，不得固定写常量。"""
    values = primary.get("values", {})
    if not C.PRODUCTION_EVIDENCE_FIELDS:
        return 0.0
    present = sum(
        1 for f in C.PRODUCTION_EVIDENCE_FIELDS
        if f in values and values[f] is not None
    )
    return round(present / len(C.PRODUCTION_EVIDENCE_FIELDS), 4)


def _default_display_format(field: str, value: Any) -> str:
    """为缺少展示格式的输入事实提供确定性合同安全默认值。

    上游字段可能只提供 normalized_value 而没有 display_format；输出合同要求
    display_format 非空，因此这里仅补展示格式，不改变原始值或业务口径。
    """
    percentage_fields = {
        C.OEE_SOURCE_FIELD,
        C.OEE_RECOMPUTED_FIELD,
        "availability",
        "performance_rate",
        "quality_factor",
        "yield_recompute",
        "source_quality_rate",
        "oee_quality_factor",
    }
    if field in percentage_fields or field.endswith("_rate") or field.endswith("_factor"):
        return "0.0%"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "0"
    if isinstance(value, float):
        return "0.0"
    return "text"


def _build_metric_list(primary: dict, fact_lookup: dict, record_key: str) -> list[dict]:
    """v0.1.2: 构建指标列表。每个 metric 的 evidence_refs 为字段级 EVREF-v1。

    只为能生成合法 EVREF 的字段创建 metric（字段绑定：evidence_refs 解析到的
    semantic_field 必须与 metric.semantic_field 一致）。
    """
    values = primary.get("values", {})
    formats = primary.get("display_formats", {})
    metrics = []
    idx = 0
    for field, value in values.items():
        if field in C.NON_METRIC_FIELDS:
            continue
        evref = _build_evref(fact_lookup, record_key, field)
        if evref is None:
            # 无法生成合法 EVREF 的字段不产出 metric（不得使用占位证据）
            continue
        display_format = formats.get(field) or _default_display_format(field, value)
        metrics.append({
            "metric_id": f"METRIC-{idx:04d}-{field}",
            "label": field,
            "value": value,
            "display_format": display_format,
            "semantic_field": field,
            "evidence_refs": [evref],
        })
        idx += 1
    return metrics


def _build_causes(oee_analysis: dict, downtime_analysis: dict, risk_class: dict) -> list[dict]:
    """v0.1.2: 构建原因列表。evidence_refs 为字段级 EVREF-v1。

    只为能生成合法 EVREF 的原因创建 cause（不得使用占位证据）。
    """
    causes = []
    idx = 0
    for driver in oee_analysis.get("direct_drivers", []):
        evref = driver.get("evidence_evref")
        if evref is None:
            continue
        causes.append({
            "cause_id": f"CAUSE-{idx:04d}",
            "category": "oee_direct_driver",
            "statement": f"{driver['driver']}={driver['value']}，OEE直接驱动因子",
            "causal_evidence_level": "direct_verified",
            "evidence_refs": [evref],
        })
        idx += 1
    for ev in downtime_analysis.get("downtime_evidence", []):
        if ev["impact"] == "availability_drop_evidence":
            evref = ev.get("evidence_evref")
            if evref is None:
                continue
            causes.append({
                "cause_id": f"CAUSE-{idx:04d}",
                "category": "availability_loss",
                "statement": f"非计划停机 {ev['value']} 分钟，为开动率下降证据（OEE直接驱动 availability 的证据）",
                "causal_evidence_level": "direct_verified",
                "evidence_refs": [evref],
            })
            idx += 1
    material_risk = downtime_analysis.get("material_continuity_risk")
    if material_risk:
        evref = material_risk.get("evidence_evref")
        if evref is not None:
            causes.append({
                "cause_id": f"CAUSE-{idx:04d}",
                "category": "material_gap_continuity_risk",
                "statement": f"物料缺口 {material_risk['value']}，关联风险（非OEE直接驱动）",
                "causal_evidence_level": "associated_risk",
                "evidence_refs": [evref],
            })
            idx += 1
    return causes


def _build_affected_objects(primary: dict) -> list[dict]:
    values = primary.get("values", {})
    objs = []
    line_id = values.get(C.LINE_ID_FIELD)
    shift_id = values.get(C.SHIFT_ID_FIELD)
    if line_id:
        objs.append({"type": "production_line", "id": line_id})
    if shift_id:
        objs.append({"type": "shift", "id": shift_id})
    return objs


def _build_recommended_actions(oee_analysis: dict, downtime_analysis: dict, risk_class: dict, primary: dict) -> list[dict]:
    """v0.1.2: 推荐动作使用共享必填字段。evidence_refs 为字段级 EVREF-v1。

    高风险动作存在时，非 blocked 结果必须为 needs_confirmation。
    只为能生成合法 EVREF 的动作创建（不得使用占位证据）。
    """
    actions = []
    idx = 0
    primary_key = primary.get("semantic_record_key", "")
    affected_obj = primary.get("values", {}).get(C.LINE_ID_FIELD, primary_key)

    for ev in downtime_analysis.get("downtime_evidence", []):
        if ev["type"] == "unplanned_downtime":
            evref = ev.get("evidence_evref")
            if evref is None:
                continue
            actions.append({
                "action_id": f"ACTION-{idx:04d}",
                "action": "建议排查非计划停机根因，确认是否影响开动率",
                "priority": "medium",
                "is_high_risk": False,
                "needs_human_confirmation": False,
                "prohibited_auto_execute": True,
                "actor_can_execute": False,
                "affected_object": affected_obj,
                "evidence_refs": [evref],
            })
            idx += 1

    if downtime_analysis.get("material_continuity_risk"):
        mr = downtime_analysis["material_continuity_risk"]
        evref = mr.get("evidence_evref")
        if evref is not None:
            actions.append({
                "action_id": f"ACTION-{idx:04d}",
                "action": "建议跟进物料供应连续性，评估后续生产影响",
                "priority": "low",
                "is_high_risk": False,
                "needs_human_confirmation": False,
                "prohibited_auto_execute": True,
                "actor_can_execute": False,
                "affected_object": affected_obj,
                "evidence_refs": [evref],
            })
            idx += 1

    # 高风险排产动作：需要 oee_source 或 oee_recomputed 的 EVREF 作为证据
    if oee_analysis.get("oee_source") or oee_analysis.get("oee_recomputed"):
        oee_src = oee_analysis.get("oee_source")
        evref = None
        if oee_src:
            evref = oee_src.get("evidence_evref")
        if evref is None and oee_analysis.get("oee_recomputed"):
            # oee_recomputed 是确定性复算，无独立 EVREF；回退到 oee_source EVREF
            pass
        if evref is not None:
            actions.append({
                "action_id": f"ACTION-{idx:04d}",
                "action": "如需调整排产计划，须由授权人员在业务系统中确认后执行",
                "priority": "high",
                "is_high_risk": True,
                "needs_human_confirmation": True,
                "prohibited_auto_execute": True,
                "actor_can_execute": False,
                "affected_object": affected_obj,
                "evidence_refs": [evref],
            })
            idx += 1

    return actions


def _collect_evidence_refs(primary: dict, fact_lookup: dict, record_key: str,
                           oee_analysis: dict, downtime_analysis: dict,
                           metric_list: list[dict] | None = None) -> list[str]:
    """v0.1.2: 收集字段级 EVREF-v1。删除所有占位证据。

    有业务事实时顶层 evidence_refs 必须非空；无合法 EVREF 时返回空列表
    （此时不应产生业务结论，status 应为 warning/blocked）。
    收集范围：PRODUCTION_EVIDENCE_FIELDS 中的字段 + 所有 metric 产生的 EVREF。
    """
    refs = []
    values = primary.get("values", {})
    for field in C.PRODUCTION_EVIDENCE_FIELDS:
        if field in values and values[field] is not None:
            evref = _build_evref(fact_lookup, record_key, field)
            if evref is not None:
                refs.append(evref)
    # 也从 metric_list 收集（确保非 PRODUCTION_EVIDENCE_FIELDS 字段的 EVREF 也纳入顶层）
    if metric_list:
        for m in metric_list:
            for r in m.get("evidence_refs", []):
                if r and r not in refs:
                    refs.append(r)
    # 去重保持顺序
    seen = set()
    unique_refs = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            unique_refs.append(r)
    return unique_refs


def _normalize_gap(gap: dict, record_key: str, entity: str) -> dict:
    """规范化 data_gap 为 merge_data_gaps 输入格式（6 字段）。"""
    return {
        "semantic_entity": entity,
        "semantic_field": gap.get("semantic_field", ""),
        "reason": gap.get("reason", ""),
        "value_consumption_status": C.VCS_MISSING,
        "source_locator": record_key,
        "required_resolution": gap.get("required_resolution", ""),
    }


def _normalize_input_data_gaps(input_gaps: list[dict]) -> list[dict]:
    """v0.1.2: 将输入 data_gaps 规范化为 merge_data_gaps 输入格式。

    source_locator 序列化为字符串，以便 merge_data_gaps 正确计算唯一 locator 数。
    """
    result = []
    for gap in input_gaps:
        vcs = gap.get("value_consumption_status", "")
        vcs_map = {
            "usable": "usable",
            "unusable": "unusable",
            "missing": "missing",
            "blocked": "blocked",
            "pending": "pending",
            "null_unavailable": "missing",
            "invalid": "unusable",
            "needs_rule": "missing",
            "field_absent": "missing",
            "specialist_gap": "missing",
        }
        out_vcs = vcs_map.get(vcs, "missing")
        sl = gap.get("source_locator")
        if isinstance(sl, dict):
            sl_str = json.dumps(sl, ensure_ascii=False, sort_keys=True) if sl else None
        elif isinstance(sl, str):
            sl_str = sl
        else:
            sl_str = None
        result.append({
            "semantic_entity": gap.get("semantic_entity", ""),
            "semantic_field": gap.get("semantic_field", ""),
            "reason": gap.get("reason", ""),
            "value_consumption_status": out_vcs,
            "source_locator": sl_str,
            "required_resolution": gap.get("required_resolution", ""),
        })
    return result


def _build_conclusion(primary: dict, oee_analysis: dict, downtime_analysis: dict, risk_class: dict, confidence: float) -> str:
    """确定性模板生成 conclusion。"""
    parts = []
    record_key = primary.get("semantic_record_key", "")
    parts.append(f"生产诊断完成，分析记录: {record_key}。")

    oee_src = oee_analysis.get("oee_source")
    if oee_src:
        parts.append(f"源OEE: {oee_src['value']}。")
    oee_rec = oee_analysis.get("oee_recomputed")
    if oee_rec:
        parts.append(f"复算OEE: {oee_rec['value']}（{oee_rec['formula']}）。")
    if oee_analysis.get("recompute_blocked_reason"):
        parts.append(f"OEE复算未执行: {oee_analysis['recompute_blocked_reason']}。")

    drivers = oee_analysis.get("direct_drivers", [])
    if drivers:
        driver_desc = ", ".join(f"{d['driver']}={d['value']}" for d in drivers)
        parts.append(f"OEE直接驱动因子: {driver_desc}。")
    else:
        parts.append("三因子不完整，未识别OEE直接驱动因子。")

    for ev in downtime_analysis.get("downtime_evidence", []):
        if ev["impact"] == "availability_drop_evidence":
            parts.append(f"非计划停机 {ev['value']} 分钟，为开动率下降证据。")

    if downtime_analysis.get("material_continuity_risk"):
        parts.append("存在物料缺口，表述为后续生产连续性风险（非OEE直接原因）。")

    parts.append(f"严重度: {risk_class['severity']}。")
    if risk_class["missing_severity_rule"]:
        parts.append("未提供批准的严重度阈值规则(missing_severity_rule)。")

    parts.append(f"证据覆盖率(confidence): {confidence}。")

    return " ".join(parts)


def _build_blocked_result(decision_input: dict, gate: dict) -> dict:
    """v0.1.2: 输入合同不合格时输出阻塞结果。

    blocked 不得含 conclusion/metrics/causes/recommended_actions。
    evidence_refs 为空列表（不使用占位证据）。
    """
    specialist_details = {
        "blocked_code": gate["blocked_code"],
        "blocked_errors": gate["errors"],
        "missing_severity_rule": True,
    }

    validation = {
        "status": "failed",
        "issues": gate["errors"],
        "warnings": [],
        "input_contract_valid": False,
        "evidence_contract_valid": False,
        "output_contract_valid": True,
    }

    return {
        "contract_name": C.SPECIALIST_CONTRACT_NAME,
        "contract_version": C.SPECIALIST_CONTRACT_VERSION,
        "specialist_type": C.SPECIALIST_TYPE,
        "status": C.STATUS_BLOCKED,
        "request_id": decision_input.get("request_id", ""),
        "source_release_id": decision_input.get("source_release_id", ""),
        "source_snapshot_id": decision_input.get("source_snapshot_id", ""),
        "conclusion": "",
        "severity": C.SEVERITY_UNKNOWN,
        "confidence": 0.0,
        "metrics": [],
        "causes": [],
        "affected_objects": [],
        "recommended_actions": [],
        "needs_human_confirmation": False,
        "evidence_refs": [],
        "data_gaps": [],
        "actor_can_execute": False,
        "contract_versions": _build_contract_versions(decision_input),
        "validation": validation,
        "local_trace_id": f"PROD-{uuid.uuid4().hex[:16].upper()}",
        "specialist_details": specialist_details,
    }


def _build_contract_versions(decision_input: dict) -> dict:
    cv = decision_input.get("contract_versions", {}) or {}
    return {
        "specialist_result_contract_version": C.SPECIALIST_CONTRACT_VERSION,
        "decision_input_contract_version": cv.get("decision_input_contract_version", C.INPUT_CONTRACT_VERSION),
        "semantic_model_version": cv.get("semantic_model_version", ""),
        "mapping_rule_version": cv.get("mapping_rule_version", ""),
        "specialist_logical_version": C.SPECIALIST_LOGICAL_VERSION,
    }

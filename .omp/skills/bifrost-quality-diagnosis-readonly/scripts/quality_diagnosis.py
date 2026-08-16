"""
BIFROST 质量诊断只读分析 Skill
logical_version: 0.1.2

链路：语义消费者 → BIFROST_DECISION_INPUT_v0.1 → bifrost-quality-diagnosis-readonly
      → BIFROST_SPECIALIST_RESULT_v0.1.3 → 决策编排智能体

10 个确定性能力：
1. validate_quality_input_contract
2. group_quality_facts_by_record
3. extract_quality_metrics
4. validate_defect_distribution_conservation
5. analyze_yield_and_defects
6. analyze_freeze_state
7. enforce_spc_cpk_data_requirements
8. classify_quality_risk
9. build_quality_result
10. validate_specialist_result_contract

v0.1.2 迁移变更（→ 输出合同 v0.1.3）：
- contract_version: BIFROST-SPECIALIST-RESULT-v0.1.1 → v0.1.3
- evidence_refs 从记录级 EV-{field}@... 升级为字段事实级 EVREF-v1:<SHA256>
  （由共享 build_canonical_evidence_ref 确定性生成）
- metrics 的 evidence_refs 实施字段绑定（semantic_field 一致）
- data_gaps 从 6 字段升级为 9 字段（+affected_record_count/occurrence_count/
  sample_source_locators），由共享 merge_data_gaps 确定性归并
- 纯 data_gap warning 模式：无业务事实时 conclusion="" / evidence_refs=[]
- 高风险动作必须返回 needs_confirmation；blocked/warning/completed 语义遵守共享优先级
- 保留：不良守恒、SPC/Cpk 数据门控、冻结关系物化检查、缺时间字段不制造趋势、
  相关性不表述为根因

v0.1.1 能力全部保留不回退（状态优先级、条件化顶层 evidence_refs、占位禁止、
blocked 语义、needs_confirmation 门控）。
"""

import json
import uuid
import os
import importlib.util
from typing import Any

QUALITY_LOGICAL_VERSION = "0.1.2"
SPECIALIST_RESULT_CONTRACT_VERSION = "BIFROST-SPECIALIST-RESULT-v0.1.3"
SPECIALIST_RESULT_CONTRACT_NAME = "BIFROST_SPECIALIST_RESULT_v0.1"

# ---- 加载共享验证器（v0.1.3 权威） ------------------------------------------
_VALIDATOR_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "validator", "specialist_contract_validator.py",
)
_spec = importlib.util.spec_from_file_location("_bifrost_shared_validator", _VALIDATOR_PATH)
_svc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_svc)
build_canonical_evidence_ref = _svc.build_canonical_evidence_ref
merge_data_gaps = _svc.merge_data_gaps
EVREF_PREFIX = _svc.EVREF_PREFIX

# 质量可分析字段集合
QUALITY_ANALYZABLE_FIELDS = {
    "yield", "yield_rate", "quality_rate",
    "defect_count", "defect_total",
    "defect_type", "defect_type_name",
    "defect_ratio", "defect_percentage",
    "freeze_status", "freeze_id", "freeze_quantity", "freeze_reason",
    "inspection_status", "reinspection_status",
    "total_output", "good_output", "defect_output",
    "spc_measurement_points", "usl", "lsl", "sample_rule",
    "material_code", "material_name",
    "line_id", "shift_id",
    "record_timestamp", "inspection_date",
    "severity", "issue_type", "root_cause", "closure_status",
    "complaint_id", "complaint_date", "responsible_department",
    "customer_satisfaction", "response_hours", "eight_d_report_no",
    "closure_date", "first_response_date", "customer_name",
    "oee_source",
    "simulated_shift_id", "source_shift_id", "decision_event_id",
}

# 高风险动作类型
HIGH_RISK_ACTIONS = {
    "unfreeze", "override_inspection", "start_100pct_reinspect",
}

# 冻结/确认的终态状态（不得重新进入待确认）
TERMINAL_FREEZE_STATUSES = {"resolved", "revoked", "released", "cancelled", "closed", "已闭环"}
TERMINAL_CONFIRMATION_STATUSES = {"已确认", "撤回", "已驳回", "超时撤回", "已关闭"}

# SPC 必需字段
SPC_REQUIRED_FIELDS = {"spc_measurement_points", "usl", "lsl"}

# v0.1.3 状态枚举
STATUS_ENUM = {"completed", "warning", "blocked", "needs_confirmation"}
STATUS_PRIORITY = {"blocked": 4, "needs_confirmation": 3, "warning": 2, "completed": 1}

# v0.1.3 severity 枚举（禁止 critical）
SEVERITY_ENUM = {"unknown", "low", "medium", "high"}

# causal_evidence_level 枚举
CAUSAL_LEVELS = {"direct_verified", "indirect_verified", "associated_risk", "insufficient"}

# 质量实体期望字段（用于缺失字段 data_gap 生成）
DEFECT_DETAIL_EXPECTED = ["defect_type", "defect_count", "defect_ratio"]
QUALITY_FREEZE_EXPECTED = ["freeze_status", "freeze_id", "freeze_quantity"]
YIELD_FIELDS = ["yield", "yield_rate", "quality_rate", "good_output", "total_output"]


# =========================================================================
# EVREF 索引构建
# =========================================================================
def build_evidence_ref_index(decision_input: dict) -> dict[tuple[str, str], str]:
    """
    从 decision_input.normalized_facts 构建字段级 EVREF 索引。

    仅纳入 value_consumption_status=usable 且能生成合法 EVREF 的事实。
    返回 {(semantic_record_key, semantic_field): evref}。
    """
    idx: dict[tuple[str, str], str] = {}
    for nf in decision_input.get("normalized_facts", []) or []:
        if not isinstance(nf, dict):
            continue
        if nf.get("value_consumption_status") != "usable":
            continue
        evref = build_canonical_evidence_ref(nf)
        if evref is None:
            continue
        key = (nf.get("semantic_record_key", ""), nf.get("semantic_field", ""))
        idx[key] = evref
    return idx


def _extract_entity_from_record_key(record_key: str) -> str:
    """从 semantic_record_key 中提取 semantic_entity。

    record_key 格式: source_table#semantic_entity#source_record_id
    """
    if not isinstance(record_key, str):
        return ""
    parts = record_key.split("#")
    if len(parts) >= 3:
        return parts[1]
    return ""


def _fact_source_locator(nf: dict) -> str:
    """从 normalized_fact 构建可读 source_locator 字符串。"""
    rk = nf.get("semantic_record_key", "")
    st = nf.get("source_table", "")
    el = (nf.get("provenance_ref") or {}).get("evidence_locator") or {}
    row = el.get("source_row_number", "")
    return f"source_table={st},record_key={rk},row={row}"


# =========================================================================
# 1. validate_quality_input_contract
# =========================================================================
def validate_quality_input_contract(decision_input: dict) -> dict:
    """
    验证 BIFROST_DECISION_INPUT_v0.1 输入合同。
    """
    result = {"valid": True, "errors": [], "warnings": [], "blocked_code": None}

    if decision_input.get("contract_name") != "BIFROST_DECISION_INPUT_v0.1":
        result["errors"].append(
            f"contract_name 不匹配: 期望=BIFROST_DECISION_INPUT_v0.1, "
            f"实际={decision_input.get('contract_name')}")
        result["valid"] = False

    if decision_input.get("contract_version") != "BIFROST-DECISION-INPUT-v0.1":
        result["errors"].append(
            f"contract_version 不匹配: 期望=BIFROST-DECISION-INPUT-v0.1, "
            f"实际={decision_input.get('contract_version')}")
        result["valid"] = False

    if decision_input.get("source_write_performed") is not False:
        result["errors"].append("source_write_performed 必须为 false")
        result["valid"] = False

    if decision_input.get("actor_can_execute") is not False:
        result["errors"].append("actor_can_execute 必须为 false")
        result["valid"] = False

    validation = decision_input.get("validation", {})
    val_status = validation.get("status", "")
    if val_status in ("failed", "blocked"):
        result["errors"].append(f"validation.status 为 {val_status}，不得消费")
        result["valid"] = False
        result["blocked_code"] = "BLOCKED_INPUT_VALIDATION"

    forbidden_fields = [
        "conclusion", "root_cause", "recommended_actions",
        "confirmation_draft", "auto_execute_command",
    ]
    for field in forbidden_fields:
        if field in decision_input:
            result["errors"].append(f"输入包含禁止字段: {field}")
            result["valid"] = False

    required_fields = [
        "contract_name", "contract_version", "request_id",
        "source_release_id", "source_snapshot_id",
        "normalized_facts", "data_gaps",
        "contract_versions", "validation",
        "source_write_performed", "actor_can_execute",
    ]
    for field in required_fields:
        if field not in decision_input:
            result["errors"].append(f"缺少必需字段: {field}")
            result["valid"] = False

    for i, fact in enumerate(decision_input.get("normalized_facts", [])):
        if "provenance_ref" not in fact:
            result["errors"].append(
                f"normalized_facts[{i}] ({fact.get('semantic_field', '?')}) "
                "缺少 provenance_ref，不可追溯")
            result["valid"] = False
        if fact.get("provenance_ref") and not fact["provenance_ref"].get("evidence_locator"):
            result["warnings"].append(
                f"normalized_facts[{i}] ({fact.get('semantic_field', '?')}) "
                "provenance_ref 缺少 evidence_locator")

    for i, fact in enumerate(decision_input.get("normalized_facts", [])):
        vcs = fact.get("value_consumption_status", "")
        if vcs != "usable":
            result["errors"].append(
                f"normalized_facts[{i}] ({fact.get('semantic_field', '?')}) "
                f"value_consumption_status={vcs}，不得作为可用事实消费")
            result["valid"] = False

    if not result["valid"] and not result["blocked_code"]:
        result["blocked_code"] = "BLOCKED_INPUT_CONTRACT"

    return result


# =========================================================================
# 2. group_quality_facts_by_record
# =========================================================================
def group_quality_facts_by_record(normalized_facts: list[dict]) -> dict[str, list[dict]]:
    """按 semantic_record_key 分组质量事实。"""
    groups: dict[str, list[dict]] = {}
    for fact in normalized_facts:
        key = fact.get("semantic_record_key", "")
        if key not in groups:
            groups[key] = []
        groups[key].append(fact)
    return groups


# =========================================================================
# 3. extract_quality_metrics
# =========================================================================
def extract_quality_metrics(grouped_facts: dict[str, list[dict]]) -> dict:
    """从分组事实中提取质量指标。"""
    records = []
    all_quality_fields_found = set()
    all_non_quality_fields = set()

    for record_key, facts in grouped_facts.items():
        record_data = {
            "record_key": record_key,
            "source_table": facts[0].get("source_table", "") if facts else "",
            "source_record_id": facts[0].get("source_record_id", "") if facts else "",
            "fields": {},
            "provenance_refs": {},
            "facts": facts,
        }
        for fact in facts:
            field_name = fact.get("semantic_field", "")
            value = fact.get("normalized_value")
            record_data["fields"][field_name] = value
            record_data["provenance_refs"][field_name] = fact.get("provenance_ref", {})
            if field_name in QUALITY_ANALYZABLE_FIELDS:
                all_quality_fields_found.add(field_name)
            else:
                all_non_quality_fields.add(field_name)
        records.append(record_data)

    return {
        "records": records,
        "quality_fields_found": all_quality_fields_found,
        "non_quality_fields": all_non_quality_fields,
    }


# =========================================================================
# 4. validate_defect_distribution_conservation
# =========================================================================
def validate_defect_distribution_conservation(records: list[dict]) -> dict:
    """验证不良分布统计守恒（单条记录级基本合理性）。"""
    data_gaps = []
    conserved = True
    for record in records:
        fields = record["fields"]
        defect_ratio_value = fields.get("defect_ratio")
        if defect_ratio_value is not None and isinstance(defect_ratio_value, float):
            if defect_ratio_value < 0 or defect_ratio_value > 1:
                data_gaps.append({
                    "semantic_entity": "defect_detail",
                    "semantic_field": "defect_ratio",
                    "reason": "defect_ratio_out_of_range",
                    "value_consumption_status": "unusable",
                    "source_locator": f"source_table={record.get('source_table', '')},record_key={record.get('record_key', '')}",
                    "required_resolution": "不良占比超出 [0,1] 范围，需数据质量团队排查",
                })
                conserved = False
    return {"conserved": conserved, "data_gaps": data_gaps,
            "details": "单条记录级别基本合理性检查完成；聚合守恒检查在 analyze_yield_and_defects 中执行"}


def validate_defect_conservation_aggregate(
    defect_type_records: list[dict], defect_total: int | float | None
) -> dict:
    """聚合级别不良分布守恒检查。不守恒时输出 data_gap，不得自动补平。"""
    data_gaps = []
    conserved = True
    details = {}
    type_counts = {}
    type_ratios = {}
    for rec in defect_type_records:
        fields = rec["fields"]
        type_name = fields.get("defect_type") or fields.get("defect_type_name")
        count = fields.get("defect_count")
        ratio = fields.get("defect_ratio")
        if type_name is not None:
            if count is not None:
                type_counts[type_name] = type_counts.get(type_name, 0) + count
            if ratio is not None:
                type_ratios[type_name] = type_ratios.get(type_name, 0) + ratio
    if type_counts and defect_total is not None:
        sum_counts = sum(type_counts.values())
        if sum_counts != defect_total:
            data_gaps.append({
                "semantic_entity": "defect_detail",
                "semantic_field": "defect_count",
                "reason": "defect_count_sum_mismatch",
                "value_consumption_status": "unusable",
                "source_locator": f"sum_of_type_counts={sum_counts},declared_defect_total={defect_total}",
                "required_resolution": f"各不良类型数量之和({sum_counts})与不良总数({defect_total})不守恒，不得自动补平，需数据质量团队排查",
            })
            conserved = False
            details["count_sum"] = sum_counts
            details["defect_total"] = defect_total
    if type_ratios:
        sum_ratios = sum(type_ratios.values())
        if abs(sum_ratios - 1.0) > 0.001:
            data_gaps.append({
                "semantic_entity": "defect_detail",
                "semantic_field": "defect_ratio",
                "reason": "defect_ratio_sum_mismatch",
                "value_consumption_status": "unusable",
                "source_locator": f"sum_of_ratios={sum_ratios},expected=1.0",
                "required_resolution": f"各不良类型占比之和({sum_ratios})不等于1，不得自动补平，需数据质量团队排查",
            })
            conserved = False
            details["ratio_sum"] = sum_ratios
    details["conserved"] = conserved
    return {"conserved": conserved, "data_gaps": data_gaps, "details": details}


# =========================================================================
# 5. analyze_yield_and_defects
# =========================================================================
def analyze_yield_and_defects(extracted: dict) -> dict:
    """分析良率和不良分布。"""
    analysis = {
        "yield_metrics": [], "defect_distribution": [], "defect_total": None,
        "conservation_result": None, "data_gaps": [],
        "trend_available": False, "trend_conclusion": None, "has_time_field": False,
    }
    records = extracted["records"]

    for record in records:
        for field_name in record["fields"]:
            if field_name in ("record_timestamp", "inspection_date", "shift_id",
                              "complaint_date", "closure_date", "first_response_date"):
                analysis["has_time_field"] = True
                break

    for record in records:
        fields = record["fields"]
        record_key = record["record_key"]
        yield_value = fields.get("yield") or fields.get("yield_rate") or fields.get("quality_rate")
        if yield_value is not None:
            yield_metric = {
                "record_key": record_key,
                "field": "yield" if fields.get("yield") else ("yield_rate" if fields.get("yield_rate") else "quality_rate"),
                "value": yield_value,
                "evidence_ref": record["provenance_refs"].get(
                    "yield", record["provenance_refs"].get(
                        "yield_rate", record["provenance_refs"].get("quality_rate", {}))),
            }
            analysis["yield_metrics"].append(yield_metric)
        oee_source = fields.get("oee_source")
        if oee_source is not None:
            analysis["yield_metrics"].append({
                "record_key": record_key, "field": "oee_source", "value": oee_source,
                "evidence_ref": record["provenance_refs"].get("oee_source", {}),
                "note": "oee_source 为 OEE 综合指标，口径与质量良率不同，仅作参考",
            })
        good_output = fields.get("good_output")
        total_output = fields.get("total_output")
        if good_output is not None and total_output is not None and total_output > 0:
            recompute_yield = good_output / total_output
            analysis["yield_metrics"].append({
                "record_key": record_key, "field": "yield_recompute", "value": recompute_yield,
                "evidence_ref": record["provenance_refs"].get("good_output", {}),
                "note": "整数良品复算率 = good_output / total_output",
            })
        defect_total = fields.get("defect_count") or fields.get("defect_total")
        if defect_total is not None:
            if analysis["defect_total"] is None:
                analysis["defect_total"] = defect_total
        defect_type = fields.get("defect_type") or fields.get("defect_type_name")
        if defect_type is not None:
            analysis["defect_distribution"].append({
                "record_key": record_key, "type": defect_type,
                "count": fields.get("defect_count"), "ratio": fields.get("defect_ratio"),
                "evidence_ref": record["provenance_refs"].get("defect_type", {}),
            })

    if analysis["defect_distribution"]:
        conservation = validate_defect_conservation_aggregate(
            [r for r in records if r["fields"].get("defect_type") or r["fields"].get("defect_type_name")],
            analysis["defect_total"])
        analysis["conservation_result"] = conservation
        analysis["data_gaps"].extend(conservation["data_gaps"])
    basic_conservation = validate_defect_distribution_conservation(records)
    analysis["data_gaps"].extend(basic_conservation["data_gaps"])

    analysis["trend_available"] = analysis["has_time_field"]
    if not analysis["has_time_field"]:
        analysis["trend_conclusion"] = None
    return analysis


# =========================================================================
# 6. analyze_freeze_state
# =========================================================================
def analyze_freeze_state(extracted: dict, data_gaps_input: list[dict] | None = None) -> dict:
    """分析质量冻结状态。不得按日期/产品名/文本相似度自行关联。"""
    analysis = {
        "freeze_records": [], "active_freezes": [], "terminal_freezes": [],
        "pending_confirmations": [], "relation_materialized": False,
        "data_gaps": [], "high_risk_actions": [],
    }
    records = extracted["records"]
    for record in records:
        fields = record["fields"]
        record_key = record["record_key"]
        freeze_status = fields.get("freeze_status")
        if freeze_status is not None:
            freeze_record = {
                "record_key": record_key,
                "freeze_id": fields.get("freeze_id"),
                "freeze_status": freeze_status,
                "freeze_quantity": fields.get("freeze_quantity"),
                "freeze_reason": fields.get("freeze_reason"),
                "material_code": fields.get("material_code"),
                "material_name": fields.get("material_name"),
                "evidence_ref": record["provenance_refs"].get("freeze_status", {}),
            }
            analysis["freeze_records"].append(freeze_record)
            status_lower = str(freeze_status).lower()
            if status_lower in TERMINAL_FREEZE_STATUSES:
                analysis["terminal_freezes"].append(freeze_record)
            else:
                analysis["active_freezes"].append(freeze_record)

    for freeze in analysis["active_freezes"]:
        analysis["pending_confirmations"].append({
            "type": "freeze_review",
            "freeze_id": freeze["freeze_id"],
            "freeze_status": freeze["freeze_status"],
            "description": f"冻结 {freeze['freeze_id']} 处于活跃状态，需人工确认是否需要解除",
            "needs_human_confirmation": True,
            "prohibited_auto_execute": True,
            "record_key": freeze["record_key"],
        })

    has_relation_field = False
    for record in records:
        for field_name in record["fields"]:
            if field_name in ("quality_event_id", "event_id", "linked_event_ref",
                              "relation_ref", "decision_event_id"):
                has_relation_field = True
                break
    analysis["relation_materialized"] = has_relation_field
    if not has_relation_field and analysis["freeze_records"]:
        analysis["data_gaps"].append({
            "semantic_entity": "quality_freeze",
            "semantic_field": "quality_event_id",
            "reason": "no_materialized_relation_to_quality_event",
            "value_consumption_status": "missing",
            "source_locator": None,
            "required_resolution": "冻结记录与质量事件之间无已物化关联字段，不得按日期/产品名/文本相似度自行关联",
        })
    return analysis


# =========================================================================
# 7. enforce_spc_cpk_data_requirements
# =========================================================================
def enforce_spc_cpk_data_requirements(extracted: dict) -> dict:
    """强制 SPC/Cpk 数据要求。缺测量点/规格限时不得计算 Cpk/Cp，输出 data_gap。"""
    result = {
        "spc_data_available": False, "cpk_calculable": False,
        "spc_cpk_results": [], "data_gaps": [], "blocked_calculations": [],
    }
    records = extracted["records"]
    spc_fields_present = set()
    for record in records:
        for field_name in record["fields"]:
            if field_name in SPC_REQUIRED_FIELDS or field_name == "sample_rule":
                spc_fields_present.add(field_name)
    missing_spc_fields = SPC_REQUIRED_FIELDS - spc_fields_present
    if missing_spc_fields:
        result["spc_data_available"] = False
        result["cpk_calculable"] = False
        result["data_gaps"].append({
            "semantic_entity": "defect_detail",
            "semantic_field": "spc_measurement_points",
            "reason": "GAP-SPC-MEASUREMENT",
            "value_consumption_status": "missing",
            "source_locator": f"missing_fields={','.join(sorted(missing_spc_fields))}",
            "required_resolution": "缺少 SPC 原始测量点/规格限(USL/LSL)/抽样规则，不得计算 Cpk/Cp，不得判断 SPC 越界",
        })
        result["blocked_calculations"].append({
            "calculation": "Cpk/Cp", "reason": "缺少 SPC 必需字段",
            "missing_fields": sorted(missing_spc_fields)})
        result["blocked_calculations"].append({
            "calculation": "SPC_control_limit_breach", "reason": "缺少 SPC 测量点数据",
            "missing_fields": sorted(missing_spc_fields)})
    else:
        result["spc_data_available"] = True
        result["cpk_calculable"] = True
        for record in records:
            if record["fields"].get("spc_measurement_points") is not None:
                result["spc_cpk_results"].append({
                    "record_key": record["record_key"],
                    "status": "spc_data_present_cpk_calculable",
                    "note": "SPC 数据完整，Cpk 可计算"})
    if "sample_rule" not in spc_fields_present:
        result["data_gaps"].append({
            "semantic_entity": "defect_detail",
            "semantic_field": "sample_rule",
            "reason": "missing_sample_rule",
            "value_consumption_status": "missing",
            "source_locator": None,
            "required_resolution": "缺少抽样规则定义，SPC 判定结果不可靠",
        })
    return result


# =========================================================================
# 缺失字段 data_gap 生成
# =========================================================================
def detect_missing_quality_field_gaps(
    decision_input: dict, extracted: dict
) -> list[dict]:
    """
    检测质量分析必需字段缺失，生成结构化 data_gap（每条受影响事实一个原始 gap，
    后续由 merge_data_gaps 归并）。

    - defect_detail 实体缺 defect_type/defect_count/defect_ratio
    - quality_freeze 实体缺 freeze_status/freeze_id/freeze_quantity
    - 全局缺 yield 相关字段
    """
    raw_gaps = []
    # 按实体分组事实
    entity_facts: dict[str, list[dict]] = {}
    for nf in decision_input.get("normalized_facts", []) or []:
        if nf.get("value_consumption_status") != "usable":
            continue
        entity = _extract_entity_from_record_key(nf.get("semantic_record_key", ""))
        if entity:
            entity_facts.setdefault(entity, []).append(nf)

    # 已发现的字段集合
    fields_found = extracted["quality_fields_found"]

    # defect_detail 缺失字段
    if "defect_detail" in entity_facts:
        for missing_field in DEFECT_DETAIL_EXPECTED:
            if missing_field not in fields_found:
                for nf in entity_facts["defect_detail"]:
                    raw_gaps.append({
                        "semantic_entity": "defect_detail",
                        "semantic_field": missing_field,
                        "reason": f"missing_{missing_field}_for_defect_analysis",
                        "value_consumption_status": "missing",
                        "source_locator": _fact_source_locator(nf),
                        "required_resolution": f"defect_detail 实体缺少 {missing_field} 字段，无法执行不良分布分析",
                    })

    # quality_freeze 缺失字段
    if "quality_freeze" in entity_facts:
        for missing_field in QUALITY_FREEZE_EXPECTED:
            if missing_field not in fields_found:
                for nf in entity_facts["quality_freeze"]:
                    raw_gaps.append({
                        "semantic_entity": "quality_freeze",
                        "semantic_field": missing_field,
                        "reason": f"missing_{missing_field}_for_freeze_analysis",
                        "value_consumption_status": "missing",
                        "source_locator": _fact_source_locator(nf),
                        "required_resolution": f"quality_freeze 实体缺少 {missing_field} 字段，无法执行冻结状态分析",
                    })

    # 全局缺 yield 字段
    has_yield = any(f in fields_found for f in YIELD_FIELDS)
    if not has_yield and entity_facts:
        # 仅有一条代表 gap（无具体记录可逐条关联）
        raw_gaps.append({
            "semantic_entity": "quality_yield",
            "semantic_field": "yield",
            "reason": "missing_yield_fields_globally",
            "value_consumption_status": "missing",
            "source_locator": None,
            "required_resolution": "全局未检出良率相关字段(yield/yield_rate/quality_rate/good_output/total_output)，无法执行良率分析",
        })

    return raw_gaps


# =========================================================================
# 8. classify_quality_risk
# =========================================================================
def classify_quality_risk(yield_analysis: dict, freeze_analysis: dict, spc_result: dict) -> dict:
    """质量风险分类。无批准阈值规则时 severity=unknown，禁止 critical。"""
    result = {
        "severity": "unknown", "confidence": 0.0,
        "risk_factors": [], "missing_severity_rule": False, "data_gaps": [],
    }
    active_freeze_count = len(freeze_analysis["active_freezes"])
    if active_freeze_count > 0:
        result["risk_factors"].append({
            "factor": "active_quality_freeze", "count": active_freeze_count,
            "description": f"存在 {active_freeze_count} 个活跃质量冻结"})
    if yield_analysis["yield_metrics"]:
        for ym in yield_analysis["yield_metrics"]:
            if isinstance(ym["value"], (int, float)):
                result["risk_factors"].append({
                    "factor": "yield_value", "field": ym["field"],
                    "value": ym["value"], "record_key": ym["record_key"],
                    "description": f"良率字段 {ym['field']} = {ym['value']}（无批准阈值规则，不判定等级）"})
    if yield_analysis["conservation_result"] and not yield_analysis["conservation_result"]["conserved"]:
        result["risk_factors"].append({
            "factor": "defect_distribution_not_conserved",
            "description": "不良分布统计不守恒，数据质量存在风险"})
    if not spc_result["cpk_calculable"]:
        result["risk_factors"].append({
            "factor": "spc_data_missing", "description": "缺少 SPC 数据，无法评估过程能力"})
    result["missing_severity_rule"] = True
    result["severity"] = "unknown"

    total_evidence = 0
    evidence_covered = 0
    for ym in yield_analysis["yield_metrics"]:
        total_evidence += 1
        if ym.get("evidence_ref") and ym["evidence_ref"].get("evidence_locator"):
            evidence_covered += 1
    for freeze in freeze_analysis["freeze_records"]:
        total_evidence += 1
        if freeze.get("evidence_ref") and freeze["evidence_ref"].get("evidence_locator"):
            evidence_covered += 1
    if total_evidence > 0:
        result["confidence"] = round(evidence_covered / total_evidence, 4)
    else:
        result["confidence"] = 0.0
    return result


# =========================================================================
# 9. build_quality_result
# =========================================================================
def build_quality_result(
    decision_input: dict, yield_analysis: dict, freeze_analysis: dict,
    spc_result: dict, risk_classification: dict, input_validation: dict,
) -> dict:
    """构建 BIFROST_SPECIALIST_RESULT_v0.1.3 输出。"""
    # EVREF 索引
    evref_idx = build_evidence_ref_index(decision_input)

    # ---- 汇总原始 data_gaps ----
    raw_data_gaps = []
    raw_data_gaps.extend(decision_input.get("data_gaps", []))
    raw_data_gaps.extend(yield_analysis.get("data_gaps", []))
    raw_data_gaps.extend(freeze_analysis.get("data_gaps", []))
    raw_data_gaps.extend(spc_result.get("data_gaps", []))
    raw_data_gaps.extend(risk_classification.get("data_gaps", []))

    # 缺失字段 data_gap（逐条事实，后续归并）
    extracted_for_gaps = {"quality_fields_found": set()}
    # 重建 extracted 用于缺失检测
    grouped = group_quality_facts_by_record(decision_input.get("normalized_facts", []))
    extracted_for_gaps = extract_quality_metrics(grouped)
    raw_data_gaps.extend(detect_missing_quality_field_gaps(decision_input, extracted_for_gaps))

    # 共享 merge_data_gaps 归并（9 字段）
    all_data_gaps = merge_data_gaps(raw_data_gaps)

    # ---- metrics（字段绑定：semantic_field 一致） ----
    metrics = []
    cited_evrefs = []
    for i, ym in enumerate(yield_analysis["yield_metrics"]):
        evref = evref_idx.get((ym["record_key"], ym["field"]))
        if evref is None:
            # 无法生成合法 EVREF 的事实不得作为指标证据 → 跳过该 metric
            continue
        display_format = "0.0%" if ("rate" in ym["field"] or "yield" in ym["field"]
                                     or "recompute" in ym["field"] or "oee" in ym["field"]) else "0"
        metrics.append({
            "metric_id": f"M-QUAL-{i+1:03d}",
            "label": ym["field"],
            "value": ym["value"],
            "display_format": display_format,
            "semantic_field": ym["field"],
            "evidence_refs": [evref],
        })
        if evref not in cited_evrefs:
            cited_evrefs.append(evref)

    # defect_total metric（需有对应字段证据，semantic_field 必须与 EVREF 解析字段一致）
    if yield_analysis["defect_total"] is not None:
        defect_evref = None
        defect_field = None
        for (rk, fld), ev in evref_idx.items():
            if fld in ("defect_count", "defect_total"):
                defect_evref = ev
                defect_field = fld
                break
        if defect_evref:
            metrics.append({
                "metric_id": f"M-QUAL-{len(metrics)+1:03d}",
                "label": "defect_total",
                "value": yield_analysis["defect_total"],
                "display_format": "0",
                "semantic_field": defect_field,
                "evidence_refs": [defect_evref],
            })
            if defect_evref not in cited_evrefs:
                cited_evrefs.append(defect_evref)

    # ---- causes（关联现象，不绑定单一字段） ----
    causes = []
    for i, dd in enumerate(yield_analysis["defect_distribution"]):
        if dd.get("type"):
            evref = evref_idx.get((dd["record_key"], "defect_type")) or \
                    evref_idx.get((dd["record_key"], "defect_type_name"))
            if evref is None:
                continue
            causes.append({
                "cause_id": f"C-QUAL-{i+1:03d}",
                "category": "associated_defect_type",
                "statement": f"不良类型「{dd['type']}」为关联现象，证据级别为关联（correlation_not_causation）",
                "causal_evidence_level": "associated_risk",
                "evidence_refs": [evref],
            })
            if evref not in cited_evrefs:
                cited_evrefs.append(evref)

    # ---- affected_objects ----
    affected_objects = []
    for freeze in freeze_analysis["active_freezes"]:
        affected_objects.append({
            "object_type": "quality_freeze",
            "object_id": freeze.get("freeze_id"),
            "status": freeze.get("freeze_status"),
            "quantity": freeze.get("freeze_quantity"),
            "material_code": freeze.get("material_code"),
        })

    # ---- recommended_actions（必须有合法 EVREF 证据） ----
    recommended_actions = []
    action_counter = 1
    for pc in freeze_analysis["pending_confirmations"]:
        # 冻结审查动作的证据 = freeze_status 字段事实
        evref = evref_idx.get((pc["record_key"], "freeze_status"))
        if evref is None:
            continue
        recommended_actions.append({
            "action_id": f"A-QUAL-{action_counter:03d}",
            "action": pc["description"],
            "priority": "high",
            "is_high_risk": True,
            "needs_human_confirmation": True,
            "prohibited_auto_execute": True,
            "actor_can_execute": False,
            "affected_object": str(pc.get("freeze_id", "unknown")),
            "evidence_refs": [evref],
        })
        if evref not in cited_evrefs:
            cited_evrefs.append(evref)
        action_counter += 1
    # 注：SPC 数据缺口不再作为 recommended_action（无事实证据），由 data_gap 承载

    # ---- 判断是否有业务事实 ----
    has_business = bool(metrics or causes or recommended_actions)

    # ---- conclusion ----
    if has_business:
        conclusion_parts = []
        for ym in yield_analysis["yield_metrics"]:
            evref = evref_idx.get((ym["record_key"], ym["field"]))
            if evref is None:
                continue
            if ym["field"] == "yield_recompute":
                conclusion_parts.append(f"整数良品复算率={ym['value']:.4f}（口径: good_output/total_output）")
            elif ym["field"] == "oee_source":
                conclusion_parts.append(f"OEE综合指标={ym['value']}（记录: {ym['record_key']}，口径与质量良率不同）")
            else:
                conclusion_parts.append(f"良率字段 {ym['field']}={ym['value']}（记录: {ym['record_key']}）")
        if yield_analysis["defect_distribution"]:
            conclusion_parts.append(f"不良类型分布: {len(yield_analysis['defect_distribution'])} 种不良类型")
            if yield_analysis["defect_total"] is not None:
                conclusion_parts.append(f"不良总数={yield_analysis['defect_total']}")
            if yield_analysis["conservation_result"]:
                if yield_analysis["conservation_result"]["conserved"]:
                    conclusion_parts.append("不良分布统计守恒检查通过")
                else:
                    conclusion_parts.append("不良分布统计不守恒，已输出 data_gap")
        if freeze_analysis["freeze_records"]:
            conclusion_parts.append(
                f"质量冻结记录: {len(freeze_analysis['freeze_records'])} 条"
                f"（活跃: {len(freeze_analysis['active_freezes'])}, "
                f"终态: {len(freeze_analysis['terminal_freezes'])}）")
        if spc_result["cpk_calculable"]:
            conclusion_parts.append("SPC 数据完整，Cpk 可计算")
        else:
            conclusion_parts.append("缺少 SPC 数据，Cpk 不可计算")
        if not yield_analysis["has_time_field"]:
            conclusion_parts.append("无时间字段，不生成趋势结论")
        conclusion = "; ".join(conclusion_parts)
    else:
        # 纯 data_gap warning 模式：无业务结论
        conclusion = ""

    # ---- 顶层 evidence_refs（条件化：有业务事实时非空，否则空） ----
    evidence_refs = list(cited_evrefs) if has_business else []

    # ---- needs_human_confirmation ----
    needs_human_confirmation = any(
        ra.get("needs_human_confirmation") for ra in recommended_actions)

    # ---- 最终 status（共享优先级：blocked > needs_confirmation > warning > completed） ----
    has_high_risk_action = any(ra.get("is_high_risk") for ra in recommended_actions)
    has_data_gaps = len(all_data_gaps) > 0
    if has_high_risk_action and needs_human_confirmation:
        final_status = "needs_confirmation"
    elif has_data_gaps:
        final_status = "warning"
    else:
        final_status = "completed"

    # ---- validation 顶层对象 ----
    validation = {
        "status": "passed",
        "issues": [],
        "warnings": [],
        "input_contract_valid": input_validation["valid"],
        "evidence_contract_valid": len(evidence_refs) > 0 or not has_business,
        "output_contract_valid": True,
    }
    if not input_validation["valid"]:
        validation["status"] = "failed"
        validation["issues"].extend(input_validation["errors"])
    elif has_data_gaps:
        validation["status"] = "warning"
        validation["warnings"].append(f"存在 {len(all_data_gaps)} 个数据缺口")

    # ---- specialist_details ----
    specialist_details = {
        "yield_analysis_summary": {
            "yield_metrics_count": len(yield_analysis["yield_metrics"]),
            "defect_distribution_count": len(yield_analysis["defect_distribution"]),
            "defect_total": yield_analysis["defect_total"],
            "conservation_conserved": (
                yield_analysis["conservation_result"]["conserved"]
                if yield_analysis["conservation_result"] else None),
            "trend_available": yield_analysis["trend_available"],
            "has_time_field": yield_analysis["has_time_field"],
        },
        "freeze_analysis_summary": {
            "freeze_records_count": len(freeze_analysis["freeze_records"]),
            "active_freezes_count": len(freeze_analysis["active_freezes"]),
            "terminal_freezes_count": len(freeze_analysis["terminal_freezes"]),
            "relation_materialized": freeze_analysis["relation_materialized"],
            "pending_confirmations_count": len(freeze_analysis["pending_confirmations"]),
        },
        "spc_analysis_summary": {
            "spc_data_available": spc_result["spc_data_available"],
            "cpk_calculable": spc_result["cpk_calculable"],
            "blocked_calculations": spc_result["blocked_calculations"],
        },
        "risk_classification": {
            "severity": risk_classification["severity"],
            "confidence": risk_classification["confidence"],
            "missing_severity_rule": risk_classification["missing_severity_rule"],
            "risk_factors": risk_classification["risk_factors"],
        },
        "input_validation": {
            "valid": input_validation["valid"],
            "blocked_code": input_validation["blocked_code"],
        },
    }

    result = {
        "contract_name": SPECIALIST_RESULT_CONTRACT_NAME,
        "contract_version": SPECIALIST_RESULT_CONTRACT_VERSION,
        "specialist_type": "quality",
        "status": final_status,
        "request_id": decision_input.get("request_id", ""),
        "source_release_id": decision_input.get("source_release_id", ""),
        "source_snapshot_id": decision_input.get("source_snapshot_id", ""),
        "conclusion": conclusion,
        "severity": risk_classification["severity"],
        "confidence": risk_classification["confidence"],
        "metrics": metrics,
        "causes": causes,
        "affected_objects": affected_objects,
        "recommended_actions": recommended_actions,
        "needs_human_confirmation": needs_human_confirmation,
        "evidence_refs": evidence_refs,
        "data_gaps": all_data_gaps,
        "actor_can_execute": False,
        "contract_versions": {
            "specialist_result_contract_version": SPECIALIST_RESULT_CONTRACT_VERSION,
            "decision_input_contract_version": "BIFROST-DECISION-INPUT-v0.1",
            "semantic_model_version": decision_input.get("contract_versions", {}).get("semantic_model_version", ""),
            "mapping_rule_version": decision_input.get("contract_versions", {}).get("mapping_rule_version", ""),
            "specialist_logical_version": f"QUAL-LOGIC-v{QUALITY_LOGICAL_VERSION}",
        },
        "validation": validation,
        "local_trace_id": f"QUALITY-{uuid.uuid4().hex[:16].upper()}",
        "specialist_details": specialist_details,
    }
    return result


# =========================================================================
# 10. validate_specialist_result_contract（内部预校验，权威校验由共享验证器承担）
# =========================================================================
def validate_specialist_result_contract(result: dict) -> dict:
    """验证 BIFROST_SPECIALIST_RESULT_v0.1.3 输出合同（内部预校验）。"""
    validation = {"valid": True, "errors": [], "warnings": []}
    required_fields = [
        "contract_name", "contract_version", "specialist_type",
        "status", "request_id", "source_release_id", "source_snapshot_id",
        "conclusion", "severity", "confidence",
        "metrics", "causes", "affected_objects", "recommended_actions",
        "needs_human_confirmation", "evidence_refs", "data_gaps",
        "actor_can_execute", "contract_versions", "validation",
        "local_trace_id", "specialist_details",
    ]
    for field in required_fields:
        if field not in result:
            validation["errors"].append(f"缺少必需字段: {field}")
            validation["valid"] = False
    if result.get("contract_name") != SPECIALIST_RESULT_CONTRACT_NAME:
        validation["errors"].append(f"contract_name 不匹配: 期望={SPECIALIST_RESULT_CONTRACT_NAME}, 实际={result.get('contract_name')}")
        validation["valid"] = False
    if result.get("contract_version") != SPECIALIST_RESULT_CONTRACT_VERSION:
        validation["errors"].append(f"contract_version 不匹配: 期望={SPECIALIST_RESULT_CONTRACT_VERSION}, 实际={result.get('contract_version')}")
        validation["valid"] = False
    if result.get("specialist_type") != "quality":
        validation["errors"].append(f"specialist_type 必须为 quality, 实际={result.get('specialist_type')}")
        validation["valid"] = False
    if result.get("actor_can_execute") is not False:
        validation["errors"].append("actor_can_execute 必须为 false")
        validation["valid"] = False
    confidence = result.get("confidence", -1)
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        validation["errors"].append(f"confidence 必须在 [0, 1] 范围内, 实际={confidence}")
        validation["valid"] = False
    if result.get("severity") not in SEVERITY_ENUM:
        validation["errors"].append(f"severity 不合法: {result.get('severity')}, 应为 {sorted(SEVERITY_ENUM)}（禁止 critical）")
        validation["valid"] = False
    status = result.get("status")
    if status not in STATUS_ENUM:
        validation["errors"].append(f"status 不合法: {status}, 应为 {sorted(STATUS_ENUM)}")
        validation["valid"] = False

    # data_gaps 9 字段检查
    for i, g in enumerate(result.get("data_gaps", [])):
        for gf in ("semantic_entity", "semantic_field", "reason",
                    "value_consumption_status", "source_locator", "required_resolution",
                    "affected_record_count", "occurrence_count", "sample_source_locators"):
            if gf not in g:
                validation["errors"].append(f"data_gaps[{i}] 缺少必填字段: {gf}")
                validation["valid"] = False
        arc = g.get("affected_record_count")
        occ = g.get("occurrence_count")
        if isinstance(arc, int) and isinstance(occ, int) and arc > occ:
            validation["errors"].append(f"data_gaps[{i}].affected_record_count({arc}) 不得超过 occurrence_count({occ})")
            validation["valid"] = False

    # 状态语义门控
    if status == "blocked":
        for f in ("conclusion", "metrics", "causes", "recommended_actions"):
            if result.get(f):
                validation["errors"].append(f"blocked 状态不得输出 {f}")
                validation["valid"] = False
    elif status == "warning":
        if not result.get("data_gaps"):
            validation["errors"].append("warning 状态必须包含 data_gaps")
            validation["valid"] = False
    elif status == "needs_confirmation":
        has_high = any(ra.get("is_high_risk") is True for ra in result.get("recommended_actions", []))
        if not has_high:
            validation["errors"].append("needs_confirmation 状态必须包含至少一个高风险动作")
            validation["valid"] = False
        if result.get("needs_human_confirmation") is not True:
            validation["errors"].append("needs_confirmation 状态需要 needs_human_confirmation=true")
            validation["valid"] = False
    elif status == "completed":
        if result.get("data_gaps"):
            validation["errors"].append("completed 状态不得包含 data_gaps")
            validation["valid"] = False

    # 高风险动作状态优先级
    has_high_risk = any(ra.get("is_high_risk") is True for ra in result.get("recommended_actions", []))
    if has_high_risk and status not in ("blocked", "needs_confirmation"):
        validation["errors"].append(f"状态优先级违反：存在高风险动作但 status={status}，应为 needs_confirmation")
        validation["valid"] = False

    # 无时间字段不制造趋势
    specialist_details = result.get("specialist_details", {})
    yield_summary = specialist_details.get("yield_analysis_summary", {})
    if not yield_summary.get("has_time_field", True):
        conclusion = result.get("conclusion", "")
        for kw in ["持续下降", "连续恶化", "趋势恶化", "持续上升", "逐月下降", "逐月上升"]:
            if kw in conclusion:
                validation["errors"].append(f"conclusion 包含趋势结论「{kw}」但无时间字段")
                validation["valid"] = False

    # 禁止虚构 ID
    for key in ("confirmation_id", "ConfirmationID", "auto_execute_command",
                "executed_action_id", "DecisionID", "RunID"):
        if key in result:
            validation["errors"].append(f"输出包含虚构 ID 字段: {key}")
            validation["valid"] = False
    return validation


# =========================================================================
# 编排入口：orchestrate_quality_diagnosis
# =========================================================================
def orchestrate_quality_diagnosis(decision_input: dict) -> dict:
    """编排质量诊断完整流程。"""
    orchestration = {
        "status": "init", "blocked_code": None, "blocked_reason": None,
        "steps": [], "result": None, "validation": None,
    }

    def _step(name, ok, detail=None):
        orchestration["steps"].append({"step": name, "ok": ok, "detail": detail or {}})
        return ok

    input_validation = validate_quality_input_contract(decision_input)
    if not _step("validate_quality_input_contract", input_validation["valid"], {
        "errors": input_validation["errors"], "blocked_code": input_validation["blocked_code"]}):
        orchestration["status"] = "BLOCKED_INPUT_CONTRACT"
        orchestration["blocked_code"] = input_validation["blocked_code"] or "BLOCKED_INPUT_CONTRACT"
        orchestration["blocked_reason"] = "; ".join(input_validation["errors"])
        blocked_result = {
            "contract_name": SPECIALIST_RESULT_CONTRACT_NAME,
            "contract_version": SPECIALIST_RESULT_CONTRACT_VERSION,
            "specialist_type": "quality",
            "status": "blocked",
            "request_id": decision_input.get("request_id", ""),
            "source_release_id": decision_input.get("source_release_id", ""),
            "source_snapshot_id": decision_input.get("source_snapshot_id", ""),
            "conclusion": "",
            "severity": "unknown",
            "confidence": 0.0,
            "metrics": [],
            "causes": [],
            "affected_objects": [],
            "recommended_actions": [],
            "needs_human_confirmation": False,
            "evidence_refs": [],
            "data_gaps": [],
            "actor_can_execute": False,
            "contract_versions": {
                "specialist_result_contract_version": SPECIALIST_RESULT_CONTRACT_VERSION,
                "decision_input_contract_version": "BIFROST-DECISION-INPUT-v0.1",
                "specialist_logical_version": f"QUAL-LOGIC-v{QUALITY_LOGICAL_VERSION}",
            },
            "validation": {
                "status": "failed",
                "issues": input_validation["errors"],
                "warnings": [],
                "input_contract_valid": False,
                "evidence_contract_valid": False,
                "output_contract_valid": False,
            },
            "local_trace_id": f"QUALITY-{uuid.uuid4().hex[:16].upper()}",
            "specialist_details": {
                "blocked_code": input_validation["blocked_code"] or "BLOCKED_INPUT_CONTRACT",
                "blocked_reason": "; ".join(input_validation["errors"]),
            },
        }
        orchestration["result"] = blocked_result
        return orchestration

    grouped = group_quality_facts_by_record(decision_input.get("normalized_facts", []))
    _step("group_quality_facts_by_record", True, {"record_count": len(grouped)})
    extracted = extract_quality_metrics(grouped)
    _step("extract_quality_metrics", True, {
        "records_count": len(extracted["records"]),
        "quality_fields_found": sorted(extracted["quality_fields_found"])})
    yield_analysis = analyze_yield_and_defects(extracted)
    _step("analyze_yield_and_defects", True, {
        "yield_metrics_count": len(yield_analysis["yield_metrics"]),
        "defect_distribution_count": len(yield_analysis["defect_distribution"]),
        "conservation_conserved": (
            yield_analysis["conservation_result"]["conserved"]
            if yield_analysis["conservation_result"] else None),
        "has_time_field": yield_analysis["has_time_field"]})
    freeze_analysis = analyze_freeze_state(extracted, decision_input.get("data_gaps"))
    _step("analyze_freeze_state", True, {
        "freeze_records_count": len(freeze_analysis["freeze_records"]),
        "active_freezes_count": len(freeze_analysis["active_freezes"]),
        "terminal_freezes_count": len(freeze_analysis["terminal_freezes"]),
        "relation_materialized": freeze_analysis["relation_materialized"]})
    spc_result = enforce_spc_cpk_data_requirements(extracted)
    _step("enforce_spc_cpk_data_requirements", True, {
        "spc_data_available": spc_result["spc_data_available"],
        "cpk_calculable": spc_result["cpk_calculable"],
        "blocked_calculations_count": len(spc_result["blocked_calculations"])})
    risk_classification = classify_quality_risk(yield_analysis, freeze_analysis, spc_result)
    _step("classify_quality_risk", True, {
        "severity": risk_classification["severity"],
        "confidence": risk_classification["confidence"],
        "missing_severity_rule": risk_classification["missing_severity_rule"],
        "risk_factors_count": len(risk_classification["risk_factors"])})
    result = build_quality_result(
        decision_input, yield_analysis, freeze_analysis,
        spc_result, risk_classification, input_validation)
    _step("build_quality_result", True, {
        "conclusion_length": len(result["conclusion"]),
        "metrics_count": len(result["metrics"]),
        "data_gaps_count": len(result["data_gaps"]),
        "evidence_refs_count": len(result["evidence_refs"]),
        "status": result["status"]})
    output_validation = validate_specialist_result_contract(result)
    _step("validate_specialist_result_contract", output_validation["valid"], {
        "errors": output_validation["errors"], "warnings": output_validation["warnings"]})
    if not output_validation["valid"]:
        orchestration["status"] = "BLOCKED_OUTPUT_CONTRACT"
        orchestration["blocked_code"] = "BLOCKED_OUTPUT_CONTRACT"
        orchestration["blocked_reason"] = "; ".join(output_validation["errors"])
        orchestration["result"] = result
        orchestration["validation"] = output_validation
        return orchestration
    orchestration["status"] = "COMPLETED"
    orchestration["result"] = result
    orchestration["validation"] = output_validation
    return orchestration

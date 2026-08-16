"""
BIFROST 供应链风险只读分析器（bifrost-supply-risk-readonly v0.1.3）

消费 BIFROST_DECISION_INPUT_v0.1，产出 BIFROST_SPECIALIST_RESULT_v0.1.3。
仅承担供应链专业的确定性分析：
- 采购订单到货状态
- 物料缺口
- 库存粒度门控
- 缺口与冻结原因分离
- 供应连续性风险分类

不承担字段映射、跨源关联、业务写回或最终决策执行。
所有输出 actor_can_execute 恒为 false。

v0.1.3 变更（04D.4B-SUPPLY-P1 到货完成状态与逾期判定语义修复）：
- actual_arrival_date 只解释为"已登记到货日期"，不得自动解释为整单完成日期
- 到货状态由 purchase_qty 与 arrived_qty 确定性确定：
  unknown / not_arrived / partial_arrival / completed / over_received_anomaly
- arrived_qty < purchase_qty 时 delivery_completion_status=indeterminate，
  不得仅因到货日期不晚于承诺交期就判定全单已完成
- 剩余数量逾期判定依赖明确 as_of_time；缺失时 overdue_status=indeterminate
- 高风险加急采购仅在明确请求 + 字段级 EVREF 充分时生成草稿
- action_id 登记 identifier_scope=local_run_only，不生成 ConfirmationID
- 保留：缺口与冻结分离、库存粒度限制、无物化关系不跨实体 join、
  缺料仅为后续生产连续性风险
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# 引入共享合同验证器中的确定性函数（字段级 EVREF 构建 + data_gap 归并）
_V_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "validator")
if _V_DIR not in sys.path:
    sys.path.insert(0, _V_DIR)
from specialist_contract_validator import (  # noqa: E402
    build_canonical_evidence_ref,
    merge_data_gaps,
)

# ---------------------------------------------------------------------------
# 常量与合同标识
# ---------------------------------------------------------------------------

CONTRACT_NAME_OUT = "BIFROST_SPECIALIST_RESULT_v0.1"
CONTRACT_VERSION_OUT = "BIFROST-SPECIALIST-RESULT-v0.1.3"
CONTRACT_NAME_IN = "BIFROST_DECISION_INPUT_v0.1"
CONTRACT_VERSION_IN = "BIFROST-DECISION-INPUT-v0.1"

SPECIALIST_TYPE = "supply"
LOGICAL_SKILL_VERSION = "0.1.3"
STAGE = "04D.4B_SUPPLY_P1_DELIVERY_SEMANTIC_FIX_LOCALLY_VALIDATED_NOT_DEPLOYED"

# 供应链可消费的语义实体
SUPPLY_ENTITIES = {
    "purchase_order",
    "inventory_snapshot",
    "material_detail",
    "material_shortage",
    "shortage_risk",
}

USABLE = "usable"

# 到货状态判定规则（v0.1.3 语义修复）
DELIVERY_STATUS_RULE = {
    "rule_id": "SUPPLY-DELIVERY-STATUS-v0.2",
    "method": (
        "arrived_qty is null => unknown; "
        "arrived_qty = 0 => not_arrived; "
        "0 < arrived_qty < purchase_qty => partial_arrival; "
        "arrived_qty = purchase_qty => completed; "
        "arrived_qty > purchase_qty => over_received_anomaly"
    ),
    "approved": True,
    "approved_by": "constructed-deterministic-qty-compare",
    "note": (
        "actual_arrival_date 只解释为已登记到货日期，不得自动解释为整单完成日期。"
        "部分到货时 delivery_completion_status=indeterminate，"
        "不得仅因到货登记日期不晚于承诺交期就判定全单已完成。"
        "剩余数量逾期判定依赖明确 as_of_time。"
    ),
}

# 到货时间比较规则（仅用于已到货事实的时间比较，不决定整单逾期）
ARRIVAL_COMPARE_RULE = {
    "rule_id": "SUPPLY-ARRIVAL-CMP-v0.2",
    "method": (
        "completed: actual_arrival_date > promised_delivery_date => overdue; "
        "partial: as_of_time > promised_delivery_date AND remaining_qty > 0 => remaining_overdue; "
        "as_of_time missing => overdue_status=indeterminate"
    ),
    "approved": True,
    "approved_by": "constructed-deterministic-date-compare",
    "note": "不使用系统当前时间猜测 as_of_time；不含宽限期/阈值",
}

# 高风险动作清单（只生成待确认草稿，禁止自动执行）
HIGH_RISK_ACTIONS = {
    "expedite_purchase": "加急采购",
    "substitute_material": "启用替代料",
    "modify_delivery_commitment": "修改交付承诺",
    "release_quality_freeze": "解除质量冻结",
    "modify_purchase_order": "修改采购订单",
}

# 库存快照当前粒度状态（来自项目规则）
INVENTORY_GRAIN = {
    "view_projection_only": True,
    "grain_status": "unresolved",
    "aggregation_allowed": False,
}

# 阻塞状态码
BLOCKED_INPUT_CONTRACT = "BLOCKED_INPUT_CONTRACT"
BLOCKED_SOURCE_WRITE = "BLOCKED_SOURCE_WRITE"
BLOCKED_EVIDENCE_MISSING = "BLOCKED_EVIDENCE_MISSING"
BLOCKED_ROLE_SCOPE = "BLOCKED_ROLE_SCOPE"

# 加急请求关键词
EXPEDITE_KEYWORDS = ("加急", "expedite", "替代料", "substitute", "紧急采购")

# 输出 data_gaps value_consumption_status 枚举映射
VCS_MAP = {
    "usable": "usable",
    "null_unavailable": "missing",
    "invalid": "unusable",
    "needs_rule": "pending",
    "aggregation_not_allowed": "blocked",
    "unusable": "unusable",
    "missing": "missing",
    "blocked": "blocked",
    "pending": "pending",
    "field_absent": "missing",
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _gen_trace_id() -> str:
    return "SUPPLY-" + uuid.uuid4().hex[:16]


def _parse_entity_from_key(semantic_record_key: str) -> str:
    """从 semantic_record_key 解析语义实体。

    key 形如: 供-采购订单与库存#purchase_order#<record_id>#<row>
    """
    if not semantic_record_key:
        return ""
    parts = semantic_record_key.split("#")
    if len(parts) >= 2:
        return parts[1]
    return ""


def _parse_record_id(semantic_record_key: str) -> str:
    parts = semantic_record_key.split("#")
    if len(parts) >= 3:
        return "#".join(parts[2:])
    return semantic_record_key


def _has_evidence(fact: dict) -> bool:
    prov = fact.get("provenance_ref") or {}
    el = prov.get("evidence_locator")
    return isinstance(el, dict) and bool(el)


def _evref(fact: dict) -> Optional[str]:
    """对一条事实构建字段级 EVREF；无法构建时返回 None。"""
    if not _has_evidence(fact):
        return None
    return build_canonical_evidence_ref(fact)


def _evrefs_of(facts: List[dict]) -> List[str]:
    """对一组事实构建 EVREF 列表，跳过无法构建的。"""
    refs = []
    for f in facts:
        r = _evref(f)
        if r:
            refs.append(r)
    return refs


def _safe_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _safe_parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m-%dT00:00:00"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _map_vcs(vcs: str) -> str:
    return VCS_MAP.get(vcs, "unusable")


def _convert_source_locator(loc: Any) -> Optional[str]:
    """将输入的 source_locator（object|null）转为输出 string|null。"""
    if loc is None:
        return None
    if isinstance(loc, str):
        return loc if loc else None
    if isinstance(loc, dict):
        parts = []
        for k in ("source_table", "source_record_id", "source_column_name"):
            v = loc.get(k)
            if v:
                parts.append(str(v))
        return "|".join(parts) if parts else json.dumps(loc, ensure_ascii=False)
    return str(loc)


def _normalize_data_gap(gap: dict) -> dict:
    """将输入或内部 data_gap 规范化为归并前 6 字段格式（供 merge_data_gaps 消费）。"""
    return {
        "semantic_entity": str(gap.get("semantic_entity", "")),
        "semantic_field": str(gap.get("semantic_field", "")),
        "reason": str(gap.get("reason", "")),
        "value_consumption_status": _map_vcs(gap.get("value_consumption_status", "unusable")),
        "source_locator": _convert_source_locator(gap.get("source_locator")),
        "required_resolution": str(gap.get("required_resolution", "")),
    }


def _extract_as_of_time(decision_input: dict) -> Optional[datetime]:
    """从 decision_input 中提取评估时点。

    优先级：
    1. query_context.as_of_time
    2. query_context.evaluation_time
    3. 顶层 as_of_time
    4. 顶层 evaluation_time

    不使用系统当前时间猜测。
    """
    qc = decision_input.get("query_context") or {}
    for key in ("as_of_time", "evaluation_time"):
        val = qc.get(key)
        dt = _safe_parse_dt(val)
        if dt is not None:
            return dt
    for key in ("as_of_time", "evaluation_time"):
        val = decision_input.get(key)
        dt = _safe_parse_dt(val)
        if dt is not None:
            return dt
    return None


def _is_explicit_expedite_request(decision_input: dict) -> bool:
    """判断查询是否明确请求加急采购/替代料。

    普通只读查询不生成高风险加急动作。
    需 query_context.requested_action 或 user_query 中包含加急关键词。
    """
    qc = decision_input.get("query_context") or {}
    ra = qc.get("requested_action", "")
    if isinstance(ra, str) and ra in ("expedite_purchase", "substitute_material", "expedite"):
        return True
    uq = qc.get("user_query", "") or decision_input.get("user_query", "") or ""
    if isinstance(uq, str) and any(kw in uq for kw in EXPEDITE_KEYWORDS):
        return True
    return False


# ---------------------------------------------------------------------------
# 1. validate_supply_input_contract
# ---------------------------------------------------------------------------

def validate_supply_input_contract(decision_input: dict) -> dict:
    """验证输入合同合规性。不合规时返回 blocked 结果。"""
    result = {
        "valid": True,
        "blocked_status": None,
        "block_reason": None,
        "issues": [],
        "consumable_facts": [],
        "non_usable_facts": [],
    }

    if not isinstance(decision_input, dict):
        result["valid"] = False
        result["blocked_status"] = BLOCKED_INPUT_CONTRACT
        result["block_reason"] = "输入不是合法 JSON 对象"
        return result

    if decision_input.get("contract_name") != CONTRACT_NAME_IN:
        result["valid"] = False
        result["blocked_status"] = BLOCKED_INPUT_CONTRACT
        result["issues"].append(
            f"contract_name 不匹配: 期望={CONTRACT_NAME_IN}, 实际={decision_input.get('contract_name')}"
        )
    if decision_input.get("contract_version") != CONTRACT_VERSION_IN:
        result["valid"] = False
        result["blocked_status"] = BLOCKED_INPUT_CONTRACT
        result["issues"].append(
            f"contract_version 不匹配: 期望={CONTRACT_VERSION_IN}, 实际={decision_input.get('contract_version')}"
        )

    if decision_input.get("source_write_performed") is not False:
        result["valid"] = False
        if not result["blocked_status"]:
            result["blocked_status"] = BLOCKED_SOURCE_WRITE
        result["issues"].append(
            f"source_write_performed 必须为 false，实际={decision_input.get('source_write_performed')}"
        )

    if decision_input.get("actor_can_execute") is not False:
        result["valid"] = False
        result["issues"].append(
            f"actor_can_execute 必须为 false，实际={decision_input.get('actor_can_execute')}"
        )

    vstatus = (decision_input.get("validation") or {}).get("status")
    if vstatus in ("failed", "blocked"):
        result["valid"] = False
        if not result["blocked_status"]:
            result["blocked_status"] = BLOCKED_INPUT_CONTRACT
        result["issues"].append(f"validation.status={vstatus}，不得消费")

    facts = decision_input.get("normalized_facts") or []
    for f in facts:
        if f.get("value_consumption_status") != USABLE:
            result["non_usable_facts"].append(f)
            continue
        if not _has_evidence(f):
            result["valid"] = False
            result["blocked_status"] = BLOCKED_EVIDENCE_MISSING
            result["issues"].append(
                f"事实缺少 evidence_locator: {f.get('semantic_record_key')}#{f.get('semantic_field')}"
            )
            continue
        if f.get("normalized_value") is None:
            result["valid"] = False
            result["issues"].append(
                f"usable 事实 normalized_value 为 null: {f.get('semantic_record_key')}#{f.get('semantic_field')}"
            )
            continue
        result["consumable_facts"].append(f)

    role = decision_input.get("role")
    if role not in ("supply", "factory"):
        result["valid"] = False
        if not result["blocked_status"]:
            result["blocked_status"] = BLOCKED_ROLE_SCOPE
        result["issues"].append(f"角色 {role} 无供应链查询权限")

    if result["issues"]:
        result["valid"] = False
        if not result["blocked_status"]:
            result["blocked_status"] = BLOCKED_INPUT_CONTRACT

    return result


# ---------------------------------------------------------------------------
# 2. group_supply_facts_by_record
# ---------------------------------------------------------------------------

def group_supply_facts_by_record(facts: List[dict]) -> Dict[str, Dict[str, dict]]:
    """按 semantic_record_key 分组，只保留供应链实体。"""
    groups: Dict[str, Dict[str, dict]] = {}
    for f in facts:
        key = f.get("semantic_record_key", "")
        entity = _parse_entity_from_key(key)
        if entity not in SUPPLY_ENTITIES:
            continue
        groups.setdefault(key, {})[f.get("semantic_field")] = f
    return groups


# ---------------------------------------------------------------------------
# 3. extract_purchase_order_facts
# ---------------------------------------------------------------------------

PO_FIELDS = {
    "material_code", "material_name", "supplier",
    "purchase_qty", "arrived_qty",
    "promised_delivery_date", "actual_arrival_date",
    "expected_arrival_date", "order_amount", "order_status",
    "po_number",
}


def extract_purchase_order_facts(record_group: Dict[str, dict]) -> dict:
    """从单条采购订单记录分组中提取结构化事实（保留字段事实用于 EVREF 构建）。"""
    po = {
        "record_key": "",
        "record_id": "",
        "material_code": None,
        "material_name": None,
        "supplier": None,
        "purchase_qty": None,
        "arrived_qty": None,
        "promised_delivery_date": None,
        "actual_arrival_date": None,
        "expected_arrival_date": None,
        "order_amount": None,
        "order_amount_unit": None,
        "order_status": None,
        "po_number": None,
        "field_facts": {},   # semantic_field -> normalized_fact（字段级证据来源）
        "facts": [],
    }
    for field, fact in record_group.items():
        if field not in PO_FIELDS:
            continue
        val = fact.get("normalized_value")
        if not po["record_key"]:
            po["record_key"] = fact.get("semantic_record_key", "")
            po["record_id"] = _parse_record_id(po["record_key"])
        if field == "order_amount":
            po["order_amount"] = _safe_float(val)
            po["order_amount_unit"] = fact.get("normalized_unit") or ""
        elif field in ("purchase_qty", "arrived_qty"):
            po[field] = _safe_float(val)
        else:
            po[field] = val
        po["field_facts"][field] = fact
        po["facts"].append(fact)
    return po


def _fact_evref(po: dict, field: str) -> Optional[str]:
    """取采购订单某字段的字段级 EVREF。"""
    f = po["field_facts"].get(field)
    if not f:
        return None
    return _evref(f)


# ---------------------------------------------------------------------------
# 4. analyze_arrival_status_if_supported（v0.1.3 语义修复版）
# ---------------------------------------------------------------------------

def analyze_arrival_status_if_supported(po: dict, decision_input: dict) -> dict:
    """到货状态分析（v0.1.3 语义修复）。

    修复 P1_RUNTIME_SEMANTIC_GAP：
    - actual_arrival_date 只解释为"已登记到货日期"，不得自动解释为整单完成日期
    - 到货状态由 purchase_qty 与 arrived_qty 确定性确定
    - arrived_qty < purchase_qty 时 delivery_completion_status=indeterminate
    - 剩余数量逾期判定依赖明确 as_of_time；缺失时 overdue_status=indeterminate
    """
    analysis = {
        "can_judge_overdue": False,
        "delivery_status": "unknown",
        "delivery_completion_status": "indeterminate",
        "arrival_status": "cannot_determine",
        "delivery_completeness": "unknown",
        "shortfall_qty": None,
        "remaining_qty": None,
        "overdue_status": "indeterminate",
        "overdue_days": None,
        "registered_arrival_note": None,
        "rule": None,
        "data_gap": None,
        "extra_data_gaps": [],
    }

    purchase_qty = po.get("purchase_qty")
    arrived_qty = po.get("arrived_qty")
    promised = _safe_parse_dt(po.get("promised_delivery_date"))
    actual = _safe_parse_dt(po.get("actual_arrival_date"))

    as_of_time = _extract_as_of_time(decision_input)

    # --- 缺少 purchase_qty ---
    if purchase_qty is None:
        analysis["data_gap"] = {
            "semantic_entity": "purchase_order",
            "semantic_field": "purchase_qty",
            "reason": "missing_purchase_qty",
            "value_consumption_status": "missing",
            "source_locator": {"source_record_id": po.get("record_id", "")},
            "required_resolution": "缺少采购数量，无法确定到货状态",
        }
        return analysis

    # --- 缺少 arrived_qty ---
    if arrived_qty is None:
        analysis["delivery_status"] = "unknown"
        analysis["data_gap"] = {
            "semantic_entity": "purchase_order",
            "semantic_field": "arrived_qty",
            "reason": "missing_arrived_qty",
            "value_consumption_status": "missing",
            "source_locator": {"source_record_id": po.get("record_id", "")},
            "required_resolution": "缺少到货数量，无法确定到货状态",
        }
        return analysis

    analysis["rule"] = DELIVERY_STATUS_RULE

    # --- 确定到货状态 ---
    if arrived_qty == 0:
        analysis["delivery_status"] = "not_arrived"
        analysis["delivery_completeness"] = "not_arrived"
        analysis["shortfall_qty"] = purchase_qty
        analysis["remaining_qty"] = purchase_qty
    elif 0 < arrived_qty < purchase_qty:
        analysis["delivery_status"] = "partial_arrival"
        analysis["delivery_completeness"] = "partial"
        analysis["shortfall_qty"] = purchase_qty - arrived_qty
        analysis["remaining_qty"] = purchase_qty - arrived_qty
    elif arrived_qty == purchase_qty:
        analysis["delivery_status"] = "completed"
        analysis["delivery_completeness"] = "full"
        analysis["delivery_completion_status"] = "completed"
        analysis["shortfall_qty"] = 0.0
        analysis["remaining_qty"] = 0.0
    elif arrived_qty > purchase_qty:
        analysis["delivery_status"] = "over_received_anomaly"
        analysis["delivery_completeness"] = "over_delivery"
        analysis["shortfall_qty"] = 0.0
        analysis["remaining_qty"] = 0.0

    # --- 缺少 promised_delivery_date ---
    if promised is None:
        analysis["data_gap"] = {
            "semantic_entity": "purchase_order",
            "semantic_field": "promised_delivery_date",
            "reason": "missing_promised_delivery_date",
            "value_consumption_status": "missing",
            "source_locator": {"source_record_id": po.get("record_id", "")},
            "required_resolution": "需业务系统补录承诺交期后方可判断逾期",
        }
        return analysis

    analysis["rule"] = ARRIVAL_COMPARE_RULE

    # --- 登记到货日期说明（仅事实描述，不作为整单逾期结论）---
    if actual is not None:
        if actual > promised:
            analysis["registered_arrival_note"] = (
                f"已登记到货日期 {actual.strftime('%Y-%m-%d')} 晚于承诺交期 "
                f"{promised.strftime('%Y-%m-%d')}（仅到货登记事实，非整单完成判定）"
            )
        else:
            analysis["registered_arrival_note"] = (
                f"已登记到货日期 {actual.strftime('%Y-%m-%d')} 不晚于承诺交期 "
                f"{promised.strftime('%Y-%m-%d')}（仅到货登记事实，非整单完成判定）"
            )

    # --- 按到货状态分支处理逾期判定 ---

    if analysis["delivery_status"] == "completed":
        # 整单完成：可基于 actual_arrival_date 判断逾期
        if actual is not None:
            analysis["can_judge_overdue"] = True
            if actual > promised:
                analysis["arrival_status"] = "overdue"
                analysis["overdue_status"] = "overdue"
                analysis["overdue_days"] = (actual - promised).days
            else:
                analysis["arrival_status"] = "on_time"
                analysis["overdue_status"] = "not_overdue"
        else:
            analysis["extra_data_gaps"].append({
                "semantic_entity": "purchase_order",
                "semantic_field": "actual_arrival_date",
                "reason": "missing_actual_arrival_date_for_completed_order",
                "value_consumption_status": "missing",
                "source_locator": po.get("record_id", ""),
                "required_resolution": "整单已完成但缺少已登记到货日期，无法判断是否逾期",
            })

    elif analysis["delivery_status"] == "partial_arrival":
        # 部分到货：delivery_completion_status 保持 indeterminate
        # 不得仅因到货日期不晚于承诺交期就判定全单已完成
        analysis["extra_data_gaps"].append({
            "semantic_entity": "purchase_order",
            "semantic_field": "complete_delivery_date",
            "reason": "missing_full_delivery_completion_evidence",
            "value_consumption_status": "missing",
            "source_locator": po.get("record_id", ""),
            "required_resolution": (
                "缺少 complete_delivery_date/order_completion_status/"
                "remaining_expected_arrival_date，整单到货完成状态不确定"
            ),
        })

        # 剩余数量逾期判定依赖 as_of_time
        if as_of_time is None:
            analysis["overdue_status"] = "indeterminate"
            analysis["extra_data_gaps"].append({
                "semantic_entity": "purchase_order",
                "semantic_field": "evaluation_time",
                "reason": "missing_as_of_time_for_remaining_overdue",
                "value_consumption_status": "missing",
                "source_locator": po.get("record_id", ""),
                "required_resolution": "缺少评估时点(as_of_time)，剩余数量是否逾期无法判定，不得使用系统当前时间猜测",
            })
        else:
            if as_of_time > promised and analysis["remaining_qty"] > 0:
                analysis["overdue_status"] = "remaining_overdue"
                analysis["overdue_days"] = (as_of_time - promised).days
                analysis["arrival_status"] = "partial_remaining_overdue"
                analysis["can_judge_overdue"] = True
            else:
                analysis["overdue_status"] = "not_overdue"
                analysis["arrival_status"] = "partial_on_time"

    elif analysis["delivery_status"] == "not_arrived":
        # 未到货：逾期判定依赖 as_of_time
        if as_of_time is None:
            analysis["overdue_status"] = "indeterminate"
            analysis["extra_data_gaps"].append({
                "semantic_entity": "purchase_order",
                "semantic_field": "evaluation_time",
                "reason": "missing_as_of_time_for_overdue",
                "value_consumption_status": "missing",
                "source_locator": po.get("record_id", ""),
                "required_resolution": "缺少评估时点(as_of_time)，无法判定逾期",
            })
        else:
            analysis["can_judge_overdue"] = True
            if as_of_time > promised:
                analysis["arrival_status"] = "overdue"
                analysis["overdue_status"] = "overdue"
                analysis["overdue_days"] = (as_of_time - promised).days
            else:
                analysis["arrival_status"] = "on_time"
                analysis["overdue_status"] = "not_overdue"

    elif analysis["delivery_status"] == "over_received_anomaly":
        analysis["overdue_status"] = "indeterminate"
        analysis["extra_data_gaps"].append({
            "semantic_entity": "purchase_order",
            "semantic_field": "arrived_qty",
            "reason": "over_received_anomaly",
            "value_consumption_status": "unusable",
            "source_locator": po.get("record_id", ""),
            "required_resolution": "到货数量超过采购数量，需源系统核实后重新评估",
        })

    return analysis


# ---------------------------------------------------------------------------
# 5. analyze_material_shortage
# ---------------------------------------------------------------------------

def analyze_material_shortage(shortage_records: Dict[str, Dict[str, dict]]) -> List[dict]:
    """物料缺口分析。逐记录计算缺口，不跨记录聚合。"""
    shortages = []
    for key, group in shortage_records.items():
        rec = {
            "record_key": key,
            "record_id": _parse_record_id(key),
            "material_code": None,
            "demand_qty": None,
            "available_qty": None,
            "shortage_qty": None,
            "field_facts": {},
            "facts": [],
        }
        for field, fact in group.items():
            val = fact.get("normalized_value")
            if field == "material_code":
                rec["material_code"] = val
            elif field == "demand_qty":
                rec["demand_qty"] = _safe_float(val)
            elif field == "available_qty":
                rec["available_qty"] = _safe_float(val)
            elif field == "shortage_qty":
                rec["shortage_qty"] = _safe_float(val)
            rec["field_facts"][field] = fact
            rec["facts"].append(fact)
        if rec["shortage_qty"] is None and rec["demand_qty"] is not None and rec["available_qty"] is not None:
            rec["shortage_qty"] = max(rec["demand_qty"] - rec["available_qty"], 0.0)
        if rec["shortage_qty"] is not None and rec["shortage_qty"] > 0:
            shortages.append(rec)
    return shortages


# ---------------------------------------------------------------------------
# 6. enforce_inventory_grain_gate
# ---------------------------------------------------------------------------

def enforce_inventory_grain_gate(inventory_records: Dict[str, Dict[str, dict]]) -> dict:
    """库存粒度门控。粒度未解决前禁止跨记录聚合，仅允许逐记录查看。

    保留字段事实用于字段级 EVREF 构建与逐记录指标。
    """
    gate = {
        "grain_status": INVENTORY_GRAIN["grain_status"],
        "aggregation_allowed": INVENTORY_GRAIN["aggregation_allowed"],
        "per_record_facts": [],
        "aggregation_blocked": True,
        "data_gap": None,
    }
    for key, group in inventory_records.items():
        rec = {
            "record_key": key,
            "record_id": _parse_record_id(key),
            "field_facts": dict(group),
        }
        gate["per_record_facts"].append(rec)

    if inventory_records:
        gate["data_gap"] = {
            "semantic_entity": "inventory_snapshot",
            "semantic_field": "aggregate_inventory",
            "reason": "grain_unresolved_aggregation_not_allowed",
            "value_consumption_status": "blocked",
            "source_locator": None,
            "required_resolution": (
                "inventory_snapshot 当前 grain_status=unresolved、aggregation_allowed=false，"
                "禁止跨记录求和/平均或推导全局库存；仅可逐记录查看"
            ),
        }
    return gate


# ---------------------------------------------------------------------------
# 7. separate_shortage_and_freeze_causes
# ---------------------------------------------------------------------------

def separate_shortage_and_freeze_causes(
    shortages: List[dict],
    freeze_records: Dict[str, Dict[str, dict]],
    relation_materialized: bool,
) -> dict:
    """缺口物料与冻结物料原因分离。"""
    separated = {
        "shortage_causes": [],
        "freeze_causes": [],
        "merged": False,
        "relation_materialized": relation_materialized,
        "cross_entity_join_blocked": not relation_materialized,
    }

    for s in shortages:
        separated["shortage_causes"].append({
            "cause_type": "material_shortage",
            "material_code": s.get("material_code"),
            "shortage_qty": s.get("shortage_qty"),
            "record_id": s.get("record_id"),
            "field_facts": s.get("field_facts", {}),
            "evidence_refs": _evrefs_of(s.get("facts", [])),
            "note": "物料缺口（后续生产连续性风险，非OEE直接原因）",
        })

    for key, group in freeze_records.items():
        rec = {
            "cause_type": "quality_freeze",
            "record_key": key,
            "record_id": _parse_record_id(key),
            "material_code": None,
            "freeze_quantity": None,
            "freeze_status": None,
            "field_facts": {},
            "facts": [],
            "evidence_refs": [],
        }
        for field, fact in group.items():
            val = fact.get("normalized_value")
            if field == "material_code":
                rec["material_code"] = val
            elif field in ("freeze_quantity", "freeze_qty"):
                rec["freeze_quantity"] = _safe_float(val)
            elif field == "freeze_status":
                rec["freeze_status"] = val
            rec["field_facts"][field] = fact
            rec["facts"].append(fact)
        rec["evidence_refs"] = _evrefs_of(rec["facts"])
        separated["freeze_causes"].append(rec)

    if relation_materialized:
        separated["merged"] = False
    return separated


# ---------------------------------------------------------------------------
# 8. classify_supply_continuity_risk
# ---------------------------------------------------------------------------

def classify_supply_continuity_risk(
    po_analyses: List[dict],
    shortages: List[dict],
    freeze_causes: List[dict],
    has_approved_severity_rule: bool = False,
) -> dict:
    """供应连续性风险分类。

    缺料只作为后续生产连续性风险，不作为当前 OEE 下降原因。
    无批准阈值规则时 severity=unknown。
    """
    risk = {
        "severity": "unknown",
        "missing_severity_rule": None,
        "risk_type": [],
        "risk_description": [],
        "is_oee_direct_cause": False,
    }
    if not has_approved_severity_rule:
        risk["missing_severity_rule"] = {
            "rule_id": "SUPPLY-SEVERITY-THRESHOLD",
            "reason": "未登记批准的供应连续性风险严重度阈值规则",
            "fallback": "severity=unknown",
        }

    # v0.1.3: overdue_pos 基于 overdue_status 而非 arrival_status
    overdue_pos = [p for p in po_analyses if p.get("overdue_status") in ("overdue", "remaining_overdue")]
    partial_pos = [p for p in po_analyses if p.get("delivery_status") == "partial_arrival"]
    anomaly_pos = [p for p in po_analyses if p.get("delivery_status") == "over_received_anomaly"]

    if shortages:
        risk["risk_type"].append("material_shortage_continuity_risk")
        risk["risk_description"].append(
            "存在物料缺口，构成后续生产连续性风险（非当前 OEE 直接原因）"
        )
    if overdue_pos:
        risk["risk_type"].append("arrival_overdue_risk")
        risk["risk_description"].append(
            f"存在 {len(overdue_pos)} 条到货逾期采购订单"
        )
    if partial_pos:
        risk["risk_type"].append("partial_delivery_risk")
        risk["risk_description"].append(
            f"存在 {len(partial_pos)} 条部分到货采购订单"
        )
    if anomaly_pos:
        risk["risk_type"].append("over_received_anomaly")
        risk["risk_description"].append(
            f"存在 {len(anomaly_pos)} 条超收异常采购订单"
        )
    if freeze_causes:
        risk["risk_type"].append("quality_freeze_risk")
        risk["risk_description"].append(
            f"存在 {len(freeze_causes)} 条质量冻结记录"
        )

    if not risk["risk_type"]:
        risk["risk_type"].append("no_supply_risk_detected")
        risk["risk_description"].append("未检测到供应连续性风险信号")

    return risk


# ---------------------------------------------------------------------------
# 9. build_supply_result
# ---------------------------------------------------------------------------

def _build_metrics(po_analyses: List[dict], inventory_gate: dict) -> List[dict]:
    """构建指标。每个 metric 的 evidence_refs 字段绑定到其 semantic_field 的事实。

    shortfall（到货缺口）为派生值，无单一字段事实支撑，故不作为 metric，
    改在 causes 中引用 purchase_qty/arrived_qty 字段事实。
    """
    metrics = []
    midx = 0
    for p in po_analyses:
        po = p["po"]
        # 采购数量
        if po.get("purchase_qty") is not None:
            ev = _fact_evref(po, "purchase_qty")
            if ev:
                midx += 1
                metrics.append({
                    "metric_id": f"M-SUP-{midx:03d}",
                    "label": f"{po['record_id']} 采购数量",
                    "value": po["purchase_qty"],
                    "display_format": "#,##0",
                    "semantic_field": "purchase_qty",
                    "evidence_refs": [ev],
                })
        # 到货数量
        if po.get("arrived_qty") is not None:
            ev = _fact_evref(po, "arrived_qty")
            if ev:
                midx += 1
                metrics.append({
                    "metric_id": f"M-SUP-{midx:03d}",
                    "label": f"{po['record_id']} 到货数量",
                    "value": po["arrived_qty"],
                    "display_format": "#,##0",
                    "semantic_field": "arrived_qty",
                    "evidence_refs": [ev],
                })
        # 到货缺口（部分到货时）：派生值，绑定 arrived_qty 字段事实
        if p.get("shortfall_qty") is not None and p["shortfall_qty"] > 0:
            ev = _fact_evref(po, "arrived_qty")
            if ev:
                midx += 1
                metrics.append({
                    "metric_id": f"M-SUP-{midx:03d}",
                    "label": f"{po['record_id']} 到货缺口",
                    "value": p["shortfall_qty"],
                    "display_format": "#,##0",
                    "semantic_field": "arrived_qty",
                    "evidence_refs": [ev],
                })
    # 库存逐记录查看：取首条记录的一个可用字段事实作为样例指标（不跨记录聚合）
    if inventory_gate["per_record_facts"]:
        first = inventory_gate["per_record_facts"][0]
        preferred = ["stock_on_hand", "safety_stock", "inventory_turnover_days", "material_shortage_risk"]
        chosen_field = None
        chosen_evref = None
        for pf in preferred:
            f = first["field_facts"].get(pf)
            if f:
                r = _evref(f)
                if r:
                    chosen_field = pf
                    chosen_evref = r
                    break
        if chosen_field is None:
            for fld, f in first["field_facts"].items():
                r = _evref(f)
                if r:
                    chosen_field = fld
                    chosen_evref = r
                    break
        if chosen_field and chosen_evref:
            midx += 1
            metrics.append({
                "metric_id": f"M-SUP-{midx:03d}",
                "label": f"库存逐记录查看（样例 {first['record_id']} {chosen_field}）",
                "value": first["field_facts"][chosen_field].get("normalized_value"),
                "display_format": "#,##0.##",
                "semantic_field": chosen_field,
                "evidence_refs": [chosen_evref],
            })
    return metrics


def _build_recommended_actions(
    risk: dict,
    shortages: List[dict],
    freeze_causes: List[dict],
    po_analyses: List[dict],
    is_explicit_expedite: bool = False,
) -> List[dict]:
    """构建推荐动作（v0.1.3）。

    高风险加急采购/替代料仅在明确请求 + 字段级 EVREF 充分时生成草稿。
    普通只读查询不生成加急动作。
    每条 action_id 登记 identifier_scope=local_run_only。
    """
    actions = []
    aidx = 0

    # 高风险：加急采购 + 替代料（仅当明确请求且有可解析证据）
    if is_explicit_expedite and shortages:
        ev = []
        mats = []
        for s in shortages:
            ev.extend(_evrefs_of(s.get("facts", [])))
            if s.get("material_code"):
                mats.append(s["material_code"])
        # 字段级 EVREF 充分性检查：至少需要 shortage_qty 的 EVREF
        has_sufficient_evref = bool(ev)
        if has_sufficient_evref:
            aidx += 1
            actions.append({
                "action_id": f"A-SUP-{aidx:03d}",
                "action": f"加急采购物料 {','.join(mats)}" if mats else "加急采购物料",
                "priority": "high",
                "is_high_risk": True,
                "needs_human_confirmation": True,
                "prohibited_auto_execute": True,
                "actor_can_execute": False,
                "affected_object": ",".join(mats) if mats else "unknown",
                "evidence_refs": ev[:3],
            })
            aidx += 1
            actions.append({
                "action_id": f"A-SUP-{aidx:03d}",
                "action": f"启用替代料 {','.join(mats)}" if mats else "启用替代料",
                "priority": "high",
                "is_high_risk": True,
                "needs_human_confirmation": True,
                "prohibited_auto_execute": True,
                "actor_can_execute": False,
                "affected_object": ",".join(mats) if mats else "unknown",
                "evidence_refs": ev[:3],
            })

    # 高风险：解除质量冻结（仅当存在冻结记录且有可解析证据）
    # 冻结解除不需要明确加急请求，但仍需证据充分
    if freeze_causes:
        ev = []
        mats = []
        for f in freeze_causes:
            ev.extend(f.get("evidence_refs", []))
            if f.get("material_code"):
                mats.append(f["material_code"])
        if ev:
            aidx += 1
            actions.append({
                "action_id": f"A-SUP-{aidx:03d}",
                "action": f"解除质量冻结 {','.join(mats)}" if mats else "解除质量冻结",
                "priority": "high",
                "is_high_risk": True,
                "needs_human_confirmation": True,
                "prohibited_auto_execute": True,
                "actor_can_execute": False,
                "affected_object": ",".join(mats) if mats else "unknown",
                "evidence_refs": ev[:3],
            })

    # 低风险：向供应商催货并登记到货预期（到货逾期时）
    overdue_pos = [p for p in po_analyses if p.get("overdue_status") in ("overdue", "remaining_overdue")]
    if overdue_pos:
        ev = []
        for p in overdue_pos:
            po = p["po"]
            for fld in ("promised_delivery_date", "actual_arrival_date", "expected_arrival_date"):
                r = _fact_evref(po, fld)
                if r:
                    ev.append(r)
        po_ids = [p["po"]["record_id"] for p in overdue_pos]
        if ev:
            aidx += 1
            actions.append({
                "action_id": f"A-SUP-{aidx:03d}",
                "action": f"向供应商催货并登记到货预期（{','.join(po_ids)}）",
                "priority": "medium",
                "is_high_risk": False,
                "needs_human_confirmation": False,
                "prohibited_auto_execute": True,
                "actor_can_execute": False,
                "affected_object": ",".join(po_ids),
                "evidence_refs": ev[:3],
            })

    return actions


def _determine_status(has_high_risk: bool, data_gaps: List[dict]) -> str:
    """按优先级确定 status: blocked > needs_confirmation > warning > completed。"""
    if has_high_risk:
        return "needs_confirmation"
    if data_gaps:
        return "warning"
    return "completed"


def build_supply_result(
    decision_input: dict,
    validation_result: dict,
    po_analyses: List[dict],
    shortages: List[dict],
    separated: dict,
    inventory_gate: dict,
    risk: dict,
    extra_data_gaps: List[dict],
    is_real_data_plane: bool = False,
) -> dict:
    """组装 BIFROST_SPECIALIST_RESULT_v0.1.3。"""
    facts = validation_result["consumable_facts"]
    total_usable = len(facts)
    with_evidence = sum(1 for f in facts if _has_evidence(f))
    confidence = round(with_evidence / total_usable, 4) if total_usable else 0.0

    risk_types = risk.get("risk_type", [])
    has_risks = risk_types != ["no_supply_risk_detected"]
    if not has_risks:
        conclusion = "未检测到供应连续性风险信号"
    else:
        conclusion = "；".join(risk.get("risk_description", [])) or "已检测到供应连续性风险信号"

    # 原因：缺口与冻结分别列出
    causes = []
    cidx = 0
    for sc in separated["shortage_causes"]:
        ev = sc.get("evidence_refs", [])
        if not ev:
            continue
        cidx += 1
        causes.append({
            "cause_id": f"C-SUP-{cidx:03d}",
            "category": sc["cause_type"],
            "statement": f"物料 {sc.get('material_code')} 缺口 {sc.get('shortage_qty')}（后续生产连续性风险）",
            "causal_evidence_level": "associated_risk",
            "evidence_refs": ev[:3],
        })
    for fc in separated["freeze_causes"]:
        ev = fc.get("evidence_refs", [])
        if not ev:
            continue
        cidx += 1
        causes.append({
            "cause_id": f"C-SUP-{cidx:03d}",
            "category": fc["cause_type"],
            "statement": f"物料 {fc.get('material_code')} 质量冻结 数量 {fc.get('freeze_quantity')}",
            "causal_evidence_level": "associated_risk",
            "evidence_refs": ev[:3],
        })

    for p in po_analyses:
        po = p["po"]
        ds = p.get("delivery_status", "unknown")
        overdue_st = p.get("overdue_status", "indeterminate")

        # 到货逾期（整单完成且逾期 / 部分到货剩余数量逾期）
        if overdue_st in ("overdue", "remaining_overdue"):
            ev = []
            for fld in ("promised_delivery_date", "actual_arrival_date", "expected_arrival_date",
                        "purchase_qty", "arrived_qty"):
                r = _fact_evref(po, fld)
                if r:
                    ev.append(r)
            if not ev:
                continue
            cidx += 1
            if overdue_st == "remaining_overdue":
                stmt = (
                    f"采购订单 {po['record_id']} 部分到货，"
                    f"截至评估时点剩余数量 {p.get('remaining_qty')} "
                    f"逾期 {p.get('overdue_days')} 天（超过承诺交期）"
                )
            else:
                stmt = f"采购订单 {po['record_id']} 到货逾期 {p.get('overdue_days')} 天"
            causes.append({
                "cause_id": f"C-SUP-{cidx:03d}",
                "category": "arrival_overdue",
                "statement": stmt,
                "causal_evidence_level": "direct_verified",
                "evidence_refs": ev[:3],
            })
        elif ds == "partial_arrival":
            # 部分到货缺口为派生值，引用 purchase_qty/arrived_qty 字段事实
            ev = []
            for fld in ("purchase_qty", "arrived_qty"):
                r = _fact_evref(po, fld)
                if r:
                    ev.append(r)
            if not ev:
                continue
            cidx += 1
            stmt = (
                f"采购订单 {po['record_id']} 部分到货，"
                f"缺口 {p.get('shortfall_qty')}（后续生产连续性风险）"
            )
            # 若有已登记到货日期说明，追加（但不作为整单完成判定）
            note = p.get("registered_arrival_note")
            if note:
                stmt += f"；{note}"
            causes.append({
                "cause_id": f"C-SUP-{cidx:03d}",
                "category": "partial_delivery_shortfall",
                "statement": stmt,
                "causal_evidence_level": "direct_verified",
                "evidence_refs": ev[:3],
            })
        elif ds == "over_received_anomaly":
            ev = []
            for fld in ("purchase_qty", "arrived_qty"):
                r = _fact_evref(po, fld)
                if r:
                    ev.append(r)
            if not ev:
                continue
            cidx += 1
            causes.append({
                "cause_id": f"C-SUP-{cidx:03d}",
                "category": "over_received_anomaly",
                "statement": (
                    f"采购订单 {po['record_id']} 到货数量 {po.get('arrived_qty')} "
                    f"超过采购数量 {po.get('purchase_qty')}，超收异常"
                ),
                "causal_evidence_level": "direct_verified",
                "evidence_refs": ev[:3],
            })

    # 受影响对象
    affected = []
    for p in po_analyses:
        affected.append({"object_type": "purchase_order", "object_id": p["po"]["record_id"]})
    for s in shortages:
        affected.append({"object_type": "material_shortage", "object_id": s.get("record_id", ""),
                         "material_code": s.get("material_code")})
    for fc in separated["freeze_causes"]:
        affected.append({"object_type": "quality_freeze", "object_id": fc.get("record_id", "")})

    # 顶层证据引用
    evidence_refs = _evrefs_of(facts)

    # data_gaps：收集归并前 6 字段缺口，再由共享 merge_data_gaps 归并
    raw_gaps = []
    for g in (decision_input.get("data_gaps") or []):
        raw_gaps.append(_normalize_data_gap(g))
    for g in extra_data_gaps:
        raw_gaps.append(_normalize_data_gap(g))
    if inventory_gate.get("data_gap"):
        raw_gaps.append(_normalize_data_gap(inventory_gate["data_gap"]))
    if has_risks and risk.get("missing_severity_rule"):
        raw_gaps.append(_normalize_data_gap({
            "semantic_entity": "supply_continuity_risk",
            "semantic_field": "severity",
            "reason": risk["missing_severity_rule"]["reason"],
            "value_consumption_status": "pending",
            "required_resolution": "需登记批准的严重度阈值规则后方可定级",
        }))
    if is_real_data_plane and not shortages and not separated["freeze_causes"]:
        raw_gaps.append(_normalize_data_gap({
            "semantic_entity": "material_shortage",
            "semantic_field": "shortage_qty",
            "reason": "entity_not_present_in_data_plane",
            "value_consumption_status": "missing",
            "required_resolution": "真实数据面无 material_shortage/quality_freeze 语义实体，无法进行缺口与冻结分析",
        }))

    data_gaps = merge_data_gaps(raw_gaps)

    # 推荐动作
    is_explicit_expedite = _is_explicit_expedite_request(decision_input)
    actions = _build_recommended_actions(
        risk, shortages, separated["freeze_causes"], po_analyses,
        is_explicit_expedite=is_explicit_expedite,
    )
    has_high_risk = any(a.get("is_high_risk") is True for a in actions)
    needs_human_confirmation = any(a.get("needs_human_confirmation") for a in actions)

    # 确定 status
    status = _determine_status(has_high_risk, data_gaps)

    metrics = _build_metrics(po_analyses, inventory_gate)

    # validation 对象
    validation_obj = {
        "status": "passed",
        "issues": [],
        "warnings": [],
        "input_contract_valid": True,
        "evidence_contract_valid": True,
        "output_contract_valid": True,
    }
    if data_gaps:
        validation_obj["status"] = "warning"
        validation_obj["warnings"].append(f"存在 {len(data_gaps)} 项数据缺口")

    result = {
        "contract_name": CONTRACT_NAME_OUT,
        "contract_version": CONTRACT_VERSION_OUT,
        "specialist_type": SPECIALIST_TYPE,
        "status": status,
        "request_id": decision_input.get("request_id", ""),
        "source_release_id": decision_input.get("source_release_id", ""),
        "source_snapshot_id": decision_input.get("source_snapshot_id", ""),
        "conclusion": conclusion,
        "severity": risk.get("severity", "unknown"),
        "confidence": confidence,
        "metrics": metrics,
        "causes": causes,
        "affected_objects": affected,
        "recommended_actions": actions,
        "needs_human_confirmation": needs_human_confirmation,
        "evidence_refs": evidence_refs,
        "data_gaps": data_gaps,
        "actor_can_execute": False,
        "contract_versions": {
            "specialist_result_contract_version": CONTRACT_VERSION_OUT,
            "decision_input_contract_version": CONTRACT_VERSION_IN,
            "specialist_logical_version": f"SUPPLY-LOGIC-v{LOGICAL_SKILL_VERSION}",
            "delivery_status_rule_version": DELIVERY_STATUS_RULE["rule_id"],
            "arrival_compare_rule_version": ARRIVAL_COMPARE_RULE["rule_id"],
        },
        "validation": validation_obj,
        "local_trace_id": _gen_trace_id(),
        "specialist_details": {
            "confidence_basis": {
                "method": "evidence_coverage",
                "usable_facts_with_evidence": with_evidence,
                "total_usable_facts": total_usable,
            },
            "stage": STAGE,
            "generated_at": _now_iso(),
            "shortage_as_continuity_risk": True,
            "inventory_grain_status": INVENTORY_GRAIN["grain_status"],
            "relation_materialized": separated.get("relation_materialized", False),
            "evidence_ref_granularity": "field_level_EVREF-v1",
            "delivery_semantic_fix": "v0.1.3_P1_actual_arrival_date_is_registered_only",
            "expedite_gate": "explicit_request_required" if not is_explicit_expedite else "explicit_request_detected",
            "action_identifier_scope": "local_run_only",
        },
    }
    return result


def build_blocked_result(decision_input: dict, validation_result: dict) -> dict:
    """输入合同不合规时构建阻塞结果。

    blocked 状态：不得产生 conclusion/metrics/causes/recommended_actions。
    无业务事实时顶层 evidence_refs 允许为空（不使用占位证据）。
    """
    request_id = decision_input.get("request_id", "") if isinstance(decision_input, dict) else ""
    source_release_id = decision_input.get("source_release_id", "") if isinstance(decision_input, dict) else ""
    source_snapshot_id = decision_input.get("source_snapshot_id", "") if isinstance(decision_input, dict) else ""

    validation_obj = {
        "status": "failed",
        "issues": validation_result.get("issues", []),
        "warnings": [],
        "input_contract_valid": False,
        "evidence_contract_valid": False,
        "output_contract_valid": True,
    }

    return {
        "contract_name": CONTRACT_NAME_OUT,
        "contract_version": CONTRACT_VERSION_OUT,
        "specialist_type": SPECIALIST_TYPE,
        "status": "blocked",
        "request_id": request_id,
        "source_release_id": source_release_id,
        "source_snapshot_id": source_snapshot_id,
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
            "specialist_result_contract_version": CONTRACT_VERSION_OUT,
            "decision_input_contract_version": CONTRACT_VERSION_IN,
            "specialist_logical_version": f"SUPPLY-LOGIC-v{LOGICAL_SKILL_VERSION}",
        },
        "validation": validation_obj,
        "local_trace_id": _gen_trace_id(),
        "specialist_details": {
            "blocked_status": validation_result.get("blocked_status") or BLOCKED_INPUT_CONTRACT,
            "block_reasons": validation_result.get("issues", []),
            "stage": STAGE,
            "generated_at": _now_iso(),
        },
    }


# ---------------------------------------------------------------------------
# 10. validate_specialist_result_contract（内部自检，非独立验证器）
# ---------------------------------------------------------------------------

def validate_specialist_result_contract(result: dict) -> dict:
    """校验输出合同合规性（内部自检，非独立验证器）。"""
    vr = {"valid": True, "errors": [], "warnings": []}

    if result.get("contract_name") != CONTRACT_NAME_OUT:
        vr["valid"] = False
        vr["errors"].append(f"contract_name 不匹配: {result.get('contract_name')}")
    if result.get("contract_version") != CONTRACT_VERSION_OUT:
        vr["valid"] = False
        vr["errors"].append(f"contract_version 不匹配: {result.get('contract_version')}")
    if result.get("specialist_type") != SPECIALIST_TYPE:
        vr["valid"] = False
        vr["errors"].append("specialist_type 必须为 supply")
    if result.get("actor_can_execute") is not False:
        vr["valid"] = False
        vr["errors"].append("actor_can_execute 必须为 false")

    for a in result.get("recommended_actions", []):
        if a.get("is_high_risk") is True:
            if a.get("needs_human_confirmation") is not True:
                vr["valid"] = False
                vr["errors"].append(f"高风险动作未标记 needs_human_confirmation: {a.get('action_id')}")
            if a.get("prohibited_auto_execute") is not True:
                vr["valid"] = False
                vr["errors"].append(f"高风险动作未禁止自动执行: {a.get('action_id')}")
        if a.get("actor_can_execute") is not False:
            vr["valid"] = False
            vr["errors"].append(f"动作 actor_can_execute 必须 false: {a.get('action_id')}")
        # v0.1.3: action_id 登记 identifier_scope 在 specialist_details 中
        # （schema 不允许 action 对象有额外字段）
        if a.get("confirmation_id"):
            vr["valid"] = False
            vr["errors"].append(f"不得生成 ConfirmationID: {a.get('action_id')}")

    c = result.get("confidence")
    if not (isinstance(c, (int, float)) and 0.0 <= c <= 1.0):
        vr["valid"] = False
        vr["errors"].append(f"confidence 必须在 [0,1]，实际={c}")

    status = result.get("status")
    if status == "blocked":
        if result.get("conclusion"):
            vr["errors"].append("blocked 状态不得有 conclusion")
            vr["valid"] = False
        if result.get("metrics"):
            vr["errors"].append("blocked 状态不得有 metrics")
            vr["valid"] = False
        if result.get("causes"):
            vr["errors"].append("blocked 状态不得有 causes")
            vr["valid"] = False
        if result.get("recommended_actions"):
            vr["errors"].append("blocked 状态不得有 recommended_actions")
            vr["valid"] = False
    elif status == "completed":
        if result.get("data_gaps"):
            vr["valid"] = False
            vr["errors"].append("completed 状态 data_gaps 必须为空")
    elif status == "warning":
        if not result.get("data_gaps"):
            vr["valid"] = False
            vr["errors"].append("warning 状态必须有 data_gaps")
    elif status == "needs_confirmation":
        if not any(a.get("is_high_risk") for a in result.get("recommended_actions", [])):
            vr["valid"] = False
            vr["errors"].append("needs_confirmation 状态必须含至少一个高风险动作")

    return vr


# ---------------------------------------------------------------------------
# 编排入口
# ---------------------------------------------------------------------------

def orchestrate_supply_analysis(decision_input: dict, is_real_data_plane: bool = False) -> dict:
    """编排供应链风险分析完整流程。

    Args:
        decision_input: BIFROST_DECISION_INPUT_v0.1 合约对象。
        is_real_data_plane: True 表示来自真实消费者数据面。
    """
    vr = validate_supply_input_contract(decision_input)
    if not vr["valid"]:
        return build_blocked_result(decision_input, vr)

    consumable = vr["consumable_facts"]

    groups = group_supply_facts_by_record(consumable)

    po_groups = {k: g for k, g in groups.items()
                 if _parse_entity_from_key(k) == "purchase_order"}
    inv_groups = {k: g for k, g in groups.items()
                  if _parse_entity_from_key(k) == "inventory_snapshot"}
    shortage_groups = {k: g for k, g in groups.items()
                       if _parse_entity_from_key(k) in ("material_shortage", "shortage_risk")}
    freeze_groups = {k: g for k, g in groups.items()
                     if _parse_entity_from_key(k) == "material_detail"}

    po_analyses = []
    extra_gaps = []
    for key, g in po_groups.items():
        po = extract_purchase_order_facts(g)
        arrival = analyze_arrival_status_if_supported(po, decision_input)
        po_analyses.append({"po": po, **arrival})
        if arrival.get("data_gap"):
            extra_gaps.append(arrival["data_gap"])
        for eg in arrival.get("extra_data_gaps", []):
            extra_gaps.append(eg)

    for p in po_analyses:
        po = p["po"]
        amt = po.get("order_amount")
        unit = (po.get("order_amount_unit") or "").lower()
        if amt is not None:
            if amt < 0:
                extra_gaps.append({
                    "semantic_entity": "purchase_order",
                    "semantic_field": "order_amount",
                    "reason": "negative_amount_not_consumable",
                    "value_consumption_status": "unusable",
                    "required_resolution": "负金额不得进入业务结论，需源系统修正",
                    "source_locator": po.get("record_id", ""),
                })
                po["order_amount"] = None
            elif unit not in ("cny", "rmb", "元"):
                extra_gaps.append({
                    "semantic_entity": "purchase_order",
                    "semantic_field": "order_amount",
                    "reason": "unregistered_currency_unit",
                    "value_consumption_status": "pending",
                    "required_resolution": "金额单位未登记为 cny，需登记货币单位规则后方可消费",
                    "source_locator": po.get("record_id", ""),
                })
                po["order_amount"] = None

    shortages = analyze_material_shortage(shortage_groups)
    inventory_gate = enforce_inventory_grain_gate(inv_groups)

    relation_materialized = False
    separated = separate_shortage_and_freeze_causes(shortages, freeze_groups, relation_materialized)

    risk = classify_supply_continuity_risk(po_analyses, shortages, separated["freeze_causes"])

    result = build_supply_result(
        decision_input, vr, po_analyses, shortages,
        separated, inventory_gate, risk, extra_gaps,
        is_real_data_plane=is_real_data_plane,
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: supply_risk_analyzer.py <decision_input.json>")
        sys.exit(2)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        di = json.load(f)
    out = orchestrate_supply_analysis(di)
    print(json.dumps(out, ensure_ascii=False, indent=2))

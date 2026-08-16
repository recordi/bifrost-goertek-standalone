"""
BIFROST 生产诊断独立验证器 v0.1.2

独立于生产诊断代码，对 BIFROST_SPECIALIST_RESULT_v0.1.3 进行外部验证。
不引用 scripts/production_diagnosis.py 的任何内部函数，只检查合同规范。
同时提供变异测试能力：删除事实后验证结论是否同步消失。

v0.1.2 变更（04D.3-PROD）：
- 适配 v0.1.3 共享输出合同字段（contract_version=v0.1.3）
- evidence_refs 必须为 EVREF-v1 规范形式（非占位、非裸记录键）
- 高风险动作存在时，非 blocked 结果必须为 needs_confirmation（不得为 warning/completed）
- data_gaps 必须含 occurrence_count（9 字段）
- 可调用共享 specialist_contract_validator 进行结构+语义+字段级证据校验
"""

import copy
import json
import os
import sys

# OEE 直接驱动白名单（与生产规则独立声明，用于交叉校验）
OEE_DIRECT_DRIVERS_WHITELIST = {"availability", "performance_rate", "quality_factor"}

EVREF_PREFIX = "EVREF-v1:"

# 占位证据关键词
PLACEHOLDER_TOKENS = (
    "no_evidence", "no_provenance", "unknown", "placeholder", "dummy",
    "null", "none", "n/a", "todo", "tbd", "fabricated", "fake",
)


def validate_specialist_result_external(result: dict) -> dict:
    """
    外部验证 BIFROST_SPECIALIST_RESULT_v0.1.3 合同。

    检查项：
    1. 必需字段存在（含 validation）
    2. 禁止字段不存在
    3. actor_can_execute=false（顶层 + 每个 action）
    4. specialist_type=production
    5. confidence 为 0-1 浮点数
    6. severity=unknown 时 specialist_details 有 missing_severity_rule
    7. OEE 直接驱动只允许白名单三项
    8. 物料缺口不得进入 direct causes
    9. 高风险动作门控（is_high_risk → needs_human_confirmation + prohibited_auto_execute + actor_can_execute=false）
    10. 不得包含虚构 ConfirmationID / DecisionID / RunID
    11. 状态语义门控（blocked/warning/completed/needs_confirmation）
    12. 顶层不得有 blocked_code/missing_severity_rule 等迁移字段
    13. evidence_refs 必须为 EVREF-v1 规范形式（非占位、非裸记录键）
    14. 高风险动作存在时，非 blocked 结果必须为 needs_confirmation
    15. data_gaps 每项必须含 occurrence_count（9 字段）
    """
    v = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": {},
    }

    # 1. 必需字段
    required = [
        "contract_name", "contract_version", "specialist_type", "status",
        "request_id", "source_release_id", "source_snapshot_id", "conclusion",
        "severity", "confidence", "metrics", "causes", "affected_objects",
        "recommended_actions", "needs_human_confirmation", "evidence_refs",
        "data_gaps", "actor_can_execute", "contract_versions", "validation",
        "local_trace_id",
    ]
    missing = [f for f in required if f not in result]
    v["checks"]["required_fields"] = len(missing) == 0
    if missing:
        v["errors"].append(f"缺少必需字段: {missing}")
        v["valid"] = False

    # 2. 禁止字段
    forbidden = ["auto_execute_command", "executed_action_id", "confirmation_id",
                 "ConfirmationID", "DecisionID", "RunID"]
    present_forbidden = [f for f in forbidden if f in result]
    v["checks"]["no_forbidden_fields"] = len(present_forbidden) == 0
    if present_forbidden:
        v["errors"].append(f"包含禁止字段: {present_forbidden}")
        v["valid"] = False

    # 12. 顶层不得有迁移字段
    forbidden_top = ["blocked_code", "missing_severity_rule", "blocked_errors",
                     "high_risk", "auto_execute"]
    present_top = [f for f in forbidden_top if f in result]
    v["checks"]["no_migrated_top_fields"] = len(present_top) == 0
    if present_top:
        v["errors"].append(f"顶层存在应迁入 specialist_details 的字段: {present_top}")
        v["valid"] = False

    # 3. actor_can_execute
    v["checks"]["actor_can_execute_false"] = result.get("actor_can_execute") is False
    if result.get("actor_can_execute") is not False:
        v["errors"].append("actor_can_execute 必须为 false")
        v["valid"] = False

    for i, action in enumerate(result.get("recommended_actions", [])):
        if action.get("actor_can_execute") is not False:
            v["errors"].append(f"recommended_actions[{i}].actor_can_execute 必须为 false")
            v["valid"] = False
    v["checks"]["actions_actor_can_execute_false"] = v["valid"]

    # 4. specialist_type
    v["checks"]["specialist_type_production"] = result.get("specialist_type") == "production"
    if result.get("specialist_type") != "production":
        v["errors"].append("specialist_type 必须为 production")
        v["valid"] = False

    # contract_version
    if result.get("contract_version") != "BIFROST-SPECIALIST-RESULT-v0.1.3":
        v["errors"].append(f"contract_version 必须为 v0.1.3，实际: {result.get('contract_version')}")
        v["valid"] = False

    # 5. confidence 范围
    conf = result.get("confidence")
    v["checks"]["confidence_range"] = isinstance(conf, (int, float)) and 0 <= conf <= 1
    if not v["checks"]["confidence_range"]:
        v["errors"].append(f"confidence 必须为 0-1 浮点数，实际: {conf!r}")
        v["valid"] = False

    # 6. severity=unknown 时 specialist_details 有 missing_severity_rule
    sev = result.get("severity")
    sd = result.get("specialist_details", {})
    has_rule = sd.get("missing_severity_rule") is True
    v["checks"]["severity_unknown_has_rule"] = not (sev == "unknown" and not has_rule)
    if sev == "unknown" and not has_rule:
        v["errors"].append("severity=unknown 时 specialist_details 应包含 missing_severity_rule=true")
        v["valid"] = False

    # 7. OEE 直接驱动只允许白名单
    for cause in result.get("causes", []):
        if cause.get("category") == "oee_direct_driver":
            statement = cause.get("statement", "")
            for driver in OEE_DIRECT_DRIVERS_WHITELIST:
                if driver in statement:
                    break
            else:
                v["errors"].append(f"OEE 直接驱动 cause 不包含白名单驱动: {statement}")
                v["valid"] = False
    v["checks"]["oee_drivers_whitelisted"] = v["valid"]

    # 8. 物料缺口不得进入 direct causes
    for cause in result.get("causes", []):
        if cause.get("category") == "oee_direct_driver":
            statement = cause.get("statement", "").lower()
            if "material" in statement or "物料" in statement:
                v["errors"].append("物料缺口不得进入 OEE 直接驱动 causes")
                v["valid"] = False
    v["checks"]["material_not_direct_oee"] = v["valid"]

    # 9. 高风险动作门控
    for action in result.get("recommended_actions", []):
        if action.get("is_high_risk") is True:
            if action.get("needs_human_confirmation") is not True:
                v["errors"].append(f"高风险动作 {action.get('action_id')} needs_human_confirmation 必须为 true")
                v["valid"] = False
            if action.get("prohibited_auto_execute") is not True:
                v["errors"].append(f"高风险动作 {action.get('action_id')} prohibited_auto_execute 必须为 true")
                v["valid"] = False
            if action.get("actor_can_execute") is not False:
                v["errors"].append(f"高风险动作 {action.get('action_id')} actor_can_execute 必须为 false")
                v["valid"] = False
    v["checks"]["high_risk_gate"] = v["valid"]

    # 11. 状态语义门控
    status = result.get("status")
    if status == "blocked":
        if result.get("conclusion"):
            v["errors"].append("blocked 状态不得产生 conclusion")
            v["valid"] = False
        if result.get("metrics"):
            v["errors"].append("blocked 状态不得产生 metrics")
            v["valid"] = False
        if result.get("causes"):
            v["errors"].append("blocked 状态不得产生 causes")
            v["valid"] = False
        if result.get("recommended_actions"):
            v["errors"].append("blocked 状态不得产生 recommended_actions")
            v["valid"] = False
    elif status == "warning":
        if not result.get("data_gaps"):
            v["errors"].append("warning 状态必须包含 data_gaps")
            v["valid"] = False
    elif status == "completed":
        if result.get("data_gaps"):
            v["errors"].append("completed 状态不得包含 data_gaps")
            v["valid"] = False
    elif status == "needs_confirmation":
        has_high = any(a.get("is_high_risk") for a in result.get("recommended_actions", []))
        if not has_high:
            v["errors"].append("needs_confirmation 状态需要至少一个 is_high_risk=true 的动作")
            v["valid"] = False
        if result.get("needs_human_confirmation") is not True:
            v["errors"].append("needs_confirmation 状态需要 needs_human_confirmation=true")
            v["valid"] = False

    # 14. 高风险动作存在时，非 blocked 结果必须为 needs_confirmation
    has_high_risk = any(a.get("is_high_risk") for a in result.get("recommended_actions", []))
    if has_high_risk and status not in ("blocked", "needs_confirmation"):
        v["errors"].append(
            f"高风险动作存在但 status={status}，非 blocked 结果必须为 needs_confirmation")
        v["valid"] = False
    v["checks"]["high_risk_status_priority"] = v["valid"]

    # 13. evidence_refs 必须为 EVREF-v1 规范形式
    def _check_evref(refs, where):
        for r in refs:
            if not isinstance(r, str) or not r.startswith(EVREF_PREFIX):
                v["errors"].append(f"{where} evidence_ref '{r}' 不是 EVREF-v1 规范形式")
                v["valid"] = False
            elif len(r) <= len(EVREF_PREFIX):
                v["errors"].append(f"{where} evidence_ref '{r}' EVREF-v1 哈希为空")
                v["valid"] = False
            else:
                low = r.lower()
                if any(tok in low for tok in PLACEHOLDER_TOKENS):
                    v["errors"].append(f"{where} evidence_ref '{r}' 包含占位令牌")
                    v["valid"] = False

    for i, m in enumerate(result.get("metrics", [])):
        _check_evref(m.get("evidence_refs", []), f"metrics[{i}]")
    for i, c in enumerate(result.get("causes", [])):
        _check_evref(c.get("evidence_refs", []), f"causes[{i}]")
    for i, a in enumerate(result.get("recommended_actions", [])):
        _check_evref(a.get("evidence_refs", []), f"recommended_actions[{i}]")
    _check_evref(result.get("evidence_refs", []), "top-level")
    v["checks"]["evidence_refs_evref_v1"] = v["valid"]

    # 15. data_gaps 每项必须含 occurrence_count（9 字段）
    dg_required = ("semantic_entity", "semantic_field", "reason",
                   "value_consumption_status", "source_locator", "required_resolution",
                   "affected_record_count", "occurrence_count", "sample_source_locators")
    for i, g in enumerate(result.get("data_gaps", [])):
        for f in dg_required:
            if f not in g:
                v["errors"].append(f"data_gaps[{i}] 缺少 '{f}'")
                v["valid"] = False
        arc = g.get("affected_record_count")
        occ = g.get("occurrence_count")
        if isinstance(arc, int) and isinstance(occ, int) and arc > occ:
            v["errors"].append(f"data_gaps[{i}].affected_record_count({arc}) > occurrence_count({occ})")
            v["valid"] = False
        ssl = g.get("sample_source_locators")
        if isinstance(ssl, list) and len(ssl) > 3:
            v["errors"].append(f"data_gaps[{i}].sample_source_locators 超过 3 条")
            v["valid"] = False
    v["checks"]["data_gaps_structure"] = v["valid"]

    return v


def mutation_test_fact_removal(decision_input: dict, build_fn, field_to_remove: str) -> dict:
    """
    变异测试：删除指定字段的所有事实后，验证结论是否同步消失。
    """
    original = build_fn(decision_input)
    original_causes = [
        c for c in original.get("causes", [])
        if field_to_remove in str(c.get("statement", "")) or field_to_remove in str(c.get("category", ""))
        or field_to_remove in str(c.get("evidence_refs", []))
    ]

    mutated_input = copy.deepcopy(decision_input)
    mutated_input["normalized_facts"] = [
        f for f in mutated_input.get("normalized_facts", [])
        if f.get("semantic_field") != field_to_remove
    ]

    mutated = build_fn(mutated_input)
    mutated_causes = [
        c for c in mutated.get("causes", [])
        if field_to_remove in str(c.get("statement", "")) or field_to_remove in str(c.get("category", ""))
        or field_to_remove in str(c.get("evidence_refs", []))
    ]

    original_actions = [
        a for a in original.get("recommended_actions", [])
        if field_to_remove in str(a.get("action", "")) or field_to_remove in str(a.get("evidence_refs", []))
    ]
    mutated_actions = [
        a for a in mutated.get("recommended_actions", [])
        if field_to_remove in str(a.get("action", "")) or field_to_remove in str(a.get("evidence_refs", []))
    ]

    return {
        "original_has_cause": len(original_causes) > 0,
        "mutated_has_cause": len(mutated_causes) > 0,
        "cause_disappeared": len(original_causes) > 0 and len(mutated_causes) == 0,
        "original_has_action": len(original_actions) > 0,
        "mutated_has_action": len(mutated_actions) > 0,
        "action_disappeared": len(original_actions) > 0 and len(mutated_actions) == 0,
    }


def scan_hardcoded_business_values(result: dict) -> dict:
    """扫描输出中是否存在硬编码业务数值。"""
    issues = []
    conclusion = result.get("conclusion", "")
    import re
    numbers_in_conclusion = re.findall(r"\d+\.?\d*", conclusion)
    evidence_refs = result.get("evidence_refs", [])
    if numbers_in_conclusion and not evidence_refs:
        issues.append("conclusion 包含数值但 evidence_refs 为空，疑似硬编码")

    return {
        "clean": len(issues) == 0,
        "issues": issues,
    }

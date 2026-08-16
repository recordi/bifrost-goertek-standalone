"""
BIFROST 供应链专业诊断 Skill 独立验证器（v0.1.3）。

独立于 supply_risk_analyzer 代码，对 BIFROST_SPECIALIST_RESULT_v0.1.3 进行外部校验。
不引用分析器内部函数，只检查合同规范与供应链专业约束。

本验证器组合两层校验：
1. 共享合同验证器 specialist_contract_validator.py（结构 + 统一语义门控）
2. 供应链专业约束（缺口与冻结分离、缺料非OEE直接原因、源码固定值扫描、变异测试、
   到货语义修复检查、加急门控检查、identifier_scope 检查）
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED_VALIDATOR = os.path.join(HERE, "specialist_contract_validator.py")

# 正式代码中禁止出现的样本固定值（仅扫描运行时脚本，不扫夹具）
FORBIDDEN_FIXED_TOKENS = [
    "MAT-001", "MAT-002",
    "PO-2026-0001",
    "6666", "6573", "93",
]

# 旧错误表述（静态扫描零命中）
FORBIDDEN_PHRASES = [
    "整单未逾期",
    "整单按期完成",
    "整单按期",
]


def _load_shared_validator():
    """动态加载共享合同验证器。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("specialist_contract_validator", SHARED_VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validate_specialist_result_external(result: dict) -> dict:
    """外部验证 BIFROST_SPECIALIST_RESULT_v0.1.3 合同。"""
    vr = {"valid": True, "errors": [], "warnings": [], "checks": {}}

    # ---- 第 1 层：共享合同验证器（结构 + 统一语义门控） ----
    shared = _load_shared_validator()
    schema_path = os.path.join(HERE, "..", "schema", "BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json")
    schema = None
    if os.path.exists(schema_path):
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    ok, errs = shared.validate_output(result, schema)
    vr["checks"]["shared_contract_validation"] = ok
    if not ok:
        vr["errors"].extend(errs)
        vr["valid"] = False

    # ---- 第 2 层：供应链专业约束 ----

    # 缺口与冻结原因不得合并为同一 category
    vr["checks"]["shortage_freeze_separated"] = True
    for c in result.get("causes", []):
        cat = c.get("category") or c.get("cause_type") or ""
        if cat == "merged_shortage_freeze":
            vr["errors"].append("缺口与冻结被合并为同一原因")
            vr["checks"]["shortage_freeze_separated"] = False
            vr["valid"] = False

    # 缺料不得表述为 OEE 直接原因
    for c in result.get("causes", []):
        cat = c.get("category") or c.get("cause_type") or ""
        stmt = c.get("statement") or c.get("description") or ""
        if cat == "material_shortage" and "OEE" in stmt and "非" not in stmt and "不是" not in stmt:
            vr["errors"].append("缺料被表述为 OEE 直接原因")
            vr["valid"] = False

    # v0.1.3: 部分到货不得出现"整单未逾期"/"整单按期完成"表述
    for c in result.get("causes", []):
        cat = c.get("category") or ""
        stmt = c.get("statement") or ""
        if cat == "partial_delivery_shortfall":
            for phrase in FORBIDDEN_PHRASES:
                if phrase in stmt:
                    vr["errors"].append(f"部分到货原因含旧错误表述 '{phrase}': {stmt}")
                    vr["valid"] = False

    # v0.1.3: action_identifier_scope 必须在 specialist_details 中登记为 local_run_only
    sd = result.get("specialist_details", {})
    if sd.get("action_identifier_scope") != "local_run_only":
        if result.get("recommended_actions"):
            vr["errors"].append("有推荐动作但 specialist_details 未登记 action_identifier_scope=local_run_only")
            vr["valid"] = False

    # v0.1.3: 不得生成 ConfirmationID
    for a in result.get("recommended_actions", []):
        if a.get("confirmation_id"):
            vr["errors"].append(f"不得生成 ConfirmationID: {a.get('action_id')}")
            vr["valid"] = False

    # v0.1.3: 高风险动作必须 prohibited_auto_execute=true
    for a in result.get("recommended_actions", []):
        if a.get("is_high_risk") is True:
            if a.get("prohibited_auto_execute") is not True:
                vr["errors"].append(f"高风险动作未禁止自动执行: {a.get('action_id')}")
                vr["valid"] = False

    return vr


def scan_source_for_fixed_values(script_dir: str) -> dict:
    """扫描运行时脚本源码，禁止硬编码样本固定值。"""
    vr = {"valid": True, "hits": [], "scanned": []}
    for root, dirs, files in os.walk(script_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(root, fn)
            with open(fp, "r", encoding="utf-8") as f:
                txt = f.read()
            vr["scanned"].append(fp)
            for tok in FORBIDDEN_FIXED_TOKENS:
                for i, line in enumerate(txt.splitlines(), 1):
                    stripped = line.lstrip()
                    if stripped.startswith("#"):
                        continue
                    if tok in line:
                        vr["hits"].append({"file": fp, "line": i, "token": tok, "line_text": line.strip()})
                        vr["valid"] = False
    return vr


def scan_source_for_old_phrases(script_dir: str) -> dict:
    """扫描运行时脚本源码，旧错误表述零命中。"""
    vr = {"valid": True, "hits": [], "scanned": []}
    for root, dirs, files in os.walk(script_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(root, fn)
            with open(fp, "r", encoding="utf-8") as f:
                txt = f.read()
            vr["scanned"].append(fp)
            for phrase in FORBIDDEN_PHRASES:
                for i, line in enumerate(txt.splitlines(), 1):
                    stripped = line.lstrip()
                    if stripped.startswith("#"):
                        continue
                    if phrase in line:
                        vr["hits"].append({"file": fp, "line": i, "phrase": phrase, "line_text": line.strip()})
                        vr["valid"] = False
    return vr


def mutation_test_delete_shortage_and_verify(analyzer_module, fixture_path: str) -> dict:
    """变异测试：删除缺口事实后，相关原因与动作应消失。"""
    with open(fixture_path, "r", encoding="utf-8") as f:
        di = json.load(f)
    base_result = analyzer_module.orchestrate_supply_analysis(di)

    mutated = json.loads(json.dumps(di))
    mutated["normalized_facts"] = [
        f for f in mutated["normalized_facts"]
        if "material_shortage" not in f.get("semantic_record_key", "")
    ]
    mutated_result = analyzer_module.orchestrate_supply_analysis(mutated)

    vr = {"valid": True, "errors": []}
    base_shortage_causes = [c for c in base_result.get("causes", []) if (c.get("category") or c.get("cause_type")) == "material_shortage"]
    mut_shortage_causes = [c for c in mutated_result.get("causes", []) if (c.get("category") or c.get("cause_type")) == "material_shortage"]
    base_exp_actions = [a for a in base_result.get("recommended_actions", []) if "加急采购" in (a.get("action") or "") or "替代料" in (a.get("action") or "")]
    mut_exp_actions = [a for a in mutated_result.get("recommended_actions", []) if "加急采购" in (a.get("action") or "") or "替代料" in (a.get("action") or "")]

    if base_shortage_causes and not mut_shortage_causes and base_exp_actions and not mut_exp_actions:
        vr["valid"] = True
    elif not base_shortage_causes:
        vr["errors"].append("基线夹具本身无缺口原因，变异测试无效")
        vr["valid"] = False
    else:
        vr["errors"].append(
            f"删除缺口后原因/动作未同步消失: base_causes={len(base_shortage_causes)} mut_causes={len(mut_shortage_causes)} base_actions={len(base_exp_actions)} mut_actions={len(mut_exp_actions)}"
        )
        vr["valid"] = False
    return vr


def mutation_test_delete_qty_evref_and_verify(analyzer_module, fixture_path: str) -> dict:
    """变异测试：删除任一数量 EVREF 后不得生成高风险草稿。

    从夹具中删除 purchase_qty 或 arrived_qty 的 provenance_ref.evidence_locator，
    验证不会生成高风险加急动作。
    """
    with open(fixture_path, "r", encoding="utf-8") as f:
        di = json.load(f)
    base_result = analyzer_module.orchestrate_supply_analysis(di)

    # 需要基线有高风险动作
    base_high_risk = [a for a in base_result.get("recommended_actions", []) if a.get("is_high_risk")]
    if not base_high_risk:
        return {"valid": False, "errors": ["基线夹具无高风险动作，变异测试无效"]}

    results = {"valid": True, "errors": [], "sub_tests": []}

    for qty_field in ("purchase_qty", "arrived_qty", "shortage_qty"):
        mutated = json.loads(json.dumps(di))
        deleted = False
        for fact in mutated["normalized_facts"]:
            if fact.get("semantic_field") == qty_field:
                fact["provenance_ref"] = {}
                deleted = True
                break
        if not deleted:
            continue
        mut_result = analyzer_module.orchestrate_supply_analysis(mutated)
        mut_high_risk = [a for a in mut_result.get("recommended_actions", []) if a.get("is_high_risk")]
        sub = {"deleted_field": qty_field, "base_high_risk_count": len(base_high_risk), "mut_high_risk_count": len(mut_high_risk)}
        results["sub_tests"].append(sub)
        if mut_high_risk:
            results["valid"] = False
            results["errors"].append(f"删除 {qty_field} EVREF 后仍生成高风险草稿: {len(mut_high_risk)} 条")

    return results

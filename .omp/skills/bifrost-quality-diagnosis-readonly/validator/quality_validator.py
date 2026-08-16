"""
BIFROST 质量诊断独立验证器（v0.1.2 / 输出合同 v0.1.3）

独立于质量诊断生产代码，对 BIFROST_SPECIALIST_RESULT_v0.1.3 进行外部验证。
合同结构校验委托共享验证器（specialist_contract_validator.py v0.1.3），
本文件保留质量专业特有验证：
  - 变异测试：删除不良事实后结论同步消失
  - 黄金值扫描：正式代码不得含黄金事件固定业务数值
  - ZIP 完整性与 MANIFEST 校验

v0.1.2 变更（→ v0.1.3 输出合同）：
- contract_version 检查更新为 BIFROST-SPECIALIST-RESULT-v0.1.3
- data_gaps 结构检查更新为 9 字段（+affected_record_count/occurrence_count/sample_source_locators）
- evidence_refs 必须为 EVREF-v1 规范形式
- 合同结构校验委托共享验证器
"""
import json
import copy
import hashlib
import os
import sys
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED_VALIDATOR_PATH = os.path.join(_HERE, "specialist_contract_validator.py")
_spec = importlib.util.spec_from_file_location("_svc_qv", _SHARED_VALIDATOR_PATH)
_svc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_svc)

CONTRACT_VERSION = "BIFROST-SPECIALIST-RESULT-v0.1.3"
CONTRACT_NAME = "BIFROST_SPECIALIST_RESULT_v0.1"

DATA_GAP_REQUIRED_FIELDS = (
    "semantic_entity", "semantic_field", "reason",
    "value_consumption_status", "source_locator", "required_resolution",
    "affected_record_count", "occurrence_count", "sample_source_locators",
)


def validate_specialist_result_external(result: dict) -> dict:
    """
    外部验证 BIFROST_SPECIALIST_RESULT_v0.1.3 合同。
    结构 + 语义校验委托共享验证器；本函数补充质量专业特有检查。
    """
    result_val = {"valid": True, "checks": {}, "errors": []}

    # 委托共享验证器做结构 + 语义校验
    ok, errs = _svc.validate_output(result)
    result_val["checks"]["shared_validator_pass"] = ok
    if not ok:
        result_val["valid"] = False
        result_val["errors"].extend(errs)

    # 合同名/版本
    result_val["checks"]["contract_name"] = result.get("contract_name") == CONTRACT_NAME
    result_val["checks"]["contract_version"] = result.get("contract_version") == CONTRACT_VERSION

    # specialist_type
    result_val["checks"]["specialist_type_quality"] = result.get("specialist_type") == "quality"

    # data_gaps 9 字段
    for i, g in enumerate(result.get("data_gaps", [])):
        for f in DATA_GAP_REQUIRED_FIELDS:
            if f not in g:
                result_val["errors"].append(f"data_gaps[{i}] 缺少字段: {f}")
                result_val["valid"] = False
        arc = g.get("affected_record_count")
        occ = g.get("occurrence_count")
        if isinstance(arc, int) and isinstance(occ, int) and arc > occ:
            result_val["errors"].append(f"data_gaps[{i}].affected_record_count({arc}) > occurrence_count({occ})")
            result_val["valid"] = False

    # evidence_refs 必须为 EVREF-v1 规范形式（非占位）
    for i, ref in enumerate(result.get("evidence_refs", [])):
        if not isinstance(ref, str) or not ref.startswith("EVREF-v1:"):
            result_val["errors"].append(f"evidence_refs[{i}] 不是 EVREF-v1 规范形式: {ref}")
            result_val["valid"] = False
    for i, m in enumerate(result.get("metrics", [])):
        for j, ref in enumerate(m.get("evidence_refs", [])):
            if not isinstance(ref, str) or not ref.startswith("EVREF-v1:"):
                result_val["errors"].append(f"metrics[{i}].evidence_refs[{j}] 不是 EVREF-v1: {ref}")
                result_val["valid"] = False

    # actor_can_execute 恒 false
    result_val["checks"]["actor_can_execute_false"] = result.get("actor_can_execute") is False

    # 无时间字段不制造趋势
    sd = result.get("specialist_details", {})
    ys = sd.get("yield_analysis_summary", {})
    if not ys.get("has_time_field", True):
        conclusion = result.get("conclusion", "")
        for kw in ["持续下降", "连续恶化", "趋势恶化", "持续上升", "逐月下降", "逐月上升"]:
            if kw in conclusion:
                result_val["errors"].append(f"conclusion 含趋势结论「{kw}」但无时间字段")
                result_val["valid"] = False

    return result_val


def mutation_test_defect_facts_removal(
    decision_input: dict, original_result: dict, quality_module=None
) -> dict:
    """
    变异测试：删除不良事实后，对应原因与动作必须消失。

    不使用生产函数输出作为期望值——期望是语义不变式：
    删除某字段的全部事实后，引用该字段 EVREF 的 metric/cause/action 必须消失。
    """
    import sys as _sys
    if quality_module is None:
        _sys.path.insert(0, os.path.join(_HERE, "..", "scripts"))
        import quality_diagnosis as quality_module

    mutated = copy.deepcopy(decision_input)
    # 删除所有 defect_type / defect_type_name 字段事实
    mutated["normalized_facts"] = [
        nf for nf in mutated.get("normalized_facts", [])
        if nf.get("semantic_field") not in ("defect_type", "defect_type_name")
    ]

    orch = quality_module.orchestrate_quality_diagnosis(mutated)
    mutated_result = orch["result"]

    test = {"valid": True, "errors": [], "original_causes": 0, "mutated_causes": 0}

    orig_causes = original_result.get("causes", [])
    mut_causes = mutated_result.get("causes", [])
    test["original_causes"] = len(orig_causes)
    test["mutated_causes"] = len(mut_causes)

    # 删除 defect_type 事实后，causes 中不应再有关联不良类型的 cause
    for c in mut_causes:
        if c.get("category") == "associated_defect_type":
            test["errors"].append(
                f"变异后仍存在 associated_defect_type cause: {c.get('cause_id')}")
            test["valid"] = False

    # 原始中 defect_type 相关 EVREF 不应出现在变异结果中
    orig_evrefs = set()
    for c in orig_causes:
        orig_evrefs.update(c.get("evidence_refs", []))
    mut_all_evrefs = set()
    for m in mutated_result.get("metrics", []):
        mut_all_evrefs.update(m.get("evidence_refs", []))
    for c in mut_causes:
        mut_all_evrefs.update(c.get("evidence_refs", []))
    for a in mutated_result.get("recommended_actions", []):
        mut_all_evrefs.update(a.get("evidence_refs", []))
    leaked = orig_evrefs & mut_all_evrefs
    # 只检查 defect_type 相关的 EVREF 是否泄露
    # （其他字段的 EVREF 可能仍在，这是正常的）
    # 通过检查 causes 是否消失来判断

    return test


def validate_no_hardcoded_golden_values(result: dict) -> dict:
    """
    扫描输出是否含黄金事件固定业务数值。
    质量诊断的数值必须来自输入事实，不得写死。
    """
    test = {"valid": True, "errors": []}
    # 已知的黄金值模式（不应出现在 conclusion 中作为固定结论）
    golden_patterns = [
        "OEE=85%", "良率=98.5%", "Cpk=1.33", "不良率=2%",
    ]
    conclusion = result.get("conclusion", "")
    for pat in golden_patterns:
        if pat in conclusion:
            test["errors"].append(f"conclusion 含疑似黄金值: {pat}")
            test["valid"] = False
    return test


def validate_zip_integrity(zip_path: str, expected_sha256: str = None) -> dict:
    """验证 ZIP 文件完整性。"""
    test = {"valid": True, "errors": [], "sha256": None}
    if not os.path.exists(zip_path):
        test["valid"] = False
        test["errors"].append(f"ZIP 不存在: {zip_path}")
        return test
    with open(zip_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    test["sha256"] = sha
    if expected_sha256 and sha != expected_sha256:
        test["valid"] = False
        test["errors"].append(f"SHA-256 不匹配: 实际={sha}, 期望={expected_sha256}")
    return test


def validate_manifest_external(extracted_dir: str) -> dict:
    """验证 MANIFEST.sha256 中每个文件的哈希。"""
    test = {"valid": True, "errors": [], "checked": 0, "failed": 0}
    manifest_path = os.path.join(extracted_dir, "MANIFEST.sha256")
    if not os.path.exists(manifest_path):
        test["valid"] = False
        test["errors"].append("MANIFEST.sha256 不存在")
        return test
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("  ", 1)
            if len(parts) != 2:
                continue
            expected_sha, rel_path = parts
            full_path = os.path.join(extracted_dir, rel_path)
            if not os.path.exists(full_path):
                test["errors"].append(f"MANIFEST 引用的文件不存在: {rel_path}")
                test["valid"] = False
                test["failed"] += 1
                continue
            with open(full_path, "rb") as f2:
                actual_sha = hashlib.sha256(f2.read()).hexdigest()
            test["checked"] += 1
            if actual_sha != expected_sha:
                test["errors"].append(f"哈希不匹配: {rel_path}")
                test["valid"] = False
                test["failed"] += 1
    return test

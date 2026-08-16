"""
BIFROST 消费者适配器独立验证器

独立于消费者适配器代码，对决策输入合同进行外部验证。
不引用消费者内部函数，只检查合同规范。
"""

import json
import hashlib


def validate_decision_input_external(decision_input: dict) -> dict:
    """
    外部验证 BIFROST_DECISION_INPUT_v0.1 合同。

    检查项：
    1. 必需字段存在
    2. 禁止字段不存在
    3. read_only=true
    4. source_write_performed=false
    5. actor_can_execute=false
    6. normalized_facts 只含 decision_usable 字段
    7. normalized_facts 不含 raw_value 作为业务值
    8. 每个 fact 有 provenance_ref
    9. data_gaps 结构完整
    10. 无业务结论字段
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "checks": {},
    }

    # 1. 必需字段
    required = [
        "contract_name", "contract_version", "request_id", "consumer_agent_id",
        "role", "query_context", "source_release_id", "source_snapshot_id",
        "normalized_facts", "data_gaps", "provenance_refs", "contract_versions",
        "validation", "source_write_performed", "actor_can_execute",
    ]
    missing = [f for f in required if f not in decision_input]
    result["checks"]["required_fields"] = len(missing) == 0
    if missing:
        result["errors"].append(f"缺少必需字段: {missing}")
        result["valid"] = False

    # 2. 禁止字段
    forbidden = [
        "conclusion", "root_cause", "recommended_actions",
        "confirmation_draft", "auto_execute_command",
    ]
    present_forbidden = [f for f in forbidden if f in decision_input]
    result["checks"]["no_forbidden_fields"] = len(present_forbidden) == 0
    if present_forbidden:
        result["errors"].append(f"包含禁止字段: {present_forbidden}")
        result["valid"] = False

    # 3. read_only
    qc = decision_input.get("query_context", {})
    result["checks"]["read_only_true"] = qc.get("read_only") is True
    if qc.get("read_only") is not True:
        result["errors"].append("query_context.read_only 必须为 true")
        result["valid"] = False

    # 4. source_write_performed
    result["checks"]["source_write_false"] = decision_input.get("source_write_performed") is False
    if decision_input.get("source_write_performed") is not False:
        result["errors"].append("source_write_performed 必须为 false")
        result["valid"] = False

    # 5. actor_can_execute
    result["checks"]["actor_can_execute_false"] = decision_input.get("actor_can_execute") is False
    if decision_input.get("actor_can_execute") is not False:
        result["errors"].append("actor_can_execute 必须为 false")
        result["valid"] = False

    # 6. normalized_facts 中不含 decision_usable=false 的字段
    facts = decision_input.get("normalized_facts", [])
    # 在消费者输出中，decision_usable 不在 fact 中（已被门控过滤），
    # 但我们检查是否有 null 值被当作事实返回
    null_facts = [f for f in facts if f.get("normalized_value") is None]
    result["checks"]["no_null_facts"] = len(null_facts) == 0
    if null_facts:
        result["errors"].append(
            f"normalized_facts 中有 {len(null_facts)} 条 null 值被当作事实返回"
        )
        result["valid"] = False

    # 7. 检查 raw_value 不在 fact 顶层（只能在 provenance_ref 中）
    raw_at_top = [f for f in facts if "raw_value" in f and "raw_value" not in f.get("provenance_ref", {})]
    result["checks"]["raw_value_not_at_top"] = len(raw_at_top) == 0
    if raw_at_top:
        result["errors"].append(
            f"normalized_facts 中有 {len(raw_at_top)} 条 raw_value 出现在顶层（应只在 provenance_ref 中）"
        )
        result["valid"] = False

    # 8. 每个 fact 有 provenance_ref
    no_prov = [f for f in facts if "provenance_ref" not in f]
    result["checks"]["all_facts_have_provenance"] = len(no_prov) == 0
    if no_prov:
        result["warnings"].append(
            f"normalized_facts 中有 {len(no_prov)} 条缺少 provenance_ref"
        )

    # 04C.5C.1：raw_value 溯源真实性
    raw_prov_bad = []
    for f in facts:
        prov = f.get("provenance_ref", {})
        rv = prov.get("raw_value")
        nv = f.get("normalized_value")
        su = prov.get("source_unit", "")
        nu = f.get("normalized_unit", "")
        # raw_value_status 缺失也视为不合规
        if "raw_value_status" not in prov:
            raw_prov_bad.append(
                f"{f.get('semantic_field','?')}: provenance_ref 缺少 raw_value_status"
            )
            continue
        if prov.get("raw_value_status") == "available":
            # 存在单位转换时 raw_value 不得等于 normalized_value
            if su and nu and su != nu and rv == nv:
                raw_prov_bad.append(
                    f"{f.get('semantic_field','?')}: raw_value 复制了 normalized_value（单位不同但值相同）"
                )
        else:
            # not_available 时 raw_value 必须为 null
            if rv is not None:
                raw_prov_bad.append(
                    f"{f.get('semantic_field','?')}: raw_value_status=not_available 但 raw_value 非 null"
                )
    result["checks"]["raw_provenance_authentic"] = len(raw_prov_bad) == 0
    if raw_prov_bad:
        result["errors"].append(f"raw_value 溯源不真实: {raw_prov_bad}")
        result["valid"] = False

    # 9. data_gaps 结构
    gaps = decision_input.get("data_gaps", [])
    gap_required = ["semantic_entity", "semantic_field", "reason", "value_consumption_status"]
    bad_gaps = []
    for i, gap in enumerate(gaps):
        missing_in_gap = [f for f in gap_required if f not in gap]
        if missing_in_gap:
            bad_gaps.append({"index": i, "missing": missing_in_gap})
    result["checks"]["data_gaps_valid"] = len(bad_gaps) == 0
    if bad_gaps:
        result["errors"].append(f"data_gaps 结构不完整: {bad_gaps}")
        result["valid"] = False

    # 10. 无业务结论
    conclusion_indicators = ["conclusion", "root_cause", "severity", "confidence",
                             "recommended_actions", "confirmation_draft"]
    found_conclusions = [ind for ind in conclusion_indicators if ind in decision_input]
    result["checks"]["no_business_conclusions"] = len(found_conclusions) == 0
    if found_conclusions:
        result["errors"].append(f"输出包含业务结论字段: {found_conclusions}")
        result["valid"] = False

    return result


def validate_zip_integrity(zip_path: str, expected_sha256: str = None) -> dict:
    """
    验证 ZIP 文件 SHA-256 完整性。
    """
    import os
    result = {
        "valid": False,
        "errors": [],
        "actual_sha256": None,
    }

    if not os.path.exists(zip_path):
        result["errors"].append(f"ZIP文件不存在: {zip_path}")
        return result

    with open(zip_path, "rb") as f:
        data = f.read()
    actual = hashlib.sha256(data).hexdigest()
    result["actual_sha256"] = actual

    if expected_sha256 and actual != expected_sha256:
        result["errors"].append(
            f"ZIP SHA-256不匹配: 期望={expected_sha256}, 实际={actual}"
        )
        return result

    result["valid"] = True
    return result


def validate_manifest_external(extracted_dir: str) -> dict:
    """
    04C.5C.1：独立验证器——独立解析 MANIFEST.sha256，不复用生产 verify_manifest。
    对 MANIFEST 中除自身外的每条记录校验路径、存在性、SHA-256、无重复、无缺失/多余/不匹配。
    同时与 CONTENTS.json 双向核对。
    """
    import os
    manifest_path = os.path.join(extracted_dir, "MANIFEST.sha256")

    result = {
        "valid": True,
        "errors": [],
        "total": 0,
        "verified": 0,
        "mismatches": [],
        "extra_files": [],
        "missing_files": [],
        "duplicate_paths": [],
        "contents_manifest_consistent": False,
    }

    if not os.path.exists(manifest_path):
        result["errors"].append("MANIFEST.sha256 不存在")
        result["valid"] = False
        return result

    # 独立解析 MANIFEST.sha256（不调用生产 _parse_manifest_sha256）
    with open(manifest_path, "r", encoding="utf-8") as f:
        raw = f.read()

    manifest_entries: dict = {}
    parsed_json = False
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for path, sha in parsed.items():
                manifest_entries[path] = str(sha)
            parsed_json = True
    except (json.JSONDecodeError, ValueError):
        pass

    if not parsed_json:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if len(line) > 66 and line[:64].isalnum():
                sha = line[:64]
                path = line[66:].strip() if line[64:66].isspace() else line[65:].strip()
                manifest_entries[path] = sha
            else:
                result["errors"].append(f"无法解析 MANIFEST.sha256 行: {line[:40]}")
                result["valid"] = False
                return result

    # 重复路径检测
    seen: set = set()
    for path in manifest_entries:
        if path in seen:
            result["duplicate_paths"].append(path)
            result["errors"].append(f"MANIFEST 重复路径: {path}")
        seen.add(path)

    if "MANIFEST.sha256" in manifest_entries:
        result["errors"].append("MANIFEST.sha256 不应登记自身")
        result["valid"] = False

    result["total"] = len(manifest_entries)

    for path, expected in manifest_entries.items():
        full_path = os.path.join(extracted_dir, path)
        if not os.path.exists(full_path):
            result["missing_files"].append(path)
            result["errors"].append(f"缺失文件: {path}")
            result["valid"] = False
            continue
        with open(full_path, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        if actual != expected:
            result["mismatches"].append({"path": path, "expected": expected, "actual": actual})
            result["errors"].append(f"哈希不匹配: {path}")
            result["valid"] = False
        else:
            result["verified"] += 1

    # 与 CONTENTS.json 双向核对
    contents_path = os.path.join(extracted_dir, "CONTENTS.json")
    if os.path.exists(contents_path):
        with open(contents_path, "r", encoding="utf-8") as f:
            contents = json.load(f)
        contents_paths = {e["path"] for e in contents.get("files", [])}
        manifest_paths = set(manifest_entries.keys())
        only_contents = contents_paths - manifest_paths
        only_manifest = manifest_paths - contents_paths
        if only_contents:
            result["extra_files"].extend(sorted(only_contents))
            result["errors"].append(f"CONTENTS 有但 MANIFEST 无: {sorted(only_contents)}")
            result["valid"] = False
        if only_manifest:
            result["missing_files"].extend(sorted(only_manifest))
            result["errors"].append(f"MANIFEST 有但 CONTENTS 无: {sorted(only_manifest)}")
            result["valid"] = False
        result["contents_manifest_consistent"] = (
            len(only_contents) == 0 and len(only_manifest) == 0
        )
    else:
        result["errors"].append("CONTENTS.json 不存在，无法双向核对")
        result["valid"] = False

    return result

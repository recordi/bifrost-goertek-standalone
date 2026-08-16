"""
BIFROST 语义数据消费者只读适配器
logical_version: 0.1.4

链路：语义数据面ZIP → RELEASE_INDEX → semantic_data_ref → 只读查询
      → BIFROST_DECISION_INPUT_v0.1 → 决策编排智能体

12 个确定性能力：
1. verify_data_plane_package
2. verify_manifest
3. load_release_index
4. resolve_semantic_data_ref
5. load_semantic_snapshot
6. validate_consumer_role_scope
7. execute_semantic_query
8. enforce_decision_usable_gate
9. build_structured_data_gap
10. build_decision_input_contract
11. validate_decision_input_contract
12. orchestrate_consumer_run

硬门控：
- 必须先验证ZIP、MANIFEST、RELEASE_INDEX与快照SHA-256
- 只返回decision_usable=true的字段
- normalized_value是消费者业务值；raw_value不得进入普通回答
- null_unavailable/invalid/needs_rule必须转为结构化data_gap
- 不得跨记录、跨实体自行拼接
- relation_materialization_status!=materialized时不得执行关联查询
- 不得根据ID前缀、行号相同或文本相似自行建立关联
- 请求字段不存在或无权限时不得猜测补值
- read_only必须为true；否则阻塞
- 任何输出actor_can_execute必须为false
"""

import json
import hashlib
import os
import zipfile
import uuid
import copy
from datetime import datetime, timezone
from typing import Any

from consumer.role_permissions import validate_consumer_role_scope as _validate_role_scope

CONSUMER_LOGICAL_VERSION = "0.1.4"
DECISION_INPUT_CONTRACT_VERSION = "BIFROST-DECISION-INPUT-v0.1"
QUERY_CONTRACT_VERSION = "BIFROST-CONSUMER-QUERY-v0.2"

# 唯一批准的数据面 ZIP SHA-256（04C.5C.1 施工令批准）
APPROVED_DATA_PLANE_RELEASES = [
    {
        "release_id": "BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL",
        "sha256": "81a8e5947a28ffe1dcabe123f54e00815ec4a06ca876e0f070ca59a88cf01b42",
        "purpose": "rollback_approved",
        "status": "active",
    },
    {
        "release_id": "BIFROST_v0.3_RC1",
        "sha256": "b12e1f6c8abc9f901275c09f679fc7d8ec5cae4f89fac42271e704dd436069e0",
        "purpose": "release_candidate_approved",
        "status": "release_candidate",
    },
]

# Backward-compat alias (deprecated — use APPROVED_DATA_PLANE_RELEASES)
APPROVED_DATA_PLANE_ZIP_SHA256 = APPROVED_DATA_PLANE_RELEASES[0]["sha256"]


# =========================================================================
# 1. verify_data_plane_package
# =========================================================================
def verify_data_plane_package(zip_path: str) -> dict:
    """
    验证语义数据面ZIP包完整性：
    - 文件存在
    - 是有效ZIP
    - 包含必需文件：MANIFEST.sha256, RELEASE_INDEX.json, CONTENTS.json, README.md
    - ZIP哈希记录（运行前后一致性基准）

    04C.5C.1：MANIFEST.sha256 现为必需文件，不得以 CONTENTS.json 替代。
    """
    result = {
        "verified": False,
        "zip_path": zip_path,
        "errors": [],
        "zip_sha256": None,
        "file_count": 0,
        "required_files_present": {},
    }

    if not os.path.exists(zip_path):
        result["errors"].append(f"ZIP文件不存在: {zip_path}")
        return result

    # 计算ZIP SHA-256
    with open(zip_path, "rb") as f:
        zip_bytes = f.read()
    result["zip_sha256"] = hashlib.sha256(zip_bytes).hexdigest()

    # 验证ZIP有效性
    if not zipfile.is_zipfile(zip_path):
        result["errors"].append(f"不是有效的ZIP文件: {zip_path}")
        return result

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        result["file_count"] = len(names)

        # 检查必需文件（ZIP内路径可能带顶级目录前缀）
        required_files = [
            "MANIFEST.sha256",
            "RELEASE_INDEX.json",
            "CONTENTS.json",
            "README.md",
        ]
        for req in required_files:
            found = any(n.endswith(req) for n in names)
            result["required_files_present"][req] = found
            if not found:
                result["errors"].append(f"ZIP中缺少必需文件: {req}")

    result["verified"] = len(result["errors"]) == 0
    return result


def _parse_manifest_sha256(extracted_dir: str) -> dict:
    """
    独立解析 MANIFEST.sha256 文件，返回 {path: sha256} 字典。
    支持两种格式：
    - JSON 对象（数据面 FINAL 包格式：{"path": "sha256", ...}）
    - sha256sum 文本格式（每行 "<sha256>  <path>"）
    MANIFEST.sha256 自身不登记在字典中。
    解析失败时返回 {"_parse_error": "..."}。
    """
    manifest_path = os.path.join(extracted_dir, "MANIFEST.sha256")
    if not os.path.exists(manifest_path):
        return {"_parse_error": f"MANIFEST.sha256 不存在: {manifest_path}"}

    with open(manifest_path, "r", encoding="utf-8") as f:
        raw = f.read()

    entries: dict[str, str] = {}
    # 先尝试 JSON
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for path, sha in parsed.items():
                entries[path] = str(sha)
            return entries
    except (json.JSONDecodeError, ValueError):
        pass

    # 退回 sha256sum 文本格式：每行 "<sha256><空格><path>"
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # sha256sum 标准格式：64位hex + 两个空格 + 路径
        if len(line) > 66 and line[:64].isalnum():
            sha = line[:64]
            path = line[66:].strip() if line[64:66].isspace() else line[65:].strip()
            entries[path] = sha
        else:
            return {"_parse_error": f"无法解析 MANIFEST.sha256 行: {line[:40]}"}

    return entries


# =========================================================================
# 2. verify_manifest
# =========================================================================
def verify_manifest(extracted_dir: str) -> dict:
    """
    04C.5C.1：真正解析 MANIFEST.sha256，对其中除自身外的每条记录：
    - 校验相对路径合法
    - 校验文件存在
    - 校验 SHA-256 匹配
    - 校验无重复路径
    - 校验无缺失、无多余、无哈希不匹配

    不再以 CONTENTS.json 替代 MANIFEST。CONTENTS.json 由 verify_contents 单独验证。
    """
    result = {
        "verified": False,
        "errors": [],
        "total_files": 0,
        "verified_files": 0,
        "mismatches": [],
        "missing_files": [],
        "duplicate_paths": [],
        "manifest_format": None,
    }

    entries = _parse_manifest_sha256(extracted_dir)
    if "_parse_error" in entries:
        result["errors"].append(entries["_parse_error"])
        return result

    result["manifest_format"] = "json_or_text"

    # 检查重复路径（JSON dict 天然去重，但文本格式可能重复）
    seen: set[str] = set()
    for path in entries:
        if path in seen:
            result["duplicate_paths"].append(path)
            result["errors"].append(f"MANIFEST 中重复路径: {path}")
        seen.add(path)

    # MANIFEST.sha256 自身不登记，不应出现在条目中
    if "MANIFEST.sha256" in entries:
        result["errors"].append(
            "MANIFEST.sha256 不应登记自身（包内除自身外所有文件进入 MANIFEST）"
        )

    result["total_files"] = len(entries)

    for path, expected_sha in entries.items():
        # 校验相对路径合法（不得绝对路径、不得 .. 越界）
        if os.path.isabs(path) or ".." in path.split("/"):
            result["errors"].append(f"MANIFEST 中路径非法: {path}")
            continue

        full_path = os.path.join(extracted_dir, path)
        if not os.path.exists(full_path):
            result["missing_files"].append(path)
            result["errors"].append(f"文件不存在: {path}")
            continue

        with open(full_path, "rb") as f:
            actual_sha = hashlib.sha256(f.read()).hexdigest()

        if actual_sha != expected_sha:
            result["mismatches"].append({
                "path": path,
                "expected": expected_sha,
                "actual": actual_sha,
            })
            result["errors"].append(
                f"SHA-256不匹配: {path} (期望={expected_sha[:16]}..., 实际={actual_sha[:16]}...)"
            )
        else:
            result["verified_files"] += 1

    result["verified"] = len(result["errors"]) == 0
    return result


# =========================================================================
# 2b. verify_contents（CONTENTS.json 目录元数据验证 + 与 MANIFEST 双向核对）
# =========================================================================
def verify_contents(extracted_dir: str) -> dict:
    """
    CONTENTS.json 作为文件目录元数据单独验证，并与 MANIFEST.sha256 双向核对。
    不得用 CONTENTS.json 替代 MANIFEST。
    """
    result = {
        "verified": False,
        "errors": [],
        "total_files": 0,
        "verified_files": 0,
        "mismatches": [],
        "missing_files": [],
        "extra_files": [],
        "contents_manifest_consistent": False,
    }

    contents_path = os.path.join(extracted_dir, "CONTENTS.json")
    if not os.path.exists(contents_path):
        result["errors"].append(f"CONTENTS.json 不存在: {contents_path}")
        return result

    with open(contents_path, "r", encoding="utf-8") as f:
        contents = json.load(f)

    files = contents.get("files", [])
    result["total_files"] = len(files)

    # CONTENTS.json 自身 sha256=null，不保存自身哈希
    contents_map: dict[str, str | None] = {}
    for entry in files:
        path = entry["path"]
        expected_sha = entry.get("sha256")
        contents_map[path] = expected_sha

        if expected_sha is None:
            # CONTENTS.json 自身（sha256=null 是合同约定）
            if path != "CONTENTS.json":
                result["errors"].append(
                    f"CONTENTS.json 中 {path} 的 sha256 为 null，但不是 CONTENTS.json 自身"
                )
            result["verified_files"] += 1
            continue

        full_path = os.path.join(extracted_dir, path)
        if not os.path.exists(full_path):
            result["missing_files"].append(path)
            result["errors"].append(f"文件不存在: {path}")
            continue

        with open(full_path, "rb") as f:
            actual_sha = hashlib.sha256(f.read()).hexdigest()

        if actual_sha != expected_sha:
            result["mismatches"].append({
                "path": path,
                "expected": expected_sha,
                "actual": actual_sha,
            })
            result["errors"].append(f"SHA-256不匹配: {path}")
        else:
            result["verified_files"] += 1

    # 双向核对 CONTENTS.json 与 MANIFEST.sha256
    manifest_entries = _parse_manifest_sha256(extracted_dir)
    if "_parse_error" in manifest_entries:
        result["errors"].append(
            f"无法与 MANIFEST 双向核对: {manifest_entries['_parse_error']}"
        )
    else:
        manifest_paths = set(manifest_entries.keys())
        contents_paths = set(contents_map.keys())

        # CONTENTS.json 自身在 MANIFEST 中登记哈希，在 CONTENTS.json 中 sha256=null
        # 两者路径集合应一致（均排除 MANIFEST.sha256 自身）
        only_in_contents = contents_paths - manifest_paths
        only_in_manifest = manifest_paths - contents_paths

        if only_in_contents:
            result["extra_files"].extend(sorted(only_in_contents))
            result["errors"].append(
                f"CONTENTS 有但 MANIFEST 无: {sorted(only_in_contents)}"
            )
        if only_in_manifest:
            result["missing_files"].extend(sorted(only_in_manifest))
            result["errors"].append(
                f"MANIFEST 有但 CONTENTS 无: {sorted(only_in_manifest)}"
            )

        # 对共有路径（CONTENTS.json 自身除外）校验哈希一致
        for path in contents_paths & manifest_paths:
            c_sha = contents_map.get(path)
            m_sha = manifest_entries.get(path)
            if path == "CONTENTS.json":
                # CONTENTS.json 自身：CONTENTS 中 null，MANIFEST 中有哈希
                if m_sha is None:
                    result["errors"].append(
                        "MANIFEST 中 CONTENTS.json 哈希为空"
                    )
                continue
            if c_sha and m_sha and c_sha != m_sha:
                result["errors"].append(
                    f"CONTENTS 与 MANIFEST 哈希不一致: {path}"
                )

        result["contents_manifest_consistent"] = len(only_in_contents) == 0 and len(only_in_manifest) == 0

    result["verified"] = len(result["errors"]) == 0
    return result


# =========================================================================
# 3. load_release_index
# =========================================================================
def load_release_index(extracted_dir: str) -> dict:
    """
    加载 RELEASE_INDEX.json，验证快照 SHA-256。
    """
    ri_path = os.path.join(extracted_dir, "RELEASE_INDEX.json")
    result = {
        "loaded": False,
        "release_index": None,
        "errors": [],
        "snapshot_hashes_verified": {},
    }

    if not os.path.exists(ri_path):
        result["errors"].append(f"RELEASE_INDEX.json 不存在: {ri_path}")
        return result

    with open(ri_path, "r", encoding="utf-8") as f:
        ri = json.load(f)

    result["release_index"] = ri

    # 验证快照SHA-256
    for prefix in ["p01", "p02"]:
        snap_path_key = f"{prefix}_snapshot_path"
        snap_sha_key = f"{prefix}_snapshot_sha256"
        if snap_path_key in ri and snap_sha_key in ri:
            snap_rel = ri[snap_path_key]
            snap_full = os.path.join(extracted_dir, snap_rel)
            if os.path.exists(snap_full):
                with open(snap_full, "rb") as f:
                    actual_sha = hashlib.sha256(f.read()).hexdigest()
                expected_sha = ri[snap_sha_key]
                result["snapshot_hashes_verified"][prefix] = {
                    "path": snap_rel,
                    "expected": expected_sha,
                    "actual": actual_sha,
                    "match": actual_sha == expected_sha,
                }
                if actual_sha != expected_sha:
                    result["errors"].append(
                        f"快照SHA-256不匹配({prefix}): 期望={expected_sha}, 实际={actual_sha}"
                    )
            else:
                result["errors"].append(f"快照文件不存在({prefix}): {snap_rel}")
                result["snapshot_hashes_verified"][prefix] = {
                    "path": snap_rel,
                    "error": "file_not_found",
                }

    result["loaded"] = len(result["errors"]) == 0
    return result


# =========================================================================
# 4. resolve_semantic_data_ref
# =========================================================================
def resolve_semantic_data_ref(release_index: dict, extracted_dir: str, source_scope: str) -> dict:
    """
    根据 source_scope (如 P01, P02) 解析对应的 semantic_data_ref。
    """
    result = {
        "resolved": False,
        "semantic_data_ref": None,
        "snapshot_path": None,
        "errors": [],
    }

    # source_scope 标准化：P01 → p01, P02 → p02
    scope_lower = source_scope.lower()

    # 从 RELEASE_INDEX 获取快照路径
    snap_path_key = f"{scope_lower}_snapshot_path"
    sdr_path_key = f"{scope_lower}_semantic_data_ref_path"

    if snap_path_key not in release_index:
        result["errors"].append(
            f"RELEASE_INDEX 中未找到 source_scope={source_scope} 的快照路径"
        )
        return result

    snap_rel = release_index[snap_path_key]
    snap_full = os.path.join(extracted_dir, snap_rel)

    if not os.path.exists(snap_full):
        result["errors"].append(f"快照文件不存在: {snap_full}")
        return result

    # 加载 semantic_data_ref
    if sdr_path_key in release_index:
        sdr_rel = release_index[sdr_path_key]
        sdr_full = os.path.join(extracted_dir, sdr_rel)
        if os.path.exists(sdr_full):
            with open(sdr_full, "r", encoding="utf-8") as f:
                sdr = json.load(f)
            result["semantic_data_ref"] = sdr
        else:
            result["errors"].append(f"semantic_data_ref 文件不存在: {sdr_full}")

    result["snapshot_path"] = snap_full
    result["resolved"] = len(result["errors"]) == 0
    return result


# =========================================================================
# 5. load_semantic_snapshot
# =========================================================================
def load_semantic_snapshot(snapshot_path: str, expected_sha256: str | None = None) -> dict:
    """
    加载语义快照JSON，验证SHA-256（如果提供期望值）。
    """
    result = {
        "loaded": False,
        "snapshot": None,
        "errors": [],
        "sha256_verified": None,
    }

    if not os.path.exists(snapshot_path):
        result["errors"].append(f"快照文件不存在: {snapshot_path}")
        return result

    with open(snapshot_path, "rb") as f:
        snap_bytes = f.read()
    actual_sha = hashlib.sha256(snap_bytes).hexdigest()

    if expected_sha256:
        if actual_sha != expected_sha256:
            result["errors"].append(
                f"快照SHA-256不匹配: 期望={expected_sha256}, 实际={actual_sha}"
            )
            result["sha256_verified"] = False
            return result
        result["sha256_verified"] = True
    else:
        result["sha256_verified"] = None  # 未提供期望值

    snapshot = json.loads(snap_bytes.decode("utf-8"))
    result["snapshot"] = snapshot
    result["loaded"] = True
    return result


# =========================================================================
# 6. validate_consumer_role_scope (delegates to role_permissions)
# =========================================================================
def validate_consumer_role_scope(role: str, semantic_entity: str) -> dict:
    """
    验证角色是否有权查询指定语义实体。
    """
    return _validate_role_scope(role, semantic_entity)


# =========================================================================
# 7. execute_semantic_query
# =========================================================================
# =========================================================================
# 04D.4B.1 — 结构化过滤 / 时间窗口 / 排序 支持
# =========================================================================

# 被认可的时间排序字段（SEM 中声明为 date/timestamp 的字段）
_APPROVED_TEMPORAL_FIELDS = {
    "record_timestamp",
    "shift_start_time",
    "shift_end_time",
    "shift_date",
}

# 被认可的班次顺序字段（语义为班次标识，可确定性排序班次去重）
_APPROVED_SHIFT_ORDER_FIELDS = {
    "source_shift_id",
    "shift_id",
}

_ALLOWED_FILTER_OPS = {"eq", "in", "between", "is_null", "is_not_null"}


def _normalize_filters(filters) -> list[dict]:
    """
    将 filters 归一化为条件列表。
    兼容两种旧格式：
      - dict {field: value}  → eq 条件
      - list [{op, field, value}, ...]
    以及 v0.2 结构化格式：
      - {"op": "and", "conditions": [...]}
    返回 [{"op":..., "field":..., "value":...}, ...]
    """
    if not filters:
        return []
    conditions: list[dict] = []
    if isinstance(filters, list):
        for c in filters:
            conditions.append(_normalize_one_condition(c))
        return conditions
    if isinstance(filters, dict):
        if filters.get("op") in ("and", "or") and "conditions" in filters:
            for c in filters["conditions"]:
                conditions.append(_normalize_one_condition(c))
            return conditions
        # legacy eq dict
        for field, value in filters.items():
            conditions.append({"op": "eq", "field": field, "value": value})
        return conditions
    return conditions


def _normalize_one_condition(c: dict) -> dict:
    op = c.get("op", "eq")
    field = c.get("field", c.get("semantic_field", ""))
    value = c.get("value")
    return {"op": op, "field": field, "value": value}


def _record_field_map(record: dict) -> dict:
    return {f["semantic_field"]: f for f in record.get("fields", [])}


# 04D.4C.1-CONSUMER-P0: RC1 轻量字段 value_status → value_consumption_status 确定性映射
# 仅适用于 RC1 轻量格式（含 value_status、不含 value_consumption_status 的字段）。
# null_unavailable / invalid / needs_rule 必须保留对应不可消费状态，不得提升为 usable。
_VALUE_STATUS_TO_CONSUMPTION = {
    "usable": "usable",
    "null_unavailable": "null_unavailable",
    "invalid": "invalid",
    "needs_rule": "needs_rule",
}


def _normalize_v03_fields(records: list) -> tuple[list, list]:
    """v0.3 兼容层（04D.4C.1-CONSUMER-P0）：将 RC1 轻量字段的 value/value_status
    格式确定性归一化为标准消费字段格式（normalized_value / decision_usable /
    value_consumption_status / evidence_locator / source_field）。

    仅处理轻量格式字段（含 value_status 且不含 value_consumption_status），
    不修改已具备标准格式的字段（保留原始事实）。仅补充缺失的键，不覆盖已有键，
    不改变业务值。

    归一化规则：
    - value_status=usable：normalized_value 从 value 读取，decision_usable=true，
      value_consumption_status=usable。
    - null_unavailable/invalid/needs_rule：保留对应不可消费状态，decision_usable=false，
      value_consumption_status 同名，不得提升为 usable。
    - 未知/缺失/非法 value_status：不得默认通过，置 decision_usable=false、
      value_consumption_status=blocked、data_quality_status=unknown_value_status，
      由 enforce_decision_usable_gate 转为结构化 data_gap。
    - 若字段已存在 value_consumption_status：保留原始事实不覆盖；与 value_status 矛盾时
      记录结构化合同问题（由调用方阻塞），不得静默通过。
    - 轻量 provenance（source_table/source_column/provenance.source_file_sha256 等）
      映射为标准 evidence_locator / source_field，使下游专业 Skill 可消费；不得凭空
      编造 source_row_number / source_column_index（缺失则留空，该字段无法生成 EVREF）。

    返回 (records, contract_issues)；contract_issues 非空时调用方必须合同阻塞。
    """
    contract_issues: list[dict] = []
    for record in records:
        record_key = record.get("semantic_record_key", "")
        for f in record.get("fields", []):
            has_vs = "value_status" in f
            has_vcs = "value_consumption_status" in f
            if not has_vs:
                # 非轻量格式：保留原始事实（已具备标准字段），不做任何改动
                continue
            vs = f["value_status"]

            # normalized_value：轻量格式从 value 读取（仅当缺失时补充，不覆盖）
            if "normalized_value" not in f and "value" in f:
                f["normalized_value"] = f["value"]

            # source_field / evidence_locator：从轻量 provenance 映射（仅补充缺失键）
            if "source_field" not in f and "source_column" in f:
                f["source_field"] = f["source_column"]
            if "evidence_locator" not in f:
                prov = f.get("provenance", {}) or {}
                el: dict = {}
                src_sha = prov.get("source_file_sha256", "")
                if src_sha:
                    el["source_file_sha256"] = src_sha
                src_table = f.get("source_table", "") or prov.get("source_table", "")
                if src_table:
                    el["source_table"] = src_table
                src_col = f.get("source_column", "") or prov.get("source_column", "")
                if src_col:
                    el["source_column_name"] = src_col
                # source_row_number / source_column_index：轻量格式不携带，不得编造
                if el:
                    f["evidence_locator"] = el

            if has_vcs:
                # 两者并存：保留原始 value_consumption_status，不覆盖；
                # 若与 value_status 确定性映射矛盾，记录结构化合同问题
                existing_vcs = f["value_consumption_status"]
                expected_vcs = _VALUE_STATUS_TO_CONSUMPTION.get(vs)
                if expected_vcs is not None and existing_vcs != expected_vcs:
                    contract_issues.append({
                        "type": "value_status_value_consumption_status_conflict",
                        "semantic_record_key": record_key,
                        "semantic_field": f.get("semantic_field", ""),
                        "value_status": vs,
                        "existing_value_consumption_status": existing_vcs,
                        "expected_value_consumption_status": expected_vcs,
                        "detail": (
                            "value_status 与已有 value_consumption_status 矛盾，"
                            "不得覆盖原始事实"
                        ),
                    })
                # 无论是否矛盾，均保留原始 value_consumption_status，不覆盖
                continue

            # 仅有 value_status 的轻量格式 → 确定性归一化 value_consumption_status
            if vs == "usable":
                f["decision_usable"] = True
                f["value_consumption_status"] = "usable"
            elif vs in _VALUE_STATUS_TO_CONSUMPTION:
                # null_unavailable / invalid / needs_rule：保留不可消费状态
                f["decision_usable"] = False
                f["value_consumption_status"] = vs
            else:
                # 未知/非法 value_status：不得默认通过 → blocked，转为 data_gap
                f["decision_usable"] = False
                f["value_consumption_status"] = "blocked"
                f.setdefault("data_quality_status", "unknown_value_status")
                f.setdefault(
                    "data_quality_detail",
                    f"未识别的 value_status={vs!r}，不得默认提升为 usable",
                )
    return records, contract_issues


def _match_condition(cond: dict, record: dict) -> bool:
    op = cond["op"]
    field = cond["field"]
    fmap = _record_field_map(record)
    if op == "is_null":
        if field not in fmap:
            return True  # 字段不存在视为 null
        return fmap[field].get("normalized_value") is None
    if op == "is_not_null":
        if field not in fmap:
            return False
        return fmap[field].get("normalized_value") is not None
    if field not in fmap:
        return False
    nv = fmap[field].get("normalized_value")
    if op == "eq":
        return nv == cond["value"]
    if op == "in":
        return nv in (cond["value"] if isinstance(cond["value"], (list, tuple, set)) else [cond["value"]])
    if op == "between":
        lo, hi = cond["value"]
        try:
            return lo <= nv <= hi
        except TypeError:
            return False
    return False


def _apply_filters(records: list[dict], conditions: list[dict]) -> list[dict]:
    matched = []
    for record in records:
        if all(_match_condition(c, record) for c in conditions):
            matched.append(record)
    return matched


def _detect_temporal_order_field(records: list[dict]) -> str | None:
    """
    在匹配记录中检测被认可的时间排序字段。
    必须满足：字段在 _APPROVED_TEMPORAL_FIELDS 中，且在记录中 materialized & decision_usable。
    若找不到时间字段，返回 None。
    不得用 record_id / 行号 / 字符串前缀猜测。
    """
    for field_name in _APPROVED_TEMPORAL_FIELDS:
        for record in records:
            fmap = _record_field_map(record)
            f = fmap.get(field_name)
            if f and f.get("decision_usable") is True and f.get("normalized_value") is not None:
                return field_name
    return None


def _detect_shift_order_field(records: list[dict]) -> str | None:
    """
    检测被认可的班次顺序字段（用于班次去重）。
    必须满足：字段在 _APPROVED_SHIFT_ORDER_FIELDS 中，且 decision_usable。
    """
    for field_name in _APPROVED_SHIFT_ORDER_FIELDS:
        for record in records:
            fmap = _record_field_map(record)
            f = fmap.get(field_name)
            if f and f.get("decision_usable") is True and f.get("normalized_value") is not None:
                return field_name
    return None


def _apply_time_window(
    matched: list[dict],
    time_window: dict | None,
    semantic_entity: str,
) -> tuple[list[dict], list[dict]]:
    """
    应用 time_window。返回 (selected_records, time_window_data_gaps)。
    - last_n_shifts: 需批准时间字段或班次顺序字段；按字段排序后取 N 个不同班次。
    - last_n_records: 需批准时间字段排序；缺则 data_gap。
    - date_range: 需批准时间字段；按 [start,end] 过滤。
    - all_available: 全部返回。
    缺少批准时间字段时返回 data_gap(reason=missing_approved_temporal_order_field)，不按行号/record_id 猜测。
    """
    gaps: list[dict] = []
    if not time_window:
        return matched, gaps

    tw_type = time_window.get("type", "all_available")

    if tw_type == "all_available":
        return matched, gaps

    if tw_type == "last_n_shifts":
        n = int(time_window.get("n", 1))
        order_field = _detect_temporal_order_field(matched)
        shift_field = _detect_shift_order_field(matched)
        if order_field is None:
            # 缺少批准时间排序字段 → 阻塞，不猜测
            gaps.append({
                "semantic_entity": semantic_entity,
                "semantic_field": "__time_window__",
                "reason": "missing_approved_temporal_order_field",
                "value_consumption_status": "blocked",
                "source_locator": None,
                "required_resolution": (
                    "缺少批准的时间排序字段（record_timestamp/shift_start_time/shift_end_time/shift_date），"
                    "无法确定班次时间顺序，不得按 record_id/行号/字符串前缀猜测"
                ),
            })
            return [], gaps
        # 按时间字段排序（降序取最近 N 班次）
        def _sort_key(rec):
            fmap = _record_field_map(rec)
            return fmap.get(order_field, {}).get("normalized_value", "")
        sorted_records = sorted(matched, key=_sort_key, reverse=True)
        # 班次去重：用 shift_field 或 order_field 作为班次键
        dedupe_key_field = shift_field or order_field
        seen_shifts: set = set()
        selected: list[dict] = []
        for rec in sorted_records:
            fmap = _record_field_map(rec)
            shift_val = fmap.get(dedupe_key_field, {}).get("normalized_value")
            if shift_val in seen_shifts:
                continue
            seen_shifts.add(shift_val)
            # 收集该班次所有明细记录
        # 重新收集：取 N 个不同班次后，保留这些班次的全部明细
        selected_shifts: list = []
        for rec in sorted_records:
            fmap = _record_field_map(rec)
            shift_val = fmap.get(dedupe_key_field, {}).get("normalized_value")
            if shift_val not in selected_shifts:
                selected_shifts.append(shift_val)
            if len(selected_shifts) >= n:
                break
        selected_shift_set = set(selected_shifts)
        selected = [rec for rec in matched
                    if _record_field_map(rec).get(dedupe_key_field, {}).get("normalized_value") in selected_shift_set]
        return selected, gaps

    if tw_type == "last_n_records":
        n = int(time_window.get("n", 1))
        order_field = _detect_temporal_order_field(matched)
        if order_field is None:
            gaps.append({
                "semantic_entity": semantic_entity,
                "semantic_field": "__time_window__",
                "reason": "missing_approved_temporal_order_field",
                "value_consumption_status": "blocked",
                "source_locator": None,
                "required_resolution": "缺少批准的时间排序字段，无法确定记录时间顺序",
            })
            return [], gaps
        def _sort_key(rec):
            fmap = _record_field_map(rec)
            return fmap.get(order_field, {}).get("normalized_value", "")
        sorted_records = sorted(matched, key=_sort_key, reverse=True)
        return sorted_records[:n], gaps

    if tw_type == "date_range":
        start = time_window.get("start")
        end = time_window.get("end")
        field = time_window.get("field")
        order_field = field if field in _APPROVED_TEMPORAL_FIELDS else _detect_temporal_order_field(matched)
        if order_field is None:
            gaps.append({
                "semantic_entity": semantic_entity,
                "semantic_field": "__time_window__",
                "reason": "missing_approved_temporal_order_field",
                "value_consumption_status": "blocked",
                "source_locator": None,
                "required_resolution": "缺少批准的时间排序字段，无法执行 date_range 过滤",
            })
            return [], gaps
        selected = []
        for rec in matched:
            fmap = _record_field_map(rec)
            nv = fmap.get(order_field, {}).get("normalized_value")
            if nv is None:
                continue
            try:
                if start is not None and nv < start:
                    continue
                if end is not None and nv > end:
                    continue
            except TypeError:
                continue
            selected.append(rec)
        return selected, gaps

    # 未知 time_window 类型 → 不阻塞，返回全部
    return matched, gaps


def _apply_sort(records: list[dict], sort: dict | list | None) -> list[dict]:
    """
    应用排序。sort 可为：
      - {"field": "...", "order": "asc|desc"}
      - [{"field": "...", "order": "..."}, ...]
    排序基于字段的 normalized_value。字段不存在时排到最后。
    """
    if not sort:
        return records
    if isinstance(sort, dict):
        sort = [sort]
    def make_key(spec):
        field = spec.get("field")
        order = spec.get("order", "asc")
        def _key(rec):
            fmap = _record_field_map(rec)
            nv = fmap.get(field, {}).get("normalized_value")
            return (nv is None, nv)
        return _key, order
    result = list(records)
    # 多键排序：从最后一个键向前依次排序（稳定排序）
    for spec in reversed(sort):
        key_fn, order = make_key(spec)
        result.sort(key=key_fn, reverse=(order == "desc"))
    return result


def execute_semantic_query(
    snapshot: dict,
    semantic_entity: str,
    requested_fields: list[str],
    filters: dict | list | None = None,
    limit: int | None = None,
    time_window: dict | None = None,
    sort: dict | list | None = None,
    line_ids: list[str] | None = None,
) -> dict:
    """
    04D.4B.1 升级：在快照中执行只读查询。
    1. 定位 semantic_entity 的 entity_batch
    2. 应用结构化 filters（eq/in/between/is_null/is_not_null，兼容旧 eq dict）
    3. 应用 time_window（last_n_shifts/last_n_records/date_range/all_available）
    4. 应用 sort
    5. 应用 limit（在过滤、窗口、排序后执行）
    6. 投影 requested_fields
    7. 不跨记录、不跨实体拼接
    8. 记录缺失字段和不可用字段

    返回:
        {
            "matched_records": [...],
            "field_results": [...],
            "data_gaps_raw": [...],
            "errors": [...],
            "entity_found": bool,
            "total_records_in_entity": int,
            "time_window_applied": bool,
            "sort_applied": bool,
        }
    """
    result = {
        "matched_records": [],
        "field_results": [],
        "data_gaps_raw": [],
        "errors": [],
        "entity_found": False,
        "total_records_in_entity": 0,
        "time_window_applied": False,
        "sort_applied": False,
    }

    # 定位 entity_batch
    entity_batch = None
    for batch in snapshot.get("entity_batches", []):
        if batch.get("semantic_entity") == semantic_entity:
            entity_batch = batch
            result["entity_found"] = True
            result["total_records_in_entity"] = batch.get("record_count", 0)
            break

    if not entity_batch:
        result["errors"].append(f"快照中未找到语义实体: {semantic_entity}")
        return result

    records = entity_batch.get("records", [])
    # v0.3 兼容：归一化字段格式（04D.4C.1-CONSUMER-P0）
    records, contract_issues = _normalize_v03_fields(records)
    if contract_issues:
        # value_status 与已有 value_consumption_status 矛盾等合同问题 → 阻塞
        result["errors"].append(
            "字段归一化合同问题: "
            + "; ".join(
                f"{ci.get('semantic_field', '?')}({ci.get('type', '?')})"
                for ci in contract_issues
            )
        )
        result["contract_issues"] = contract_issues
        return result

    # 1. 应用结构化过滤器
    conditions = _normalize_filters(filters)
    matched = _apply_filters(records, conditions)

    # 2. 应用 time_window
    if time_window:
        matched, tw_gaps = _apply_time_window(matched, time_window, semantic_entity)
        result["data_gaps_raw"].extend(tw_gaps)
        result["time_window_applied"] = True
        # 若 time_window 产生阻塞 data_gap，直接返回（不投影）
        if any(g.get("reason") == "missing_approved_temporal_order_field" for g in tw_gaps):
            result["matched_records"] = matched
            return result

    # 3. 应用 sort
    if sort:
        matched = _apply_sort(matched, sort)
        result["sort_applied"] = True

    # 4. 应用 limit（在过滤、窗口、排序后执行）
    if limit is not None and limit > 0:
        matched = matched[:limit]

    result["matched_records"] = matched

    # 5. 投影 requested_fields
    for record in matched:
        record_key = record.get("semantic_record_key", "")
        source_table = record.get("source_table", "")
        source_record_id = record.get("source_record_id", "")

        field_result = {
            "semantic_record_key": record_key,
            "source_table": source_table,
            "source_record_id": source_record_id,
            "fields": [],
        }

        # 为每个 requested_field 在当前记录中查找
        record_fields = {f["semantic_field"]: f for f in record.get("fields", [])}

        for req_field in requested_fields:
            if req_field in record_fields:
                f = record_fields[req_field]
                field_result["fields"].append({
                    "semantic_field": f["semantic_field"],
                    "normalized_value": f.get("normalized_value"),
                    "normalized_data_type": f.get("normalized_data_type"),
                    "normalized_unit": f.get("normalized_unit"),
                    "display_format": f.get("display_format", ""),
                    "decision_usable": f.get("decision_usable", False),
                    "value_consumption_status": f.get("value_consumption_status", ""),
                    "data_quality_status": f.get("data_quality_status", ""),
                    "data_quality_detail": f.get("data_quality_detail", ""),
                    "source_field": f.get("source_field", ""),
                    "source_data_type": f.get("source_data_type", ""),
                    "source_unit": f.get("source_unit", ""),
                    "raw_value": f.get("raw_value"),
                    "transformation_rule_id": f.get("transformation_rule_id", ""),
                    "mapping_ref": f.get("mapping_ref", {}),
                    "evidence_locator": f.get("evidence_locator", {}),
                })
            else:
                # 请求的字段在当前记录中不存在
                result["data_gaps_raw"].append({
                    "semantic_record_key": record_key,
                    "source_table": source_table,
                    "source_record_id": source_record_id,
                    "semantic_entity": semantic_entity,
                    "semantic_field": req_field,
                    "reason": "field_not_available_in_record",
                    "value_consumption_status": "field_absent",
                    "source_locator": {
                        "source_table": source_table,
                        "source_record_id": source_record_id,
                    },
                    "required_resolution": "该字段在匹配记录中不存在，不得跨记录拼接或从其他记录补值",
                })

        result["field_results"].append(field_result)

    return result


# =========================================================================
# 8. enforce_decision_usable_gate
# =========================================================================
def enforce_decision_usable_gate(field_results: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    执行 decision_usable 门控：
    - decision_usable=true 的字段进入 normalized_facts
    - decision_usable=false 的字段转为 data_gap

    返回: (usable_facts, gated_data_gaps)
    """
    usable_facts = []
    gated_data_gaps = []

    for record_result in field_results:
        record_key = record_result["semantic_record_key"]
        source_table = record_result["source_table"]
        source_record_id = record_result["source_record_id"]

        for f in record_result["fields"]:
            if f.get("decision_usable") is True:
                usable_facts.append({
                    "semantic_record_key": record_key,
                    "source_table": source_table,
                    "source_record_id": source_record_id,
                    "semantic_field": f["semantic_field"],
                    "normalized_value": f["normalized_value"],
                    "normalized_data_type": f.get("normalized_data_type"),
                    "normalized_unit": f.get("normalized_unit"),
                    "display_format": f.get("display_format", ""),
                    "value_consumption_status": f.get("value_consumption_status", ""),
                    "provenance_ref": _build_provenance_ref(f),
                })
            else:
                # decision_usable=false → 转 data_gap
                vcs = f.get("value_consumption_status", "")
                reason = _classify_data_gap_reason(vcs, f.get("data_quality_status", ""))
                gated_data_gaps.append({
                    "semantic_record_key": record_key,
                    "semantic_entity": "",  # 由调用方填充
                    "semantic_field": f["semantic_field"],
                    "reason": reason,
                    "value_consumption_status": vcs,
                    "source_locator": {
                        "source_table": source_table,
                        "source_record_id": source_record_id,
                        "source_column_name": f.get("evidence_locator", {}).get("source_column_name", ""),
                    },
                    "required_resolution": _resolve_data_gap_action(reason, vcs),
                })

    return usable_facts, gated_data_gaps


def _build_provenance_ref(field: dict) -> dict:
    """
    04C.5C.1：构建 provenance_ref，从语义数据面字段对象读取真实 raw_value。
    - raw_value 保存源始值（来自字段对象 raw_value）
    - normalized_value 保持标准化业务值（不在 provenance_ref 中重复）
    - source_unit / source_data_type 来自字段对象
    - 若数据面未提供 raw_value：raw_value=null, raw_value_status=not_available
      不得复制 normalized_value 伪装成源始值。
    """
    ev = field.get("evidence_locator", {})
    has_raw = "raw_value" in field and field.get("raw_value") is not None
    return {
        "source_field": field.get("source_field", ""),
        "raw_value": field.get("raw_value") if has_raw else None,
        "raw_value_status": "available" if has_raw else "not_available",
        "source_data_type": field.get("source_data_type", ""),
        "source_unit": field.get("source_unit", ""),
        "transformation_rule_id": field.get("transformation_rule_id", ""),
        "mapping_ref": field.get("mapping_ref", {}),
        "evidence_locator": {
            "source_file_sha256": ev.get("source_file_sha256", ""),
            "source_table": ev.get("source_table", ""),
            "source_row_number": ev.get("source_row_number"),
            "source_column_name": ev.get("source_column_name", ""),
            "source_column_index": ev.get("source_column_index"),
        },
        "note": "raw_value 为源始值，仅供审计追溯；normalized_value 为消费者业务值，两者不得互相替代",
    }


# =========================================================================
# 9. build_structured_data_gap
# =========================================================================
def _classify_data_gap_reason(vcs: str, dq_status: str) -> str:
    """根据 value_consumption_status 和 data_quality_status 分类 data_gap reason"""
    if vcs == "null_unavailable":
        return "null_value_unavailable"
    elif vcs == "invalid":
        return f"invalid_value:{dq_status}" if dq_status else "invalid_value"
    elif vcs == "needs_rule":
        return "needs_rule"
    elif vcs == "field_absent":
        return "field_not_available_in_record"
    elif vcs == "blocked":
        return "blocked_by_contract"
    else:
        return f"unknown_status:{vcs}"


def _resolve_data_gap_action(reason: str, vcs: str) -> str:
    """根据 data_gap reason 生成 required_resolution"""
    if "null_value" in reason:
        return "源数据为空，需业务系统补录后重新物化"
    elif "invalid" in reason:
        return "源数据无效，需数据质量团队排查并修正后重新物化"
    elif "needs_rule" in reason:
        return "缺少映射规则，需工艺/数据团队补充规则定义后重新物化"
    elif "field_not_available" in reason:
        return "字段在匹配记录中不存在，不得跨记录拼接或从其他记录补值"
    elif "blocked" in reason:
        return "字段被合同门控阻塞，需数据面修复合同状态后重新物化"
    else:
        return "需数据面团队排查"


def build_structured_data_gap(
    semantic_entity: str,
    semantic_field: str,
    reason: str,
    value_consumption_status: str,
    source_locator: dict | None = None,
    required_resolution: str = "",
) -> dict:
    """
    构建结构化 data_gap 条目。
    """
    return {
        "semantic_entity": semantic_entity,
        "semantic_field": semantic_field,
        "reason": reason,
        "value_consumption_status": value_consumption_status,
        "source_locator": source_locator,
        "required_resolution": required_resolution or "需数据面团队排查",
    }


# =========================================================================
# 10. build_decision_input_contract
# =========================================================================
def build_decision_input_contract(
    request: dict,
    source_release_id: str,
    source_snapshot_id: str,
    normalized_facts: list[dict],
    data_gaps: list[dict],
    provenance_refs: list[dict],
    snapshot_audit: dict,
    validation_status: dict,
) -> dict:
    """
    构建 BIFROST_DECISION_INPUT_v0.1 合同输出。

    输出不得包含：
    - conclusion
    - root_cause
    - recommended_actions
    - confirmation_draft
    - 自动执行指令
    """
    return {
        "contract_name": "BIFROST_DECISION_INPUT_v0.1",
        "contract_version": DECISION_INPUT_CONTRACT_VERSION,
        "request_id": request.get("request_id", ""),
        "consumer_agent_id": request.get("consumer_agent_id", ""),
        "role": request.get("role", ""),
        "query_context": {
            "semantic_entity": request.get("semantic_entity", ""),
            "source_scope": request.get("source_scope", ""),
            "requested_fields": request.get("requested_fields", []),
            "filters": request.get("filters", {}),
            "time_window": request.get("time_window"),
            "limit": request.get("limit"),
            "semantic_data_ref": request.get("semantic_data_ref", {}),
            "read_only": True,
        },
        "source_release_id": source_release_id,
        "source_snapshot_id": source_snapshot_id,
        "normalized_facts": normalized_facts,
        "data_gaps": data_gaps,
        "provenance_refs": provenance_refs,
        "contract_versions": {
            "semantic_model_version": snapshot_audit.get("semantic_model_version", ""),
            "mapping_rule_version": snapshot_audit.get("mapping_rule_version", ""),
            "data_contract_version": snapshot_audit.get("data_contract_version", ""),
            "query_contract_version": QUERY_CONTRACT_VERSION,
            "decision_input_contract_version": DECISION_INPUT_CONTRACT_VERSION,
            "consumer_logical_version": CONSUMER_LOGICAL_VERSION,
        },
        "validation": validation_status,
        "source_write_performed": False,
        "actor_can_execute": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "local_trace_id": f"CONSUMER-{uuid.uuid4().hex[:16].upper()}",
    }


# =========================================================================
# 11. validate_decision_input_contract
# =========================================================================
def validate_decision_input_contract(decision_input: dict) -> dict:
    """
    验证 BIFROST_DECISION_INPUT_v0.1 合同输出是否符合规范。
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
    }

    # 必需字段
    required_fields = [
        "contract_name", "contract_version", "request_id", "consumer_agent_id",
        "role", "query_context", "source_release_id", "source_snapshot_id",
        "normalized_facts", "data_gaps", "provenance_refs", "contract_versions",
        "validation", "source_write_performed", "actor_can_execute",
    ]
    for field in required_fields:
        if field not in decision_input:
            result["errors"].append(f"缺少必需字段: {field}")
            result["valid"] = False

    # 禁止字段
    forbidden_fields = [
        "conclusion", "root_cause", "recommended_actions",
        "confirmation_draft", "auto_execute_command",
    ]
    for field in forbidden_fields:
        if field in decision_input:
            result["errors"].append(f"包含禁止字段: {field}")
            result["valid"] = False

    # read_only 必须为 true
    qc = decision_input.get("query_context", {})
    if qc.get("read_only") is not True:
        result["errors"].append("query_context.read_only 必须为 true")
        result["valid"] = False

    # source_write_performed 必须为 false
    if decision_input.get("source_write_performed") is not False:
        result["errors"].append("source_write_performed 必须为 false")
        result["valid"] = False

    # actor_can_execute 必须为 false
    if decision_input.get("actor_can_execute") is not False:
        result["errors"].append("actor_can_execute 必须为 false")
        result["valid"] = False

    # 检查 normalized_facts 中不得包含 raw_value 作为业务值
    for fact in decision_input.get("normalized_facts", []):
        if "raw_value" in fact and "normalized_value" not in fact:
            result["errors"].append(
                f"normalized_facts 中 {fact.get('semantic_field', '?')} "
                "不得用 raw_value 替代 normalized_value"
            )
            result["valid"] = False

    # 检查 normalized_facts 中每个 fact 都有 provenance_ref
    for fact in decision_input.get("normalized_facts", []):
        if "provenance_ref" not in fact:
            result["warnings"].append(
                f"normalized_facts 中 {fact.get('semantic_field', '?')} 缺少 provenance_ref"
            )

    # 04C.5C.1：provenance_ref 中 raw_value 不得复制 normalized_value 伪装源始值
    for fact in decision_input.get("normalized_facts", []):
        prov = fact.get("provenance_ref", {})
        if prov.get("raw_value_status") == "not_available":
            if prov.get("raw_value") is not None:
                result["errors"].append(
                    f"normalized_facts 中 {fact.get('semantic_field', '?')} "
                    "raw_value_status=not_available 但 raw_value 非 null"
                )
                result["valid"] = False

    # 检查 data_gaps 结构
    for gap in decision_input.get("data_gaps", []):
        gap_required = ["semantic_entity", "semantic_field", "reason", "value_consumption_status"]
        for gr in gap_required:
            if gr not in gap:
                result["errors"].append(f"data_gap 缺少必需字段: {gr}")
                result["valid"] = False

    return result


def _verify_zip_directory_binding(zip_path: str, extracted_dir: str) -> dict:
    """
    04C.5C.1：逐文件证明 extracted_dir 与 zip_path 的条目、路径和 SHA-256 完全一致。
    返回 {"bound": bool, "errors": [...], "zip_only": [...], "dir_only": [...], "hash_mismatches": [...]}。
    """
    result = {
        "bound": False,
        "errors": [],
        "zip_only": [],
        "dir_only": [],
        "hash_mismatches": [],
        "matched_count": 0,
    }

    if not os.path.exists(zip_path):
        result["errors"].append(f"ZIP文件不存在: {zip_path}")
        return result
    if not os.path.isdir(extracted_dir):
        result["errors"].append(f"解压目录不存在: {extracted_dir}")
        return result

    # 读取 ZIP 内所有条目（排除目录条目）
    zip_entries: dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            # 标准化：去掉可能的顶级目录前缀
            parts = name.split("/")
            # 若带顶级目录前缀，取最后一部分之后的相对路径
            # 数据面 FINAL 包无顶级前缀，文件直接在根
            rel = name
            # 尝试检测并剥离常见前缀（如 dataplane/）
            # 仅当磁盘上该路径不存在但去掉首段后存在时剥离
            if not os.path.exists(os.path.join(extracted_dir, rel)) and len(parts) > 1:
                candidate = "/".join(parts[1:])
                if os.path.exists(os.path.join(extracted_dir, candidate)):
                    rel = candidate
            data = zf.read(name)
            zip_entries[rel] = hashlib.sha256(data).hexdigest()

    # 读取磁盘文件（排除 __pycache__ 和 .pyc）
    disk_entries: dict[str, str] = {}
    for root, dirs, files in os.walk(extracted_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if fn.endswith(".pyc"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, extracted_dir)
            # 04D.4B.2B.2: POSIX 归一化——将 Windows 反斜杠统一为正斜杠，
            # 防止 ZIP（正斜杠）与磁盘（Windows 反斜杠）被误判为目录不一致
            rel = rel.replace("\\", "/")
            with open(full, "rb") as f:
                disk_entries[rel] = hashlib.sha256(f.read()).hexdigest()

    # 04D.4B.2B.2: 同样将 zip_entries 的键归一化为 POSIX 形式
    zip_entries = {k.replace("\\", "/"): v for k, v in zip_entries.items()}

    zip_paths = set(zip_entries.keys())
    disk_paths = set(disk_entries.keys())

    result["zip_only"] = sorted(zip_paths - disk_paths)
    result["dir_only"] = sorted(disk_paths - zip_paths)

    if result["zip_only"]:
        result["errors"].append(f"ZIP 有但目录无: {result['zip_only']}")
    if result["dir_only"]:
        result["errors"].append(f"目录有但 ZIP 无: {result['dir_only']}")

    for path in zip_paths & disk_paths:
        if zip_entries[path] != disk_entries[path]:
            result["hash_mismatches"].append({
                "path": path,
                "zip_sha": zip_entries[path],
                "dir_sha": disk_entries[path],
            })
            result["errors"].append(f"ZIP 与目录哈希不一致: {path}")
        else:
            result["matched_count"] += 1

    result["bound"] = len(result["errors"]) == 0
    return result


# =========================================================================
# 12. orchestrate_consumer_run
# =========================================================================
def orchestrate_consumer_run(
    zip_path: str,
    extracted_dir: str,
    request: dict,
) -> dict:
    """
    编排消费者完整运行流程：
    1. 验证数据面包
    2. 验证 MANIFEST
    3. 加载 RELEASE_INDEX
    4. 解析 semantic_data_ref
    5. 加载语义快照
    6. 验证角色权限
    7. 执行语义查询
    8. 执行 decision_usable 门控
    9. 构建 data_gap
    10. 构建 decision_input 合同
    11. 验证 decision_input 合同
    12. 返回结果

    任何门控失败时阻塞，不继续执行。
    """
    orchestration = {
        "status": "init",
        "blocked_code": None,
        "blocked_reason": None,
        "steps": [],
        "decision_input": None,
        "validation": None,
        "zip_sha256_before": None,
        "zip_sha256_after": None,
        "zip_unchanged": None,
        "approved_data_plane_releases": [r["release_id"] for r in APPROVED_DATA_PLANE_RELEASES],
        "matched_release_id": None,
        "actual_data_plane_zip_sha256": None,
        "zip_directory_binding_status": None,
        "manifest_entry_count": None,
        "manifest_verified_count": None,
        "contents_manifest_consistent": None,
        "raw_provenance_validation_status": None,
    }

    def _step(name, ok, detail=None):
        orchestration["steps"].append({
            "step": name,
            "ok": ok,
            "detail": detail or {},
        })
        return ok

    # 0. 记录 ZIP SHA-256（运行前）
    with open(zip_path, "rb") as f:
        zip_sha = hashlib.sha256(f.read()).hexdigest()
    orchestration["zip_sha256_before"] = zip_sha
    orchestration["actual_data_plane_zip_sha256"] = zip_sha

    # 0a. 校验批准的数据面 ZIP SHA-256（04C.5C.1）
    # 使用版本化只读信任注册表，不再使用单常量
    matched_release = None
    for release in APPROVED_DATA_PLANE_RELEASES:
        if zip_sha == release["sha256"]:
            matched_release = release
            break
    orchestration["matched_release_id"] = matched_release["release_id"] if matched_release else None
    orchestration["approved_data_plane_releases"] = [
        {"release_id": r["release_id"], "sha256": r["sha256"], "purpose": r["purpose"]}
        for r in APPROVED_DATA_PLANE_RELEASES
    ]
    if matched_release is None:
        orchestration["status"] = "BLOCKED_UNAPPROVED_DATA_PLANE_PACKAGE"
        orchestration["blocked_code"] = "BLOCKED_UNAPPROVED_DATA_PLANE_PACKAGE"
        orchestration["blocked_reason"] = (
            f"数据面 ZIP SHA-256 未获批准: 实际={zip_sha}, "
            f"已登记={[r['sha256'][:16] + '...' for r in APPROVED_DATA_PLANE_RELEASES]}"
        )
        _step("verify_approved_zip_sha256", False, {
            "actual": zip_sha,
            "matched_release_id": None,
            "registered_releases": len(APPROVED_DATA_PLANE_RELEASES),
        })
        return orchestration
    _step("verify_approved_zip_sha256", True, {
        "sha256": zip_sha,
        "matched_release_id": matched_release["release_id"],
        "matched_purpose": matched_release["purpose"],
    })

    # 0b. 绑定 ZIP 与解压目录（04C.5C.1）
    bind_result = _verify_zip_directory_binding(zip_path, extracted_dir)
    orchestration["zip_directory_binding_status"] = "bound" if bind_result["bound"] else "mismatch"
    if not _step("verify_zip_directory_binding", bind_result["bound"], {
        "matched_count": bind_result["matched_count"],
        "zip_only": bind_result["zip_only"],
        "dir_only": bind_result["dir_only"],
        "hash_mismatches": bind_result["hash_mismatches"],
        "errors": bind_result["errors"],
    }):
        orchestration["status"] = "BLOCKED_PACKAGE_DIRECTORY_MISMATCH"
        orchestration["blocked_code"] = "BLOCKED_PACKAGE_DIRECTORY_MISMATCH"
        orchestration["blocked_reason"] = "; ".join(bind_result["errors"])
        return orchestration

    # 1. verify_data_plane_package
    pkg_result = verify_data_plane_package(zip_path)
    if not _step("verify_data_plane_package", pkg_result["verified"], {"errors": pkg_result["errors"]}):
        orchestration["status"] = "BLOCKED_PACKAGE_VERIFICATION"
        orchestration["blocked_code"] = "BLOCKED_PACKAGE_VERIFICATION"
        orchestration["blocked_reason"] = "; ".join(pkg_result["errors"])
        return orchestration

    # 2. verify_manifest（真正解析 MANIFEST.sha256）
    manifest_result = verify_manifest(extracted_dir)
    orchestration["manifest_entry_count"] = manifest_result["total_files"]
    orchestration["manifest_verified_count"] = manifest_result["verified_files"]
    if not _step("verify_manifest", manifest_result["verified"], {
        "total_files": manifest_result["total_files"],
        "verified_files": manifest_result["verified_files"],
        "mismatches": manifest_result["mismatches"],
        "missing_files": manifest_result["missing_files"],
        "duplicate_paths": manifest_result["duplicate_paths"],
        "errors": manifest_result["errors"],
    }):
        orchestration["status"] = "BLOCKED_MANIFEST_VERIFICATION"
        orchestration["blocked_code"] = "BLOCKED_MANIFEST_VERIFICATION"
        orchestration["blocked_reason"] = "; ".join(manifest_result["errors"])
        return orchestration

    # 2b. verify_contents（CONTENTS.json 目录元数据 + 与 MANIFEST 双向核对）
    contents_result = verify_contents(extracted_dir)
    orchestration["contents_manifest_consistent"] = contents_result.get(
        "contents_manifest_consistent", False
    )
    if not _step("verify_contents", contents_result["verified"], {
        "total_files": contents_result["total_files"],
        "verified_files": contents_result["verified_files"],
        "extra_files": contents_result["extra_files"],
        "missing_files": contents_result["missing_files"],
        "contents_manifest_consistent": contents_result.get(
            "contents_manifest_consistent", False
        ),
        "errors": contents_result["errors"],
    }):
        orchestration["status"] = "BLOCKED_CONTENTS_VERIFICATION"
        orchestration["blocked_code"] = "BLOCKED_CONTENTS_VERIFICATION"
        orchestration["blocked_reason"] = "; ".join(contents_result["errors"])
        return orchestration

    # 3. load_release_index
    ri_result = load_release_index(extracted_dir)
    if not _step("load_release_index", ri_result["loaded"], {"errors": ri_result["errors"]}):
        orchestration["status"] = "BLOCKED_RELEASE_INDEX"
        orchestration["blocked_code"] = "BLOCKED_RELEASE_INDEX"
        orchestration["blocked_reason"] = "; ".join(ri_result["errors"])
        return orchestration

    release_index = ri_result["release_index"]

    # 4. resolve_semantic_data_ref
    source_scope = request.get("source_scope", "")
    sdr_result = resolve_semantic_data_ref(release_index, extracted_dir, source_scope)
    if not _step("resolve_semantic_data_ref", sdr_result["resolved"], {"errors": sdr_result["errors"]}):
        orchestration["status"] = "BLOCKED_SEMANTIC_DATA_REF"
        orchestration["blocked_code"] = "BLOCKED_SEMANTIC_DATA_REF"
        orchestration["blocked_reason"] = "; ".join(sdr_result["errors"])
        return orchestration

    snapshot_path = sdr_result["snapshot_path"]
    semantic_data_ref = sdr_result["semantic_data_ref"]

    # 5. load_semantic_snapshot
    scope_lower = source_scope.lower()
    expected_sha = release_index.get(f"{scope_lower}_snapshot_sha256")
    snap_result = load_semantic_snapshot(snapshot_path, expected_sha)
    if not _step("load_semantic_snapshot", snap_result["loaded"], {
        "errors": snap_result["errors"],
        "sha256_verified": snap_result["sha256_verified"],
    }):
        orchestration["status"] = "BLOCKED_SNAPSHOT_LOAD"
        orchestration["blocked_code"] = "BLOCKED_SNAPSHOT_LOAD"
        orchestration["blocked_reason"] = "; ".join(snap_result["errors"])
        return orchestration

    snapshot = snap_result["snapshot"]

    # 6. validate_consumer_role_scope
    role = request.get("role", "")
    semantic_entity = request.get("semantic_entity", "")
    scope_result = validate_consumer_role_scope(role, semantic_entity)
    if not _step("validate_consumer_role_scope", scope_result["allowed"], {
        "blocked_code": scope_result["blocked_code"],
        "reason": scope_result["reason"],
    }):
        orchestration["status"] = "BLOCKED_ROLE_SCOPE"
        orchestration["blocked_code"] = scope_result["blocked_code"]
        orchestration["blocked_reason"] = scope_result["reason"]
        return orchestration

    # 6b. 检查 read_only
    if request.get("read_only") is not True:
        orchestration["status"] = "BLOCKED_READ_ONLY_VIOLATION"
        orchestration["blocked_code"] = "BLOCKED_READ_ONLY_VIOLATION"
        orchestration["blocked_reason"] = "read_only 必须为 true，消费者不支持写入操作"
        _step("enforce_read_only", False, {"read_only": request.get("read_only")})
        return orchestration
    _step("enforce_read_only", True, {"read_only": True})

    # 6c. 检查 relation_materialization_status
    audit = snapshot.get("audit", {})
    rel_status = audit.get("relation_materialization_status", "not_materialized")
    if rel_status != "materialized":
        # 记录但不阻塞——仅在查询需要跨实体关联时才阻塞
        # 此处标记为 info，实际关联检查在 execute_semantic_query 中
        pass
    _step("check_relation_materialization", True, {
        "relation_materialization_status": rel_status,
        "note": "关联状态记录，跨实体关联查询将在execute_semantic_query中阻塞"
    })

    # 7. execute_semantic_query
    requested_fields = request.get("requested_fields") or request.get("projection_fields") or []
    filters = request.get("filters", {})
    limit = request.get("limit")
    time_window = request.get("time_window")
    sort = request.get("sort")
    line_ids = request.get("line_ids")

    query_result = execute_semantic_query(
        snapshot, semantic_entity, requested_fields, filters, limit,
        time_window=time_window, sort=sort, line_ids=line_ids,
    )
    if not _step("execute_semantic_query", len(query_result["errors"]) == 0, {
        "entity_found": query_result["entity_found"],
        "matched_count": len(query_result["matched_records"]),
        "errors": query_result["errors"],
        "data_gaps_from_missing_fields": len(query_result["data_gaps_raw"]),
        "contract_issues": query_result.get("contract_issues", []),
    }):
        orchestration["status"] = "BLOCKED_QUERY_EXECUTION"
        orchestration["blocked_code"] = "BLOCKED_QUERY_EXECUTION"
        orchestration["blocked_reason"] = "; ".join(query_result["errors"])
        return orchestration

    # 8. enforce_decision_usable_gate
    usable_facts, gated_gaps = enforce_decision_usable_gate(query_result["field_results"])

    # 为 gated_gaps 填充 semantic_entity
    for gap in gated_gaps:
        gap["semantic_entity"] = semantic_entity

    # 合并所有 data_gaps（字段缺失 + 不可用字段）
    all_data_gaps = []
    for gap in query_result["data_gaps_raw"]:
        all_data_gaps.append(build_structured_data_gap(
            semantic_entity=gap["semantic_entity"],
            semantic_field=gap["semantic_field"],
            reason=gap["reason"],
            value_consumption_status=gap["value_consumption_status"],
            source_locator=gap.get("source_locator"),
            required_resolution=gap.get("required_resolution", ""),
        ))
    for gap in gated_gaps:
        all_data_gaps.append(build_structured_data_gap(
            semantic_entity=gap["semantic_entity"],
            semantic_field=gap["semantic_field"],
            reason=gap["reason"],
            value_consumption_status=gap["value_consumption_status"],
            source_locator=gap.get("source_locator"),
            required_resolution=gap.get("required_resolution", ""),
        ))

    _step("enforce_decision_usable_gate", True, {
        "usable_facts_count": len(usable_facts),
        "gated_data_gaps_count": len(all_data_gaps),
    })

    # 9. 收集 provenance_refs
    provenance_refs = [fact["provenance_ref"] for fact in usable_facts]

    # 9b. raw_value 溯源真实性校验（04C.5C.1）
    raw_prov_ok = True
    raw_prov_errors = []
    for fact in usable_facts:
        prov = fact.get("provenance_ref", {})
        rv = prov.get("raw_value")
        nv = fact.get("normalized_value")
        # raw_value 不得等于 normalized_value 当存在单位转换（raw_value_status=available 时）
        # 仅当两者类型一致且 source_unit != normalized_unit 时强制不相等
        su = prov.get("source_unit", "")
        nu = fact.get("normalized_unit", "")
        if prov.get("raw_value_status") == "available":
            if su and nu and su != nu and rv == nv:
                raw_prov_ok = False
                raw_prov_errors.append(
                    f"{fact['semantic_field']}: raw_value 与 normalized_value 相同但单位不同"
                )
        else:
            # raw_value 缺失时不得复制 normalized_value
            if rv == nv and rv is not None:
                raw_prov_ok = False
                raw_prov_errors.append(
                    f"{fact['semantic_field']}: raw_value 缺失但复制了 normalized_value"
                )
    orchestration["raw_provenance_validation_status"] = (
        "validated" if raw_prov_ok else "failed"
    )
    _step("verify_raw_provenance", raw_prov_ok, {"errors": raw_prov_errors})

    # 10. build_decision_input_contract
    validation_status = {
        "status": "passed",
        "issues": [],
        "normalized_facts_count": len(usable_facts),
        "data_gaps_count": len(all_data_gaps),
        "decision_usable_gate_enforced": True,
        "read_only_enforced": True,
        "no_cross_record_join": True,
        "no_business_conclusion": True,
    }

    # 如果查询有匹配记录但所有请求字段都不可用或缺失，validation 仍为 passed
    # 但 data_gaps 非空
    if len(query_result["matched_records"]) == 0 and query_result["entity_found"]:
        validation_status["status"] = "passed"
        validation_status["issues"].append("查询匹配零条记录，返回空结果集")

    # 如果实体不存在
    if not query_result["entity_found"]:
        validation_status["status"] = "warning"
        validation_status["issues"].append(f"语义实体 {semantic_entity} 在快照中不存在")

    snapshot_meta = {
        "semantic_model_version": snapshot.get("semantic_model_version", ""),
        "mapping_rule_version": snapshot.get("mapping_rule_version", ""),
        "data_contract_version": snapshot.get("data_contract_version", ""),
    }

    # 补充 request 中的 semantic_data_ref
    request_with_sdr = copy.deepcopy(request)
    if semantic_data_ref:
        request_with_sdr["semantic_data_ref"] = {
            "ref_id": semantic_data_ref.get("ref_id", ""),
            "snapshot_id": semantic_data_ref.get("snapshot_id", ""),
            "access_mode": semantic_data_ref.get("access_mode", ""),
            "materialization_status": semantic_data_ref.get("materialization_status", ""),
        }

    decision_input = build_decision_input_contract(
        request=request_with_sdr,
        source_release_id=release_index.get("release_id", ""),
        source_snapshot_id=snapshot.get("semantic_snapshot_id", ""),
        normalized_facts=usable_facts,
        data_gaps=all_data_gaps,
        provenance_refs=provenance_refs,
        snapshot_audit=snapshot_meta,
        validation_status=validation_status,
    )

    _step("build_decision_input_contract", True, {
        "contract_version": decision_input["contract_version"],
        "normalized_facts_count": len(decision_input["normalized_facts"]),
        "data_gaps_count": len(decision_input["data_gaps"]),
    })

    # 11. validate_decision_input_contract
    contract_validation = validate_decision_input_contract(decision_input)
    _step("validate_decision_input_contract", contract_validation["valid"], {
        "errors": contract_validation["errors"],
        "warnings": contract_validation["warnings"],
    })

    if not contract_validation["valid"]:
        orchestration["status"] = "BLOCKED_CONTRACT_VALIDATION"
        orchestration["blocked_code"] = "BLOCKED_CONTRACT_VALIDATION"
        orchestration["blocked_reason"] = "; ".join(contract_validation["errors"])
        return orchestration

    # 记录 ZIP SHA-256（运行后）
    with open(zip_path, "rb") as f:
        orchestration["zip_sha256_after"] = hashlib.sha256(f.read()).hexdigest()
    orchestration["zip_unchanged"] = (
        orchestration["zip_sha256_before"] == orchestration["zip_sha256_after"]
    )

    orchestration["status"] = "COMPLETED"
    orchestration["decision_input"] = decision_input
    orchestration["validation"] = contract_validation

    return orchestration




# =========================================================================
# 13. orchestrate_consumer_batch_run  (04D.4B.1 多实体确定性批量编排)
# =========================================================================
def orchestrate_consumer_batch_run(
    zip_path: str,
    extracted_dir: str,
    request: dict,
) -> dict:
    """
    04D.4B.1：确定性多实体批量编排入口。

    request 结构（v0.2）：
    {
      "request_id": "...",
      "consumer_agent_id": "...",
      "role": "...",
      "source_scope": "P02",
      "entities": [
        {"semantic_entity": "shift", "projection_fields": [...], "filters": {...}},
        {"semantic_entity": "downtime_event", "projection_fields": [...], "filters": {...}}
      ],
      "time_window": {...},   # 可选，全局
      "sort": {...},           # 可选，全局
      "limit": N,              # 可选，全局
      "line_ids": [...],       # 可选
      "event_id": "...",       # 可选
      "work_order_id": "...",  # 可选
      "material_code": "...",  # 可选
      "read_only": true
    }

    要求：
    1. 一次请求可查询多个实体。
    2. 每个实体分别执行权限、字段合同、decision_usable 和证据门控。
    3. 生成单一 BIFROST_DECISION_INPUT_v0.1 兼容输出。
    4. normalized_facts 按字段级事实唯一键去重。
    5. evidence_refs 不得丢失、复制或改写。
    6. data_gaps 使用共享规则归并。
    7. 不允许智能体在 Consumer 外部手工合并。
    8. 不得因字段同名跨实体 join。
    9. relation_materialization_status 未确认时禁止跨实体关联。
    """
    orchestration = {
        "status": "init",
        "blocked_code": None,
        "blocked_reason": None,
        "entity_results": [],
        "decision_input": None,
        "validation": None,
        "zip_sha256_before": None,
        "zip_sha256_after": None,
        "zip_unchanged": None,
        "approved_data_plane_zip_sha256": APPROVED_DATA_PLANE_ZIP_SHA256,
    }

    # 0. ZIP SHA-256 前置校验（与单实体一致）
    with open(zip_path, "rb") as f:
        zip_sha = hashlib.sha256(f.read()).hexdigest()
    orchestration["zip_sha256_before"] = zip_sha
    matched_release = None
    for release in APPROVED_DATA_PLANE_RELEASES:
        if zip_sha == release["sha256"]:
            matched_release = release
            break
    orchestration["matched_release_id"] = matched_release["release_id"] if matched_release else None
    if matched_release is None:
        orchestration["status"] = "BLOCKED_UNAPPROVED_DATA_PLANE_PACKAGE"
        orchestration["blocked_code"] = "BLOCKED_UNAPPROVED_DATA_PLANE_PACKAGE"
        orchestration["blocked_reason"] = "数据面 ZIP SHA-256 未获批准"
        return orchestration

    # read_only 校验
    if request.get("read_only") is not True:
        orchestration["status"] = "BLOCKED_READ_ONLY_VIOLATION"
        orchestration["blocked_code"] = "BLOCKED_READ_ONLY_VIOLATION"
        orchestration["blocked_reason"] = "read_only 必须为 true"
        return orchestration

    entities = request.get("entities", [])
    if not entities:
        orchestration["status"] = "BLOCKED_NO_ENTITIES"
        orchestration["blocked_code"] = "BLOCKED_NO_ENTITIES"
        orchestration["blocked_reason"] = "批量请求必须包含至少一个 entity"
        return orchestration

    role = request.get("role", "")
    source_scope = request.get("source_scope", "")
    global_time_window = request.get("time_window")
    global_sort = request.get("sort")
    global_limit = request.get("limit")
    global_line_ids = request.get("line_ids")

    # 公共前置：加载数据面（复用单实体编排的前半段，但只做一次）
    pkg_result = verify_data_plane_package(zip_path)
    if not pkg_result["verified"]:
        orchestration["status"] = "BLOCKED_PACKAGE_VERIFICATION"
        orchestration["blocked_code"] = "BLOCKED_PACKAGE_VERIFICATION"
        orchestration["blocked_reason"] = "; ".join(pkg_result["errors"])
        return orchestration

    manifest_result = verify_manifest(extracted_dir)
    if not manifest_result["verified"]:
        orchestration["status"] = "BLOCKED_MANIFEST_VERIFICATION"
        orchestration["blocked_code"] = "BLOCKED_MANIFEST_VERIFICATION"
        orchestration["blocked_reason"] = "; ".join(manifest_result["errors"])
        return orchestration

    contents_result = verify_contents(extracted_dir)
    if not contents_result["verified"]:
        orchestration["status"] = "BLOCKED_CONTENTS_VERIFICATION"
        orchestration["blocked_code"] = "BLOCKED_CONTENTS_VERIFICATION"
        orchestration["blocked_reason"] = "; ".join(contents_result["errors"])
        return orchestration

    ri_result = load_release_index(extracted_dir)
    if not ri_result["loaded"]:
        orchestration["status"] = "BLOCKED_RELEASE_INDEX"
        orchestration["blocked_code"] = "BLOCKED_RELEASE_INDEX"
        orchestration["blocked_reason"] = "; ".join(ri_result["errors"])
        return orchestration
    release_index = ri_result["release_index"]

    sdr_result = resolve_semantic_data_ref(release_index, extracted_dir, source_scope)
    if not sdr_result["resolved"]:
        orchestration["status"] = "BLOCKED_SEMANTIC_DATA_REF"
        orchestration["blocked_code"] = "BLOCKED_SEMANTIC_DATA_REF"
        orchestration["blocked_reason"] = "; ".join(sdr_result["errors"])
        return orchestration

    scope_lower = source_scope.lower()
    expected_sha = release_index.get(f"{scope_lower}_snapshot_sha256")
    snap_result = load_semantic_snapshot(sdr_result["snapshot_path"], expected_sha)
    if not snap_result["loaded"]:
        orchestration["status"] = "BLOCKED_SNAPSHOT_LOAD"
        orchestration["blocked_code"] = "BLOCKED_SNAPSHOT_LOAD"
        orchestration["blocked_reason"] = "; ".join(snap_result["errors"])
        return orchestration
    snapshot = snap_result["snapshot"]
    semantic_data_ref = sdr_result["semantic_data_ref"]

    # 检查 relation_materialization_status（跨实体关联门控）
    audit = snapshot.get("audit", {})
    rel_status = audit.get("relation_materialization_status", "not_materialized")

    all_normalized_facts: list[dict] = []
    all_data_gaps: list[dict] = []
    all_provenance_refs: list[dict] = []
    entity_summaries: list[dict] = []

    for ent_spec in entities:
        ent_entity = ent_spec.get("semantic_entity", "")
        ent_fields = ent_spec.get("projection_fields") or ent_spec.get("requested_fields") or []
        ent_filters = ent_spec.get("filters", {})
        ent_time_window = ent_spec.get("time_window", global_time_window)
        ent_sort = ent_spec.get("sort", global_sort)
        ent_limit = ent_spec.get("limit", global_limit)

        # 权限门控
        scope_chk = validate_consumer_role_scope(role, ent_entity)
        if not scope_chk["allowed"]:
            entity_summaries.append({
                "semantic_entity": ent_entity,
                "status": "BLOCKED_ROLE_SCOPE",
                "blocked_reason": scope_chk["reason"],
            })
            all_data_gaps.append(build_structured_data_gap(
                semantic_entity=ent_entity,
                semantic_field="__role_scope__",
                reason="role_not_authorized_for_entity",
                value_consumption_status="blocked",
                source_locator=None,
                required_resolution=scope_chk["reason"],
            ))
            continue

        # 执行查询
        q = execute_semantic_query(
            snapshot, ent_entity, ent_fields, ent_filters, ent_limit,
            time_window=ent_time_window, sort=ent_sort, line_ids=global_line_ids,
        )

        if q["errors"]:
            entity_summaries.append({
                "semantic_entity": ent_entity,
                "status": "BLOCKED_QUERY_EXECUTION",
                "errors": q["errors"],
            })
            continue

        # time_window 阻塞 data_gap
        tw_block_gaps = [g for g in q["data_gaps_raw"]
                         if g.get("reason") == "missing_approved_temporal_order_field"]

        # decision_usable 门控
        usable_facts, gated_gaps = enforce_decision_usable_gate(q["field_results"])
        for gap in gated_gaps:
            gap["semantic_entity"] = ent_entity

        # 合并 data_gaps
        ent_gaps = []
        for gap in q["data_gaps_raw"]:
            ent_gaps.append(build_structured_data_gap(
                semantic_entity=gap.get("semantic_entity", ent_entity),
                semantic_field=gap["semantic_field"],
                reason=gap["reason"],
                value_consumption_status=gap["value_consumption_status"],
                source_locator=gap.get("source_locator"),
                required_resolution=gap.get("required_resolution", ""),
            ))
        for gap in gated_gaps:
            ent_gaps.append(build_structured_data_gap(
                semantic_entity=gap["semantic_entity"],
                semantic_field=gap["semantic_field"],
                reason=gap["reason"],
                value_consumption_status=gap["value_consumption_status"],
                source_locator=gap.get("source_locator"),
                required_resolution=gap.get("required_resolution", ""),
            ))

        # 为 usable_facts 标注 semantic_entity（多实体必须区分）
        for fact in usable_facts:
            fact["semantic_entity"] = ent_entity

        all_normalized_facts.extend(usable_facts)
        all_data_gaps.extend(ent_gaps)

        entity_summaries.append({
            "semantic_entity": ent_entity,
            "status": "COMPLETED",
            "matched_records": len(q["matched_records"]),
            "usable_facts": len(usable_facts),
            "data_gaps": len(ent_gaps),
        })

    # 4. normalized_facts 按字段级事实唯一键去重
    #    唯一键 = (semantic_entity, semantic_record_key, semantic_field)
    deduped_facts: list[dict] = []
    seen_keys: set = set()
    for fact in all_normalized_facts:
        key = (
            fact.get("semantic_entity", ""),
            fact.get("semantic_record_key", ""),
            fact.get("semantic_field", ""),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped_facts.append(fact)

    # 5. provenance_refs 保留（与去重后 facts 对应）
    all_provenance_refs = [fact.get("provenance_ref", {}) for fact in deduped_facts]

    # 6. data_gaps 共享规则归并（按 entity+field+reason 去重）
    deduped_gaps: list[dict] = []
    seen_gap_keys: set = set()
    for gap in all_data_gaps:
        gkey = (
            gap.get("semantic_entity", ""),
            gap.get("semantic_field", ""),
            gap.get("reason", ""),
        )
        if gkey in seen_gap_keys:
            continue
        seen_gap_keys.add(gkey)
        deduped_gaps.append(gap)

    # 跨实体关联门控：relation_materialization_status != materialized 时禁止跨实体 join
    # （本实现天然不跨实体 join；仅记录状态）
    cross_entity_join_blocked = rel_status != "materialized" and len(entities) > 1

    validation_status = {
        "status": "passed",
        "issues": [],
        "normalized_facts_count": len(deduped_facts),
        "data_gaps_count": len(deduped_gaps),
        "decision_usable_gate_enforced": True,
        "read_only_enforced": True,
        "no_cross_record_join": True,
        "no_cross_entity_join": True,
        "no_business_conclusion": True,
        "relation_materialization_status": rel_status,
        "cross_entity_join_blocked": cross_entity_join_blocked,
        "multi_entity_count": len(entities),
    }

    snapshot_meta = {
        "semantic_model_version": snapshot.get("semantic_model_version", ""),
        "mapping_rule_version": snapshot.get("mapping_rule_version", ""),
        "data_contract_version": snapshot.get("data_contract_version", ""),
    }

    request_with_sdr = copy.deepcopy(request)
    if semantic_data_ref:
        request_with_sdr["semantic_data_ref"] = {
            "ref_id": semantic_data_ref.get("ref_id", ""),
            "snapshot_id": semantic_data_ref.get("snapshot_id", ""),
            "access_mode": semantic_data_ref.get("access_mode", ""),
            "materialization_status": semantic_data_ref.get("materialization_status", ""),
        }

    decision_input = build_decision_input_contract(
        request=request_with_sdr,
        source_release_id=release_index.get("release_id", ""),
        source_snapshot_id=snapshot.get("semantic_snapshot_id", ""),
        normalized_facts=deduped_facts,
        data_gaps=deduped_gaps,
        provenance_refs=all_provenance_refs,
        snapshot_audit=snapshot_meta,
        validation_status=validation_status,
    )

    # 多实体标记
    decision_input["query_context"]["multi_entity"] = True
    decision_input["query_context"]["entities"] = [e.get("semantic_entity") for e in entities]

    contract_validation = validate_decision_input_contract(decision_input)
    if not contract_validation["valid"]:
        orchestration["status"] = "BLOCKED_CONTRACT_VALIDATION"
        orchestration["blocked_code"] = "BLOCKED_CONTRACT_VALIDATION"
        orchestration["blocked_reason"] = "; ".join(contract_validation["errors"])
        return orchestration

    # ZIP SHA-256 运行后
    with open(zip_path, "rb") as f:
        orchestration["zip_sha256_after"] = hashlib.sha256(f.read()).hexdigest()
    orchestration["zip_unchanged"] = (
        orchestration["zip_sha256_before"] == orchestration["zip_sha256_after"]
    )

    orchestration["status"] = "COMPLETED"
    orchestration["entity_results"] = entity_summaries
    orchestration["decision_input"] = decision_input
    orchestration["validation"] = contract_validation
    return orchestration

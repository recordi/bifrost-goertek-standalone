"""
BIFROST 04D.4B.1.1 专业字段覆盖矩阵生成器（跨源隔离纠偏版）

核心修正：
1. generate_coverage_matrix 必须显式接收 source_scope / source_id / source_family /
   source_type / source_file_sha256，只扫描当前源对应的 Excel、MAP、快照。
2. 禁止跨源引用：P01 不得引用 P02 表字段，反之亦然。
3. 跨源字段只能登记为 cross_source_candidate，不得登记为 source_exists。
4. source_missing 只能在当前 source_scope 完整扫描后确认。
5. 字段发现综合：当前源真实表头、MAP 映射草稿、SEM 语义模型、已批准 handoff 映射、
   单位/别名/transformation_rule。
6. 不得只依赖 label_cn 子串匹配。
7. 模糊标签匹配只能生成候选，不得直接判定 source_exists 或 trusted。
8. performance_rate 与 performance_rate_raw 必须区分。
9. quality_rate 与 quality_factor 必须区分，未证明等价时保持 ambiguous。
10. 带单位后缀的停机时长字段必须经过字段合同和单位规则判断。

coverage_status 枚举（v0.2）：
  trusted_available
  source_exists_mapping_unapproved
  source_exists_semantic_alias_unresolved
  source_exists_contract_failed
  source_exists_not_materialized
  source_missing
  cross_source_candidate
  relation_not_materialized
  role_not_visible
"""

import hashlib
import json
import os
from typing import Any

# =========================================================================
# 生产字段清单（semantic_field → 候选 semantic_entity）
# =========================================================================
PRODUCTION_FIELDS = [
    ("line_id", "shift"),
    ("source_shift_id", "shift"),
    ("simulated_shift_id", "shift"),
    ("record_timestamp", "shift"),
    ("shift_start_time", "shift"),
    ("shift_end_time", "shift"),
    ("shift_date", "shift"),
    ("oee_source", "shift"),
    ("oee_recomputed", "shift"),
    ("oee_deviation", "shift"),
    ("availability", "shift"),
    ("performance_rate", "shift"),
    ("performance_rate_raw", "shift"),
    ("quality_factor", "shift"),
    ("quality_rate", "shift"),
    ("downtime_duration", "downtime_event"),
    ("downtime_type", "downtime_event"),
    ("downtime_reason", "downtime_event"),
    ("equipment_id", "downtime_event"),
    ("fault_code", "downtime_event"),
    ("repair_work_order", "downtime_event"),
    ("material_shortage_qty", "material_detail"),
]

# =========================================================================
# 质量字段清单
# =========================================================================
QUALITY_FIELDS = [
    ("line_id", "defect_detail"),
    ("shift_id", "defect_detail"),
    ("simulated_shift_id", "defect_detail"),
    ("record_timestamp", "defect_detail"),
    ("yield", "defect_detail"),
    ("yield_rate", "shift"),
    ("total_output", "shift"),
    ("good_output", "shift"),
    ("defect_output", "defect_detail"),
    ("defect_count", "defect_detail"),
    ("defect_total", "defect_detail"),
    ("defect_type", "defect_detail"),
    ("defect_ratio", "defect_detail"),
    ("freeze_id", "quality_freeze"),
    ("freeze_status", "quality_freeze"),
    ("freeze_quantity", "quality_freeze"),
    ("freeze_reason", "quality_freeze"),
    ("inspection_status", "quality_freeze"),
    ("reinspection_status", "quality_freeze"),
    ("spc_measurement_points", "quality_freeze"),
    ("usl", "quality_freeze"),
    ("lsl", "quality_freeze"),
    ("sample_rule", "quality_freeze"),
]

# =========================================================================
# 别名混淆防护表：这些字段对必须严格区分，不得自动等价
# =========================================================================
_ALIAS_PROTECTION = {
    # performance_rate != performance_rate_raw
    frozenset({"performance_rate", "performance_rate_raw"}),
    # quality_rate != quality_factor
    frozenset({"quality_rate", "quality_factor"}),
    # yield != yield_rate
    frozenset({"yield", "yield_rate"}),
    # downtime_duration != duration_min (不同单位)
    frozenset({"downtime_duration", "duration_min"}),
}

# 带单位后缀的停机时长字段，必须经过字段合同判断
_UNIT_SUFFIX_TEMPORAL_FIELDS = {
    "downtime_duration",
    "duration_min",
    "planned_downtime_sec",
    "unplanned_downtime_sec",
    "full_speed_sec",
    "low_speed_sec",
}


# =========================================================================
# 快照扫描
# =========================================================================
def _scan_snapshot_fields(snapshot: dict) -> dict:
    """
    扫描快照，返回 {(semantic_entity, semantic_field): field_sample_dict}。
    field_sample_dict 取自第一条含该字段的记录。
    """
    found: dict[tuple[str, str], dict] = {}
    for batch in snapshot.get("entity_batches", []):
        ent = batch.get("semantic_entity", "")
        for rec in batch.get("records", []):
            for f in rec.get("fields", []):
                sf = f.get("semantic_field", "")
                key = (ent, sf)
                if key not in found:
                    found[key] = f
    return found


# =========================================================================
# 源 Excel 表头扫描
# =========================================================================
def _scan_source_excel_headers(excel_paths: list[str]) -> dict:
    """
    返回 {sheet_name: set(column_headers)}。
    只扫描当前 source_scope 对应的 Excel 文件。
    """
    try:
        import openpyxl
    except ImportError:
        return {}
    result: dict[str, set] = {}
    for path in excel_paths:
        if not os.path.exists(path):
            continue
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            for ws in wb.worksheets:
                rows = ws.iter_rows(max_row=1, values_only=True)
                try:
                    hdr = next(rows)
                except StopIteration:
                    hdr = []
                result[ws.title] = set(str(h) for h in hdr if h is not None)
            wb.close()
        except Exception:
            continue
    return result


# =========================================================================
# MAP 映射加载（按 source_scope 过滤）
# =========================================================================
def _load_map_for_scope(
    map_path: str,
    source_scope: str,
    source_excel_sheets: set,
) -> dict:
    """
    加载 MAP 映射草稿，只保留 source_table 属于当前 source_scope 的条目。
    返回 {(target_entity, target_field): mapping_dict}。

    source_scope 过滤逻辑：
    - P01_OFFICIAL: 只保留 source_table 在 P01 Excel sheets 中的映射
    - P02_SIM: 只保留 source_table 在 P02 Excel sheets 中的映射
    """
    trusted: dict[tuple[str, str], dict] = {}
    if not map_path or not os.path.exists(map_path):
        return trusted
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return trusted

    if not isinstance(data, list):
        return trusted

    for m in data:
        if not isinstance(m, dict):
            continue
        st = m.get("source_table", "")
        # 只保留当前 source_scope 的表
        if st not in source_excel_sheets:
            continue
        ent = m.get("target_entity", "")
        fld = m.get("target_field", "")
        if ent and fld:
            trusted[(ent, fld)] = m
    return trusted


# =========================================================================
# handoff trusted/downgraded 加载
# =========================================================================
def _load_handoff_trusted(handoff_dir: str) -> dict:
    """
    从 handoff samples JSON 中加载 trusted_mappings。
    返回 {(target_entity, target_field): mapping_dict}。
    """
    trusted: dict[tuple[str, str], dict] = {}
    if not handoff_dir or not os.path.isdir(handoff_dir):
        return trusted
    for root, dirs, files in os.walk(handoff_dir):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(root, fn), "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            for m in data.get("trusted_mappings", []):
                ent = m.get("target_entity", "")
                fld = m.get("target_field", "")
                if ent and fld:
                    trusted[(ent, fld)] = m
            for m in data.get("downgraded_mappings", []):
                ent = m.get("target_entity", "")
                fld = m.get("target_field", "")
                if ent and fld:
                    trusted[(ent, fld)] = m
    return trusted


# =========================================================================
# SEM 语义模型加载
# =========================================================================
def _load_sem_field_labels(sem_path: str) -> dict:
    """
    加载 SEM，返回 {(entity, semantic_field): field_def_dict}。
    field_def_dict 包含 label_cn, unit, type 等完整信息。
    """
    result: dict[tuple[str, str], dict] = {}
    if not sem_path or not os.path.exists(sem_path):
        return result
    try:
        with open(sem_path, "r", encoding="utf-8") as f:
            sem = json.load(f)
    except Exception:
        return result
    for entity_name, entity_def in sem.items():
        if not isinstance(entity_def, dict):
            continue
        for field_name, field_def in entity_def.items():
            if isinstance(field_def, dict) and "label_cn" in field_def:
                result[(entity_name, field_name)] = field_def
    return result


# =========================================================================
# 别名安全检查
# =========================================================================
def _check_alias_safety(
    semantic_field: str,
    source_field: str,
    label_cn: str,
    sem_field_def: dict,
) -> tuple[bool, str]:
    """
    检查字段匹配是否违反别名防护规则。
    返回 (is_safe, reason)。
    如果不安全，应标记为 source_exists_semantic_alias_unresolved。
    """
    # 1. performance_rate vs performance_rate_raw 区分
    if semantic_field == "performance_rate":
        if "raw" in source_field.lower() or "原始" in label_cn or "原始" in (sem_field_def.get("label_cn", "") or ""):
            return False, "performance_rate 与 performance_rate_raw 必须区分，源字段含 raw/原始 标记"
    if semantic_field == "performance_rate_raw":
        if "raw" not in source_field.lower() and "原始" not in label_cn and "原始" not in (sem_field_def.get("label_cn", "") or ""):
            # 检查是否匹配到了非 raw 字段
            if "性能" in source_field or "performance" in source_field.lower():
                return False, "performance_rate_raw 源字段未含 raw 标记，可能误匹配 performance_rate"

    # 2. quality_rate vs quality_factor 区分
    if semantic_field == "quality_rate":
        if "factor" in source_field.lower() or "因子" in label_cn:
            return False, "quality_rate 与 quality_factor 必须区分，源字段含 factor/因子 标记"
    if semantic_field == "quality_factor":
        if ("rate" in source_field.lower() or "率" in source_field) and "factor" not in source_field.lower() and "因子" not in source_field:
            return False, "quality_factor 源字段含 rate/率 但不含 factor/因子，可能误匹配 quality_rate"

    # 3. yield vs yield_rate 区分
    if semantic_field == "yield":
        if "rate" in source_field.lower() or "率" in label_cn:
            return False, "yield 与 yield_rate 必须区分，源字段含 rate/率 标记"

    return True, ""


# =========================================================================
# 单位后缀字段合同检查
# =========================================================================
def _check_unit_suffix_field(
    semantic_field: str,
    source_field: str,
    sem_field_def: dict,
) -> tuple[bool, str]:
    """
    带单位后缀的停机时长字段必须经过字段合同和单位规则判断。
    返回 (contract_passed, reason)。
    """
    if semantic_field not in _UNIT_SUFFIX_TEMPORAL_FIELDS:
        return True, ""

    sem_unit = sem_field_def.get("unit", "")
    sem_type = sem_field_def.get("type", "")

    # 检查源字段是否含单位后缀
    suffixes = ["_sec", "_min", "_hour", "秒", "分钟", "小时", "(秒)", "(分钟)", "(小时)"]
    has_suffix = any(s in source_field.lower() for s in [s.lower() for s in suffixes])

    if has_suffix and sem_unit:
        # 检查单位是否匹配
        if "sec" in sem_unit and ("min" in source_field.lower() or "分钟" in source_field):
            return False, f"单位不匹配：SEM unit={sem_unit}，源字段含 min/分钟 后缀"
        if "minute" in sem_unit and ("sec" in source_field.lower() and "min" not in source_field.lower()):
            return False, f"单位不匹配：SEM unit={sem_unit}，源字段含 sec 后缀"

    return True, ""


# =========================================================================
# 源字段发现（综合多源证据）
# =========================================================================
def _find_source_field_evidence(
    semantic_entity: str,
    semantic_field: str,
    sem_field_defs: dict,
    source_headers: dict,
    map_for_scope: dict,
    field_sample: dict | None,
) -> dict:
    """
    综合多源证据查找当前 source_scope 下的源字段。
    返回:
    {
        "source_field": str,
        "source_table": str,
        "source_exists": bool,
        "match_method": str,  # exact_map / snapshot_evidence / semantic_alias_candidate / not_found
        "alias_unresolved": bool,
        "unit_contract_failed": bool,
        "cross_source": bool,
        "evidence_detail": str,
    }
    """
    result = {
        "source_field": "",
        "source_table": "",
        "source_exists": False,
        "match_method": "not_found",
        "alias_unresolved": False,
        "unit_contract_failed": False,
        "cross_source": False,
        "evidence_detail": "",
    }

    sem_def = sem_field_defs.get((semantic_entity, semantic_field), {})
    label_cn = sem_def.get("label_cn", "")

    # 1. 优先：快照中的字段物化证据（field_sample 来自当前源快照）
    if field_sample is not None:
        sf = field_sample.get("source_field", "")
        ev = field_sample.get("evidence_locator", {})
        st = ev.get("source_table", field_sample.get("source_table", ""))
        result["source_field"] = sf
        result["source_table"] = st
        result["source_exists"] = True
        result["match_method"] = "snapshot_evidence"
        result["evidence_detail"] = f"快照物化证据: source_field={sf}, source_table={st}"

        # 别名安全检查
        safe, reason = _check_alias_safety(semantic_field, sf, label_cn, sem_def)
        if not safe:
            result["alias_unresolved"] = True
            result["evidence_detail"] += f"; 别名未解决: {reason}"

        # 单位后缀检查
        unit_ok, unit_reason = _check_unit_suffix_field(semantic_field, sf, sem_def)
        if not unit_ok:
            result["unit_contract_failed"] = True
            result["evidence_detail"] += f"; 单位合同失败: {unit_reason}"

        return result

    # 2. MAP 映射草稿（当前 source_scope 过滤后）
    map_entry = map_for_scope.get((semantic_entity, semantic_field))
    if map_entry:
        sf = map_entry.get("source_field", "")
        st = map_entry.get("source_table", "")
        ms = map_entry.get("mapping_status", "")
        result["source_field"] = sf
        result["source_table"] = st
        result["source_exists"] = True
        if ms == "confirmed":
            result["match_method"] = "exact_map_confirmed"
        elif ms == "proposed":
            result["match_method"] = "exact_map_proposed"
        else:
            result["match_method"] = "exact_map"
        result["evidence_detail"] = f"MAP映射: {st}.{sf} -> {semantic_entity}.{semantic_field} (status={ms})"

        # 别名安全检查
        safe, reason = _check_alias_safety(semantic_field, sf, label_cn, sem_def)
        if not safe:
            result["alias_unresolved"] = True
            result["evidence_detail"] += f"; 别名未解决: {reason}"

        # 单位后缀检查
        unit_ok, unit_reason = _check_unit_suffix_field(semantic_field, sf, sem_def)
        if not unit_ok:
            result["unit_contract_failed"] = True
            result["evidence_detail"] += f"; 单位合同失败: {unit_reason}"

        return result

    # 3. SEM label_cn 模糊匹配（只生成候选，不得直接判定 source_exists）
    if label_cn:
        for sheet, headers in source_headers.items():
            for h in headers:
                if h and (label_cn in h or h in label_cn):
                    # 模糊匹配 → 候选，需要进一步验证
                    safe, reason = _check_alias_safety(semantic_field, h, label_cn, sem_def)
                    if not safe:
                        result["source_field"] = h
                        result["source_table"] = sheet
                        result["source_exists"] = False  # 模糊匹配不直接判定 source_exists
                        result["match_method"] = "semantic_alias_candidate"
                        result["alias_unresolved"] = True
                        result["evidence_detail"] = f"模糊标签匹配候选: {sheet}.{h} ~ label_cn={label_cn}; 别名未解决: {reason}"
                        return result
                    # 安全的模糊匹配 → 仍为候选，不直接判定 source_exists
                    result["source_field"] = h
                    result["source_table"] = sheet
                    result["source_exists"] = False
                    result["match_method"] = "semantic_alias_candidate"
                    result["evidence_detail"] = f"模糊标签匹配候选: {sheet}.{h} ~ label_cn={label_cn}"
                    return result

    # 4. 未找到
    result["evidence_detail"] = f"当前源未找到: entity={semantic_entity}, field={semantic_field}, label_cn={label_cn}"
    return result


# =========================================================================
# 覆盖状态分类
# =========================================================================
def _classify_coverage(
    field_sample: dict | None,
    evidence: dict,
    in_trusted: bool,
    in_downgraded: bool,
    relation_materialized: bool,
) -> tuple[str, str, str]:
    """
    返回 (coverage_status, blocking_reason, required_resolution)。
    """
    # 快照中已物化
    if field_sample is not None:
        du = field_sample.get("decision_usable", False)
        fcs = field_sample.get("field_contract_status", "")
        vcs = field_sample.get("value_consumption_status", "")
        mapping_ref = field_sample.get("mapping_ref", {})
        match_method = mapping_ref.get("match_method", "")

        # 别名未解决
        if evidence.get("alias_unresolved"):
            return (
                "source_exists_semantic_alias_unresolved",
                f"别名未解决: {evidence.get('evidence_detail', '')}",
                "需人工确认字段等价性后重新映射",
            )

        # 单位合同失败
        if evidence.get("unit_contract_failed"):
            return (
                "source_exists_contract_failed",
                f"单位合同失败: {evidence.get('evidence_detail', '')}",
                "需解决单位/口径冲突后重新映射",
            )

        if du is True and vcs == "usable" and fcs == "passed":
            return ("trusted_available", "", "")

        if fcs != "passed" and fcs != "not_applicable" and fcs:
            return (
                "source_exists_contract_failed",
                f"field_contract_status={fcs}",
                "需数据面修复字段合同后重新物化",
            )

        if vcs != "usable" and vcs != "not_applicable" and vcs:
            return (
                "source_exists_not_materialized",
                f"value_consumption_status={vcs}",
                "源数据存在但值不可用，需补录/修正后重新物化",
            )

        if match_method != "approved_contract":
            return (
                "source_exists_mapping_unapproved",
                f"match_method={match_method}, 未获批准",
                "映射尚未批准，需人工确认后重新物化",
            )

        return ("trusted_available", "", "")

    # 未物化：检查源是否存在
    if evidence.get("source_exists"):
        if evidence.get("alias_unresolved"):
            return (
                "source_exists_semantic_alias_unresolved",
                f"别名未解决: {evidence.get('evidence_detail', '')}",
                "需人工确认字段等价性后重新映射",
            )
        if evidence.get("unit_contract_failed"):
            return (
                "source_exists_contract_failed",
                f"单位合同失败: {evidence.get('evidence_detail', '')}",
                "需解决单位/口径冲突后重新映射",
            )
        if in_trusted:
            return (
                "source_exists_not_materialized",
                "源字段存在且映射已批准，但未在快照中物化",
                "需数据面重新物化该字段",
            )
        if in_downgraded:
            return (
                "source_exists_contract_failed",
                "源字段存在但映射降级（单位/口径冲突）",
                "需解决单位/口径冲突后重新映射",
            )
        return (
            "source_exists_mapping_unapproved",
            "源字段存在但映射尚未批准",
            "需人工确认映射后重新物化",
        )

    # 模糊标签匹配候选
    if evidence.get("match_method") == "semantic_alias_candidate":
        return (
            "source_exists_semantic_alias_unresolved",
            f"模糊标签匹配候选未确认: {evidence.get('evidence_detail', '')}",
            "需人工确认字段等价性后方可登记为 source_exists",
        )

    # 源不存在
    return (
        "source_missing",
        "当前 source_scope 完整扫描后未找到此字段",
        "需业务系统补充数据源字段",
    )


# =========================================================================
# 跨源候选检测
# =========================================================================
def _detect_cross_source_candidate(
    semantic_entity: str,
    semantic_field: str,
    other_scope_found_fields: dict,
) -> dict | None:
    """
    检测字段是否在其他 source_scope 的快照中物化。
    如果是，返回 cross_source_candidate 信息。
    """
    for (ent, sf), f in other_scope_found_fields.items():
        if sf == semantic_field:
            return {
                "cross_source_entity": ent,
                "cross_source_field": sf,
                "cross_source_field_sample": {
                    "source_field": f.get("source_field", ""),
                    "source_table": f.get("evidence_locator", {}).get("source_table", ""),
                },
            }
    return None


# =========================================================================
# 主入口：generate_coverage_matrix（跨源隔离版）
# =========================================================================
def generate_coverage_matrix(
    snapshot: dict,
    source_excel_paths: list[str],
    handoff_dir: str,
    role: str = "factory",
    sem_path: str = "",
    map_path: str = "",
    source_scope: str = "",
    source_id: str = "",
    source_family: str = "",
    source_type: str = "",
    source_file_sha256: str = "",
    other_scope_snapshot: dict | None = None,
) -> dict:
    """
    生成当前 source_scope 的覆盖矩阵。

    参数：
    - snapshot: 当前 source_scope 的语义快照
    - source_excel_paths: 当前 source_scope 对应的 Excel 文件路径列表
    - handoff_dir: handoff 目录
    - role: 查询角色
    - sem_path: SEM 语义模型文件路径
    - map_path: MAP 映射草稿文件路径
    - source_scope: 源范围标识 (P01_OFFICIAL / P02_SIM)
    - source_id: 源 ID
    - source_family: 源族
    - source_type: 源类型
    - source_file_sha256: 源文件 SHA-256
    - other_scope_snapshot: 其他 source_scope 的快照（用于跨源候选检测）
    """
    from consumer.role_permissions import get_allowed_entities

    found_fields = _scan_snapshot_fields(snapshot)
    source_headers = _scan_source_excel_headers(source_excel_paths)
    source_excel_sheets = set(source_headers.keys())
    map_for_scope = _load_map_for_scope(map_path, source_scope, source_excel_sheets)
    trusted = _load_handoff_trusted(handoff_dir)
    sem_field_defs = _load_sem_field_labels(sem_path)

    # 其他源的快照字段（用于跨源候选检测）
    other_scope_found_fields: dict = {}
    if other_scope_snapshot is not None:
        other_scope_found_fields = _scan_snapshot_fields(other_scope_snapshot)

    audit = snapshot.get("audit", {})
    relation_materialized = audit.get("relation_materialization_status") == "materialized"

    allowed = get_allowed_entities(role)

    entries: list[dict] = []

    for category, fields in [("production", PRODUCTION_FIELDS), ("quality", QUALITY_FIELDS)]:
        for semantic_field, primary_entity in fields:
            # 角色可见性
            if allowed is not None and primary_entity not in allowed:
                entries.append({
                    "category": category,
                    "semantic_entity": primary_entity,
                    "semantic_field": semantic_field,
                    "source_scope": source_scope,
                    "source_id": source_id,
                    "source_family": source_family,
                    "source_type": source_type,
                    "source_file_sha256": source_file_sha256,
                    "source_field": "",
                    "source_table": "",
                    "source_exists": False,
                    "mapping_status": "not_applicable",
                    "approval_status": "not_applicable",
                    "field_contract_status": "not_applicable",
                    "value_consumption_status": "not_applicable",
                    "decision_usable": False,
                    "evidence_available": False,
                    "match_method": "not_applicable",
                    "coverage_status": "role_not_visible",
                    "blocking_reason": f"角色 {role} 无权查询实体 {primary_entity}",
                    "required_resolution": "需切换有权角色或扩展角色权限",
                    "evidence_detail": "",
                })
                continue

            # 在当前源快照中查找该字段
            field_sample = found_fields.get((primary_entity, semantic_field))
            scan_entity = primary_entity
            if field_sample is None:
                for (ent, sf), f in found_fields.items():
                    if sf == semantic_field:
                        field_sample = f
                        scan_entity = ent
                        break

            # 综合多源证据查找
            evidence = _find_source_field_evidence(
                scan_entity, semantic_field, sem_field_defs,
                source_headers, map_for_scope, field_sample,
            )

            # 提取字段元数据
            source_field = evidence["source_field"]
            source_table = evidence["source_table"]
            source_exists = evidence["source_exists"]
            match_method = evidence["match_method"]
            mapping_status = "unmapped"
            approval_status = "not_approved"
            field_contract_status = ""
            value_consumption_status = ""
            decision_usable = False
            evidence_available = False

            if field_sample is not None:
                mapping_ref = field_sample.get("mapping_ref", {})
                mapping_status = "confirmed" if mapping_ref.get("match_method") == "approved_contract" else "proposed"
                approval_status = "approved" if mapping_ref.get("inherited_approval") else "not_approved"
                field_contract_status = field_sample.get("field_contract_status", "")
                value_consumption_status = field_sample.get("value_consumption_status", "")
                decision_usable = field_sample.get("decision_usable", False)
                ev = field_sample.get("evidence_locator", {})
                evidence_available = bool(ev.get("source_file_sha256") or ev.get("source_column_name"))

            # handoff trusted/downgraded
            in_trusted = (scan_entity, semantic_field) in trusted
            in_downgraded = False
            m = trusted.get((scan_entity, semantic_field))
            cls_rule = str((m or {}).get("classification_rule_id", "") or "")
            if m and cls_rule.startswith("CLS"):
                in_downgraded = not in_trusted or "DOWNGRADE" in cls_rule.upper()

            coverage_status, blocking_reason, required_resolution = _classify_coverage(
                field_sample, evidence, in_trusted, in_downgraded, relation_materialized,
            )

            # 跨源候选检测：字段在其他源快照中物化但当前源未物化
            cross_source_info = None
            if field_sample is None:
                cross_source_info = _detect_cross_source_candidate(
                    scan_entity, semantic_field, other_scope_found_fields,
                )
                if cross_source_info is not None:
                    coverage_status = "cross_source_candidate"
                    blocking_reason = (
                        f"字段在其他 source_scope 物化: "
                        f"{cross_source_info['cross_source_entity']}."
                        f"{cross_source_info['cross_source_field']}, "
                        f"不得跨源引用"
                    )
                    required_resolution = "需在当前 source_scope 中独立物化，禁止跨源引用"

            # 跨实体覆盖（同一源内）
            if field_sample is None and coverage_status != "cross_source_candidate":
                cross_entity = False
                if not source_exists and not relation_materialized:
                    for (other_ent, other_sf), _ in found_fields.items():
                        if other_sf == semantic_field and other_ent != primary_entity:
                            cross_entity = True
                            break
                if cross_entity and not relation_materialized:
                    coverage_status = "relation_not_materialized"
                    blocking_reason = "字段在其他语义实体物化，但跨实体关联未物化，禁止 join"
                    required_resolution = "需数据面物化跨实体关联后重新消费"

            entries.append({
                "category": category,
                "semantic_entity": scan_entity,
                "semantic_field": semantic_field,
                "source_scope": source_scope,
                "source_id": source_id,
                "source_family": source_family,
                "source_type": source_type,
                "source_file_sha256": source_file_sha256,
                "source_field": source_field,
                "source_table": source_table,
                "source_exists": source_exists,
                "mapping_status": mapping_status,
                "approval_status": approval_status,
                "field_contract_status": field_contract_status or "not_applicable",
                "value_consumption_status": value_consumption_status or "not_applicable",
                "decision_usable": decision_usable,
                "evidence_available": evidence_available,
                "match_method": match_method,
                "coverage_status": coverage_status,
                "blocking_reason": blocking_reason,
                "required_resolution": required_resolution,
                "evidence_detail": evidence.get("evidence_detail", ""),
                "cross_source_candidate": cross_source_info,
            })

    # 动态聚合统计
    summary = {}
    for e in entries:
        cs = e["coverage_status"]
        summary[cs] = summary.get(cs, 0) + 1

    return {
        "matrix_version": "COVERAGE-MATRIX-v0.2",
        "generated_for": "04D.4B.1.1",
        "source_scope": source_scope,
        "source_id": source_id,
        "source_family": source_family,
        "source_type": source_type,
        "source_file_sha256": source_file_sha256,
        "role": role,
        "relation_materialization_status": audit.get("relation_materialization_status", "not_materialized"),
        "total_fields": len(entries),
        "production_field_count": len(PRODUCTION_FIELDS),
        "quality_field_count": len(QUALITY_FIELDS),
        "summary": summary,
        "entries": entries,
    }


# =========================================================================
# 合并汇总矩阵（只汇总，不传递覆盖）
# =========================================================================
def generate_combined_summary(
    matrix_p01: dict,
    matrix_p02: dict,
) -> dict:
    """
    生成 P01/P02 合并汇总矩阵。
    只汇总各源独立计数，不得把一个数据源的字段覆盖传递给另一个数据源。
    所有计数由 entries 数组动态聚合。
    """
    combined_entries = []

    for e in matrix_p01.get("entries", []):
        entry = dict(e)
        entry["source_scope"] = "P01_OFFICIAL"
        combined_entries.append(entry)

    for e in matrix_p02.get("entries", []):
        entry = dict(e)
        entry["source_scope"] = "P02_SIM"
        combined_entries.append(entry)

    # 动态聚合
    summary = {}
    for e in combined_entries:
        cs = e["coverage_status"]
        key = f"{e['source_scope']}:{cs}"
        summary[key] = summary.get(key, 0) + 1

    # 各源独立统计
    p01_summary = matrix_p01.get("summary", {})
    p02_summary = matrix_p02.get("summary", {})

    # 跨源候选计数
    cross_source_count = sum(1 for e in combined_entries if e.get("coverage_status") == "cross_source_candidate")

    return {
        "matrix_version": "COVERAGE-MATRIX-COMBINED-v0.2",
        "generated_for": "04D.4B.1.1",
        "description": "P01/P02 合并汇总矩阵，只汇总不传递覆盖",
        "p01_source_scope": "P01_OFFICIAL",
        "p02_source_scope": "P02_SIM",
        "total_entries": len(combined_entries),
        "cross_source_candidate_count": cross_source_count,
        "p01_summary": p01_summary,
        "p02_summary": p02_summary,
        "combined_summary": summary,
        "entries": combined_entries,
    }

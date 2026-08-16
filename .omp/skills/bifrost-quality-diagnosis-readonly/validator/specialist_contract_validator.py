#!/usr/bin/env python3
"""
BIFROST 专业诊断 Skill 统一合同独立验证器（v0.1.3 字段级 EvidenceRef 收口版）。

相对 v0.1.2 的收口：
  1. EvidenceRef 从"记录级"升级为"字段事实级"。
     不得仅使用 semantic_record_key 作为 EvidenceRef——同一记录的多个
     semantic_field 共用同一个 record key，记录级引用无法区分字段事实。
  2. 新增确定性函数 build_canonical_evidence_ref(normalized_fact)。
     规范形式：EVREF-v1:<SHA256>。
     哈希输入为确定性 canonical JSON，至少包括：
       semantic_record_key / semantic_field /
       provenance_ref.evidence_locator.source_file_sha256 /
       source_table / source_row_number /
       source_column_name / source_column_index
  3. validate_specialist_result_against_input 从每条 usable normalized_fact
     计算字段级合法 EvidenceRef 集合；metrics/causes/recommended_actions/
     top-level evidence_refs 只能引用该集合中的值。
     metrics 的每条 evidence_ref 还必须解析到 semantic_field 与
     metric.semantic_field 一致的字段事实（字段绑定）。
     不得继续接受裸 semantic_record_key。
  4. data_gap 计数修正：
     affected_record_count 按唯一 source_locator 计数；
     occurrence_count 表示原始出现次数。
     merge_data_gaps 输出 affected_record_count(唯一 locator) 与 occurrence_count(原始条数)。

保留 v0.1.2 全部能力（不得回退）：
  - 状态双向优先级（blocked > needs_confirmation > warning > completed）
  - 条件化顶层 evidence_refs
  - 占位证据禁止
  - data_gap 归并
  - blocked 语义

本验证器为"独立验证器"：不依赖三个专业 Skill 的任何生产函数，
仅消费本包内的权威输出 Schema 与被测样例。

使用：
  python3 specialist_contract_validator.py validate --doc <result.json> [--schema <schema.json>]
  python3 specialist_contract_validator.py validate-input --doc <input.json> --schema <input_schema.json>
  python3 specialist_contract_validator.py validate-against-input --doc <result.json> --input <decision_input.json>
  python3 specialist_contract_validator.py build-evref --input <decision_input.json>
  python3 specialist_contract_validator.py merge-gaps --doc <result_with_raw_gaps.json>
  python3 specialist_contract_validator.py diff <old_schema.json>

退出码：0 = 通过；非 0 = 校验失败（含语义违规）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_SCHEMA = os.path.join(HERE, "..", "schema", "BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json")
DEFAULT_INPUT_SCHEMA = os.path.join(HERE, "..", "schema", "BIFROST_DECISION_INPUT_v0.1.schema.json")

# ---- 语义常量（来自冻结合同，禁止从被测对象读取） -----------------------------
CONTRACT_NAME = "BIFROST_SPECIALIST_RESULT_v0.1"
CONTRACT_VERSION = "BIFROST-SPECIALIST-RESULT-v0.1.3"
INPUT_CONTRACT_NAME = "BIFROST_DECISION_INPUT_v0.1"
INPUT_CONTRACT_VERSION = "BIFROST-DECISION-INPUT-v0.1"

SPECIALIST_TYPES = {"production", "quality", "supply"}
STATUS_ENUM = {"completed", "warning", "blocked", "needs_confirmation"}
STATUS_PRIORITY = {"blocked": 4, "needs_confirmation": 3, "warning": 2, "completed": 1}
SEVERITY_ENUM = {"unknown", "low", "medium", "high"}
FORBIDDEN_SEVERITY = {"critical", "ok", "no_data", "failed"}
CAUSAL_LEVELS = {"direct_verified", "indirect_verified", "associated_risk", "insufficient"}
PRIORITY_ENUM = {"low", "medium", "high"}
VALIDATION_STATUS = {"passed", "warning", "failed", "blocked_by_evidence"}

# 占位/虚假证据引用关键词（出现即视为不可解析）
PLACEHOLDER_EVIDENCE_TOKENS = (
    "no_evidence", "no_provenance", "unknown", "placeholder", "dummy",
    "null", "none", "n/a", "todo", "tbd", "fabricated", "fake",
)

DATA_GAP_DEDUP_KEYS = (
    "semantic_entity", "semantic_field", "reason",
    "value_consumption_status", "required_resolution",
)

# ---- 字段级 EvidenceRef 规范 -------------------------------------------------
EVREF_PREFIX = "EVREF-v1:"

# 构建规范 EvidenceRef 所需的 canonical 字段（全部来自 normalized_fact 及其
# provenance_ref.evidence_locator）。任一缺失则该事实无法生成合法 EVREF。
EVREF_CANONICAL_KEYS = (
    "semantic_record_key",
    "semantic_field",
    "source_file_sha256",
    "source_table",
    "source_row_number",
    "source_column_name",
    "source_column_index",
)


class ValidationError(Exception):
    pass


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _jsonschema_available() -> bool:
    try:
        import jsonschema  # noqa: F401
        return True
    except Exception:
        return False


def _struct_validate(doc: dict, schema: dict) -> list[str]:
    """结构校验。优先使用 jsonschema；不可用时回退到内置最小校验。"""
    errs: list[str] = []
    if _jsonschema_available():
        import jsonschema
        try:
            jsonschema.validate(doc, schema)
        except jsonschema.ValidationError as e:
            path = "/".join(str(p) for p in e.absolute_path) or "<root>"
            errs.append(f"struct: {path}: {e.message}")
    else:
        errs.extend(_fallback_struct(doc, schema, ""))
    return errs


def _fallback_struct(doc: Any, schema: dict, path: str) -> list[str]:
    errs: list[str] = []
    if schema.get("type") == "object" and isinstance(doc, dict):
        for req in schema.get("required", []):
            if req not in doc:
                errs.append(f"struct: {path or '<root>'}: missing required '{req}'")
        props = schema.get("properties", {})
        for k, v in doc.items():
            if k in props:
                errs.extend(_fallback_struct(v, props[k], f"{path}/{k}" if path else k))
            elif schema.get("additionalProperties") is False:
                errs.append(f"struct: {path or '<root>'}: additional property '{k}' not allowed")
    elif schema.get("type") == "array" and isinstance(doc, list):
        items = schema.get("items", {})
        for i, it in enumerate(doc):
            errs.extend(_fallback_struct(it, items, f"{path}[{i}]"))
    elif "enum" in schema and doc not in schema["enum"]:
        errs.append(f"struct: {path}: '{doc}' not in {schema['enum']}")
    elif "const" in schema and doc != schema["const"]:
        errs.append(f"struct: {path}: '{doc}' != const '{schema['const']}'")
    return errs


# ---- 字段级 EvidenceRef 构建 -------------------------------------------------
def _canonical_evidence_payload(normalized_fact: dict) -> dict | None:
    """从 normalized_fact 抽取确定性 canonical 载荷。

    source_table 优先取 evidence_locator.source_table，回退到
    normalized_fact.source_table（两者在 consumer v0.1.1 中一致）。
    任一关键字段缺失返回 None（该事实无法生成合法 EVREF）。
    """
    if not isinstance(normalized_fact, dict):
        return None
    prov = normalized_fact.get("provenance_ref") or {}
    el = prov.get("evidence_locator")
    if not isinstance(el, dict) or not el:
        return None
    record_key = normalized_fact.get("semantic_record_key")
    field = normalized_fact.get("semantic_field")
    src_sha = el.get("source_file_sha256")
    src_table = el.get("source_table")
    if not src_table:
        src_table = normalized_fact.get("source_table")
    src_row = el.get("source_row_number")
    src_col_name = el.get("source_column_name")
    src_col_idx = el.get("source_column_index")
    payload = {
        "semantic_record_key": record_key,
        "semantic_field": field,
        "source_file_sha256": src_sha,
        "source_table": src_table,
        "source_row_number": src_row,
        "source_column_name": src_col_name,
        "source_column_index": src_col_idx,
    }
    # 任一关键字段缺失/为空 → 无法生成合法 EVREF
    for k in EVREF_CANONICAL_KEYS:
        v = payload[k]
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
    return payload


def build_canonical_evidence_ref(normalized_fact: dict) -> str | None:
    """确定性构建字段级 EvidenceRef。

    规范形式：EVREF-v1:<SHA256>
    哈希输入为 canonical JSON（sort_keys + ensure_ascii + compact），
    包含 semantic_record_key / semantic_field / source_file_sha256 /
    source_table / source_row_number / source_column_name / source_column_index。
    输入事实缺少必要 evidence_locator 字段时返回 None。
    """
    payload = _canonical_evidence_payload(normalized_fact)
    if payload is None:
        return None
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{EVREF_PREFIX}{digest}"


def _evref_is_canonical_form(ref: str) -> bool:
    return isinstance(ref, str) and ref.startswith(EVREF_PREFIX) and len(ref) > len(EVREF_PREFIX)


def build_valid_evidence_index(decision_input: dict) -> dict[str, dict]:
    """从输入 normalized_facts 构建字段级合法 EvidenceRef 索引。

    仅纳入 value_consumption_status=usable 且能生成合法 EVREF 的事实。
    返回 {evref: {normalized_fact, semantic_field, semantic_record_key, evidence_locator}}。
    """
    index: dict[str, dict] = {}
    for nf in decision_input.get("normalized_facts", []) or []:
        if not isinstance(nf, dict):
            continue
        if nf.get("value_consumption_status") != "usable":
            continue
        evref = build_canonical_evidence_ref(nf)
        if evref is None:
            continue
        prov = nf.get("provenance_ref") or {}
        el = prov.get("evidence_locator") or {}
        index[evref] = {
            "normalized_fact": nf,
            "semantic_field": nf.get("semantic_field"),
            "semantic_record_key": nf.get("semantic_record_key"),
            "evidence_locator": el,
        }
    return index


def _collect_record_keys(decision_input: dict) -> set[str]:
    """收集输入中所有 normalized_fact 的 semantic_record_key（用于识别裸记录键引用）。"""
    keys: set[str] = set()
    for nf in decision_input.get("normalized_facts", []) or []:
        if isinstance(nf, dict):
            rk = nf.get("semantic_record_key")
            if isinstance(rk, str) and rk.strip():
                keys.add(rk)
    return keys


# ---- 占位证据检测 ------------------------------------------------------------
def _is_placeholder_evidence(ref: str) -> bool:
    if not isinstance(ref, str) or not ref.strip():
        return True
    low = ref.strip().lower()
    return any(tok in low for tok in PLACEHOLDER_EVIDENCE_TOKENS)


def _check_placeholder_refs(refs: list[str], where: str, errs: list[str]) -> None:
    for r in refs:
        if _is_placeholder_evidence(r):
            errs.append(f"semantic: {where} evidence_ref '{r}' is a forbidden placeholder/unknown token")


# ---- 业务事实判定 ------------------------------------------------------------
def _has_business_facts(doc: dict) -> bool:
    """是否存在形成业务结论的事实：非空 conclusion / metrics / causes / recommended_actions。"""
    if doc.get("conclusion") and str(doc["conclusion"]).strip():
        return True
    if doc.get("metrics"):
        return True
    if doc.get("causes"):
        return True
    if doc.get("recommended_actions"):
        return True
    return False


def _has_high_risk_action(doc: dict) -> bool:
    return any(a.get("is_high_risk") is True for a in doc.get("recommended_actions", []))


# ---- 语义门控 ----------------------------------------------------------------
def _semantic_check(doc: dict) -> list[str]:
    errs: list[str] = []

    # 0. 顶层契约常量
    if doc.get("contract_name") != CONTRACT_NAME:
        errs.append(f"semantic: contract_name must be '{CONTRACT_NAME}', got '{doc.get('contract_name')}'")
    if doc.get("contract_version") != CONTRACT_VERSION:
        errs.append(f"semantic: contract_version must be '{CONTRACT_VERSION}', got '{doc.get('contract_version')}'")

    # 1. specialist_type
    st = doc.get("specialist_type")
    if st not in SPECIALIST_TYPES:
        errs.append(f"semantic: specialist_type '{st}' not in {sorted(SPECIALIST_TYPES)}")

    # 2. status 枚举 + 禁用值
    status = doc.get("status")
    if status in FORBIDDEN_SEVERITY or status in {"ok", "no_data", "failed"}:
        errs.append(f"semantic: status '{status}' is forbidden (use {sorted(STATUS_ENUM)})")
    elif status not in STATUS_ENUM:
        errs.append(f"semantic: status '{status}' not in {sorted(STATUS_ENUM)}")

    # 3. severity 枚举 + 禁止 critical/ok/no_data/failed
    sev = doc.get("severity")
    if sev in FORBIDDEN_SEVERITY:
        errs.append(f"semantic: severity '{sev}' is forbidden (critical/ok/no_data/failed not allowed)")
    elif sev not in SEVERITY_ENUM:
        errs.append(f"semantic: severity '{sev}' not in {sorted(SEVERITY_ENUM)}")

    # 4. actor_can_execute 必须恒 false（顶层 + 每个 action）
    if doc.get("actor_can_execute") is not False:
        errs.append("semantic: top-level actor_can_execute must be false (permission contract)")
    for i, a in enumerate(doc.get("recommended_actions", [])):
        if a.get("actor_can_execute") is not False:
            errs.append(f"semantic: recommended_actions[{i}].actor_can_execute must be false")
        # 高风险门控一致性（单向：is_high_risk=true 的三项联动）
        if a.get("is_high_risk") is True:
            if a.get("needs_human_confirmation") is not True:
                errs.append(f"semantic: recommended_actions[{i}] is_high_risk=true but needs_human_confirmation!=true")
            if a.get("prohibited_auto_execute") is not True:
                errs.append(f"semantic: recommended_actions[{i}] is_high_risk=true but prohibited_auto_execute!=true")
            if a.get("actor_can_execute") is not False:
                errs.append(f"semantic: recommended_actions[{i}] is_high_risk=true but actor_can_execute!=false")

    # 5. validation 子结构
    val = doc.get("validation", {})
    if not isinstance(val, dict):
        errs.append("semantic: validation must be an object")
    else:
        for f in ("status", "issues", "warnings", "input_contract_valid",
                  "evidence_contract_valid", "output_contract_valid"):
            if f not in val:
                errs.append(f"semantic: validation missing '{f}'")
        if val.get("status") not in VALIDATION_STATUS and val.get("status") is not None:
            errs.append(f"semantic: validation.status '{val.get('status')}' not in {sorted(VALIDATION_STATUS)}")

    # 6. causes / metrics / actions 的 causal_evidence_level / priority / evidence_refs（子项必须非空）
    for i, c in enumerate(doc.get("causes", [])):
        cel = c.get("causal_evidence_level")
        if cel not in CAUSAL_LEVELS:
            errs.append(f"semantic: causes[{i}].causal_evidence_level '{cel}' not in {sorted(CAUSAL_LEVELS)}")
        refs = c.get("evidence_refs", [])
        if not refs:
            errs.append(f"semantic: causes[{i}].evidence_refs must be non-empty (business conclusion requires real evidence)")
        _check_placeholder_refs(refs, f"causes[{i}]", errs)
    for i, m in enumerate(doc.get("metrics", [])):
        refs = m.get("evidence_refs", [])
        if not refs:
            errs.append(f"semantic: metrics[{i}].evidence_refs must be non-empty (business metric requires real evidence)")
        _check_placeholder_refs(refs, f"metrics[{i}]", errs)
    for i, a in enumerate(doc.get("recommended_actions", [])):
        pr = a.get("priority")
        if pr not in PRIORITY_ENUM:
            errs.append(f"semantic: recommended_actions[{i}].priority '{pr}' not in {sorted(PRIORITY_ENUM)}")
        refs = a.get("evidence_refs", [])
        if not refs:
            errs.append(f"semantic: recommended_actions[{i}].evidence_refs must be non-empty (recommended action requires real evidence)")
        _check_placeholder_refs(refs, f"recommended_actions[{i}]", errs)

    # 7. 顶层 evidence_refs 条件化（替换 v0.1.1 的无条件非空）
    top_refs = doc.get("evidence_refs", [])
    _check_placeholder_refs(top_refs, "top-level", errs)
    if _has_business_facts(doc):
        # 有业务事实时顶层证据必须非空
        if not top_refs:
            errs.append("semantic: top-level evidence_refs must be non-empty when business facts (conclusion/metrics/causes/actions) exist")
    # blocked 或纯 data_gap warning 允许 evidence_refs=[] —— 不报错

    # 8. data_gaps 结构（每项 9 字段，含归并字段）+ 占位检测 + 归并去重校验
    _data_gap_check(doc, errs)

    # 9. 状态语义门控（含 v0.1.2 状态优先级双向强制）
    _status_semantic(doc, status, errs)

    # 10. 禁止顶层互不兼容字段
    forbidden_top = {"yield_analysis_summary", "blocked_status", "missing_severity_rule",
                     "blocked_code", "freeze_analysis_summary", "spc_analysis_summary",
                     "risk_classification", "input_validation", "stage", "generated_at",
                     "confidence_basis", "prohibited_auto_execute"}
    extra = forbidden_top & set(doc.keys())
    if extra:
        errs.append(f"semantic: forbidden top-level fields present (move to specialist_details): {sorted(extra)}")

    # 11. 禁止虚构 ID
    for f in ("confirmation_id", "ConfirmationID", "auto_execute_command",
              "executed_action_id", "DecisionID", "RunID"):
        if f in doc:
            errs.append(f"semantic: forbidden fabricated id field '{f}'")

    return errs


def _data_gap_check(doc: dict, errs: list[str]) -> None:
    gaps = doc.get("data_gaps", [])
    for i, g in enumerate(gaps):
        for f in ("semantic_entity", "semantic_field", "reason",
                  "value_consumption_status", "source_locator", "required_resolution",
                  "affected_record_count", "occurrence_count", "sample_source_locators"):
            if f not in g:
                errs.append(f"semantic: data_gaps[{i}] missing '{f}'")
        arc = g.get("affected_record_count")
        if isinstance(arc, int) and arc < 1:
            errs.append(f"semantic: data_gaps[{i}].affected_record_count must be >= 1, got {arc}")
        occ = g.get("occurrence_count")
        if isinstance(occ, int) and occ < 1:
            errs.append(f"semantic: data_gaps[{i}].occurrence_count must be >= 1, got {occ}")
        # affected_record_count（唯一 locator 数）不得超过 occurrence_count（原始条数）
        if isinstance(arc, int) and isinstance(occ, int) and arc > occ:
            errs.append(
                f"semantic: data_gaps[{i}].affected_record_count({arc}) must not exceed "
                f"occurrence_count({occ}); affected_record_count counts unique source_locators"
            )
        ssl = g.get("sample_source_locators")
        if isinstance(ssl, list) and len(ssl) > 3:
            errs.append(f"semantic: data_gaps[{i}].sample_source_locators must have at most 3 entries, got {len(ssl)}")
    # 归并去重校验：同 dedup-key 不得出现多条
    seen: dict[tuple, int] = {}
    for i, g in enumerate(gaps):
        key = tuple(str(g.get(k, "")) for k in DATA_GAP_DEDUP_KEYS)
        if key in seen:
            errs.append(
                f"semantic: data_gaps[{i}] duplicates data_gaps[{seen[key]}] on dedup key "
                f"(semantic_entity/semantic_field/reason/value_consumption_status/required_resolution); "
                f"data_gaps must be deterministically merged"
            )
        else:
            seen[key] = i


def _status_semantic(doc: dict, status: str | None, errs: list[str]) -> None:
    if status == "blocked":
        # blocked: 不得产生业务结论、指标、原因或动作
        if doc.get("conclusion") and str(doc["conclusion"]).strip():
            errs.append("semantic: blocked status must not produce a business conclusion")
        if doc.get("metrics"):
            errs.append("semantic: blocked status must not produce metrics")
        if doc.get("causes"):
            errs.append("semantic: blocked status must not produce causes")
        if doc.get("recommended_actions"):
            errs.append("semantic: blocked status must not produce recommended_actions")
    elif status == "warning":
        # warning: 允许返回事实，但必须同时返回 data_gaps
        if not doc.get("data_gaps"):
            errs.append("semantic: warning status must include data_gaps")
    elif status == "needs_confirmation":
        # needs_confirmation: 当前结果含高风险建议
        if not _has_high_risk_action(doc):
            errs.append("semantic: needs_confirmation status requires at least one high-risk action")
        if doc.get("needs_human_confirmation") is not True:
            errs.append("semantic: needs_confirmation status requires needs_human_confirmation=true")
    elif status == "completed":
        val = doc.get("validation", {})
        if val.get("status") == "failed":
            errs.append("semantic: completed status conflicts with validation.status=failed")
        if doc.get("data_gaps"):
            errs.append("semantic: completed status must not contain data_gaps that affect conclusions")

    # ---- v0.1.2 状态优先级双向强制 ----
    # 任一 is_high_risk=true 时，非 blocked 结果必须为 needs_confirmation。
    # 不允许高风险动作存在而 status=warning/completed。
    if _has_high_risk_action(doc) and status not in ("blocked", "needs_confirmation"):
        errs.append(
            f"semantic: status priority violation — high-risk action present but status='{status}'; "
            f"non-blocked result with high-risk action must be needs_confirmation "
            f"(priority: blocked > needs_confirmation > warning > completed)"
        )


def validate_output(doc: dict, schema: dict | None = None) -> tuple[bool, list[str]]:
    """校验一个 specialist result 文档。返回 (ok, errors)。"""
    errs: list[str] = []
    if schema is None:
        schema = _load_json(DEFAULT_OUTPUT_SCHEMA)
    errs.extend(_struct_validate(doc, schema))
    errs.extend(_semantic_check(doc))
    return (len(errs) == 0, errs)


def validate_input(doc: dict, schema: dict | None = None) -> tuple[bool, list[str]]:
    if schema is None:
        schema = _load_json(DEFAULT_INPUT_SCHEMA)
    errs = _struct_validate(doc, schema)
    if doc.get("contract_name") != INPUT_CONTRACT_NAME:
        errs.append(f"semantic: input contract_name must be '{INPUT_CONTRACT_NAME}'")
    if doc.get("contract_version") != INPUT_CONTRACT_VERSION:
        errs.append(f"semantic: input contract_version must be '{INPUT_CONTRACT_VERSION}'")
    if doc.get("source_write_performed") is not False:
        errs.append("semantic: input source_write_performed must be false")
    if doc.get("actor_can_execute") is not False:
        errs.append("semantic: input actor_can_execute must be false")
    return (len(errs) == 0, errs)


# ---- 跨输入输出证据验证（字段级） --------------------------------------------
def extract_valid_evidence_keys(decision_input: dict) -> set[str]:
    """[v0.1.3 字段级] 从输入 normalized_facts 提取字段级合法 EvidenceRef 集合。

    可解析条件：value_consumption_status=usable 且能生成合法 EVREF-v1。
    返回 EVREF-v1:<SHA256> 集合（字段事实级，非记录级）。
    """
    return set(build_valid_evidence_index(decision_input).keys())


def validate_specialist_result_against_input(
    result: dict, decision_input: dict
) -> tuple[bool, list[str]]:
    """跨输入输出字段级证据验证。

    metrics / causes / recommended_actions / top-level 的每条 evidence_ref
    必须是字段级 EVREF-v1 并能在输入 usable normalized_facts 中解析。
    metrics 的每条 evidence_ref 还必须解析到 semantic_field 与
    metric.semantic_field 一致的字段事实（字段绑定）。
    禁止占位引用；禁止裸 semantic_record_key；不得为满足 minItems 创建虚构 EVREF。
    返回 (ok, errors)。
    """
    errs: list[str] = []
    index = build_valid_evidence_index(decision_input)
    record_keys = _collect_record_keys(decision_input)

    def _resolve(ref: str, where: str, bind_field: str | None = False) -> None:
        # bind_field: None=不绑定; False=不绑定(占位); 字符串=绑定到该 semantic_field
        if _is_placeholder_evidence(ref):
            errs.append(f"evidence: {where} evidence_ref '{ref}' is a forbidden placeholder/unknown token")
            return
        # 禁止裸 semantic_record_key：非 EVREF-v1 规范形式但匹配输入记录键
        if not _evref_is_canonical_form(ref):
            if ref in record_keys:
                errs.append(
                    f"evidence: {where} evidence_ref '{ref}' is a bare semantic_record_key; "
                    f"field-level EVREF-v1 required (same record key is shared by multiple semantic_fields)"
                )
            else:
                errs.append(
                    f"evidence: {where} evidence_ref '{ref}' is not a canonical EVREF-v1 reference "
                    f"(must be 'EVREF-v1:<SHA256>' resolved from a usable normalized_fact)"
                )
            return
        if ref not in index:
            errs.append(
                f"evidence: {where} evidence_ref '{ref}' cannot be resolved against "
                f"input usable normalized_facts (not found among {len(index)} field-level evidence refs)"
            )
            return
        # 字段绑定：metrics 的证据必须来自与其 semantic_field 一致的字段事实
        if bind_field is not None and bind_field is not False:
            resolved_field = index[ref]["semantic_field"]
            if resolved_field != bind_field:
                errs.append(
                    f"evidence: {where} evidence_ref '{ref}' resolves to semantic_field "
                    f"'{resolved_field}' but metric declares semantic_field='{bind_field}'; "
                    f"a metric's evidence must come from the same field fact"
                )

    # metrics：字段绑定
    for i, m in enumerate(result.get("metrics", []) or []):
        mfield = m.get("semantic_field")
        for r in m.get("evidence_refs", []) or []:
            _resolve(r, f"metrics[{i}]", mfield)
    # causes / actions / top-level：仅成员校验
    for i, c in enumerate(result.get("causes", []) or []):
        for r in c.get("evidence_refs", []) or []:
            _resolve(r, f"causes[{i}]", None)
    for i, a in enumerate(result.get("recommended_actions", []) or []):
        for r in a.get("evidence_refs", []) or []:
            _resolve(r, f"recommended_actions[{i}]", None)
    for r in result.get("evidence_refs", []) or []:
        _resolve(r, "top-level", None)

    return (len(errs) == 0, errs)


# ---- data_gap 确定性归并 -----------------------------------------------------
def merge_data_gaps(raw_gaps: list[dict]) -> list[dict]:
    """按 semantic_entity + semantic_field + reason + value_consumption_status +
    required_resolution 去重归并。

    归并后每项包含：
      - 原始 6 字段（取首条）
      - affected_record_count：归并到该键的【唯一 source_locator】数
      - occurrence_count：归并到该键的【原始条目】数
      - sample_source_locators：最多 3 条源定位串（取前 3 条不重复）
    """
    merged: dict[tuple, dict] = {}
    order: list[tuple] = []
    for g in raw_gaps or []:
        key = tuple(str(g.get(k, "")) for k in DATA_GAP_DEDUP_KEYS)
        if key not in merged:
            merged[key] = {
                "semantic_entity": g.get("semantic_entity"),
                "semantic_field": g.get("semantic_field"),
                "reason": g.get("reason"),
                "value_consumption_status": g.get("value_consumption_status"),
                "source_locator": g.get("source_locator"),
                "required_resolution": g.get("required_resolution"),
                "affected_record_count": 0,
                "occurrence_count": 0,
                "sample_source_locators": [],
                "_locators_seen": set(),
            }
            order.append(key)
        entry = merged[key]
        entry["occurrence_count"] += 1
        loc = g.get("source_locator")
        loc_str = loc if isinstance(loc, str) else (json.dumps(loc, ensure_ascii=False) if loc is not None else None)
        if isinstance(loc_str, str) and loc_str.strip():
            if loc_str not in entry["_locators_seen"]:
                entry["_locators_seen"].add(loc_str)
                entry["affected_record_count"] += 1
                if len(entry["sample_source_locators"]) < 3:
                    entry["sample_source_locators"].append(loc_str)
        else:
            # 无 source_locator 的条目仍计入 affected_record_count（视为独立记录）
            entry["affected_record_count"] += 1
    # 清理内部字段
    result = []
    for k in order:
        e = merged[k]
        del e["_locators_seen"]
        result.append(e)
    return result


def input_schema_byte_identical(candidate_path: str, reference_path: str = DEFAULT_INPUT_SCHEMA) -> tuple[bool, str, str]:
    """校验输入 Schema 与本包权威 Schema 字节一致。"""
    with open(candidate_path, "rb") as f:
        a = f.read()
    with open(reference_path, "rb") as f:
        b = f.read()
    ha = hashlib.sha256(a).hexdigest()
    hb = hashlib.sha256(b).hexdigest()
    return (a == b, ha, hb)


def normalized_json_sha256(path: str) -> str:
    """规范化 JSON 哈希：sort_keys + ensure_ascii + compact。"""
    obj = _load_json(path)
    norm = json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# ---- 旧包差异扫描 ------------------------------------------------------------
def diff_old_schema(old_path: str) -> list[str]:
    """扫描一个旧专业输出 Schema 相对权威 v0.1.3 的差异点，返回差异描述列表。"""
    old = _load_json(old_path)
    ref = _load_json(DEFAULT_OUTPUT_SCHEMA)
    diffs: list[str] = []
    name = os.path.basename(old_path)

    props_old = old.get("properties", {})
    props_ref = ref.get("properties", {})

    old_status = props_old.get("status", {}).get("enum")
    ref_status = props_ref.get("status", {}).get("enum")
    if old_status != ref_status:
        diffs.append(f"{name}: status enum {old_status} !=权威 {ref_status}")

    old_sev = props_old.get("severity", {}).get("enum")
    ref_sev = props_ref.get("severity", {}).get("enum")
    if old_sev != ref_sev:
        diffs.append(f"{name}: severity enum {old_sev} !=权威 {ref_sev}")

    extra_top = sorted(set(props_old) - set(props_ref))
    if extra_top:
        diffs.append(f"{name}: 顶层额外字段 {extra_top}（权威合同禁止）")

    def _item_keys(p):
        it = p.get("items", {})
        return set(it.get("properties", {}).keys()) if isinstance(it, dict) else set()

    def _item_required(p):
        it = p.get("items", {})
        return set(it.get("required", [])) if isinstance(it, dict) else set()

    for fld in ("metrics", "causes", "recommended_actions", "data_gaps"):
        ok = _item_keys(props_old.get(fld, {}))
        rk = _item_keys(props_ref.get(fld, {}))
        missing = sorted(rk - ok)
        extra = sorted(ok - rk)
        if missing or extra:
            diffs.append(f"{name}: {fld} 子结构 缺失={missing} 额外={extra}")
        oreq = _item_required(props_old.get(fld, {}))
        rreq = _item_required(props_ref.get(fld, {}))
        if oreq != rreq:
            diffs.append(f"{name}: {fld} required {sorted(oreq)} !=权威 {sorted(rreq)}")

    ocv = props_old.get("contract_version", {}).get("const")
    if ocv != CONTRACT_VERSION:
        diffs.append(f"{name}: contract_version const '{ocv}' !=权威 '{CONTRACT_VERSION}'")

    has_validation = "validation" in props_old
    if not has_validation:
        diffs.append(f"{name}: 缺失顶层 validation 字段")

    return diffs


# ---- CLI ---------------------------------------------------------------------
def _cmd_validate(args):
    doc = _load_json(args.doc)
    schema = _load_json(args.schema) if args.schema else None
    ok, errs = validate_output(doc, schema)
    if ok:
        print(f"PASS: {args.doc}")
        return 0
    print(f"FAIL: {args.doc}")
    for e in errs:
        print(f"  - {e}")
    return 1


def _cmd_validate_input(args):
    doc = _load_json(args.doc)
    schema = _load_json(args.schema) if args.schema else None
    ok, errs = validate_input(doc, schema)
    if ok:
        print(f"PASS(input): {args.doc}")
        return 0
    print(f"FAIL(input): {args.doc}")
    for e in errs:
        print(f"  - {e}")
    return 1


def _cmd_validate_against_input(args):
    result = _load_json(args.doc)
    decision_input = _load_json(args.input)
    ok, errs = validate_specialist_result_against_input(result, decision_input)
    if ok:
        print(f"PASS(against-input): {args.doc}")
        return 0
    print(f"FAIL(against-input): {args.doc}")
    for e in errs:
        print(f"  - {e}")
    return 1


def _cmd_build_evref(args):
    di = _load_json(args.input)
    index = build_valid_evidence_index(di)
    out = []
    for evref, info in index.items():
        out.append({
            "evidence_ref": evref,
            "semantic_record_key": info["semantic_record_key"],
            "semantic_field": info["semantic_field"],
        })
    out.sort(key=lambda x: (x["semantic_record_key"] or "", x["semantic_field"] or ""))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _cmd_merge_gaps(args):
    doc = _load_json(args.doc)
    merged = merge_data_gaps(doc.get("data_gaps", []))
    print(json.dumps(merged, ensure_ascii=False, indent=2))
    return 0


def _cmd_diff(args):
    diffs = diff_old_schema(args.old)
    if not diffs:
        print(f"NO_DIFF: {args.old}")
        return 0
    print(f"DIFF({len(diffs)}): {args.old}")
    for d in diffs:
        print(f"  - {d}")
    return len(diffs)


def _cmd_input_check(args):
    ok, ha, hb = input_schema_byte_identical(args.doc)
    print(f"candidate_sha256={ha}")
    print(f"reference_sha256={hb}")
    print("BYTE_IDENTICAL_OK" if ok else "BYTE_MISMATCH")
    return 0 if ok else 1


def main(argv=None):
    p = argparse.ArgumentParser(description="BIFROST 专业诊断合同独立验证器 v0.1.3")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="校验 specialist result 输出文档")
    v.add_argument("--doc", required=True)
    v.add_argument("--schema")
    v.set_defaults(func=_cmd_validate)
    vi = sub.add_parser("validate-input", help="校验 decision input 输入文档")
    vi.add_argument("--doc", required=True)
    vi.add_argument("--schema")
    vi.set_defaults(func=_cmd_validate_input)
    vai = sub.add_parser("validate-against-input", help="跨输入输出字段级证据验证")
    vai.add_argument("--doc", required=True)
    vai.add_argument("--input", required=True)
    vai.set_defaults(func=_cmd_validate_against_input)
    be = sub.add_parser("build-evref", help="从 decision_input 构建字段级 EvidenceRef 索引")
    be.add_argument("--input", required=True)
    be.set_defaults(func=_cmd_build_evref)
    mg = sub.add_parser("merge-gaps", help="对 data_gaps 执行确定性归并")
    mg.add_argument("--doc", required=True)
    mg.set_defaults(func=_cmd_merge_gaps)
    d = sub.add_parser("diff", help="扫描旧包 Schema 差异")
    d.add_argument("old")
    d.set_defaults(func=_cmd_diff)
    ic = sub.add_parser("input-check", help="校验输入 Schema 字节一致性")
    ic.add_argument("--doc", required=True)
    ic.set_defaults(func=_cmd_input_check)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

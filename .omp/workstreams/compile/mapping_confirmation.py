"""Versioned, auditable mapping confirmation contract."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable


def _mapping_id(item: dict[str, Any]) -> str:
    raw = f"{item.get('source_table','')}::{item.get('source_field','')}::{item.get('target_entity','')}::{item.get('target_field','')}"
    return "MAPITEM-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12].upper()


def build_mapping_manifest(
    mapping_response: dict[str, Any],
    confirmations: Iterable[str] | None = None,
    *,
    version: str = "MAP-RUNTIME-v1.0",
    auto_threshold: float = 0.95,
) -> dict[str, Any]:
    """Create a manifest without silently approving ambiguous mappings."""
    explicit = set(confirmations or [])
    entries: list[dict[str, Any]] = []
    for source in mapping_response.get("mapping_draft", []) or []:
        if not isinstance(source, dict) or not source.get("target_field"):
            continue
        item = dict(source)
        # Providers sometimes classify the Chinese header ``产线`` as a
        # display label.  It is the physical grouping key in the source
        # contract; normalize this one unambiguous header before approval so
        # dynamic projections do not lose the line dimension.
        source_field = str(item.get("source_field") or "").strip()
        if source_field in {"产线", "LineID", "产线ID", "line_id", "lineid"}:
            item["target_field"] = "line_id"
        elif source_field in {"产线名称", "line_name"}:
            item["target_field"] = "line_name"
        item["mapping_id"] = _mapping_id(item)
        confidence = float(item.get("confidence") or 0)
        fallback_requires_confirmation = bool(item.get("fallback_requires_confirmation"))
        existing = item.get("mapping_status")
        inherited = bool(item.get("inherited_approval")) and not bool(item.get("inherited_approval_suspended"))
        exact_alias = item.get("target_field") in EXACT_DOMAIN_ALIASES and str(item.get("source_field")) in EXACT_DOMAIN_ALIASES[item.get("target_field")]
        # Deterministic provider fallback is intentionally advisory.  Even an
        # exact alias must remain pending until the user explicitly confirms
        # its mapping id; this prevents a provider outage from creating KPI
        # rows from an unreviewed guess.
        approved = item["mapping_id"] in explicit or (
            not fallback_requires_confirmation
            and (inherited or exact_alias or (existing == "confirmed" and confidence >= auto_threshold))
        )
        item["runtime_status"] = "approved" if approved else "needs_confirmation"
        item["requires_human_confirmation"] = not approved
        item["approval_reason"] = "explicit_confirmation" if item["mapping_id"] in explicit else "deterministic_fallback_requires_confirmation" if fallback_requires_confirmation else "inherited_approved_contract" if inherited else "exact_domain_alias" if exact_alias else "approved_contract_high_confidence" if approved else "confidence_or_ambiguity"
        entries.append(item)
    return {
        "contract_version": "BIFROST_MAPPING_MANIFEST_v1",
        "mapping_version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_id": mapping_response.get("source_identity", {}).get("detected_source_family", "UNKNOWN"),
        "entries": entries,
        "approved_count": sum(item["runtime_status"] == "approved" for item in entries),
        "confirmation_count": sum(item["runtime_status"] == "needs_confirmation" for item in entries),
        "status": "approved" if entries and all(item["runtime_status"] == "approved" for item in entries) else "needs_confirmation",
        "read_only": True,
        "source_write_performed": False,
    }


__all__ = ["build_mapping_manifest"]
EXACT_DOMAIN_ALIASES = {
    "availability": {"开动率", "availability", "available_rate"},
    "performance_rate_raw": {"性能率", "performance_rate", "performance_rate_raw"},
    "quality_rate": {"质量率", "quality_rate", "yield", "yield_rate", "良率(%)", "良率"},
    "total_output": {"总产量", "total_output", "产量", "实际产量", "实际产量(件)"},
    "good_output": {"良品数", "good_output", "合格品数", "良品数量"},
    "oee_source": {"OEE", "OEE(%)", "oee", "oee_source"},
    # “产线” is the source key used for grouping.  Keep “产线名称” as the
    # optional display label; treating the former as line_name silently drops
    # the dimension from dynamic projections.
    "line_id": {"LineID", "产线", "产线ID", "line_id"},
    "line_name": {"产线名称", "line_name"},
    "shift_date": {"班次日期", "生产日期", "日期", "shift_date", "date"},
    "production_date": {"生产日期", "production_date"},
    "actual_qty": {"实际产量", "actual_qty", "actual_output"},
    "phase": {"阶段", "phase", "stage"},
}

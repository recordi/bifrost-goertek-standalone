"""Compile canonical rows into one safe Overview/Event payload pair."""

from __future__ import annotations

from typing import Any

try:  # package import from the pipeline
    from .view_projection import build_view_projection
except ImportError:  # direct import from the standalone test runner
    from view_projection import build_view_projection


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _capability(records: list[dict[str, Any]], required: tuple[str, ...]) -> dict[str, Any]:
    aliases = {"performance_rate": ("performance_rate", "performance_rate_raw"), "quality_rate": ("quality_rate", "quality_factor")}
    present = {key for record in records for key in record if record.get(key) is not None}
    missing = sorted(key for key in required if not any(alias in present for alias in aliases.get(key, (key,))))
    return {"status": "available" if not missing else "not_observable", "missing_fields": missing, "calculation_allowed": not missing}


def compile_payloads(source_profile: dict[str, Any], mapping_manifest: dict[str, Any], canonical: dict[str, Any]) -> dict[str, Any]:
    records = canonical.get("records", [])
    projection = build_view_projection(records)
    projection["view_coverage"].update({
        "source_file_name": source_profile.get("file_name"),
        "source_sha256": source_profile.get("source_sha256"),
        "provenance_status": "physical_source_dimensions",
        "source_truncation": canonical.get("truncation", {"truncated": False}),
    })
    capabilities = {
        "oee": _capability(records, ("availability", "performance_rate", "quality_rate")),
        "yield": _capability(records, ("total_output", "good_output")),
        "spc": _capability(records, ("spc_measurement_points", "usl", "lsl", "sample_rule")),
        "mtbf": _capability(records, ("equipment_id", "failure_start", "failure_end")),
        "supply_risk": _capability(records, ("material_id", "required_quantity", "available_quantity")),
    }
    observed_oee = [_number(record.get("oee_source")) for record in records]
    observed_oee = [value for value in observed_oee if value is not None]
    if observed_oee:
        capabilities["oee"]["source_observed"] = True
        capabilities["oee"]["observed_source_count"] = len(observed_oee)
        capabilities["oee"]["value_mode"] = "observed_source" if not capabilities["oee"]["calculation_allowed"] else "recomputed_with_source_available"
        # A source OEE is useful for a cross-source view, but it is not a
        # substitute for A×P×Q. Keep the missing component fields visible.
        if not capabilities["oee"]["calculation_allowed"]:
            capabilities["oee"]["status"] = "available"
    metrics: dict[str, Any] = {}
    if capabilities["oee"]["calculation_allowed"]:
        values = []
        for record in records:
            parts = [
                _number(record.get("availability")),
                _number(record.get("performance_rate", record.get("performance_rate_raw"))),
                _number(record.get("quality_rate", record.get("quality_factor"))),
            ]
            if all(value is not None for value in parts):
                values.append(parts[0] * parts[1] * parts[2])
        if values:
            metrics["oee"] = {"label": "综合设备效率（OEE，复算）", "value": sum(values) / len(values), "evidence_count": len(values), "value_mode": "recomputed"}
    if "oee" not in metrics and observed_oee:
        metrics["oee"] = {"label": "来源 OEE（未完成 A×P×Q 复算）", "value": sum(observed_oee) / len(observed_oee), "evidence_count": len(observed_oee), "value_mode": "observed_source", "calculation_allowed": False}
    yield_values = []
    for record in records:
        total = _number(record.get("total_output"))
        good = _number(record.get("good_output"))
        if total and good is not None:
            yield_values.append(good / total)
    if yield_values:
        metrics["yield"] = {"label": "良率（复算）", "value": sum(yield_values) / len(yield_values), "evidence_count": len(yield_values), "value_mode": "recomputed"}
    else:
        observed_yield = [_number(record.get("quality_rate")) for record in records]
        observed_yield = [value for value in observed_yield if value is not None]
        if observed_yield:
            metrics["yield"] = {"label": "来源良率（未复算）", "value": sum(observed_yield) / len(observed_yield), "evidence_count": len(observed_yield), "value_mode": "observed_source", "calculation_allowed": False}
    lines = projection["view_coverage"].get("lines", [])
    source_sha = str(source_profile.get("source_sha256") or "")
    dynamic_event_id = f"EVT-DYNAMIC-{source_sha[:12] or 'UNHASHED'}"
    roles = ["factory", "line", "quality", "equipment", "process", "supply"]
    role_scopes = {
        "factory": "ALL_LINES",
        "line": lines[0] if lines else "ALL_LINES",
        "quality": "ALL_LINES",
        "equipment": "ALL_LINES",
        "process": "ALL_LINES",
        "supply": "ALL_LINES",
    }
    event_roles = []
    projection_snapshots = projection.get("view_snapshots", [])

    def role_snapshot(role: str, scope: str) -> dict[str, Any] | None:
        matches = [
            item for item in projection_snapshots
            if item.get("role") == role and item.get("view_key", "").endswith(f"|{scope}|full_history")
        ]
        return matches[0] if matches else None

    for role in roles:
        role_scope = role_scopes[role]
        snapshot = role_snapshot(role, role_scope)
        role_kpis = snapshot.get("kpis", []) if snapshot else []
        role_gaps = [] if snapshot and role_kpis else [
            {"metric": name, "missing_fields": info["missing_fields"]}
            for name, info in capabilities.items() if info["missing_fields"]
        ]
        # Specialist snapshots currently reuse the production evidence slice
        # so that a role/line view never silently falls back to factory data.
        # Reused OEE/YIELD is therefore only partial evidence for a specialist
        # role; do not advertise it as a complete, role-specific view.
        shared_specialist = role in roles[2:] and bool(snapshot and role_kpis)
        if shared_specialist:
            role_gaps = [
                {"metric": name, "missing_fields": info["missing_fields"]}
                for name, info in capabilities.items() if info["missing_fields"]
            ]
            if not role_gaps:
                role_gaps = [{"metric": f"{role}_specific_evidence", "missing_fields": ["role_specific_source_fields"]}]
        role_status = "partial" if shared_specialist else ("ready" if role_kpis else "needs_confirmation")
        role_scope_payload = (
            {"mode": "all_lines", "line_ids": lines}
            if role_scope == "ALL_LINES"
            else {"mode": "single_line", "line_ids": [role_scope]}
        )
        event_role = {
            "role": role,
            "scope": role_scope_payload,
            "status": role_status,
            "kpis": role_kpis,
            "tasks": [],
            "alerts": [],
            "data_gaps": role_gaps,
            "evidence_refs": snapshot.get("evidence_refs", []) if snapshot else [],
        }
        if shared_specialist:
            event_role["role_projection"] = "shared_production_evidence"
        event_roles.append(event_role)
    dimensions = {
        "lines": [{"line_id": line, "label": line} for line in lines],
        "roles": [
            {"role": "factory", "default_scope": "ALL_LINES", "allowed_line_ids": lines},
            {"role": "line", "default_scope": lines[0] if lines else "ALL_LINES", "allowed_line_ids": lines},
            *[{"role": role, "default_scope": "ALL_LINES", "allowed_line_ids": lines} for role in roles[2:]],
        ],
    }
    return {
        "overview": {
            "payload_type": "overview",
            "contract_version": "BIFROST_OVERVIEW_DYNAMIC_v1",
            "source_profile": source_profile,
            "mapping_version": mapping_manifest.get("mapping_version"),
            "capability_manifest": capabilities,
            "metrics": metrics,
            "dimensions": dimensions,
            "view_snapshots": projection["view_snapshots"],
            "view_coverage": projection["view_coverage"],
            "record_count": canonical.get("record_count", 0),
            "evidence_count": len(canonical.get("evidence_index", [])),
            "source_write_performed": False,
        },
        "event": {
            "payload_type": "event_detail",
            "contract_version": "BIFROST_EVENT_DYNAMIC_v1",
            "event_id": dynamic_event_id,
            "headline": "当前数据源的跨角色分析结果（动态生成）",
            "line_ids": lines,
            "data_as_of": source_profile.get("data_as_of"),
            "mapping_version": mapping_manifest.get("mapping_version"),
            "status": "ready" if metrics else "needs_confirmation",
            "conclusion": {
                "headline": "已生成跨角色分析" if metrics else "数据尚未足以生成统一结论",
                "summary": "指标来自统一字段映射与当前数据源证据；专业角色若仅复用生产证据，会明确标记为部分可用。",
                "needs_human_confirmation": not bool(metrics),
            },
            "capability_manifest": capabilities,
            "roles": event_roles,
            "view_coverage": projection["view_coverage"],
            "evidence_index": canonical.get("evidence_index", []),
            "data_gaps": [
                {"metric": name, "missing_fields": info["missing_fields"]}
                for name, info in capabilities.items() if info["missing_fields"]
            ],
            "source_write_performed": False,
        },
    }


__all__ = ["compile_payloads"]

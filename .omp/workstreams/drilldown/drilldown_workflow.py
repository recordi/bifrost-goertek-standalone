"""Dataset-agnostic production drill-down helpers.

The workflow operates on canonical rows and semantic fields, never on a
specific workbook name or a fixed production-line list. It returns facts and
evidence first; causal language is only emitted as a ranked *candidate* and
is never presented as a confirmed root cause without supporting evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from typing import Any


DIMENSION_ALIASES: dict[str, tuple[str, ...]] = {
    "line": ("line_id", "production_line", "line"),
    "date": ("shift_date", "production_date", "date", "event_date", "timestamp"),
    "shift": ("shift_id", "shift", "shift_name", "班次"),
    "work_order": ("work_order_id", "work_order", "order_no", "工单号"),
    "product": ("product_id", "product_code", "model", "product"),
    "equipment": ("equipment_id", "machine_id", "equipment", "设备编号"),
    "material": ("material_id", "material_code", "business_key", "物料编码"),
    "defect": ("defect_type", "defect_code", "defect", "不良类型"),
    "stop_reason": ("stop_reason", "reason_code", "downtime_reason", "停机原因", "group"),
    "process": ("process_step", "operation", "process", "工序"),
}

FACT_GROUPS: dict[str, tuple[str, ...]] = {
    "downtime": ("duration_minutes", "downtime_minutes", "minutes", "stop_minutes"),
    "defect_count": ("defect_count", "defect_qty", "bad_qty", "defect_total", "不良数"),
    "output": ("total_output", "actual_output", "quantity", "产量"),
    "quality": ("quality_rate", "yield_recompute", "yield_rate", "良率"),
}


def _first_value(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for key in aliases:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _numeric(row: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    value = _first_value(row, aliases)
    if isinstance(value, bool):
        return None
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def infer_dimensions(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Describe observed dimensions without assuming they exist."""
    total = len(records)
    result: dict[str, dict[str, Any]] = {}
    for dimension, aliases in DIMENSION_ALIASES.items():
        values = [_first_value(row, aliases) for row in records]
        present = [str(value) for value in values if value not in (None, "")]
        result[dimension] = {
            "available": bool(present),
            "field_aliases": list(aliases),
            "observed_count": len(present),
            "coverage": round(len(present) / total, 4) if total else 0.0,
            "distinct_count": len(set(present)),
            "values_preview": sorted(set(present))[:20],
        }
    return result


def _evidence(row: dict[str, Any]) -> str | None:
    value = row.get("evidence_ref") or row.get("evidence_id")
    return str(value) if value not in (None, "") else None


def _match(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    for dimension, expected in (filters or {}).items():
        aliases = DIMENSION_ALIASES.get(dimension, (dimension,))
        actual = _first_value(row, aliases)
        wanted = expected if isinstance(expected, (list, tuple, set)) else [expected]
        if actual not in wanted and str(actual) not in {str(item) for item in wanted}:
            return False
    return True


def _fact_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"record_count": len(rows)}
    for name, aliases in FACT_GROUPS.items():
        values = [value for value in (_numeric(row, aliases) for row in rows) if value is not None]
        if values:
            result[name] = {"sum": round(sum(values), 4), "average": round(sum(values) / len(values), 4), "count": len(values)}
    refs = sorted({ref for row in rows if (ref := _evidence(row))})
    result["evidence_refs"] = refs
    result["evidence_count"] = len(refs)
    return result


def _rank_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank observable associations; never label them as confirmed causes."""
    candidates: list[dict[str, Any]] = []
    for category, aliases in (("停机原因", DIMENSION_ALIASES["stop_reason"]), ("不良类型", DIMENSION_ALIASES["defect"]), ("设备", DIMENSION_ALIASES["equipment"]), ("工序", DIMENSION_ALIASES["process"]), ("物料", DIMENSION_ALIASES["material"])):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            value = _first_value(row, aliases)
            if value not in (None, ""):
                groups[str(value)].append(row)
        for label, group in groups.items():
            summary = _fact_summary(group)
            impact = summary.get("downtime", {}).get("sum", 0) + summary.get("defect_count", {}).get("sum", 0)
            candidates.append({
                "category": category,
                "label": label,
                "record_count": len(group),
                "impact_score": round(impact, 4),
                "evidence_refs": summary["evidence_refs"],
                "interpretation": "关联线索，尚不能单独证明根因",
            })
    return sorted(candidates, key=lambda item: (-item["impact_score"], -item["record_count"], item["category"], item["label"]))[:20]


def build_drilldown_manifest(records: list[dict[str, Any]], *, source_sha256: str | None = None) -> dict[str, Any]:
    """Create a reusable drill-down capability contract for any source."""
    dimensions = infer_dimensions(records)
    available = [name for name, info in dimensions.items() if info["available"]]
    levels = [
        {"level": "overview", "requires": [], "available": True},
        {"level": "time_slice", "requires": ["date"], "available": dimensions["date"]["available"]},
        {"level": "shift", "requires": ["shift"], "available": dimensions["shift"]["available"]},
        {"level": "work_order", "requires": ["work_order"], "available": dimensions["work_order"]["available"]},
        {"level": "event_evidence", "requires": ["equipment", "stop_reason", "defect", "material"], "available": any(dimensions[key]["available"] for key in ("equipment", "stop_reason", "defect", "material"))},
    ]
    return {
        "contract_version": "BIFROST_DRILLDOWN_MANIFEST_v1",
        "source_sha256": source_sha256,
        "record_count": len(records),
        "dimensions": dimensions,
        "available_dimensions": available,
        "levels": levels,
        "join_policy": "semantic_fields_then_shared_evidence_refs; no_fixed_table_names",
        "root_cause_policy": "ranked_association_only_until_evidence_gate_passes",
        "data_gaps": [f"missing_{name}" for name, info in dimensions.items() if not info["available"]],
        "source_write_performed": False,
    }


def query_drilldown(records: list[dict[str, Any]], *, filters: dict[str, Any] | None = None, source_sha256: str | None = None) -> dict[str, Any]:
    """Return facts, candidate associations, and missing dimensions for a query."""
    selected = [row for row in records if _match(row, filters or {})]
    manifest = build_drilldown_manifest(selected, source_sha256=source_sha256)
    return {
        "contract_version": "BIFROST_DRILLDOWN_RESULT_v1",
        "filters": filters or {},
        "facts": _fact_summary(selected),
        "root_cause_candidates": _rank_candidates(selected),
        "dimensions": manifest["dimensions"],
        "data_gaps": manifest["data_gaps"],
        "evidence_refs": sorted({ref for row in selected if (ref := _evidence(row))}),
        "confidence": "evidence_backed_facts_only" if selected else "no_matching_records",
        "source_write_performed": False,
        "actor_can_execute": False,
    }


__all__ = ["build_drilldown_manifest", "query_drilldown", "infer_dimensions"]

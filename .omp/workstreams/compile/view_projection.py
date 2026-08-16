"""Truthful role/line/time-window projection for dynamic payloads.

Only dimensions physically present in canonical rows are projected. Missing
dimensions produce no fabricated views; the payload exposes coverage instead.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _ratio(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row.get(key) for row in rows if isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool)]
    return sum(values) / len(values) if values else None


def _date_value(row: dict[str, Any]) -> date | None:
    value = _value(row, "shift_date", "production_date", "date", "event_date", "timestamp")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed.date()
    except ValueError:
        pass
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _metric_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metric_keys = {
        "oee_recomputed", "oee_source", "yield_recompute", "quality_rate",
        "availability", "performance_rate", "performance_rate_raw",
        "total_output", "good_output",
    }
    detail_keys = {"defect_type", "defect_count", "stop_reason", "downtime_minutes", "duration_min", "changeover_overtime_min"}
    return [row for row in records if any(isinstance(row.get(key), (int, float)) and not isinstance(row.get(key), bool) for key in metric_keys) or any(row.get(key) not in (None, "") for key in detail_keys)]


def _detail_rows(records: list[dict[str, Any]], *, label_keys: tuple[str, ...], value_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in records:
        label = _value(row, *label_keys)
        value = _value(row, *value_keys)
        if label in (None, "") or not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        key = str(label)
        item = grouped.setdefault(key, {"label": key, "count": 0.0, "evidence_refs": []})
        item["count"] += float(value)
        ref = row.get("evidence_ref")
        if isinstance(ref, str) and ref:
            item["evidence_refs"].append(ref)
    result = []
    for item in grouped.values():
        item["count"] = int(item["count"]) if item["count"].is_integer() else round(item["count"], 2)
        item["evidence_refs"] = sorted(set(item["evidence_refs"]))
        result.append(item)
    return sorted(result, key=lambda item: item["count"], reverse=True)


def _active_line_ids(metric_rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Separate comparable production lines from source-lineage identifiers.

    The team workbook intentionally contains the original public single-line
    lineage (``LINE-R01``) alongside simulated comparison lines
    (``LINE-S01``/…).  The lineage must remain available for provenance, but
    it must not become a fourth production line in the operational views.
    Official workbooks use their observed line identifiers unchanged.
    """
    observed = sorted({
        str(value)
        for row in metric_rows
        if (value := _value(row, "line_id")) is not None
    })
    simulated = [line for line in observed if line.upper().startswith("LINE-S")]
    lineage = [line for line in observed if line.upper().startswith("LINE-R")]
    if simulated and lineage:
        return simulated, lineage
    return observed, []


def _phase(row: dict[str, Any]) -> str | None:
    raw = _value(row, "phase", "stage", "improvement_phase", "改进阶段")
    if raw in (None, ""):
        return None
    text = str(raw).strip().lower()
    if any(token in text for token in ("改善前", "改善前段", "before", "pre")):
        return "before_improvement"
    if any(token in text for token in ("改善后", "改善后段", "after", "post")):
        return "after_improvement"
    return None


def _windows(rows: list[dict[str, Any]]) -> tuple[list[tuple[str, str, list[dict[str, Any]]]], dict[str, str]]:
    """Build only windows supported by observed date/phase fields."""
    result: list[tuple[str, str, list[dict[str, Any]]]] = [("full_history", "全历史", rows)]
    omitted: dict[str, str] = {}
    dated = [(idx, _date_value(row), row) for idx, row in enumerate(rows)]
    dated = [(idx, value, row) for idx, value, row in dated if value is not None]
    if dated:
        ordered = [row for _, _, row in sorted(dated, key=lambda item: (item[1], item[0]))]
        for count in (7, 30):
            result.append((f"recent_{count}_shifts", f"最近{count}个班次", ordered[-count:]))
    else:
        omitted["recent_7_shifts"] = "未观察到日期字段"
        omitted["recent_30_shifts"] = "未观察到日期字段"
    phases = {_phase(row) for row in rows}
    if {"before_improvement", "after_improvement"}.issubset(phases):
        result.append(("before_improvement", "改善前", [row for row in rows if _phase(row) == "before_improvement"]))
        result.append(("after_improvement", "改善后", [row for row in rows if _phase(row) == "after_improvement"]))
    else:
        omitted["before_improvement"] = "未同时观察到改善前与改善后阶段"
        omitted["after_improvement"] = "未同时观察到改善前与改善后阶段"
    return result, omitted


def build_view_projection(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return only evidence-backed view snapshots and coverage metadata."""
    metric_rows = _metric_rows(records)
    # Only the canonical identifier participates in scope/join logic. A
    # human-readable line_name remains display metadata and is never treated
    # as an ID.
    observed_lines = sorted({
        str(value)
        for row in metric_rows
        if (value := _value(row, "line_id")) is not None
    })
    lines, excluded_lineage = _active_line_ids(metric_rows)
    active_set = set(lines)
    projected_rows = [
        row for row in metric_rows
        if _value(row, "line_id") in (None, "") or str(_value(row, "line_id")) in active_set
    ]
    metric_rows = projected_rows
    dated_rows = [row for row in projected_rows if _date_value(row) is not None]
    windows, omitted_windows = _windows(metric_rows) if metric_rows else ([], {"recent_7_shifts": "没有可计算指标记录", "recent_30_shifts": "没有可计算指标记录", "before_improvement": "没有可计算指标记录", "after_improvement": "没有可计算指标记录"})
    scopes = ["ALL_LINES", *lines] if lines else ["ALL_LINES"]
    role_names = ["factory", "line", "quality", "equipment", "process", "supply"]

    snapshots: list[dict[str, Any]] = []
    for window_id, window_label, window_rows in windows:
        for scope in scopes:
            rows = window_rows if scope == "ALL_LINES" else [row for row in window_rows if str(_value(row, "line_id")) == scope]
            if not rows:
                continue
            kpis: list[dict[str, Any]] = []
            oee = _ratio(rows, "oee_recomputed")
            oee_mode = "recomputed"
            if oee is None:
                oee = _ratio(rows, "oee_source")
                oee_mode = "observed_source" if oee is not None else None
            if oee is not None:
                kpis.append({"metric_code": "OEE", "label": "综合设备效率（OEE，复算）" if oee_mode == "recomputed" else "来源 OEE（未复算）", "value": oee, "value_type": "ratio", "display_format": "0.0%", "status": "available", "value_mode": oee_mode})
            # Preserve observed A/P/Q components when the source provides
            # them.  A loss-tree analysis may consume these fields, but it
            # must never derive them from an observed OEE value.
            for metric_code, source_keys, label in (
                ("AVAILABILITY", ("availability",), "开动率"),
                ("PERFORMANCE", ("performance_rate", "performance_rate_raw"), "性能率"),
                ("QUALITY", ("quality_rate", "quality_factor"), "质量率"),
            ):
                component = next((_ratio(rows, key) for key in source_keys if _ratio(rows, key) is not None), None)
                if component is not None:
                    kpis.append({
                        "metric_code": metric_code,
                        "label": label,
                        "value": component,
                        "value_type": "ratio",
                        "display_format": "0.0%",
                        "status": "available",
                        "value_mode": "observed_source",
                    })
            yield_rate = _ratio(rows, "yield_recompute")
            if yield_rate is None:
                yield_rate = _ratio(rows, "quality_rate")
            if yield_rate is not None:
                kpis.append({"metric_code": "YIELD", "label": "良率（复算）" if any(row.get("yield_recompute") is not None for row in rows) else "来源良率", "value": yield_rate, "value_type": "ratio", "display_format": "0.0%", "status": "available"})
            dates = [_date_value(row) for row in rows]
            dates = [value for value in dates if value is not None]
            time_window = {"window_id": window_id, "label": window_label, "actual_record_count": len(rows)}
            if dates:
                time_window.update({"date_start": min(dates).isoformat(), "date_end": max(dates).isoformat()})
            scope_payload = {"mode": "all_lines", "line_ids": lines} if scope == "ALL_LINES" else {"mode": "single_line", "line_ids": [scope]}
            evidence_refs = sorted({
                str(row.get("evidence_ref"))
                for row in rows
                if isinstance(row.get("evidence_ref"), str) and row.get("evidence_ref")
            })
            snapshot = {
                "view_key": f"factory|{scope}|{window_id}",
                "role": "factory",
                "scope": scope_payload,
                "time_window": time_window,
                "kpis": kpis,
                "alerts": [],
                "tasks": [],
                "decisions_required": [],
                "charts": [],
                "tables": [],
                "evidence_record_count": len(rows),
                "evidence_refs": evidence_refs,
            }
            defect_rows = _detail_rows(rows, label_keys=("defect_type", "defect_code"), value_keys=("defect_count", "defect_qty", "bad_qty"))
            stop_rows = _detail_rows(rows, label_keys=("stop_reason", "reason_code", "downtime_group", "downtime_reason"), value_keys=("downtime_minutes", "duration_minutes", "duration_min", "stop_minutes", "changeover_overtime_min"))
            if defect_rows:
                snapshot["tables"].append({"table_id": "defect_table", "title": "主要不良分类", "rows": defect_rows})
            if stop_rows:
                snapshot["tables"].append({"table_id": "stop_table", "title": "主要停机原因", "rows": stop_rows})
            snapshots.append(snapshot)
            if scope != "ALL_LINES":
                snapshots.append({**snapshot, "view_key": f"line|{scope}|{window_id}", "role": "line"})
            # Specialist roles consume the same evidence-backed production
            # slice but are separate views, so the UI never silently falls
            # back to a factory role or an empty stale scope.
            for specialist in role_names[2:] if lines else []:
                snapshots.append({
                    **snapshot,
                    "view_key": f"{specialist}|{scope}|{window_id}",
                    "role": specialist,
                    "role_projection": "shared_production_evidence",
                })

    coverage = {
        "roles": sorted({item["role"] for item in snapshots}),
        "lines": lines,
        "observed_line_ids": observed_lines,
        "source_line_ids": excluded_lineage,
        "excluded_line_ids": [
            {"line_id": line, "reason": "source_lineage_not_comparable"}
            for line in excluded_lineage
        ],
        "time_windows": [window_id for window_id, _, _ in windows],
        "window_labels": {window_id: label for window_id, label, _ in windows},
        "omitted_windows": omitted_windows,
        "date_field_observed": bool(dated_rows),
        "line_field_observed": bool(lines),
        "improvement_phase_observed": sorted({phase for phase in (_phase(row) for row in metric_rows) if phase}),
        "source_dimensions_are_physical": True,
        "projection_policy": "只投影证据充分的窗口；缺失窗口保留省略原因",
        "projection_method": "metric_rows_sorted_by_observed_date",
        "scope_schema": "{mode,line_ids}",
    }
    return {"view_snapshots": snapshots, "view_coverage": coverage}


__all__ = ["build_view_projection"]

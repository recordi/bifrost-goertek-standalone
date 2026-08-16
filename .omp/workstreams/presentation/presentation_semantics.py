"""Human-facing display semantics; raw source fields remain evidence-only."""

from __future__ import annotations

from typing import Any


FIELD_LABELS = {
    "oee": "综合设备效率（OEE）", "availability": "开动率", "performance_rate": "性能率",
    "quality_rate": "质量率", "yield": "良率", "total_output": "总产量", "good_output": "良品数",
    "defect_total": "不良总数", "unplanned_downtime_minutes": "非计划停机时长",
    "spc_measurement_points": "SPC测量点", "usl": "规格上限", "lsl": "规格下限",
    "sample_rule": "抽样规则", "equipment_id": "设备编号", "material_id": "物料编码",
    "blocked_gap_count": "受阻缺口数", "data_gap": "数据缺口", "field_mapping": "字段映射",
    "supply_insufficient": "供应不足", "not_observable": "暂无足够数据判定",
}

STATUS_LABELS = {
    "available": "可用", "completed": "已完成", "warning": "预警", "blocked": "暂不可判定",
    "not_observed": "未观察到", "not_observable": "暂无足够数据判定", "needs_confirmation": "待人工确认",
    "resolved": "已处理", "open": "待处理", "active": "当前使用", "not_connected": "未接入实时数据",
}

UNIT_LABELS = {"ratio": "%", "percent": "%", "minutes": "分钟", "hours": "小时", "count": "件", "days": "天"}


def humanize(value: Any, *, kind: str = "field") -> str:
    if value is None:
        return "—"
    key = str(value)
    if kind == "status":
        return STATUS_LABELS.get(key, key)
    if kind == "unit":
        return UNIT_LABELS.get(key, key)
    return FIELD_LABELS.get(key, key.replace("_", " "))


def metric_display(field: str, value: Any, unit: str | None = None, status: str | None = None) -> dict[str, Any]:
    return {
        "field": field,
        "label": humanize(field),
        "value": value if value is not None else None,
        "unit": humanize(unit, kind="unit") if unit else None,
        "status": humanize(status, kind="status") if status else "可用" if value is not None else "暂无足够数据判定",
        "show_raw_field": False,
        "raw_field_in_evidence": True,
    }


__all__ = ["humanize", "metric_display"]

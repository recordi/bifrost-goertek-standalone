"""Evidence-first business interpretation for BIFROST.

This module is deliberately deterministic.  It does not replace an
authoritative KPI and it never upgrades an association into a root cause.  It
turns facts already present in a snapshot/adapter result into a small,
business-readable decision brief with provenance and limitations.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional


ROLE_LABELS = {
    "factory": "厂长",
    "line": "线长",
    "quality": "质量",
    "equipment": "设备",
    "process": "工艺",
    "supply": "供应链",
}

DEFECT_LABELS = {
    "appearance": "外观不良",
    "appearance_defect": "外观不良",
    "size": "尺寸超差",
    "size_exceed": "尺寸超差",
    "function": "功能失效",
    "functional": "功能失效",
    "electrical": "电气不良",
    "other": "其他不良",
}


def _first(*values: Any) -> Any:
    return next((value for value in values if value not in (None, "")), None)


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _unique(values: Iterable[Any]) -> list[str]:
    return sorted({str(value) for value in values if value not in (None, "")})


def _label(value: Any) -> str:
    raw = str(value or "").strip()
    key = raw.lower().replace(" ", "_").replace("-", "_")
    return DEFECT_LABELS.get(key, raw or "未标注类别")


def _row_value(row: dict[str, Any]) -> Optional[float]:
    return _number(_first(row.get("count"), row.get("quantity"), row.get("defect_count"), row.get("minutes"), row.get("duration_minutes"), row.get("value")))


def _rows_from_view(view: dict[str, Any], table_hint: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in view.get("tables") or []:
        if not isinstance(table, dict):
            continue
        table_id = str(table.get("table_id") or table.get("id") or "")
        if table_hint in table_id.lower() or not table_hint:
            rows.extend(row for row in table.get("rows") or [] if isinstance(row, dict))
    for chart in view.get("charts") or []:
        if not isinstance(chart, dict):
            continue
        chart_id = str(chart.get("chart_id") or chart.get("id") or "")
        if table_hint in chart_id.lower():
            data = chart.get("data")
            if isinstance(data, list):
                rows.extend(row for row in data if isinstance(row, dict))
    return rows


def _kpi(view: dict[str, Any], *codes: str) -> Optional[dict[str, Any]]:
    codes_set = set(codes)
    return next((item for item in view.get("kpis") or [] if isinstance(item, dict) and item.get("metric_code") in codes_set), None)


def _source_profile(payload: dict[str, Any]) -> dict[str, Any]:
    overview = payload.get("overview") if isinstance(payload.get("overview"), dict) else payload
    registry = overview.get("data_source_registry") or []
    first = registry[0] if registry and isinstance(registry[0], dict) else {}
    return {
        "dataset_id": _first(overview.get("dataset_id"), first.get("dataset_id")),
        "data_nature": _first(overview.get("data_nature"), first.get("data_nature"), "来源性质未提供"),
        "source_sha256": _first(overview.get("source_payload_sha256"), first.get("source_sha256")),
        "rule_version": _first(overview.get("rule_version"), overview.get("ruleset_version")),
    }


def build_business_interpretation(
    payload: dict[str, Any],
    *,
    role: str = "factory",
    scope: str = "ALL_LINES",
    time_window: Optional[str] = None,
) -> dict[str, Any]:
    """Return an auditable business brief for an overview or adapter payload."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    view = payload.get("view") if isinstance(payload.get("view"), dict) else payload
    # The read-only adapter exposes task contracts rather than Overview
    # snapshots.  Normalize only for interpretation; the original payload is
    # never overwritten.
    if not (view.get("kpis") or view.get("tables") or view.get("charts")) and isinstance(payload.get("tasks"), list):
        kpis: list[dict[str, Any]] = []
        task_rows: list[dict[str, Any]] = []
        for task in payload.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            for metric in task.get("metrics") or []:
                if not isinstance(metric, dict):
                    continue
                field = str(metric.get("semantic_field") or "")
                code = {
                    "oee": "OEE",
                    "quality_rate": "QUALITY",
                    "yield": "YIELD",
                    "availability": "AVAILABILITY",
                    "performance_rate": "PERFORMANCE",
                    "defect_total": "DEFECT_TOTAL",
                }.get(field, field.upper())
                kpis.append({"metric_code": code, "value": metric.get("value"), "value_type": "ratio" if metric.get("unit") == "ratio" else None, "value_mode": metric.get("value_mode")})
                if code == "DEFECT_TOTAL":
                    task_rows.append({"label": "全部不良", "count": metric.get("value"), "evidence_refs": metric.get("evidence_refs") or []})
        view = {"kpis": kpis, "tables": [{"table_id": "defect_summary", "rows": task_rows}], "time_window": {}}
    source = _source_profile(payload)
    kpi_oee = _kpi(view, "OEE")
    kpi_quality = _kpi(view, "QUALITY", "YIELD")
    evidence_refs = _unique(view.get("evidence_refs") or payload.get("evidence_refs") or [])
    defects = _rows_from_view(view, "defect")
    defects = [row for row in defects if _row_value(row) is not None]
    defect_total = sum(_row_value(row) or 0 for row in defects)
    ranked_defects = []
    for row in sorted(defects, key=lambda item: _row_value(item) or 0, reverse=True):
        count = _row_value(row) or 0
        ranked_defects.append({
            "label": _label(_first(row.get("type"), row.get("defect_type"), row.get("category"), row.get("label"))),
            "count": int(count) if count.is_integer() else round(count, 2),
            "share": round(count / defect_total, 4) if defect_total else None,
            "evidence_refs": _unique(row.get("evidence_refs") or []),
        })
    top_defect = ranked_defects[0] if ranked_defects else None
    gaps = _unique(payload.get("data_gaps") or view.get("data_gaps") or [])
    source_ready = bool(source["dataset_id"] and source["data_nature"] and (evidence_refs or view.get("view_key")))
    confidence = "高" if evidence_refs else ("中" if source_ready else "低")
    fact_status = "已核验事实" if source_ready else "数据范围已识别，证据仍需补充"
    findings: list[dict[str, Any]] = []
    if kpi_oee and _number(kpi_oee.get("value")) is not None:
        value = _number(kpi_oee.get("value")) or 0
        target = _number(kpi_oee.get("target"))
        gap = (value - target) if target is not None else None
        findings.append({
            "finding_id": f"brief-oee-{role}-{scope}",
            "type": "performance",
            "title": "当前生产效率",
            "summary": f"当前综合设备效率为 {value * 100:.1f}%" + (f"，低于目标 {abs(gap) * 100:.1f} 个百分点" if gap is not None and gap < 0 else "，目标已达到" if gap is not None else ""),
            "meaning": "OEE反映设备可用、运行速度和良品产出的综合结果；它提示需要继续查看停机、速度和质量明细，不能单独证明根因。",
            "impact": "优先确认损失来自停机、速度还是不良，再决定排产、设备或质量动作。",
            "next_actions": ["按班次和产线下钻停机、不良与产量", "由对应责任人确认异常原因后再生成整改任务"],
            "fact_status": fact_status,
            "confidence": confidence,
            "metrics": [{"label": "综合设备效率（OEE）", "value": value, "value_type": "ratio", "target": target}],
            "evidence_refs": evidence_refs,
            "limitations": gaps or ["当前结论仅解释已提供的统计事实，不自动认定根因"],
            "requires_human_confirmation": True,
        })
    if ranked_defects:
        top_text = f"最多的是“{top_defect['label']}”，{top_defect['count']} 件，占不良记录约 {top_defect['share'] * 100:.1f}%" if top_defect and top_defect.get("share") is not None else "已按不良数量完成排序"
        findings.append({
            "finding_id": f"brief-defects-{role}-{scope}",
            "type": "quality",
            "title": "不良分布意味着什么",
            "summary": f"当前范围共统计 {int(defect_total) if defect_total.is_integer() else round(defect_total, 2)} 件不良；{top_text}。",
            "meaning": "“不良类型”是检测结果的分类，表示出现了什么问题，不等于已经确认的根因；累计占比达到100%是因为把当前范围内的分类全部纳入统计。",
            "impact": "先按班次、工单、工序和物料继续下钻，确认问题集中在哪些生产条件，再决定改善措施。",
            "next_actions": ["点击类别查看班次、工单和证据记录", "质量工程师复核抽样规则与缺陷判定标准"],
            "fact_status": fact_status,
            "confidence": confidence,
            "metrics": ranked_defects[:5],
            "evidence_refs": evidence_refs + _unique(ref for row in defects for ref in row.get("evidence_refs") or []),
            "limitations": gaps or ["分类分布只能说明关联项，不能单独证明产品根因"],
            "requires_human_confirmation": False,
        })
    if not findings:
        findings.append({
            "finding_id": f"brief-data-{role}-{scope}",
            "type": "data_quality",
            "title": "当前数据能说明什么",
            "summary": "当前范围尚未形成可解释的业务结论。",
            "meaning": "系统不会用缺失或未核验的数据推断生产问题。",
            "impact": "暂不建议基于此结果调整排产、冻结解除或修改规则。",
            "next_actions": ["补齐数据来源、时间范围和证据记录后重新分析"],
            "fact_status": "暂不可判定",
            "confidence": "低",
            "metrics": [],
            "evidence_refs": evidence_refs,
            "limitations": gaps or ["没有足够的指标或分类记录"],
            "requires_human_confirmation": True,
        })
    findings = _polish_findings(findings)
    fact_status = "\u5df2\u6838\u9a8c\u4e8b\u5b9e" if evidence_refs else "\u5df2\u8bc6\u522b\u6570\u636e\u8303\u56f4\uff0c\u8bc1\u636e\u4ecd\u9700\u8865\u5145"
    confidence = "\u9ad8" if evidence_refs else ("\u4e2d" if source_ready else "\u4f4e")
    for finding in findings:
        finding["fact_status"] = fact_status
        finding["confidence"] = confidence
    return {
        "contract_version": "BIFROST-BUSINESS-INTERPRETATION-v1",
        "role": role,
        "scope": scope,
        "time_window": time_window or (view.get("time_window") or {}).get("window_id"),
        "source": source,
        "fact_status": fact_status,
        "confidence": confidence,
        "findings": findings,
        "source_write_performed": False,
        "authoritative_metrics_unchanged": True,
    }


def _polish_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace legacy mojibake/technical prose with business-facing Chinese.

    The interpretation contract is intentionally deterministic: wording is
    generated from facts already present in the finding and never invents a
    root cause.  This also keeps old payloads readable after a source refresh.
    """
    polished: list[dict[str, Any]] = []
    for item in findings:
        current = dict(item)
        kind = current.get("type")
        if kind == "performance":
            metric = next((m for m in current.get("metrics", []) if isinstance(m, dict)), {})
            value = _number(metric.get("value"))
            target = _number(metric.get("target"))
            current.update({
                "title": "\u5f53\u524d\u7efc\u5408\u6548\u7387",
                "summary": f"\u5f53\u524d OEE \u4e3a {value * 100:.1f}%" + (f"\uff0c\u6bd4\u76ee\u6807\u4f4e {abs(value-target) * 100:.1f} \u4e2a\u767e\u5206\u70b9" if value is not None and target is not None and value < target else "\u3002"),
                "meaning": "OEE \u53ea\u662f\u6548\u7387\u603b\u4f53\u4fe1\u53f7\uff0c\u9700\u7ee7\u7eed\u67e5\u770b\u5f00\u52a8\u7387\u3001\u6027\u80fd\u7387\u3001\u826f\u54c1\u7387\u4e0e\u505c\u673a\u660e\u7ec6\u3002",
                "impact": "\u5148\u786e\u8ba4\u635f\u5931\u4e3b\u8981\u6765\u81ea\u505c\u673a\u3001\u901f\u5ea6\u8fd8\u662f\u8d28\u91cf\uff0c\u518d\u51b3\u5b9a\u6392\u4ea7\u6216\u6539\u5584\u65b9\u5411\u3002",
                "next_actions": ["\u6309\u4ea7\u7ebf\u3001\u73ed\u6b21\u4e0b\u94bb\u505c\u673a\u3001\u4e0d\u826f\u548c\u4ea7\u91cf", "\u7531\u8d23\u4efb\u4eba\u6838\u5b9e\u5f02\u5e38\u539f\u56e0\u540e\u518d\u521b\u5efa\u6574\u6539\u4efb\u52a1"],
            })
        elif kind == "quality":
            metrics = [m for m in current.get("metrics", []) if isinstance(m, dict)]
            total = sum((_number(m.get("count")) or 0) for m in metrics)
            top = metrics[0] if metrics else {}
            label = top.get("label") or "\u672a\u6807\u6ce8\u7c7b\u522b"
            count = _number(top.get("count")) or 0
            share = (count / total * 100) if total else 0
            current.update({
                "title": "\u4e3b\u8981\u4e0d\u826f\u53ca\u7d2f\u8ba1\u5f71\u54cd",
                "summary": f"\u5171\u8bb0\u5f55 {int(total) if total.is_integer() else round(total, 2)} \u4ef6\u4e0d\u826f\uff0c\u6392\u540d\u7b2c\u4e00\u7684\u7c7b\u522b\u662f\u201c{label}\u201d\uff0c\u5360 {share:.1f}%\u3002",
                "meaning": f"\u4e0d\u826f\u7c7b\u578b\u662f\u68c0\u6d4b\u7ed3\u679c\u7684\u5206\u7c7b\uff0c\u8868\u793a\u51fa\u73b0\u4e86\u4ec0\u4e48\u95ee\u9898\uff0c\u4e0d\u7b49\u4e8e\u5df2\u7ecf\u786e\u8ba4\u7684\u6839\u56e0\u3002\u7d2f\u8ba1\u5360\u6bd4 {share:.1f}% \u4ee3\u8868\u5f53\u524d\u7b5b\u9009\u8303\u56f4\u5185\u7684\u7c7b\u522b\u5df2\u5168\u90e8\u5217\u5165\u7edf\u8ba1\u3002",
                "impact": "\u6309\u73ed\u6b21\u3001\u5de5\u5355\u3001\u5de5\u5e8f\u548c\u4ea7\u54c1\u7ee7\u7eed\u4e0b\u94bb\uff0c\u786e\u8ba4\u95ee\u9898\u96c6\u4e2d\u7684\u751f\u4ea7\u6761\u4ef6\u540e\u518d\u51b3\u5b9a\u6539\u5584\u63aa\u65bd\u3002",
                "next_actions": ["\u6253\u5f00\u4e0d\u826f\u7c7b\u522b\u67e5\u770b\u73ed\u6b21\u3001\u5de5\u5355\u548c\u8bc1\u636e", "\u7531\u8d28\u91cf\u5de5\u7a0b\u5e08\u590d\u6838\u62bd\u6837\u89c4\u5219\u548c\u5224\u5b9a\u6807\u51c6"],
                "limitations": ["\u5206\u7c7b\u5206\u5e03\u53ea\u8868\u793a\u5173\u8054\u9879\uff0c\u4e0d\u5355\u72ec\u8bc1\u660e\u6839\u56e0"],
            })
        else:
            current.update({
                "title": "\u5f53\u524d\u6570\u636e\u80fd\u8bf4\u660e\u4ec0\u4e48",
                "summary": "\u5f53\u524d\u8303\u56f4\u8fd8\u6ca1\u6709\u5f62\u6210\u53ef\u89e3\u91ca\u7684\u4e1a\u52a1\u7ed3\u8bba\u3002",
                "meaning": "\u6570\u636e\u4e0d\u8db3\u65f6\u4e0d\u63a8\u65ad\u4ea7\u7ebf\u5f02\u5e38\uff0c\u4e5f\u4e0d\u81ea\u52a8\u4fee\u6539\u751f\u4ea7\u51b3\u7b56\u3002",
                "impact": "\u5148\u8865\u9f50\u6570\u636e\u6765\u6e90\u3001\u65f6\u95f4\u8303\u56f4\u548c\u8bc1\u636e\u540e\u518d\u5206\u6790\u3002",
                "next_actions": ["\u8865\u9f50\u7f3a\u5931\u5b57\u6bb5\u5e76\u91cd\u65b0\u8fd0\u884c\u6821\u9a8c"],
            })
        polished.append(current)
    return polished


__all__ = ["build_business_interpretation"]

"""Translate a dynamic AutoAdapt payload into the peer task contract.

The bridge is intentionally additive and read-only.  It does not infer
missing production facts, promote partial role projections, or turn an
observed OEE into A/P/Q components.  It only copies metrics and evidence that
are already present in the dynamic event.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


ROLE_AGENT = {
    "factory": "production-specialist",
    "line": "production-specialist",
    "quality": "quality-specialist",
    "supply": "supply-specialist",
}

METRIC_FIELDS = {
    "OEE": "oee",
    "YIELD": "yield",
    "QUALITY": "quality_rate",
    "AVAILABILITY": "availability",
    "PERFORMANCE": "performance_rate",
    "TOTAL_OUTPUT": "total_output",
    "GOOD_OUTPUT": "good_output",
    "DEFECT_TOTAL": "defect_total",
}


def _stable_id(event: dict[str, Any], overview: dict[str, Any]) -> str:
    event_id = event.get("event_id")
    if isinstance(event_id, str) and event_id.strip():
        return event_id
    source = str((overview.get("source_profile") or {}).get("source_sha256") or "")
    if not source:
        source = sha256(repr(sorted(overview.items())).encode("utf-8")).hexdigest()
    return f"EVT-DYNAMIC-{source[:16]}"


def _flatten_gaps(gaps: list[Any]) -> list[str]:
    result: list[str] = []
    for gap in gaps or []:
        if isinstance(gap, str):
            result.append(gap)
        elif isinstance(gap, dict):
            fields = gap.get("missing_fields") or gap.get("field") or gap.get("metric")
            if isinstance(fields, list):
                result.extend(str(item) for item in fields)
            elif fields:
                result.append(str(fields))
    return sorted(set(result))


def _metrics(role: dict[str, Any], evidence_refs: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for kpi in role.get("kpis") or []:
        if not isinstance(kpi, dict) or not isinstance(kpi.get("value"), (int, float)):
            continue
        code = str(kpi.get("metric_code") or "")
        field = METRIC_FIELDS.get(code, code.lower())
        item = {
            "semantic_field": field,
            "value": kpi["value"],
            "unit": kpi.get("unit") or ("ratio" if kpi.get("value_type") == "ratio" else None),
            "value_mode": kpi.get("value_mode"),
            "calculation_allowed": kpi.get("calculation_allowed"),
            "evidence_refs": list(kpi.get("evidence_refs") or evidence_refs),
        }
        result.append(item)
    return result


def _drilldown_metrics(drilldown_result: dict[str, Any], evidence_refs: list[str]) -> list[dict[str, Any]]:
    """Turn selected facts into peer inputs without inventing a KPI."""
    facts = drilldown_result.get("facts") or {}
    result: list[dict[str, Any]] = []
    fact_map = (
        ("output", "total_output", "count"),
        ("defect_count", "defect_total", "count"),
        ("downtime", "downtime_minutes", "minutes"),
        ("quality", "quality_rate", "ratio"),
    )
    for source, field, unit in fact_map:
        summary = facts.get(source)
        if not isinstance(summary, dict) or not isinstance(summary.get("sum"), (int, float)):
            continue
        result.append({
            "semantic_field": field,
            "value": summary["sum"] if source != "quality" else summary.get("average"),
            "unit": unit,
            "value_mode": "drilldown_fact",
            "calculation_allowed": False,
            "evidence_refs": list(drilldown_result.get("evidence_refs") or evidence_refs),
        })
    return result


def _drilldown_causes(drilldown_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose ranked associations as causes, explicitly not confirmed roots."""
    causes: list[dict[str, Any]] = []
    for item in drilldown_result.get("root_cause_candidates") or []:
        if not isinstance(item, dict) or not item.get("label"):
            continue
        causes.append({
            "category": item.get("category"),
            "statement": f"{item.get('label')}（关联线索，需进一步确认）",
            "count": item.get("record_count"),
            "impact_score": item.get("impact_score"),
            "evidence_refs": list(item.get("evidence_refs") or []),
            "interpretation": "association_only",
        })
    return causes


def _role_evidence(role: dict[str, Any], evidence_index: list[dict[str, Any]], all_refs: list[str]) -> list[str]:
    explicit = sorted(set(role.get("evidence_refs") or []))
    if explicit:
        return explicit
    scope = role.get("scope") or {}
    line_ids = set(scope.get("line_ids") or []) if isinstance(scope, dict) else set()
    if not line_ids:
        return list(all_refs)
    scoped = sorted({
        item.get("evidence_ref") for item in evidence_index
        if isinstance(item, dict)
        and item.get("line_id") in line_ids
        and isinstance(item.get("evidence_ref"), str)
    })
    return scoped or list(all_refs)


def build_peer_task_payload(
    dynamic_payloads: dict[str, Any],
    *,
    drilldown_result: dict[str, Any] | None = None,
    drilldown_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a fixed peer-task input from generated Overview/Event payloads.

    Only factory/line, quality and supply tasks are created because those are
    the peer executors currently available.  Equipment/process remain role
    views with explicit capability gaps and are not silently re-labelled as
    specialist tasks.
    """
    if not isinstance(dynamic_payloads, dict):
        raise TypeError("dynamic_payloads must be an object")
    overview = dynamic_payloads.get("overview") or {}
    event = deepcopy(dynamic_payloads.get("event") or {})
    event_id = _stable_id(event, overview)
    event["event_id"] = event_id
    source_profile = deepcopy(overview.get("source_profile") or {})
    evidence_index = overview.get("evidence_index") or event.get("evidence_index") or []
    all_refs = sorted({
        item.get("evidence_ref") for item in evidence_index
        if isinstance(item, dict) and isinstance(item.get("evidence_ref"), str)
    })
    role_map = {item.get("role"): item for item in event.get("roles") or [] if isinstance(item, dict)}
    drilldown_result = drilldown_result if isinstance(drilldown_result, dict) else None
    drilldown_refs = sorted(set(drilldown_result.get("evidence_refs") or [])) if drilldown_result else []
    drilldown_facts = deepcopy(drilldown_result.get("facts") or {}) if drilldown_result else {}
    drilldown_causes = _drilldown_causes(drilldown_result) if drilldown_result else []
    drilldown_hash = sha256(repr(sorted((drilldown_filters or {}).items())).encode("utf-8")).hexdigest()[:10] if drilldown_filters else None
    # Prefer the all-lines factory slice for the production specialist.  A
    # line slice is only a fallback; emitting both would duplicate the same
    # production conclusion under one agent contract.
    selected_roles = ["factory" if "factory" in role_map else "line", "quality", "supply"]
    tasks: list[dict[str, Any]] = []
    for role in selected_roles:
        agent_id = ROLE_AGENT[role]
        role_data = role_map.get(role)
        if not role_data:
            continue
        refs = _role_evidence(role_data, evidence_index, all_refs)
        if drilldown_result is not None:
            refs = sorted(set(refs) & set(drilldown_refs)) if drilldown_refs else []
        scope = role_data.get("scope") or {}
        line_ids = list(scope.get("line_ids") or []) if isinstance(scope, dict) else []
        if drilldown_filters and drilldown_filters.get("line") not in (None, ""):
            requested_line = drilldown_filters.get("line")
            requested_lines = requested_line if isinstance(requested_line, list) else [requested_line]
            line_ids = [str(item) for item in requested_lines]
        status = role_data.get("status") or "needs_confirmation"
        if not refs and status in {"ready", "completed"}:
            status = "needs_confirmation"
        task = {
            "event_id": event_id,
            "task_id": f"{event_id}{('-DD-' + drilldown_hash) if drilldown_hash else ''}-TASK-{role.upper()}",
            "agent_id": agent_id,
            "objective": f"Analyze {role} evidence without replacing authoritative metrics",
            "status": status,
            "metrics": _metrics(role_data, refs) + (_drilldown_metrics(drilldown_result, refs) if drilldown_result else []),
            "causes": drilldown_causes if drilldown_result else [],
            "affected_objects": [{"line_id": line_id} for line_id in line_ids],
            "recommended_actions": [],
            "needs_human_confirmation": status not in {"ready", "completed"},
            "evidence_refs": refs,
            "data_gaps": _flatten_gaps(role_data.get("data_gaps") or []),
            "analysis_scope": {"filters": deepcopy(drilldown_filters or {}), "source": "drilldown_result" if drilldown_result else "event_payload"},
            "drilldown_facts": drilldown_facts,
            "source_write_performed": False,
            "actor_can_execute": False,
        }
        tasks.append(task)
    return {
        "contract_version": "BIFROST_DYNAMIC_PEER_TASK_INPUT_v1",
        "adapter": "dynamic-autoadapt-bridge",
        "event": event,
        "event_id": event_id,
        "source_profile": source_profile,
        "tasks": tasks,
        "authoritative_metrics": deepcopy(overview.get("metrics") or {}),
        "source_write_performed": False,
        "actor_can_execute": False,
        "evidence_index": deepcopy(evidence_index),
        "analysis_scope": {"filters": deepcopy(drilldown_filters or {}), "source": "drilldown_result" if drilldown_result else "event_payload"},
    }


def build_formal_derived_insights(
    peer_analysis: dict[str, Any] | None,
    *,
    event_id: str,
    dataset_id: str | None,
) -> dict[str, Any]:
    """Project only evidence-backed peer results into an additive payload section.

    This is deliberately not an authoritative KPI update and does not mean a
    rule/decision was published.  A result is eligible only when its executor
    returned an available result, passed the evidence gate, has source evidence,
    and its source task was ready/completed (or the legacy executor omitted the
    optional status).  Partial/blocked/warning results stay out of the formal
    derived section and remain visible as data gaps in ``peer_analysis``.
    """
    results = peer_analysis.get("peer_results", []) if isinstance(peer_analysis, dict) else []
    eligible: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "available":
            continue
        if (item.get("evidence_gate") or {}).get("status") != "passed":
            continue
        refs = item.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            continue
        source_status = item.get("source_task_status")
        if source_status not in (None, "ready", "completed"):
            continue
        if item.get("event_id") not in (None, event_id):
            continue
        eligible.append(item)

    role_by_agent = {
        "production-specialist": ["factory", "line", "equipment"],
        "quality-specialist": ["quality", "process"],
        "supply-specialist": ["factory", "supply"],
    }
    derived = []
    for item in eligible:
        skill_id = str(item.get("skill_id") or "unknown")
        agent_id = str(item.get("agent_id") or "")
        audience_roles = role_by_agent.get(agent_id, ["factory"])
        if skill_id == "a03-spc-rules":
            audience_roles = ["quality", "process"]
        elif skill_id == "a08-supply-chain-gap":
            audience_roles = ["factory", "supply"]
        business_summary = item.get("business_summary")
        if not business_summary:
            if skill_id == "a01-oee-loss-tree":
                tree = item.get("oee_loss_tree") or {}
                count = sum(len(value or []) for value in tree.values())
                business_summary = f"已识别 {count} 项影响生产效率的直接因素，建议按损失分解中的优先项排查。"
            elif skill_id == "a02-pareto":
                items = (item.get("pareto") or {}).get("items") or []
                business_summary = f"已按当前数据识别 {len(items)} 项主要关联原因，排序用于确定改善优先级，不等同于已确认根因。"
            elif skill_id == "a07-yield-funnel":
                stages = (item.get("yield_funnel") or {}).get("stages") or []
                business_summary = f"已形成 {len(stages)} 个良率环节的证据链，可用于定位产出损失发生在哪一段。"
            elif skill_id == "a08-supply-chain-gap":
                business_summary = "已完成物料缺口与交付影响核对，结果仅基于当前订单、库存和冻结证据。"
            else:
                business_summary = item.get("summary")
        derived.append({
            "insight_id": f"DERIVED-{event_id}-{skill_id}",
            "skill_id": skill_id,
            "authority": "bifrost_derived",
            "status": "validated",
            "promotion_scope": "formal-derived-additive",
            "business_projection": "first_class_role_finding",
            "dataset_id": dataset_id,
            "event_id": event_id,
            "task_id": item.get("task_id"),
            "agent_id": agent_id,
            "audience_roles": audience_roles,
            "presentation_mode": "first_class_business",
            "title_zh": (item.get("display_descriptor") or {}).get("title_zh") or skill_id,
            "business_summary": business_summary,
            "metrics": deepcopy(item.get("metrics") or []),
            "conclusion": item.get("conclusion") or item.get("summary"),
            "evidence_refs": list(item.get("evidence_refs") or []),
            "evidence_gate": deepcopy(item.get("evidence_gate") or {}),
            "source_task_status": item.get("source_task_status") or "ready",
            "does_not_replace_authoritative_metrics": True,
            "requires_human_confirmation": False,
        })

    role_findings: dict[str, list[dict[str, Any]]] = {}
    for insight in derived:
        business_finding = {
            "insight_id": insight["insight_id"],
            "title_zh": insight["title_zh"],
            "summary": insight.get("business_summary") or insight.get("conclusion"),
            "metrics": deepcopy(insight.get("metrics") or []),
            "evidence_refs": list(insight.get("evidence_refs") or []),
            "requires_human_confirmation": bool(insight.get("requires_human_confirmation")),
            "presentation_mode": "first_class_business",
            "source_status": insight.get("source_task_status"),
        }
        for role in insight.get("audience_roles") or ["factory"]:
            role_findings.setdefault(role, []).append(deepcopy(business_finding))

    return {
        "promotion_status": "validated" if derived else "not_available",
        "formal_integration_status": "attached_additive" if derived else "not_attached",
        "authority": "bifrost_derived",
        "presentation_mode": "first_class_business",
        "dataset_id": dataset_id,
        "event_id": event_id,
        "derived_insights": derived,
        "role_findings": role_findings,
        "event_findings": deepcopy(derived),
        "requires_human_confirmation": False,
    }


__all__ = ["build_formal_derived_insights", "build_peer_task_payload"]

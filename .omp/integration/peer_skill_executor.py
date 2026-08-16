"""Deterministic, read-only execution boundary for peer analysis skills.

The Markdown files in ``skills/`` describe peer capabilities; they are not
executable programs. This module is the explicit executable adapter boundary.
It only analyzes facts already present in the fixed BIFROST adapter payload.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from peer_skill_contract import CONTRACT_VERSION, validate_output


SPC_FIELDS = {"spc_measurement_points", "usl", "lsl", "sample_rule"}


def _refs(task: dict[str, Any]) -> list[str]:
    refs: set[str] = set(x for x in task.get("evidence_refs", []) or [] if isinstance(x, str))
    for group in ("metrics", "causes"):
        for item in task.get(group, []) or []:
            if isinstance(item, dict):
                refs.update(x for x in item.get("evidence_refs", []) or [] if isinstance(x, str))
    return sorted(refs)


def _metrics(task: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        x.get("semantic_field"): x
        for x in task.get("metrics", []) or []
        if isinstance(x, dict) and isinstance(x.get("semantic_field"), str)
    }


def _gaps(task: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for gap in task.get("data_gaps", []) or []:
        if isinstance(gap, dict):
            for key in ("semantic_field", "field", "missing_field"):
                if isinstance(gap.get(key), str):
                    out.add(gap[key])
    return out


def _evidence_gate(task: dict[str, Any]) -> dict[str, Any]:
    """Describe whether a peer result has auditable source evidence.

    This is deliberately a gate, not a source of evidence.  References are
    copied from the fixed adapter payload and are never created here.
    """
    refs = _refs(task)
    return {
        "status": "passed" if refs else "blocked",
        "required": True,
        "evidence_refs": refs,
        "missing_fields": [] if refs else ["evidence_refs"],
        "source": "fixed_adapter_payload",
    }


def _spc_gate(task: dict[str, Any]) -> dict[str, Any]:
    """Require every SPC input and field-level evidence before analysis."""
    metrics = _metrics(task)
    gaps = _gaps(task)
    missing_fields: list[str] = []
    evidence_missing_fields: list[str] = []
    refs: set[str] = set()
    for field in sorted(SPC_FIELDS):
        item = metrics.get(field)
        value = task.get(field) if field not in metrics else item.get("value")
        if field in gaps or value is None:
            missing_fields.append(field)
            continue
        field_refs = item.get("evidence_refs", []) if item is not None else task.get("evidence_refs", [])
        valid_refs = [ref for ref in field_refs if isinstance(ref, str) and ref]
        refs.update(valid_refs)
        if not valid_refs:
            evidence_missing_fields.append(field)
    # A broad task reference cannot substitute for field-level evidence.  It
    # remains available in the result for traceability, but does not pass SPC.
    passed = not missing_fields and not evidence_missing_fields
    return {
        "status": "passed" if passed else "blocked",
        "required_fields": sorted(SPC_FIELDS),
        "missing_fields": missing_fields,
        "evidence_missing_fields": evidence_missing_fields,
        "evidence_refs": sorted(refs),
    }


def _base(skill_id: str, task: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "skill_id": skill_id,
        "status": status,
        "event_id": task.get("event_id"),
        "task_id": task.get("task_id"),
        "agent_id": task.get("agent_id"),
        "analysis_scope": copy.deepcopy(task.get("analysis_scope") or {}),
        "affected_objects": copy.deepcopy(task.get("affected_objects") or []),
        "recommended_actions": copy.deepcopy(task.get("recommended_actions") or []),
        "evidence_refs": _refs(task),
        "data_gaps": sorted(_gaps(task)),
        "insights": [],
        "evidence_gate": _evidence_gate(task),
        "display_descriptor": {"language": "zh-CN", "source": "peer_skill_executor"},
        "does_not_replace_authoritative_metrics": True,
    }


def _oee_loss_tree(task: dict[str, Any]) -> dict[str, Any]:
    metrics = _metrics(task)
    tree: dict[str, list[dict[str, Any]]] = {"availability": [], "performance": [], "quality": []}
    field_layer = {
        "availability": "availability",
        "performance_rate": "performance",
        "quality_factor": "quality",
        "quality_rate": "quality",
    }
    for field, layer in field_layer.items():
        if field in metrics:
            item = metrics[field]
            tree[layer].append({
                "cause_type": "direct_driver",
                "semantic_field": field,
                "value": item.get("value"),
                "unit": item.get("unit", "ratio"),
                "evidence_refs": item.get("evidence_refs", []),
            })
    for cause in task.get("causes", []) or []:
        if not isinstance(cause, dict):
            continue
        category = str(cause.get("category", ""))
        layer = "availability" if "availability" in category or "downtime" in category else "quality" if "defect" in category or "quality" in category else "performance" if "performance" in category or "cycle" in category else None
        if layer:
            tree[layer].append({
                "cause_type": "observed_cause",
                "category": cause.get("category"),
                "statement": cause.get("statement"),
                "evidence_refs": cause.get("evidence_refs", []),
            })
    status = "available" if any(tree.values()) else "not_observed"
    result = _base("a01-oee-loss-tree", task, status)
    result["oee_loss_tree"] = tree
    result["display_descriptor"].update({"title_zh": "OEE损失树", "chart_type": "loss_tree"})
    return result


def _pareto(task: dict[str, Any]) -> dict[str, Any]:
    # Only categorical causes with an explicit count/duration are valid. Never
    # rank total_output/good_output/defect_total together as a fake Pareto.
    items: list[dict[str, Any]] = []
    dimension: str | None = None
    unit: str | None = None
    for cause in task.get("causes", []) or []:
        if not isinstance(cause, dict):
            continue
        value_key = next((k for k in ("count", "duration_minutes", "quantity") if isinstance(cause.get(k), (int, float)) and not isinstance(cause.get(k), bool)), None)
        if not value_key:
            continue
        candidate_unit = "minutes" if value_key == "duration_minutes" else "count"
        if unit is None:
            unit = candidate_unit
            dimension = "downtime_cause" if value_key == "duration_minutes" else "cause_category"
        if candidate_unit != unit:
            continue
        items.append({"label": cause.get("category"), "value": cause[value_key], "unit": unit, "evidence_refs": cause.get("evidence_refs", [])})
    items.sort(key=lambda x: x["value"], reverse=True)
    result = _base("a02-pareto", task, "available" if items else "not_observed")
    result["pareto"] = {"dimension": dimension, "unit": unit, "items": items}
    result["display_descriptor"].update({"title_zh": "原因 Pareto", "chart_type": "horizontal_bar"})
    if not items:
        result["data_gaps"].append("categorical_cause_values")
        result["reason"] = "no_categorical_cause_values"
    return result


def _yield_funnel(task: dict[str, Any]) -> dict[str, Any]:
    metrics = _metrics(task)
    stages = []
    for field in ("total_output", "good_output", "defect_total", "yield", "yield_rate", "quality_rate"):
        if field in metrics:
            item = metrics[field]
            stages.append({"semantic_field": field, "value": item.get("value"), "unit": item.get("unit"), "evidence_refs": item.get("evidence_refs", [])})
    result = _base("a07-yield-funnel", task, "available" if stages else "not_observed")
    result["yield_funnel"] = {"stages": stages}
    result["display_descriptor"].update({"title_zh": "良率漏斗", "chart_type": "funnel"})
    return result


def _spc(task: dict[str, Any]) -> dict[str, Any]:
    gate = _spc_gate(task)
    missing = sorted(set(gate["missing_fields"]) | set(gate["evidence_missing_fields"]))
    result = _base("a03-spc-rules", task, "available" if gate["status"] == "passed" else "blocked")
    result["data_gaps"] = sorted(set(result["data_gaps"]) | set(missing))
    if gate["evidence_missing_fields"]:
        result["data_gaps"].append("spc_evidence_refs")
    if gate["status"] != "passed" and not result["data_gaps"]:
        result["data_gaps"].append("spc_required_inputs")
    result["spc_gate"] = gate
    result["evidence_gate"] = {
        "status": "passed" if gate["status"] == "passed" else "blocked",
        "required": True,
        "evidence_refs": gate["evidence_refs"],
        "missing_fields": sorted(set(gate["missing_fields"]) | set(gate["evidence_missing_fields"])),
        "source": "fixed_adapter_payload",
    }
    result["spc"] = {"cpk": None, "measurement_points": None, "missing_fields": missing}
    # Compatibility aliases are temporary; consumers should read ``spc``.
    result["cpk"] = None
    result["display_descriptor"].update({"title_zh": "SPC状态", "chart_type": "status_card"})
    if gate["status"] == "passed":
        result["data_gaps"].append("spc_executor_not_enabled")
    return result


def _supply_gap(task: dict[str, Any]) -> dict[str, Any]:
    task_status = task.get("status")
    status = {
        "completed": "available",
        "needs_confirmation": "warning",
        "warning": "warning",
        "blocked": "blocked",
        "failed": "blocked",
    }.get(task_status, "not_observed")
    result = _base("a08-supply-chain-gap", task, status)
    result["supply_gap"] = {"metrics": copy.deepcopy(task.get("metrics", [])), "oee_attribution": "forbidden"}
    # Compatibility alias for the existing read-only regression contract.
    result["oee_attribution"] = "forbidden"
    result["display_descriptor"].update({"title_zh": "供应缺口", "chart_type": "table"})
    return result


EXECUTORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "production-specialist": lambda t: _oee_loss_tree(t),
    "quality-specialist": lambda t: _yield_funnel(t),
    "supply-specialist": lambda t: _supply_gap(t),
}


def execute_peer_skills(payload: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for task in payload.get("tasks", []) or []:
        if not isinstance(task, dict):
            continue
        agent = task.get("agent_id")
        if agent == "production-specialist":
            selected = [_oee_loss_tree(task), _pareto(task)]
        elif agent == "quality-specialist":
            selected = [_yield_funnel(task), _spc(task)]
        elif agent == "supply-specialist":
            selected = [_supply_gap(task)]
        else:
            selected = []
        for output in selected:
            # A complete-looking derived chart cannot outrank an incomplete
            # source task.  Keep the analysis visible as advisory, but prevent
            # it from being promoted into the formal chain until the source
            # task is ready/completed.
            if task.get("status") in {"partial", "blocked", "failed"}:
                output["source_task_status"] = task.get("status", "unknown")
                output.setdefault("data_gaps", []).append("source_task_not_ready")
                if output.get("status") == "available":
                    output["status"] = "warning"
            # No result is allowed to claim a usable analysis without at least
            # one source EvidenceRef.  The source payload remains untouched;
            # this only annotates the additive postprocessor result.
            if output.get("evidence_gate", {}).get("status") == "blocked":
                if "evidence_refs" not in output.setdefault("data_gaps", []):
                    output["data_gaps"].append("evidence_refs")
                if output.get("status") == "available":
                    output["status"] = "blocked"
            output["validation_errors"] = validate_output(output)
            if output["validation_errors"]:
                output["status"] = "blocked"
            outputs.append(output)
    return outputs


__all__ = ["execute_peer_skills"]

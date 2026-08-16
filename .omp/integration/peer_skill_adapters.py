"""Read-only adapters for peer analysis skills.

The adapter consumes an already validated BIFROST fixed-adapter payload. It
never recalculates metrics, changes task results, creates EvidenceRefs, or
writes source/UI data. It only adds traceable presentation/analysis hints.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from peer_skill_executor import execute_peer_skills
from role_projection import project_roles, validate_role_projections


REQUIRED_EVIDENCE_FIELDS = {"event_id", "task_id", "agent_id"}
SPC_REQUIRED_FIELDS = {"spc_measurement_points", "usl", "lsl", "sample_rule"}


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _physical_binding_map(value: Any) -> dict[str, dict[str, Any]]:
    """Normalize physical source bindings without inventing provenance."""
    if isinstance(value, dict):
        entries = []
        for evidence_ref, item in value.items():
            if isinstance(item, dict):
                entries.append({"evidence_ref": evidence_ref, **item})
    elif isinstance(value, list):
        entries = [item for item in value if isinstance(item, dict)]
    else:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in entries:
        ref = item.get("evidence_ref")
        if not isinstance(ref, str) or not ref.strip():
            continue
        physical_sha = item.get("physical_source_sha256") or item.get("source_sha256")
        if all(isinstance(item.get(key), str) and item[key].strip() for key in ("dataset_id", "source_table", "adapter_payload_sha256")) and isinstance(physical_sha, str) and len(physical_sha) == 64 and item.get("record_id", item.get("record_key")):
            item = {**item, "physical_source_sha256": physical_sha}
            result[ref] = copy.deepcopy(item)
    return result


def _metric_map(task: dict) -> dict[str, dict]:
    return {
        item.get("semantic_field"): item
        for item in task.get("metrics", [])
        if isinstance(item, dict) and item.get("semantic_field")
    }


def _all_evidence(task: dict) -> set[str]:
    refs = set(task.get("evidence_refs", []) or [])
    for item in task.get("metrics", []) or []:
        if isinstance(item, dict):
            refs.update(item.get("evidence_refs", []) or [])
    for item in task.get("causes", []) or []:
        if isinstance(item, dict):
            refs.update(item.get("evidence_refs", []) or [])
    return {ref for ref in refs if isinstance(ref, str)}


def _gap_fields(task: dict) -> set[str]:
    fields: set[str] = set()
    for gap in task.get("data_gaps", []) or []:
        if not isinstance(gap, dict):
            continue
        for key in ("semantic_field", "field", "missing_field"):
            value = gap.get(key)
            if isinstance(value, str):
                fields.add(value)
    return fields


def _evidence_bound(item: dict, task_refs: set[str]) -> bool:
    refs = item.get("evidence_refs", [])
    return isinstance(refs, list) and all(ref in task_refs for ref in refs)


def _production_enhancement(task: dict) -> dict:
    refs = _all_evidence(task)
    branches = []
    for cause in task.get("causes", []) or []:
        if not isinstance(cause, dict):
            continue
        cause_refs = cause.get("evidence_refs", []) or []
        if not cause_refs or not all(ref in refs for ref in cause_refs):
            continue
        branches.append({
            "category": cause.get("category"),
            "statement": cause.get("statement"),
            "causal_evidence_level": cause.get("causal_evidence_level"),
            "evidence_refs": list(cause_refs),
        })
    return {
        "skill_id": "a01-oee-loss-tree",
        "status": "available" if branches else "not_observed",
        "branches": branches,
        "metric_source": "authoritative_task_metrics",
        "does_not_recalculate": True,
    }


def _pareto_enhancement(task: dict) -> dict:
    refs = _all_evidence(task)
    rankable = []
    for item in (task.get("causes", []) or []) + (task.get("metrics", []) or []):
        if not isinstance(item, dict) or not _evidence_bound(item, refs):
            continue
        numeric = next((item.get(key) for key in ("count", "quantity", "duration_minutes", "value")
                        if isinstance(item.get(key), (int, float)) and not isinstance(item.get(key), bool)), None)
        if numeric is not None:
            rankable.append({"label": item.get("category") or item.get("semantic_field"),
                             "value": numeric, "evidence_refs": list(item.get("evidence_refs", []))})
    rankable.sort(key=lambda item: item["value"], reverse=True)
    return {
        "skill_id": "a02-pareto",
        "status": "available" if rankable else "not_available",
        "items": rankable,
        "reason": None if rankable else "no_evidence_bound_rankable_values",
        "does_not_recalculate": True,
    }


def _quality_enhancements(task: dict) -> list[dict]:
    metrics = _metric_map(task)
    refs = _all_evidence(task)
    funnel = []
    for field in ("total_output", "good_output", "defect_total", "yield", "yield_rate", "quality_rate"):
        metric = metrics.get(field)
        if metric is not None:
            funnel.append({"field": field, "value": metric.get("value"),
                           "evidence_refs": list(metric.get("evidence_refs", []))})

    gaps = _gap_fields(task)
    missing_spc = sorted(SPC_REQUIRED_FIELDS.intersection(gaps))
    spc = {
        "skill_id": "a03-spc-rules",
        "status": "blocked" if missing_spc else "not_enabled",
        "missing_fields": missing_spc,
        "reason": "required_spc_inputs_missing" if missing_spc else "spc_adapter_not_enabled",
        "cpk": None,
        "evidence_refs": sorted(refs),
    }
    return [
        {
            "skill_id": "a07-yield-funnel",
            "status": "available" if funnel else "not_observed",
            "stages": funnel,
            "does_not_recalculate": True,
        },
        spc,
    ]


def _supply_enhancement(task: dict) -> dict:
    return {
        "skill_id": "a08-supply-chain-gap",
        "status": task.get("status", "unknown"),
        "task_metrics": copy.deepcopy(task.get("metrics", [])),
        "data_gaps": copy.deepcopy(task.get("data_gaps", [])),
        "oee_attribution": "forbidden",
        "evidence_refs": sorted(_all_evidence(task)),
    }


def build_peer_enhancements(adapter_payload: dict) -> dict:
    """Return a copy with additive, evidence-bound peer enhancements only."""
    if not isinstance(adapter_payload, dict):
        raise TypeError("adapter_payload must be an object")
    output = copy.deepcopy(adapter_payload)
    input_hash = _stable_hash(adapter_payload)
    # The old helper functions are retained only for backwards-compatible
    # imports. Runtime output now comes from the explicit executable contract
    # boundary, not from field-to-UI overlay heuristics.
    working_payload = copy.deepcopy(adapter_payload)
    enhancements = execute_peer_skills(working_payload)
    output_hash = _stable_hash(working_payload)
    authoritative_hash = _stable_hash(adapter_payload.get("authoritative_metrics"))

    output["peer_integration"] = {
        "matrix_version": "BIFROST-SKILL-COMPAT-v1.0",
        "adapter_version": "2.0.0",
        "execution_mode": "contract-executed-readonly",
        "overlay_mode": "deprecated",
        "source_payload_sha256": input_hash,
        "source_payload_unchanged": output_hash == input_hash,
        "authoritative_metrics_unchanged": authoritative_hash == _stable_hash(working_payload.get("authoritative_metrics")),
        "source_write_performed": False,
        "actor_can_execute": False,
    }
    output["analysis_enhancements"] = enhancements
    output["peer_skill_outputs"] = copy.deepcopy(enhancements)
    output["role_projections"] = project_roles(enhancements)
    output["peer_integration"]["role_projection_errors"] = validate_role_projections(enhancements, output["role_projections"])
    role_scope = {
        "factory": ["event", "analysis_enhancements"],
        "line": ["production-specialist", "analysis_enhancements"],
        "quality": ["quality-specialist", "analysis_enhancements"],
        "equipment": ["production-specialist", "data_gaps"],
        "process": ["quality-specialist", "data_gaps"],
        "supply": ["supply-specialist", "analysis_enhancements"],
    }
    output["peer_overlay"] = {
        "overlay_version": "PEER-OVERLAY-v1.0",
        "source_payload_sha256": input_hash,
        "status": "active",
        "read_only": True,
        "target": "adapter-test-only",
        "role_scope": role_scope,
        "display_hints": {
            "a01-oee-loss-tree": {"title_key": "oee_loss_tree", "chart": "loss_tree", "roles": ["factory", "line", "equipment"]},
            "a02-pareto": {"title_key": "pareto", "chart": "horizontal_bar", "roles": ["factory", "line", "quality"]},
            "a07-yield-funnel": {"title_key": "yield_funnel", "chart": "funnel", "roles": ["factory", "quality", "line"]},
            "a03-spc-rules": {"title_key": "spc_gate", "chart": "status_card", "roles": ["quality", "process"]},
            "a08-supply-chain-gap": {"title_key": "supply_gap", "chart": "table", "roles": ["supply", "factory", "line"]},
        },
    }
    output["governance_findings"] = {
        "status": "not_run",
        "reason": "fixed adapter contract contains validated results, not raw governance input",
        "required_next_input": ["raw_rows", "schema", "reference_tables", "time_fields"],
    }
    output["role_projection_hints"] = [
        {"role": "factory", "allowed_sources": ["event", "tasks", "analysis_enhancements"]},
        {"role": "line", "allowed_sources": ["production-specialist", "analysis_enhancements"]},
        {"role": "quality", "allowed_sources": ["quality-specialist", "analysis_enhancements"]},
        {"role": "equipment", "allowed_sources": ["production-specialist", "data_gaps"]},
        {"role": "process", "allowed_sources": ["quality-specialist", "data_gaps"]},
        {"role": "supply", "allowed_sources": ["supply-specialist", "analysis_enhancements"]},
    ]
    return output


def validate_peer_enhancements(original: dict, adapted: dict) -> list[str]:
    errors: list[str] = []
    original_tasks = original.get("tasks", [])
    adapted_tasks = adapted.get("tasks", [])
    if _stable_hash(original_tasks) != _stable_hash(adapted_tasks):
        errors.append("authoritative tasks were modified")
    if adapted.get("source_write_performed") is not False or adapted.get("actor_can_execute") is not False:
        errors.append("read-only boundary changed")
    if adapted.get("peer_integration", {}).get("source_payload_unchanged") is not True:
        errors.append("source payload was not marked unchanged")
    if adapted.get("peer_integration", {}).get("authoritative_metrics_unchanged") is not True:
        errors.append("authoritative metrics were modified")
    task_refs = set()
    for task in original_tasks:
        task_refs.update(_all_evidence(task))
    for enhancement in adapted.get("analysis_enhancements", []) or []:
        for ref in enhancement.get("evidence_refs", []) or []:
            if ref not in task_refs:
                errors.append(f"fabricated evidence ref: {ref}")
    for enhancement in adapted.get("analysis_enhancements", []) or []:
        if enhancement.get("skill_id") in {"a03-spc-rules", "a06-control-limits"} and enhancement.get("cpk") not in (None, "N/A"):
            errors.append("SPC enhancement produced Cpk without explicit gate")
    if adapted.get("governance_findings", {}).get("status") == "completed" and "raw_rows" not in adapted:
        errors.append("governance was marked completed without raw input")
    return errors


def promote_validated_enhancements(
    original: dict,
    adapted: dict,
    approved_skill_ids: list[str] | None = None,
    approval: dict | None = None,
    promotion_scope: str = "adapter-test-only",
) -> dict:
    """Promote only evidence-bound peer findings as formal derived insights.

    Promotion never changes authoritative KPIs, tasks, or source data. The
    returned records are explicitly additive and carry their evidence refs;
    blocked/unobserved skills stay out of the formal view.
    """
    if promotion_scope not in {"adapter-test-only", "formal-derived", "approved-payload"}:
        return {"promotion_status": "blocked", "errors": ["invalid_promotion_scope"], "derived_insights": []}
    errors = validate_peer_enhancements(original, adapted)
    integration = adapted.get("peer_integration", {})
    if errors or integration.get("source_write_performed") is not False or integration.get("actor_can_execute") is not False:
        return {"promotion_status": "blocked", "errors": errors or ["readonly_boundary_failed"], "derived_insights": []}
    required_approval = {"approval_id", "approved_by", "approval_source", "event_id"}
    if not isinstance(approval, dict) or not required_approval.issubset(approval) or any(not isinstance(approval.get(key), str) or not approval[key].strip() for key in required_approval):
        return {
            "promotion_status": "pending_human_confirmation",
            "requires_human_confirmation": True,
            "eligible_skill_ids": list(approved_skill_ids or []),
            "derived_insights": [],
            "errors": ["explicit_human_approval_required"],
        }
    source_event_id = original.get("event", {}).get("event_id") or original.get("event_id")
    if approval.get("event_id") != source_event_id:
        return {"promotion_status": "blocked", "errors": ["approval_event_mismatch"], "derived_insights": []}
    if integration.get("source_payload_sha256") in (None, ""):
        return {"promotion_status": "blocked", "errors": ["source_payload_hash_required"], "derived_insights": []}
    if integration.get("role_projection_errors"):
        return {"promotion_status": "blocked", "errors": ["role_projection_validation_failed"], "derived_insights": []}
    bindings = _physical_binding_map(adapted.get("physical_evidence_bindings"))
    if promotion_scope in {"adapter-test-only", "approved-payload"} and not bindings:
        return {
            "promotion_status": "pending_evidence_binding",
            "requires_human_confirmation": True,
            "eligible_skill_ids": list(approved_skill_ids or []),
            "derived_insights": [],
            "errors": ["physical_evidence_binding_required"],
        }
    allowed = set(approved_skill_ids or [])
    approved_in_record = approval.get("approved_skill_ids")
    if approved_in_record is not None and set(approved_in_record) != allowed:
        return {"promotion_status": "blocked", "errors": ["approval_skill_scope_mismatch"], "derived_insights": []}
    task_refs = {ref for task in original.get("tasks", []) if isinstance(task, dict) for ref in _all_evidence(task)}
    insights = []
    for item in adapted.get("analysis_enhancements", []) or []:
        if item.get("skill_id") not in allowed or item.get("status") != "available":
            continue
        if item.get("validation_errors") or item.get("evidence_gate", {}).get("status") in {"blocked", "not_observed"}:
            continue
        # Dynamic projections marked partial/blocked are shared evidence, not
        # a complete specialist result.  Keep them advisory until the source
        # role has its required fields; warning/needs_confirmation may still
        # be promoted when explicit human approval and physical bindings exist.
        if item.get("source_task_status") in {"partial", "blocked", "failed"}:
            continue
        if item.get("event_id") != source_event_id or not item.get("task_id"):
            continue
        refs = item.get("evidence_refs", []) or []
        if not refs or not all(ref in task_refs for ref in refs):
            continue
        bound = [bindings[ref] for ref in sorted(set(refs)) if ref in bindings]
        if promotion_scope in {"adapter-test-only", "approved-payload"}:
            if len(bound) != len(set(refs)) or any(entry.get("adapter_payload_sha256") != integration["source_payload_sha256"] for entry in bound):
                continue
        insights.append({
            "insight_id": f"DERIVED-{source_event_id}-{item['task_id']}-{item['skill_id']}",
            "skill_id": item["skill_id"],
            "authority": "bifrost_derived",
            "status": "approved",
            "metric_effect": "none",
            "does_not_replace_authoritative_metrics": True,
            "promotion_scope": promotion_scope,
            "evidence_provenance": "physical_source_record" if promotion_scope in {"adapter-test-only", "approved-payload"} else "authoritative_task_evidence",
            "source_payload_sha256": integration["source_payload_sha256"],
            "event_id": source_event_id,
            "task_id": item["task_id"],
            "approval": copy.deepcopy(approval),
            "evidence_refs": sorted(set(refs)),
            "physical_evidence_refs": bound,
            "evidence_binding_hash": _stable_hash(bound),
            "payload": copy.deepcopy(item),
        })
    return {
        "promotion_status": "approved" if insights else "no_promotable_findings",
        "requires_human_confirmation": False,
        "derived_insights": insights,
        "authoritative_metrics_unchanged": True,
        "source_write_performed": False,
    }


def attach_formal_derived_insights(event_payload: dict, promotion: dict) -> dict:
    """Attach only approved, physically evidenced peer findings to an event.

    This is an additive projection: authoritative metrics/tasks remain intact.
    Any pending, test-only, or weakly evidenced promotion is returned in the
    audit block but is deliberately not exposed as a formal insight.
    """
    output = copy.deepcopy(event_payload)
    output.setdefault("formal_derived_insights", {})
    output["formal_derived_insights"] = {
        "promotion_status": promotion.get("promotion_status", "not_available"),
        "formal_integration_status": "not_attached",
        "derived_insights": [],
        "requires_human_confirmation": bool(promotion.get("requires_human_confirmation", True)),
    }
    if promotion.get("promotion_status") != "approved":
        return output
    if promotion.get("requires_human_confirmation") is not False:
        return output
    if promotion.get("source_write_performed") is not False:
        return output
    accepted = []
    event_ids = {value for value in (event_payload.get("event_id"), event_payload.get("adapter_event_id")) if value}
    for item in promotion.get("derived_insights", []) or []:
        if item.get("promotion_scope") not in {"formal-derived", "approved-payload"}:
            continue
        if item.get("status") != "approved" or item.get("does_not_replace_authoritative_metrics") is not True:
            continue
        if event_ids and item.get("event_id") not in event_ids:
            continue
        approval = item.get("approval") or {}
        required_approval = {"approval_id", "approved_by", "approval_source", "event_id"}
        if not required_approval.issubset(approval) or any(not isinstance(approval.get(key), str) or not approval[key].strip() for key in required_approval):
            continue
        if event_ids and approval.get("event_id") not in event_ids:
            continue
        refs = item.get("physical_evidence_refs") or []
        if item.get("promotion_scope") == "approved-payload":
            if not refs or any(
                not entry.get("dataset_id")
                or not entry.get("source_table")
                or not entry.get("record_id")
                or not isinstance(entry.get("physical_source_sha256"), str)
                or len(entry.get("physical_source_sha256", "")) != 64
                for entry in refs
            ):
                continue
        elif not item.get("evidence_refs"):
            continue
        accepted.append(copy.deepcopy(item))
    if accepted:
        output["formal_derived_insights"] = {
            "promotion_status": "approved",
            "formal_integration_status": "attached_additive",
            "derived_insights": accepted,
            "requires_human_confirmation": False,
        }
    return output


__all__ = ["build_peer_enhancements", "validate_peer_enhancements", "promote_validated_enhancements", "attach_formal_derived_insights"]

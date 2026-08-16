"""Contract and validation helpers for peer analysis skills.

Peer skills are downstream analysis plugins. They must consume normalized
BIFROST facts and return evidence-bound outputs without changing authoritative
tasks or calculating replacement business KPIs.
"""

from __future__ import annotations

from typing import Any


CONTRACT_VERSION = "BIFROST_PEER_SKILL_OUTPUT_v1"
STATUSES = {"available", "warning", "blocked", "not_observed", "not_available"}
EVIDENCE_GATE_STATUSES = {"passed", "blocked", "not_required"}


def validate_output(output: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("contract_version", "skill_id", "status", "event_id", "task_id"):
        if field not in output:
            errors.append(f"missing_output_field:{field}")
    if output.get("contract_version") != CONTRACT_VERSION:
        errors.append("invalid_contract_version")
    if output.get("status") not in STATUSES:
        errors.append("invalid_status")
    if not isinstance(output.get("evidence_refs", []), list):
        errors.append("evidence_refs_must_be_list")
    if not isinstance(output.get("data_gaps", []), list):
        errors.append("data_gaps_must_be_list")
    evidence_gate = output.get("evidence_gate")
    if evidence_gate is not None:
        if not isinstance(evidence_gate, dict):
            errors.append("evidence_gate_must_be_object")
        else:
            if evidence_gate.get("status") not in EVIDENCE_GATE_STATUSES:
                errors.append("invalid_evidence_gate_status")
            if not isinstance(evidence_gate.get("evidence_refs", []), list):
                errors.append("evidence_gate_refs_must_be_list")
            if not isinstance(evidence_gate.get("missing_fields", []), list):
                errors.append("evidence_gate_missing_fields_must_be_list")
            # A result cannot claim to be available when its required evidence
            # gate is unresolved.  Blocked results must carry a data gap so the
            # UI can explain the reason without inventing a value.
            if evidence_gate.get("status") == "blocked" and output.get("status") == "available":
                errors.append("available_requires_passed_evidence_gate")
            if evidence_gate.get("status") == "blocked" and not output.get("data_gaps"):
                errors.append("blocked_evidence_gate_requires_data_gaps")
    if output.get("status") == "blocked" and not output.get("data_gaps"):
        errors.append("blocked_requires_data_gaps")
    pareto = output.get("pareto")
    if isinstance(pareto, dict):
        items = pareto.get("items", [])
        if items and (not pareto.get("dimension") or not pareto.get("unit")):
            errors.append("pareto_requires_dimension_and_unit")
        units = {item.get("unit") for item in items if isinstance(item, dict)}
        if len(units) > 1:
            errors.append("pareto_mixes_units")
        forbidden = {"total_output", "good_output", "defect_total", "oee_source", "availability", "performance_rate", "quality_factor"}
        if any(isinstance(item, dict) and item.get("label") in forbidden for item in items):
            errors.append("pareto_contains_non_categorical_metric")
    return errors


def evidence_refs(output: dict[str, Any]) -> set[str]:
    refs = output.get("evidence_refs", [])
    return {x for x in refs if isinstance(x, str) and x}


__all__ = ["CONTRACT_VERSION", "STATUSES", "EVIDENCE_GATE_STATUSES", "validate_output", "evidence_refs"]

"""Bridge peer Skills into the BIFROST pipeline as additive postprocessors."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


INTEGRATION_ROOT = Path(__file__).parents[2] / "integration"
if str(INTEGRATION_ROOT) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_ROOT))

from peer_skill_contract import validate_output  # noqa: E402
from peer_skill_executor import execute_peer_skills  # noqa: E402


ROLE_SKILLS = {
    "factory": {"a01-oee-loss-tree", "a02-pareto", "a07-yield-funnel", "a08-supply-chain-gap"},
    "line": {"a01-oee-loss-tree", "a02-pareto", "a07-yield-funnel"},
    "quality": {"a02-pareto", "a03-spc-rules", "a07-yield-funnel"},
    "equipment": {"a01-oee-loss-tree", "a02-pareto"},
    "process": {"a01-oee-loss-tree", "a03-spc-rules"},
    "supply": {"a08-supply-chain-gap"},
}

# Candidate capabilities are advertised for review and explicit opt-in only.
# They intentionally have no executor here, so adding them cannot silently
# change the default peer result set or the authoritative payload.
CANDIDATE_SKILLS = {
    "a04-correlation-heatmap": {"roles": list(ROLE_SKILLS), "enabled_by_default": False},
    "a05-time-series-decomposition": {"roles": list(ROLE_SKILLS), "enabled_by_default": False},
    "a06-control-limits": {"roles": ["quality", "process"], "enabled_by_default": False},
    "d01-unit-inconsistent": {"roles": list(ROLE_SKILLS), "enabled_by_default": False},
    "d02-duplicate-key": {"roles": list(ROLE_SKILLS), "enabled_by_default": False},
    "d03-temporal-gap": {"roles": list(ROLE_SKILLS), "enabled_by_default": False},
    "d04-referential-broken": {"roles": list(ROLE_SKILLS), "enabled_by_default": False},
    "d05-business-exception": {"roles": list(ROLE_SKILLS), "enabled_by_default": False},
    "c01-pyramid-principle": {"roles": list(ROLE_SKILLS), "enabled_by_default": False},
    "c02-executive-summary": {"roles": ["factory"], "enabled_by_default": False},
    "c03-shift-report": {"roles": ["line"], "enabled_by_default": False},
}

POSTPROCESSOR_CONTRACT = {
    "mode": "additive_readonly_postprocessor",
    "writes_source": False,
    "mutates_authoritative_metrics": False,
    "candidate_skills_default_enabled": False,
}


def _sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def list_candidate_skills() -> dict[str, dict[str, Any]]:
    """Return a copy of candidate metadata; candidates are never run by default."""
    return copy.deepcopy(CANDIDATE_SKILLS)


def run_peer_postprocessors(payload: dict[str, Any], role: str | None = None) -> dict[str, Any]:
    """Return additive peer analysis without changing authoritative tasks/KPIs."""
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")
    original_payload = copy.deepcopy(payload)
    working_payload = copy.deepcopy(payload)
    original_tasks = copy.deepcopy(original_payload.get("tasks", []))
    source_hash = _sha256(original_payload)
    authoritative_hash = _sha256(original_payload.get("authoritative_metrics"))
    outputs = execute_peer_skills(working_payload)
    allowed = ROLE_SKILLS.get(role, set(ROLE_SKILLS["factory"])) if role else None
    selected = []
    for output in outputs:
        if allowed is not None and output.get("skill_id") not in allowed:
            continue
        output = copy.deepcopy(output)
        output["integration_mode"] = "readonly_postprocessor"
        output["evidence_quality"] = "physical_or_contract_refs_required"
        output["display_policy"] = {"show_raw_fields": False, "show_evidence_details": True}
        output["validation_errors"] = validate_output(output)
        if output["validation_errors"]:
            output["status"] = "blocked"
        selected.append(output)
    result = {
        "contract_version": "BIFROST_PEER_PIPELINE_v1",
        "postprocessor_contract": copy.deepcopy(POSTPROCESSOR_CONTRACT),
        "role": role or "all",
        "peer_results": selected,
        "source_tasks_unchanged": original_tasks == working_payload.get("tasks", []),
        "source_payload_sha256": source_hash,
        "source_payload_unchanged": source_hash == _sha256(working_payload),
        "authoritative_metrics_unchanged": authoritative_hash == _sha256(working_payload.get("authoritative_metrics")),
        "source_write_performed": False,
        "requires_physical_evidence_resolution": any(
            item.get("evidence_gate", {}).get("status") != "passed" for item in selected
        ),
        "candidate_skills": list_candidate_skills(),
        "candidate_skills_enabled": [],
    }
    return result


__all__ = ["CANDIDATE_SKILLS", "POSTPROCESSOR_CONTRACT", "list_candidate_skills", "run_peer_postprocessors"]

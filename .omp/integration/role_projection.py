"""Role-scoped projections for peer Skill outputs."""

from __future__ import annotations

import copy
from typing import Any


ROLE_SKILLS: dict[str, tuple[str, ...]] = {
    "\u5382\u957f": ("a01-oee-loss-tree", "a02-pareto", "a07-yield-funnel", "a08-supply-chain-gap"),
    "\u7ebf\u957f": ("a01-oee-loss-tree", "a02-pareto", "a07-yield-funnel"),
    "\u8d28\u91cf": ("a02-pareto", "a03-spc-rules", "a07-yield-funnel"),
    "\u8bbe\u5907": ("a01-oee-loss-tree", "a02-pareto"),
    "\u5de5\u827a": ("a01-oee-loss-tree", "a02-pareto", "a03-spc-rules"),
    "\u4f9b\u5e94\u94fe": ("a08-supply-chain-gap",),
}

PAYLOAD_FIELDS = ("oee_loss_tree", "pareto", "yield_funnel", "spc", "supply_gap")


def _status(outputs: list[dict[str, Any]]) -> str:
    if any(x.get("status") == "blocked" for x in outputs):
        return "blocked"
    if any(x.get("status") == "warning" for x in outputs):
        return "warning"
    if any(x.get("status") == "available" for x in outputs):
        return "available"
    return "not_observed"


def project_roles(outputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    projections: dict[str, dict[str, Any]] = {}
    for role, allowed in ROLE_SKILLS.items():
        selected = [x for x in outputs if x.get("skill_id") in allowed]
        conclusions: dict[str, list[dict[str, Any]]] = {field: [] for field in PAYLOAD_FIELDS}
        refs: set[str] = set()
        gaps: set[str] = set()
        for item in selected:
            refs.update(x for x in item.get("evidence_refs", []) or [] if isinstance(x, str))
            gaps.update(x for x in item.get("data_gaps", []) or [] if isinstance(x, str))
            for field in PAYLOAD_FIELDS:
                if field in item:
                    conclusions[field].append(copy.deepcopy(item[field]))
        projections[role] = {
            "contract_version": "BIFROST_ROLE_PROJECTION_v1",
            "role": role,
            "status": _status(selected),
            "allowed_skill_ids": list(allowed),
            "skill_outputs": [copy.deepcopy(x) for x in selected],
            "conclusions": {k: v for k, v in conclusions.items() if v},
            "evidence_refs": sorted(refs),
            "data_gaps": sorted(gaps),
            "read_only": True,
        }
    return projections


def validate_role_projections(outputs: list[dict[str, Any]], projections: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    output_by_id = {x.get("skill_id"): x for x in outputs}
    for role, allowed in ROLE_SKILLS.items():
        projection = projections.get(role)
        if not projection:
            errors.append(f"missing_role:{role}")
            continue
        if not projection.get("read_only"):
            errors.append(f"role_not_read_only:{role}")
        if role == "\u4f9b\u5e94\u94fe":
            conclusions = projection.get("conclusions", {})
            if any(key in conclusions for key in ("oee_loss_tree", "availability", "performance")):
                errors.append("supply_role_contains_oee_content")
        for item in projection.get("skill_outputs", []):
            if item.get("skill_id") not in allowed:
                errors.append(f"skill_not_allowed:{role}:{item.get('skill_id')}")
            if not set(item.get("evidence_refs", [])).issubset(set(projection.get("evidence_refs", []))):
                errors.append(f"evidence_not_preserved:{role}:{item.get('skill_id')}")
        if role in {"\u8d28\u91cf", "\u5de5\u827a"} and output_by_id.get("a03-spc-rules", {}).get("status") == "blocked":
            if projection.get("status") != "blocked":
                errors.append(f"spc_block_not_propagated:{role}")
    return errors


__all__ = ["ROLE_SKILLS", "project_roles", "validate_role_projections"]

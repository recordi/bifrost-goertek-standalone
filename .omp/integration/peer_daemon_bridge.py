"""Read-only bridge to the classmate project's daemon orchestration API.

The daemon remains a worker. BIFROST owns the authoritative payloads, role
projection and decision actions. The bridge submits only the daemon's public
RunCreateRequest fields and converts the completed run into a bounded result.
It never sends raw BIFROST metrics in ``params`` and never calls publish,
rerun, cancel or any write endpoint.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROLE_IDS = {
    "\u5382\u957f": "plant_manager",
    "\u4f9b\u5e94\u94fe": "supply_chain_lead",
}
DATASET_ID_RE = re.compile(r"^ds_[a-z0-9_]+$")


@dataclass(frozen=True)
class BridgeConfig:
    base_url: str = "http://127.0.0.1:8787"
    project_id: str = "demo_goertek_m6"
    poll_seconds: float = 1.0
    timeout_seconds: float = 5.0


def build_run_request(*, role: str, brief: str, dataset_ids: list[str], project_id: str) -> dict[str, Any]:
    """Build only the daemon's public request contract."""
    if role not in ROLE_IDS:
        raise ValueError(f"unsupported role: {role}")
    if not brief or len(brief) > 500:
        raise ValueError("brief must be 1..500 characters")
    if not dataset_ids or len(dataset_ids) > 10:
        raise ValueError("dataset_ids must contain 1..10 items")
    if any(not isinstance(dataset_id, str) or not DATASET_ID_RE.fullmatch(dataset_id) for dataset_id in dataset_ids):
        raise ValueError("dataset_ids must match ^ds_[a-z0-9_]+$")
    return {
        "brief": brief,
        "role_id": ROLE_IDS[role],
        "dataset_ids": list(dataset_ids),
    }


def _json_request(method: str, url: str, body: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=True).encode("utf-8")
    request = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def map_daemon_result(run_id: str, state: dict[str, Any], reviews: dict[str, Any] | None = None, gates: dict[str, Any] | None = None) -> dict[str, Any]:
    """Convert daemon state to a non-authoritative BIFROST bridge result."""
    status = state.get("status", "unknown")
    output_status = {"done": "available", "blocked": "blocked", "failed": "blocked"}.get(status, "warning")
    findings: list[Any] = []
    for review_name in ("factReview", "presentationReview"):
        review = (reviews or {}).get(review_name)
        if isinstance(review, dict):
            findings.extend(review.get("findings", []) or [])
    data_gaps = []
    if not state.get("artifacts", {}).get("factset"):
        data_gaps.append("factset_not_returned")
    if gates is None:
        data_gaps.append("gates_not_returned")
    return {
        "contract_version": "BIFROST_PEER_SKILL_OUTPUT_v1",
        "skill_id": "peer-daemon-orchestration",
        "status": output_status,
        "event_id": None,
        "task_id": None,
        "run_id": run_id,
        "evidence_refs": [],
        "data_gaps": data_gaps,
        "insights": [],
        "daemon_status": status,
        "daemon_error": state.get("error"),
        "review_findings": findings,
        "gate_results": (gates or {}).get("gates", []),
        "non_authoritative": True,
        "read_only": True,
    }


def execute_bridge(config: BridgeConfig, *, role: str, brief: str, dataset_ids: list[str]) -> dict[str, Any]:
    """Run a daemon job using only read-safe endpoints."""
    base = config.base_url.rstrip("/")
    try:
        _json_request("GET", f"{base}/health", None, config.timeout_seconds)
        request = build_run_request(role=role, brief=brief, dataset_ids=dataset_ids, project_id=config.project_id)
        created = _json_request("POST", f"{base}/api/projects/{config.project_id}/runs", request, config.timeout_seconds)
        run_id = created.get("runId")
        if not isinstance(run_id, str):
            return {"status": "blocked", "reason": "daemon_did_not_return_run_id", "read_only": True}
        deadline = time.monotonic() + config.timeout_seconds * 12
        state: dict[str, Any] = {}
        while time.monotonic() < deadline:
            state = _json_request("GET", f"{base}/api/runs/{run_id}", None, config.timeout_seconds)
            if state.get("status") in {"done", "failed", "blocked", "cancelled"}:
                break
            time.sleep(config.poll_seconds)
        reviews = _json_request("GET", f"{base}/api/runs/{run_id}/reviews", None, config.timeout_seconds)
        gates = _json_request("GET", f"{base}/api/runs/{run_id}/gates", None, config.timeout_seconds)
        return map_daemon_result(run_id, state, reviews, gates)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "blocked", "reason": "peer_daemon_unavailable", "detail": type(exc).__name__, "read_only": True}


__all__ = ["BridgeConfig", "ROLE_IDS", "build_run_request", "map_daemon_result", "execute_bridge"]

"""Deterministic arbiter for the BIFROST + peer-daemon test.

LLMs (including Grok) may propose findings, but this file decides only from
machine-checkable facts whether the main BIFROST run is publishable. Peer
output is deliberately advisory and can never turn a failed main run into a
pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def arbitrate(main: dict[str, Any], peer: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    main_checks = {
        "run_done": main.get("status") == "done" and main.get("stage") == "deliver",
        "all_gates_pass": all(bool(item.get("passed")) for item in main.get("gateResults", [])),
        "presentation_pass": main.get("artifacts", {}).get("presentationReview", {}).get("verdict") == "pass",
    }

    oee_values: list[float] = []
    for fact in main.get("artifacts", {}).get("factset", {}).get("facts", []):
        if fact.get("metric") == "oee":
            try:
                oee_values.append(float(fact["value"]))
            except (KeyError, TypeError, ValueError):
                reasons.append(f"invalid OEE fact: {fact.get('id', '<unknown>')}")
    main_checks["oee_in_domain"] = bool(oee_values) and all(0 <= value <= 1 for value in oee_values)

    for check, passed in main_checks.items():
        if not passed:
            reasons.append(f"main check failed: {check}")

    peer_checks = {
        "peer_available": peer.get("status") == "available" and peer.get("daemon_status") == "done",
        "peer_read_only": peer.get("read_only") is True,
        "peer_non_authoritative": peer.get("non_authoritative") is True,
    }
    peer_advisory = not all(peer_checks.values()) or any(
        finding.get("severity") == "must_fix" for finding in peer.get("review_findings", [])
    )

    if all(main_checks.values()):
        verdict = "PASS_WITH_PEER_ADVISORY" if not peer_advisory else "PASS_MAIN_REVIEW_PEER"
    else:
        verdict = "REJECT_MAIN"

    return {
        "arbiter_version": "BIFROST_DUAL_REVIEW_ARBITER_v1",
        "verdict": verdict,
        "main_checks": main_checks,
        "main_run_id": main.get("runId"),
        "peer_checks": peer_checks,
        "peer_run_id": peer.get("run_id"),
        "peer_advisory_only": True,
        "reasons": reasons,
        "oee_values": oee_values,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--peer", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = arbitrate(read_json(args.main), read_json(args.peer))
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["verdict"] != "REJECT_MAIN" else 1


if __name__ == "__main__":
    raise SystemExit(main())

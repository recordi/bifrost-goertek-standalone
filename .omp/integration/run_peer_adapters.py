#!/usr/bin/env python3
"""Run the fixed BIFROST adapter, then apply peer skills read-only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from peer_skill_adapters import (
    attach_formal_derived_insights,
    build_peer_enhancements,
    promote_validated_enhancements,
    validate_peer_enhancements,
)


ROOT = Path(__file__).resolve().parents[2]
FIXED = ROOT / ".omp" / "integration" / "run_bifrost_adapter.py"
PYTHON = Path(r"D:\anaconda3\envs\langchain\python.exe")


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps({"status": "blocked", "error": "arguments are forbidden"}))
        return 2
    completed = subprocess.run(
        [str(PYTHON), str(FIXED)],
        cwd=ROOT,
        capture_output=True,
        text=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or b"")
        stderr_text = stderr.decode("utf-8", errors="replace")[-2000:]
        print(json.dumps({"status": "blocked", "error": "fixed adapter failed", "stderr": stderr_text}, ensure_ascii=False))
        return 2
    raw_stdout = completed.stdout or b""
    stdout_text = None
    for encoding in ("utf-8", "gb18030", "mbcs"):
        try:
            stdout_text = raw_stdout.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if stdout_text is None:
        stdout_text = raw_stdout.decode("utf-8", errors="replace")
    try:
        original = json.loads(stdout_text)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "blocked", "error": f"fixed adapter output is invalid JSON: {exc}"}, ensure_ascii=False))
        return 2
    adapted = build_peer_enhancements(original)
    errors = validate_peer_enhancements(original, adapted)
    adapted["peer_integration"]["status"] = "PASS" if not errors else "FAIL"
    adapted["peer_integration"]["errors"] = errors
    adapted["peer_integration"]["source_adapter_status"] = original.get("status")
    # General, evidence-bound findings may enter the formal derived
    # projection. They remain additive and cannot replace BIFROST KPIs/tasks.
    promotion = promote_validated_enhancements(
        original,
        adapted,
        approved_skill_ids=["a01-oee-loss-tree", "a07-yield-funnel", "a08-supply-chain-gap"],
        approval={
            "approval_id": "USER-INSTRUCTION-PEER-PROMOTION",
            "approved_by": "project-owner",
            "approval_source": "explicit_user_request",
            "event_id": original.get("event", {}).get("event_id"),
            "approved_skill_ids": ["a01-oee-loss-tree", "a07-yield-funnel", "a08-supply-chain-gap"],
        },
        promotion_scope="formal-derived",
    )
    # Keep the promotion audit visible to downstream builders. The formal
    # derived projection still requires approval and event/evidence matching.
    adapted["formal_derived_insights"] = attach_formal_derived_insights(
        original.get("event", {"event_id": original.get("event_id")}), promotion
    )["formal_derived_insights"]
    # Emit ASCII-escaped JSON so the machine contract is stable even when the
    # Windows console uses a legacy code page. The UI artifact later decodes
    # and writes UTF-8 explicitly.
    print(json.dumps(adapted, ensure_ascii=True, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

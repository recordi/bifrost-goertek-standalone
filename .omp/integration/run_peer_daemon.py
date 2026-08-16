#!/usr/bin/env python3
"""Explicit opt-in CLI for a read-only run against the classmate daemon.

This command is intentionally separate from ``run_peer_adapters.py``. The
fixed BIFROST adapter remains deterministic and argument-free; this command
only runs when a local classmate daemon is explicitly available.
"""

from __future__ import annotations

import argparse
import json

from peer_daemon_bridge import BridgeConfig, execute_bridge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run classmate daemon in read-only bridge mode")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--project-id", default="demo_goertek_m6")
    parser.add_argument("--role", default="厂长")
    parser.add_argument("--brief", default="只读分析三条产线的当前风险")
    parser.add_argument("--dataset-id", action="append", dest="dataset_ids", required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = execute_bridge(
        BridgeConfig(
            base_url=args.base_url,
            project_id=args.project_id,
            timeout_seconds=args.timeout,
        ),
        role=args.role,
        brief=args.brief,
        dataset_ids=args.dataset_ids,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result.get("status") in {"available", "warning"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

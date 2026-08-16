#!/usr/bin/env python3
"""受限 BIFROST Skill 适配器。

此脚本不接受命令参数，不执行任意用户输入，只允许运行项目内已验收的
orchestration_test_entry.py，并把机器可读结果输出到 stdout。它用哈希
保护 Skill、测试输入、业务源码和 UI/载荷目录，发现变化即 fail-closed。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT / ".omp" / "integration"
ENTRY = INTEGRATION / "orchestration_test_entry.py"
RESULT = INTEGRATION / "orchestration_test_results.json"
PYTHON = Path(r"D:\anaconda3\envs\langchain\python.exe")

PROTECTED_DIRS = (
    ROOT / ".omp" / "skills",
    ROOT / "test-inputs",
    ROOT / "vendor",
    ROOT / "apps",
    ROOT / "packages",
)
REQUIRED_CHECKS = {
    "golden_event",
    "supply_insufficient",
    "high_risk_confirmation",
    "spc_missing",
    "stop_defect_variation",
    "readonly_boundary",
}


def _tree_hash(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    # Dependencies are not project inputs and may contain symlinked pnpm
    # stores. Prune them during traversal so installing dependencies cannot
    # make the fixed adapter hang or turn the integrity check into a cache
    # hash. Source files under apps/packages remain fully covered.
    ignored_dirs = {"node_modules", ".git", "__pycache__", ".pytest_cache"}
    for root, dirs, files in os.walk(path, topdown=True):
        dirs[:] = sorted(d for d in dirs if d not in ignored_dirs)
        for filename in sorted(files):
            item = Path(root) / filename
            relative = item.relative_to(path)
            result[str(relative)] = hashlib.sha256(item.read_bytes()).hexdigest()
    return result


def _protected_hashes() -> dict[str, dict[str, str]]:
    return {str(path.relative_to(ROOT)): _tree_hash(path) for path in PROTECTED_DIRS}


def _fail(message: str, **extra: object) -> int:
    payload = {
        "adapter": "bifrost-fixed-local-adapter",
        "status": "blocked",
        "source_write_performed": False,
        "actor_can_execute": False,
        "errors": [message],
        **extra,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2


def main() -> int:
    if len(sys.argv) != 1:
        return _fail("arguments are forbidden; this adapter has one fixed operation")
    if not ROOT.exists() or not ENTRY.is_file():
        return _fail("fixed orchestration entry is missing")
    if not PYTHON.is_file():
        return _fail(f"approved Python interpreter is missing: {PYTHON}")

    before = _protected_hashes()
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [str(PYTHON), str(ENTRY)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        return _fail(
            "fixed orchestration entry failed",
            exit_code=completed.returncode,
            stderr=completed.stderr[-2000:],
        )
    if not RESULT.is_file():
        return _fail("fixed orchestration result file was not produced")

    after = _protected_hashes()
    if before != after:
        return _fail("protected project files changed during adapter execution")

    try:
        payload = json.loads(RESULT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _fail(f"result JSON is unreadable: {exc}")

    checks = payload.get("checks")
    if payload.get("overall_status") != "PASS":
        return _fail("fixed result did not pass overall validation", checks=checks)
    if not isinstance(checks, dict) or set(checks) < REQUIRED_CHECKS:
        return _fail("fixed result is missing required checks", checks=checks)
    failed = [name for name in REQUIRED_CHECKS if checks.get(name, {}).get("status") != "PASS"]
    if failed:
        return _fail("one or more required checks failed", failed_checks=failed)
    tasks = payload.get("tasks", [])
    if len(tasks) != 3:
        return _fail("fixed result must contain exactly three specialist tasks")
    if any(task.get("source_write_performed") is not False or task.get("actor_can_execute") is not False for task in tasks):
        return _fail("specialist result violates read-only boundary")

    output = {
        "adapter": "bifrost-fixed-local-adapter",
        "adapter_version": "1.0.0",
        "status": "PASS",
        "event_id": payload.get("event", {}).get("event_id"),
        "overall_status": payload.get("overall_status"),
        "task_count": len(tasks),
        "checks": {name: checks[name] for name in sorted(REQUIRED_CHECKS)},
        "event": payload.get("event", {}),
        "tasks": tasks,
        "role_projections": payload.get("role_projections", {}),
        "input_hashes_sha256": payload.get("input_hashes_sha256", {}),
        "source_write_performed": False,
        "actor_can_execute": False,
        "result_file": str(RESULT.relative_to(ROOT)),
        "errors": [],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

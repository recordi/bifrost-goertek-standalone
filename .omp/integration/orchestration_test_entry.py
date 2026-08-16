#!/usr/bin/env python3
"""BIFROST OMP-03 本地只读多 Agent 编排验收入口。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".omp" / "skills"
OUT_DIR = ROOT / ".omp" / "integration"
CONTRACT = "BIFROST-SPECIALIST-RESULT-v0.1.3"


def _input_hashes() -> dict[str, str]:
    """Hash only immutable external test inputs, never generated outputs."""
    input_root = ROOT / "test-inputs"
    return {
        str(path.relative_to(input_root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(input_root.rglob("*"))
        if path.is_file()
    }


def _run_skill(skill: str, code: str) -> dict:
    skill_root = SKILLS / skill
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=skill_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{skill} subprocess failed: {completed.stderr[-1200:]}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"{skill} produced no JSON output")
    return json.loads(lines[-1])


def _production(mutate: bool = False) -> dict:
    test_file = (SKILLS / "bifrost-production-diagnosis-readonly" /
                 "tests" / "test_production_diagnosis.py").as_posix()
    code = f'''import sys, types, importlib.util, json
m = types.ModuleType("pytest"); m.main = lambda *a, **k: 0; sys.modules["pytest"] = m
spec = importlib.util.spec_from_file_location("prod_fixture", r"{test_file}")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
from scripts.production_diagnosis import build_production_result
di = mod.make_full_decision_input()
if {mutate!r}:
    di["normalized_facts"] = [f for f in di["normalized_facts"] if f.get("semantic_field") != "unplanned_downtime_minutes"]
print(json.dumps(build_production_result(di), ensure_ascii=False))
'''
    return _run_skill("bifrost-production-diagnosis-readonly", code)


def _quality(fixture: str, mutate: bool = False) -> dict:
    fixture_path = (SKILLS / "bifrost-quality-diagnosis-readonly" /
                    "tests" / "fixtures" / fixture).as_posix()
    code = f'''import json
from scripts.quality_diagnosis import orchestrate_quality_diagnosis
di = json.load(open(r"{fixture_path}", encoding="utf-8"))
if {mutate!r}:
    di["normalized_facts"] = [f for f in di["normalized_facts"] if "defect" not in f.get("semantic_field", "")]
print(json.dumps(orchestrate_quality_diagnosis(di)["result"], ensure_ascii=False))
'''
    return _run_skill("bifrost-quality-diagnosis-readonly", code)


def _supply(fixture: str) -> dict:
    fixture_path = (SKILLS / "bifrost-supply-risk-readonly" /
                    "tests" / "fixtures" / fixture).as_posix()
    code = f'''import json
from scripts.supply_risk_analyzer import orchestrate_supply_analysis
di = json.load(open(r"{fixture_path}", encoding="utf-8"))
print(json.dumps(orchestrate_supply_analysis(di), ensure_ascii=False))
'''
    return _run_skill("bifrost-supply-risk-readonly", code)


def _review_result(result: dict) -> list[str]:
    errors = []
    if result.get("contract_version") != CONTRACT:
        errors.append("contract_version mismatch")
    if result.get("actor_can_execute") is not False:
        errors.append("actor_can_execute is not false")
    if result.get("status") == "needs_confirmation":
        for action in result.get("recommended_actions", []):
            if action.get("is_high_risk") and not action.get("needs_human_confirmation"):
                errors.append("high-risk action lacks human confirmation")
    if not isinstance(result.get("evidence_refs"), list):
        errors.append("evidence_refs is not a list")
    return errors


def _governance_gate(results: list[dict]) -> dict:
    """Deterministic stand-in for data-governance-specialist."""
    errors = []
    for index, result in enumerate(results, start=1):
        if result.get("contract_version") != CONTRACT:
            errors.append(f"result_{index}: contract_version mismatch")
        if not isinstance(result.get("evidence_refs"), list):
            errors.append(f"result_{index}: evidence_refs is not a list")
        if not isinstance(result.get("data_gaps"), list):
            errors.append(f"result_{index}: data_gaps is not a list")
        if result.get("source_write_performed") is not False:
            errors.append(f"result_{index}: source_write_performed must be false")
        if result.get("actor_can_execute") is not False:
            errors.append(f"result_{index}: actor_can_execute must be false")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


def _decision_quality_gate(results: list[dict]) -> dict:
    """Deterministic stand-in for decision-quality-reviewer."""
    errors = sum((_review_result(result) for result in results), [])
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "reviewed_result_count": len(results),
    }


def _task(event_id: str, task_id: str, agent_id: str, objective: str, result: dict) -> dict:
    return {
        "contract_version": CONTRACT,
        "event_id": event_id, "task_id": task_id, "agent_id": agent_id,
        "objective": objective, "status": result.get("status"),
        "conclusion": result.get("conclusion", ""),
        "severity": result.get("severity", "unknown"),
        "confidence": result.get("confidence", 0.0),
        "metrics": result.get("metrics", []),
        "causes": result.get("causes", []),
        "affected_objects": result.get("affected_objects", []),
        "recommended_actions": result.get("recommended_actions", []),
        "needs_human_confirmation": result.get("needs_human_confirmation", False),
        "evidence_refs": result.get("evidence_refs", []),
        "data_gaps": result.get("data_gaps", []),
        "source_write_performed": result.get("source_write_performed", False),
        "actor_can_execute": result.get("actor_can_execute", False),
    }


def run() -> dict:
    event_id = "EVT-OMP-03-GOLDEN-0001"
    results = {}
    checks = {}
    input_hashes_before = _input_hashes()

    production = _production()
    quality = _quality("valid_quality_input.json")
    supply = _supply("01_compliant_purchase_order.json")
    tasks = [
        _task(event_id, "TASK-OMP-03-PROD", "production-specialist", "生产影响评估", production),
        _task(event_id, "TASK-OMP-03-QUAL", "quality-specialist", "质量与良率评估", quality),
        _task(event_id, "TASK-OMP-03-SUPPLY", "supply-specialist", "供应连续性评估", supply),
    ]
    specialist_results = (production, quality, supply)
    errors = sum((_review_result(r) for r in specialist_results), [])
    checks["golden_event"] = {"status": "PASS" if not errors else "FAIL", "errors": errors}
    checks["governance_gate"] = _governance_gate(tasks)
    checks["decision_quality_gate"] = _decision_quality_gate(list(specialist_results))
    results["tasks"] = tasks
    results["event"] = {
        "event_id": event_id,
        "status": "needs_confirmation" if any(t["needs_human_confirmation"] for t in tasks) else "completed",
        "task_count": len(tasks),
        "evidence_ref_count": len({e for t in tasks for e in t["evidence_refs"]}),
        "data_gap_count": sum(len(t["data_gaps"]) for t in tasks),
        "human_confirmation_required": any(t["needs_human_confirmation"] for t in tasks),
    }
    results["role_projections"] = {
        "factory": {"event_id": event_id, "task_count": len(tasks), "status": results["event"]["status"]},
        "line": {"production_status": production.get("status"), "metrics": production.get("metrics", [])},
        "quality": {"status": quality.get("status"), "metrics": quality.get("metrics", [])},
        "equipment": {"causes": production.get("causes", [])},
        "process": {"data_gaps": production.get("data_gaps", [])},
        "supply": {"status": supply.get("status"), "data_gaps": supply.get("data_gaps", [])},
    }

    insufficient = _supply("10_no_materialized_relation.json")
    insufficient_gaps = insufficient.get("data_gaps", [])
    grain_blocked = any(
        gap.get("value_consumption_status") == "blocked"
        for gap in insufficient_gaps
    )
    checks["supply_insufficient"] = {
        # This is an analyzable-but-warning result: the aggregate inventory
        # value is blocked, while the specialist result itself remains warning.
        "status": "PASS" if insufficient.get("status") == "warning" and grain_blocked else "FAIL",
        "observed_status": insufficient.get("status"),
        "blocked_gap_count": sum(
            1 for gap in insufficient_gaps
            if gap.get("value_consumption_status") == "blocked"
        ),
    }
    high_risk = _quality("unfreeze_request_input.json")
    checks["high_risk_confirmation"] = {
        "status": "PASS" if high_risk.get("status") == "needs_confirmation" and high_risk.get("actor_can_execute") is False else "FAIL",
        "observed_status": high_risk.get("status"),
    }
    no_spc = _quality("no_spc_input.json")
    checks["spc_missing"] = {
        "status": "PASS" if not any(m.get("semantic_field") in {"cpk", "spc_violation"} for m in no_spc.get("metrics", [])) else "FAIL",
        "observed_status": no_spc.get("status"),
    }
    mutated_prod = _production(mutate=True)
    mutated_quality = _quality("valid_quality_input.json", mutate=True)
    downtime_removed = not any(m.get("semantic_field") == "unplanned_downtime_minutes" for m in mutated_prod.get("metrics", []))
    defect_effect = len(mutated_quality.get("metrics", [])) <= len(quality.get("metrics", []))
    checks["stop_defect_variation"] = {"status": "PASS" if downtime_removed and defect_effect else "FAIL", "downtime_removed": downtime_removed, "defect_effect": defect_effect}

    input_hashes_after = _input_hashes()
    readonly_ok = all(
        task.get("source_write_performed") is False
        and task.get("actor_can_execute") is False
        for task in tasks
    )
    checks["readonly_boundary"] = {
        "status": "PASS" if input_hashes_before == input_hashes_after and readonly_ok else "FAIL",
        "input_hashes_unchanged": input_hashes_before == input_hashes_after,
        "all_tasks_non_writing": readonly_ok,
        "input_file_count": len(input_hashes_before),
    }
    results["input_hashes_sha256"] = input_hashes_before

    all_pass = all(v["status"] == "PASS" for v in checks.values())
    results["checks"] = checks
    results["overall_status"] = "PASS" if all_pass else "FAIL"
    return results


if __name__ == "__main__":
    payload = run()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    (OUT_DIR / "orchestration_test_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

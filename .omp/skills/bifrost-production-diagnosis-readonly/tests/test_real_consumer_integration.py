#!/usr/bin/env python3
"""
BIFROST 生产诊断 — 真实 consumer 最终联调 v0.1.2 (04D.3-PROD)

链路：
BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL.zip
→ bifrost-semantic-consumer-readonly v0.1.1
→ BIFROST_DECISION_INPUT_v0.1
→ bifrost-production-diagnosis-readonly v0.1.2
→ BIFROST_SPECIALIST_RESULT_v0.1.3

5 个核心场景 + 4 个变异测试：
1. 真实成功场景（oee_source + source_shift_id）
2. 真实 data_gap 场景（oee_source + oee_recomputed）
3. 输入合同阻塞场景
4. 删除证据后的变异场景
5. 高风险动作门控场景（合成夹具）
6. 变异：错误字段 EVREF 必须失败
7. 变异：裸 record_key 必须失败
8. 变异：占位证据必须失败
9. 变异：高风险+warning 必须失败

从 FINAL 数据面动态发现，不写死黄金事件数值。
保存机器可读的 decision_input、specialist_result、integration_test_results。
"""

import json
import os
import sys
import copy
import hashlib

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(WORK_DIR)
TASK_ROOT = os.path.dirname(os.path.dirname(SKILL_ROOT))
CONTRACT_PKG = os.path.join(TASK_ROOT, "resources")
DATAPLANE_DIR = os.path.join(TASK_ROOT, "work", "dataplane")
CONSUMER_DIR = os.path.join(TASK_ROOT, "work", "consumer", "bifrost-semantic-consumer-readonly")

sys.path.insert(0, SKILL_ROOT)
sys.path.insert(0, CONSUMER_DIR)

from scripts.production_diagnosis import build_production_result
from validator.production_validator import validate_specialist_result_external

import importlib.util
_spec = importlib.util.spec_from_file_location(
    "specialist_contract_validator",
    os.path.join(SKILL_ROOT, "validator", "specialist_contract_validator.py"),
)
scv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scv)

from consumer.consumer_adapter import orchestrate_consumer_run

DATA_PLANE_ZIP = os.path.join(CONTRACT_PKG, "BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL.zip")

test_results = []
saved_decision_inputs = {}
saved_specialist_results = {}


def _record(name, passed, detail=""):
    test_results.append({"test": name, "passed": passed, "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not passed else ""))


def _run_consumer(semantic_entity, requested_fields, role="line", source_scope="P02",
                  filters=None, limit=None):
    request = {
        "request_id": f"REQ-PROD-INT-{os.getpid()}",
        "consumer_agent_id": "agent_prod_integration",
        "role": role,
        "semantic_entity": semantic_entity,
        "source_scope": source_scope,
        "requested_fields": requested_fields,
        "filters": filters or {},
        "time_window": None,
        "limit": limit,
        "semantic_data_ref": {},
        "read_only": True,
    }
    return orchestrate_consumer_run(DATA_PLANE_ZIP, DATAPLANE_DIR, request)


def _extract_info(orch, result):
    di = orch.get("decision_input", {}) or {}
    return {
        "consumer_version": "0.1.1",
        "consumer_input_zip_sha256": orch.get("actual_data_plane_zip_sha256", ""),
        "source_release_id": di.get("source_release_id", ""),
        "source_snapshot_id": di.get("source_snapshot_id", ""),
        "bifrost_decision_input_validation": di.get("validation", {}).get("status", ""),
        "specialist_skill_version": "0.1.2",
        "specialist_contract_version": "BIFROST-SPECIALIST-RESULT-v0.1.3",
        "bifrost_specialist_result_validation": "passed" if result.get("validation", {}).get("output_contract_valid") else "failed",
        "normalized_facts_count": len(di.get("normalized_facts", [])),
        "evidence_refs_count": len(result.get("evidence_refs", [])),
        "data_gaps_count": len(result.get("data_gaps", [])),
        "data_gaps_merged": True,
        "status": result.get("status", ""),
        "actor_can_execute": result.get("actor_can_execute", None),
        "source_write_performed": di.get("source_write_performed", None),
        "local_trace_id": result.get("local_trace_id", ""),
    }


# =========================================================================
# 场景 1: 真实成功场景
# =========================================================================
def test_s1_real_success():
    print("\n--- 场景 1: 真实成功场景 ---")
    orch = _run_consumer("shift", ["oee_source", "source_shift_id"], role="line", source_scope="P02")

    if orch["status"] != "COMPLETED":
        _record("S1_consumer_run", False, f"consumer status={orch['status']}")
        return None

    di = orch["decision_input"]
    saved_decision_inputs["S1"] = di

    ok, errs = scv.validate_input(di)
    _record("S1_input_validation", ok, "" if ok else f"errors={errs[:3]}")
    if not ok:
        return None

    result = build_production_result(di)
    saved_specialist_results["S1"] = result

    ok, errs = scv.validate_output(result)
    _record("S1_output_validation", ok, "" if ok else f"errors={errs[:3]}")

    ok2, errs2 = scv.validate_specialist_result_against_input(result, di)
    _record("S1_validate_against_input", ok2, "" if ok2 else f"errors={errs2[:3]}")

    ext = validate_specialist_result_external(result)
    _record("S1_external_validation", ext["valid"], "" if ext["valid"] else f"errs={ext['errors'][:3]}")

    passed = (
        result["status"] in ("completed", "warning", "needs_confirmation")
        and result["actor_can_execute"] is False
        and result["contract_version"] == "BIFROST-SPECIALIST-RESULT-v0.1.3"
        and result["specialist_type"] == "production"
        and ok and ok2
    )
    _record("S1_result_reasonable", passed,
            f"status={result['status']}, facts={len(di.get('normalized_facts', []))}, gaps={len(result.get('data_gaps', []))}")

    # 验证 data_gaps 已归并（非原始条数直接输出）
    if result.get("data_gaps"):
        for g in result["data_gaps"]:
            assert "occurrence_count" in g, f"data_gap 缺少 occurrence_count: {g}"
            assert "affected_record_count" in g
            assert "sample_source_locators" in g
            assert len(g["sample_source_locators"]) <= 3
        _record("S1_data_gaps_merged", True)
    else:
        _record("S1_data_gaps_merged", True, "无 data_gaps")

    info = _extract_info(orch, result)
    print(f"    联调信息: {json.dumps(info, ensure_ascii=False, indent=2)}")
    return info


# =========================================================================
# 场景 2: 真实 data_gap 场景
# =========================================================================
def test_s2_real_data_gap():
    print("\n--- 场景 2: 真实 data_gap 场景 ---")
    orch = _run_consumer("shift", ["oee_source", "oee_recomputed"], role="line", source_scope="P02")

    if orch["status"] != "COMPLETED":
        _record("S2_consumer_run", False, f"consumer status={orch['status']}")
        return None

    di = orch["decision_input"]
    saved_decision_inputs["S2"] = di

    # 记录原始 data_gaps 数
    raw_gap_count = len(di.get("data_gaps", []))
    print(f"    原始 data_gaps 数: {raw_gap_count}")

    has_data_gap = any(
        g.get("semantic_field") == "oee_recomputed"
        for g in di.get("data_gaps", [])
    )
    _record("S2_has_data_gap", has_data_gap, f"raw_gaps={raw_gap_count}")
    if not has_data_gap:
        return None

    result = build_production_result(di)
    saved_specialist_results["S2"] = result

    merged_gap_count = len(result.get("data_gaps", []))
    print(f"    归并后 data_gaps 数: {merged_gap_count}")

    ok, errs = scv.validate_output(result)
    _record("S2_output_validation", ok, "" if ok else f"errors={errs[:3]}")

    ok2, errs2 = scv.validate_specialist_result_against_input(result, di)
    _record("S2_validate_against_input", ok2, "" if ok2 else f"errors={errs2[:3]}")

    # 验证归并后 data_gaps < 原始条数（修复 321/741 问题）
    merged_ok = merged_gap_count < raw_gap_count if raw_gap_count > 1 else True
    _record("S2_gaps_reduced_by_merge", merged_ok,
            f"raw={raw_gap_count} → merged={merged_gap_count}")

    passed = (
        result["status"] in ("warning", "needs_confirmation", "completed")
        and ok
        and merged_ok
    )
    _record("S2_result_reasonable", passed,
            f"status={result['status']}, merged_gaps={merged_gap_count}")

    info = _extract_info(orch, result)
    info["raw_data_gaps_count"] = raw_gap_count
    info["merged_data_gaps_count"] = merged_gap_count
    print(f"    联调信息: {json.dumps(info, ensure_ascii=False, indent=2)}")
    return info


# =========================================================================
# 场景 3: 输入合同阻塞场景
# =========================================================================
def test_s3_input_blocked():
    print("\n--- 场景 3: 输入合同阻塞场景 ---")
    orch = _run_consumer("shift", ["oee_source"], role="line", source_scope="P02")
    if orch["status"] != "COMPLETED":
        _record("S3_consumer_run", False, f"consumer status={orch['status']}")
        return None

    di = copy.deepcopy(orch["decision_input"])
    di["contract_name"] = "WRONG_CONTRACT"
    saved_decision_inputs["S3"] = di

    result = build_production_result(di)
    saved_specialist_results["S3"] = result

    ok, errs = scv.validate_output(result)
    _record("S3_output_validation", ok, "" if ok else f"errors={errs[:3]}")

    passed = (
        result["status"] == "blocked"
        and result["conclusion"] == ""
        and len(result["metrics"]) == 0
        and len(result["causes"]) == 0
        and len(result["recommended_actions"]) == 0
        and len(result["evidence_refs"]) == 0
        and ok
    )
    _record("S3_blocked_correct", passed,
            f"status={result['status']}, evref_count={len(result.get('evidence_refs', []))}")

    info = _extract_info(orch, result)
    print(f"    联调信息: {json.dumps(info, ensure_ascii=False, indent=2)}")
    return info


# =========================================================================
# 场景 4: 删除证据后的变异场景
# =========================================================================
def test_s4_mutation():
    print("\n--- 场景 4: 删除证据后的变异场景 ---")
    orch = _run_consumer("shift", ["oee_source", "source_shift_id"], role="line", source_scope="P02")
    if orch["status"] != "COMPLETED":
        _record("S4_consumer_run", False, f"consumer status={orch['status']}")
        return None

    di = orch["decision_input"]
    saved_decision_inputs["S4_original"] = di

    original_result = build_production_result(di)
    saved_specialist_results["S4_original"] = original_result

    mutated_di = copy.deepcopy(di)
    mutated_di["normalized_facts"] = [
        f for f in mutated_di["normalized_facts"]
        if f["semantic_field"] != "oee_source"
    ]
    saved_decision_inputs["S4_mutated"] = mutated_di

    mutated_result = build_production_result(mutated_di)
    saved_specialist_results["S4_mutated"] = mutated_result

    original_has_oee = any(
        "oee_source" in str(m.get("semantic_field", "")) or "oee_source" in str(m.get("label", ""))
        for m in original_result.get("metrics", [])
    )
    mutated_has_oee = any(
        "oee_source" in str(m.get("semantic_field", "")) or "oee_source" in str(m.get("label", ""))
        for m in mutated_result.get("metrics", [])
    )

    passed = original_has_oee and not mutated_has_oee
    _record("S4_mutation_oee_disappeared", passed,
            f"orig_has_oee={original_has_oee}, mut_has_oee={mutated_has_oee}")

    # 变异后 data_gaps 应变化
    orig_gaps = len(original_result.get("data_gaps", []))
    mut_gaps = len(mutated_result.get("data_gaps", []))
    _record("S4_gap_count_changed", mut_gaps != orig_gaps,
            f"orig_gaps={orig_gaps}, mut_gaps={mut_gaps}")

    ok, errs = scv.validate_output(mutated_result)
    _record("S4_mutated_valid", ok, "" if ok else f"errors={errs[:3]}")

    info = _extract_info(orch, mutated_result)
    info["original_data_gaps_count"] = orig_gaps
    info["mutated_data_gaps_count"] = mut_gaps
    print(f"    联调信息: {json.dumps(info, ensure_ascii=False, indent=2)}")
    return info


# =========================================================================
# 场景 5: 高风险动作门控场景
# =========================================================================
def test_s5_high_risk_gate():
    print("\n--- 场景 5: 高风险动作门控场景 ---")
    with open(os.path.join(SKILL_ROOT, "tests", "fixtures", "golden_event_values.json")) as f:
        GOLDEN = json.load(f)
    GV = GOLDEN["values"]

    def make_prov(field):
        return {
            "source_field": f"src_{field}", "raw_value": None, "source_data_type": "number",
            "transformation_rule_id": "TR-PROD-001",
            "mapping_ref": {"map_id": "MAP-PROD-001"},
            "evidence_locator": {
                "source_file_sha256": "abc123def456789012345678901234567890abcdef1234567890abcdef12345678",
                "source_table": "12_多产线班次_模拟",
                "source_row_number": 1, "source_column_name": field, "source_column_index": 0,
            },
            "note": "test",
        }

    def make_fact(field, value, dt="number", df=None):
        f = {
            "semantic_record_key": GOLDEN["record_key"],
            "source_table": "12_多产线班次_模拟",
            "source_record_id": GOLDEN["shift_id"],
            "semantic_field": field, "normalized_value": value,
            "normalized_data_type": dt, "value_consumption_status": "usable",
            "provenance_ref": make_prov(field),
        }
        if df:
            f["display_format"] = df
        return f

    facts = [
        make_fact("oee_source", GV["oee_source"], df="0.0%"),
        make_fact("availability", GV["availability"], df="0.0%"),
        make_fact("performance_rate", GV["performance_rate"], df="0.0%"),
        make_fact("quality_factor", GV["quality_factor"], df="0.0%"),
        make_fact("can_recompute_oee", GV["can_recompute_oee"], dt="boolean"),
        make_fact("total_output", GV["total_output"], dt="integer"),
        make_fact("good_output", GV["good_output"], dt="integer"),
        make_fact("defect_total", GV["defect_total"], dt="integer"),
        make_fact("unplanned_downtime_minutes", GV["unplanned_downtime_minutes"], dt="integer"),
        make_fact("line_id", GOLDEN["line_id"], dt="string"),
        make_fact("shift_id", GOLDEN["shift_id"], dt="string"),
    ]

    di = {
        "contract_name": "BIFROST_DECISION_INPUT_v0.1",
        "contract_version": "BIFROST-DECISION-INPUT-v0.1",
        "request_id": "REQ-S5-HIGH-RISK",
        "consumer_agent_id": "agent_test",
        "role": "line",
        "query_context": {"semantic_entity": "shift", "source_scope": "P02",
                          "requested_fields": [], "filters": {}, "time_window": None,
                          "limit": None, "semantic_data_ref": {}, "read_only": True},
        "source_release_id": "SYNTHETIC-FIXTURE",
        "source_snapshot_id": "SYNTHETIC-S5",
        "normalized_facts": facts,
        "data_gaps": [],
        "provenance_refs": [],
        "contract_versions": {"semantic_model_version": "SEM-v1.1.1",
                              "mapping_rule_version": "MAP-v1.0.1",
                              "decision_input_contract_version": "BIFROST-DECISION-INPUT-v0.1",
                              "consumer_logical_version": "0.1.1"},
        "validation": {"status": "passed", "issues": [], "normalized_facts_count": len(facts),
                       "data_gaps_count": 0, "decision_usable_gate_enforced": True,
                       "read_only_enforced": True, "no_cross_record_join": True,
                       "no_business_conclusion": True},
        "source_write_performed": False, "actor_can_execute": False,
        "generated_at": "2026-08-10T08:00:00+00:00", "local_trace_id": "CONSUMER-S5",
    }

    saved_decision_inputs["S5"] = di

    result = build_production_result(di)
    saved_specialist_results["S5"] = result

    ok, errs = scv.validate_output(result)
    _record("S5_output_validation", ok, "" if ok else f"errors={errs[:3]}")

    ok2, errs2 = scv.validate_specialist_result_against_input(result, di)
    _record("S5_validate_against_input", ok2, "" if ok2 else f"errors={errs2[:3]}")

    high_risk_actions = [a for a in result.get("recommended_actions", []) if a.get("is_high_risk") is True]
    passed = (
        len(high_risk_actions) > 0
        and all(a.get("needs_human_confirmation") is True for a in high_risk_actions)
        and all(a.get("prohibited_auto_execute") is True for a in high_risk_actions)
        and all(a.get("actor_can_execute") is False for a in high_risk_actions)
        and result["status"] == "needs_confirmation"
        and ok
    )
    _record("S5_high_risk_gate_needs_confirmation", passed,
            f"high_risk_count={len(high_risk_actions)}, status={result['status']}")

    # 破坏门控测试：将 needs_confirmation 改为 warning
    broken = copy.deepcopy(result)
    broken["status"] = "warning"
    ok_broken, errs_broken = scv.validate_output(broken)
    _record("S5_gate_break_warning_rejected", not ok_broken,
            f"broken_warning_rejected={not ok_broken}")

    info = {
        "consumer_version": "N/A (合成夹具)",
        "specialist_skill_version": "0.1.2",
        "specialist_contract_version": "BIFROST-SPECIALIST-RESULT-v0.1.3",
        "bifrost_decision_input_validation": "passed",
        "bifrost_specialist_result_validation": "passed" if ok else "failed",
        "normalized_facts_count": len(facts),
        "evidence_refs_count": len(result.get("evidence_refs", [])),
        "data_gaps_count": len(result.get("data_gaps", [])),
        "status": result.get("status", ""),
        "high_risk_count": len(high_risk_actions),
        "actor_can_execute": result.get("actor_can_execute", None),
        "source_write_performed": False,
        "local_trace_id": result.get("local_trace_id", ""),
    }
    print(f"    联调信息: {json.dumps(info, ensure_ascii=False, indent=2)}")
    return info


# =========================================================================
# 场景 6-9: v0.1.3 变异测试
# =========================================================================
def test_s6_mutation_wrong_field_evref():
    """变异：错误字段 EVREF 必须失败。"""
    print("\n--- 场景 6: 变异 - 错误字段 EVREF ---")
    result = saved_specialist_results.get("S5") or saved_specialist_results.get("S1")
    di = saved_decision_inputs.get("S5") or saved_decision_inputs.get("S1")
    if not result or not di:
        _record("S6_no_base_result", False, "无可用基础结果")
        return None

    broken = copy.deepcopy(result)
    if broken["metrics"]:
        broken["metrics"][0]["evidence_refs"] = ["EVREF-v1:0000000000000000000000000000000000000000000000000000000000000000"]

    # validate_against_input 会检查 EVREF 是否可解析到输入事实
    ok2, errs2 = scv.validate_specialist_result_against_input(broken, di)
    _record("S6_wrong_evref_against_input_rejected", not ok2,
            f"rejected={not ok2}" + (f", errs={errs2[:2]}" if ok2 else ""))
    return None


def test_s7_mutation_bare_record_key():
    """变异：裸 record_key 必须失败。"""
    print("\n--- 场景 7: 变异 - 裸 record_key ---")
    result = saved_specialist_results.get("S5") or saved_specialist_results.get("S1")
    di = saved_decision_inputs.get("S5") or saved_decision_inputs.get("S1")
    if not result:
        _record("S7_no_base_result", False, "无可用基础结果")
        return None

    broken = copy.deepcopy(result)
    if broken["metrics"]:
        broken["metrics"][0]["evidence_refs"] = ["REC-PROD-S03-001"]

    # 外部验证器检查 EVREF-v1 前缀
    ext = validate_specialist_result_external(broken)
    _record("S7_bare_key_ext_rejected", not ext["valid"], f"rejected={not ext['valid']}")

    # validate_against_input 也会拒绝
    if di:
        ok2, errs2 = scv.validate_specialist_result_against_input(broken, di)
        _record("S7_bare_key_against_input_rejected", not ok2, f"rejected={not ok2}")
    return None


def test_s8_mutation_placeholder_evidence():
    """变异：占位证据必须失败。"""
    print("\n--- 场景 8: 变异 - 占位证据 ---")
    result = saved_specialist_results.get("S5") or saved_specialist_results.get("S1")
    if not result:
        _record("S8_no_base_result", False, "无可用基础结果")
        return None

    broken = copy.deepcopy(result)
    if broken["metrics"]:
        broken["metrics"][0]["evidence_refs"] = ["EV:no_evidence:REC-PROD-S03-001"]
    ok, errs = scv.validate_output(broken)
    _record("S8_placeholder_rejected", not ok, f"rejected={not ok}")

    ext = validate_specialist_result_external(broken)
    _record("S8_placeholder_ext_rejected", not ext["valid"], f"rejected={not ext['valid']}")
    return None


def test_s9_mutation_high_risk_warning():
    """变异：高风险+warning 必须失败。"""
    print("\n--- 场景 9: 变异 - 高风险+warning ---")
    result = saved_specialist_results.get("S5")
    if not result:
        _record("S9_no_base_result", False, "无 S5 结果")
        return None

    has_high = any(a.get("is_high_risk") for a in result.get("recommended_actions", []))
    if not has_high:
        _record("S9_no_high_risk", False, "S5 无高风险动作")
        return None

    broken = copy.deepcopy(result)
    broken["status"] = "warning"
    ok, errs = scv.validate_output(broken)
    _record("S9_high_risk_warning_rejected", not ok, f"rejected={not ok}")

    ext = validate_specialist_result_external(broken)
    _record("S9_high_risk_warning_ext_rejected", not ext["valid"], f"rejected={not ext['valid']}")

    # 高风险+completed 也必须失败
    broken2 = copy.deepcopy(result)
    broken2["status"] = "completed"
    broken2["data_gaps"] = []
    ok2, _ = scv.validate_output(broken2)
    _record("S9_high_risk_completed_rejected", not ok2, f"rejected={not ok2}")
    return None


# =========================================================================
# 主入口
# =========================================================================
def run_all_scenarios():
    print("=" * 60)
    print("BIFROST 生产诊断 — 真实 consumer 最终联调 v0.1.2 (04D.3-PROD)")
    print("=" * 60)
    print(f"数据面 ZIP: {DATA_PLANE_ZIP}")
    print(f"Consumer: bifrost-semantic-consumer-readonly v0.1.1")
    print(f"专业 Skill: bifrost-production-diagnosis-readonly v0.1.2")
    print(f"输出合同: BIFROST-SPECIALIST-RESULT-v0.1.3")

    with open(DATA_PLANE_ZIP, "rb") as f:
        zip_sha = hashlib.sha256(f.read()).hexdigest()
    print(f"数据面 ZIP SHA-256: {zip_sha}")
    print()

    all_infos = {}

    info1 = test_s1_real_success()
    if info1:
        all_infos["scenario_1_real_success"] = info1

    info2 = test_s2_real_data_gap()
    if info2:
        all_infos["scenario_2_real_data_gap"] = info2

    info3 = test_s3_input_blocked()
    if info3:
        all_infos["scenario_3_input_blocked"] = info3

    info4 = test_s4_mutation()
    if info4:
        all_infos["scenario_4_mutation"] = info4

    info5 = test_s5_high_risk_gate()
    if info5:
        all_infos["scenario_5_high_risk_gate"] = info5

    # 变异测试（依赖前面的结果）
    test_s6_mutation_wrong_field_evref()
    test_s7_mutation_bare_record_key()
    test_s8_mutation_placeholder_evidence()
    test_s9_mutation_high_risk_warning()

    total = len(test_results)
    passed = sum(1 for r in test_results if r["passed"])
    failed = total - passed

    print()
    print("-" * 60)
    print(f"总计: {total}, 通过: {passed}, 失败: {failed}")
    print(f"all_passed: {failed == 0}")
    print("=" * 60)

    return {
        "total": total, "passed": passed, "failed": failed,
        "all_passed": failed == 0, "results": test_results,
        "integration_infos": all_infos,
        "data_plane_zip_sha256": zip_sha,
        "skill_version": "0.1.2",
        "contract_version": "BIFROST-SPECIALIST-RESULT-v0.1.3",
    }


if __name__ == "__main__":
    summary = run_all_scenarios()

    results_dir = os.path.join(SKILL_ROOT, "tests", "results")
    os.makedirs(results_dir, exist_ok=True)

    # 保存 integration_test_results
    with open(os.path.join(results_dir, "integration_test_results.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 保存 machine-readable decision_input
    with open(os.path.join(results_dir, "decision_input_saved.json"), "w", encoding="utf-8") as f:
        json.dump(saved_decision_inputs, f, ensure_ascii=False, indent=2)

    # 保存 machine-readable specialist_result
    with open(os.path.join(results_dir, "specialist_result_saved.json"), "w", encoding="utf-8") as f:
        json.dump(saved_specialist_results, f, ensure_ascii=False, indent=2)

    sys.exit(0 if summary["all_passed"] else 1)

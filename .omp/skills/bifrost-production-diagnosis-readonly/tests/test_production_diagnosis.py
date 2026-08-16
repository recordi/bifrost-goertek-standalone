#!/usr/bin/env python3
"""
BIFROST 生产诊断 — 合成合同测试 v0.1.2

测试维度：
1. 输入合同失败测试
2. 数据缺失测试
3. EvidenceRef 缺失测试
4. 删除事实后结论同步消失的变异测试
5. 禁止硬编码业务数值扫描
6. 禁止越权关联测试
7. 高风险动作禁止执行测试
8. 输出合同独立校验
9. v0.1.3 变异测试：错误字段 EVREF、裸 record_key、占位证据、高风险+warning 必须失败
"""

import copy
import json
import os
import sys

import pytest

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(WORK_DIR)
sys.path.insert(0, SKILL_ROOT)

from scripts.production_diagnosis import build_production_result, validate_production_input_contract, validate_specialist_result_contract
from validator.production_validator import validate_specialist_result_external, mutation_test_fact_removal, scan_hardcoded_business_values

# 共享验证器
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "specialist_contract_validator",
    os.path.join(SKILL_ROOT, "validator", "specialist_contract_validator.py"),
)
scv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scv)

# 加载合成夹具
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


def make_full_decision_input():
    """创建三因子齐全 + oee_source 的完整 decision_input。"""
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
    return {
        "contract_name": "BIFROST_DECISION_INPUT_v0.1",
        "contract_version": "BIFROST-DECISION-INPUT-v0.1",
        "request_id": "REQ-TEST-001",
        "consumer_agent_id": "agent_test",
        "role": "line",
        "query_context": {"semantic_entity": "shift", "source_scope": "P02",
                          "requested_fields": [], "filters": {}, "time_window": None,
                          "limit": None, "semantic_data_ref": {}, "read_only": True},
        "source_release_id": "TEST-RELEASE",
        "source_snapshot_id": "TEST-SNAPSHOT",
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
        "generated_at": "2026-08-10T08:00:00+00:00", "local_trace_id": "CONSUMER-TEST",
    }


# =========================================================================
# 1. 输入合同失败测试
# =========================================================================
class TestInputContractFailures:
    def test_wrong_contract_name(self):
        di = make_full_decision_input()
        di["contract_name"] = "WRONG"
        result = build_production_result(di)
        assert result["status"] == "blocked"
        assert result["conclusion"] == ""
        assert len(result["metrics"]) == 0

    def test_source_write_performed_true(self):
        di = make_full_decision_input()
        di["source_write_performed"] = True
        result = build_production_result(di)
        assert result["status"] == "blocked"

    def test_actor_can_execute_true(self):
        di = make_full_decision_input()
        di["actor_can_execute"] = True
        result = build_production_result(di)
        assert result["status"] == "blocked"

    def test_validation_failed(self):
        di = make_full_decision_input()
        di["validation"]["status"] = "failed"
        result = build_production_result(di)
        assert result["status"] == "blocked"

    def test_unusable_fact(self):
        di = make_full_decision_input()
        di["normalized_facts"][0]["value_consumption_status"] = "unusable"
        result = build_production_result(di)
        assert result["status"] == "blocked"

    def test_missing_provenance(self):
        di = make_full_decision_input()
        di["normalized_facts"][0]["provenance_ref"] = None
        result = build_production_result(di)
        assert result["status"] == "blocked"

    def test_null_normalized_value(self):
        di = make_full_decision_input()
        di["normalized_facts"][0]["normalized_value"] = None
        result = build_production_result(di)
        assert result["status"] == "blocked"


# =========================================================================
# 2. 数据缺失测试
# =========================================================================
class TestDataGaps:
    def test_missing_oee_source_generates_gap(self):
        di = make_full_decision_input()
        di["normalized_facts"] = [f for f in di["normalized_facts"]
                                   if f["semantic_field"] != "oee_source"]
        result = build_production_result(di)
        assert result["status"] in ("warning", "completed")
        # oee_source 缺失应该产生 data_gap
        has_oee_gap = any(
            g.get("semantic_field") == "oee_source"
            for g in result.get("data_gaps", [])
        )
        assert has_oee_gap, "缺失 oee_source 应生成 data_gap"

    def test_data_gaps_merged(self):
        """v0.1.3: data_gaps 必须经过 merge_data_gaps 归并。"""
        di = make_full_decision_input()
        # 添加大量重复 data_gaps
        for i in range(50):
            di["data_gaps"].append({
                "semantic_entity": "shift",
                "semantic_field": "oee_source",
                "reason": "source_value_absent",
                "value_consumption_status": "missing",
                "source_locator": f"REC-{i:04d}",
                "required_resolution": "oee_source 值缺失",
            })
        result = build_production_result(di)
        # 50 条重复 gap 应归并为 1 条
        oee_gaps = [g for g in result["data_gaps"] if g.get("semantic_field") == "oee_source"]
        assert len(oee_gaps) <= 1, f"50 条重复 oee_source gap 应归并为 1 条，实际 {len(oee_gaps)}"
        if oee_gaps:
            assert oee_gaps[0]["occurrence_count"] >= 1
            assert "affected_record_count" in oee_gaps[0]
            assert "sample_source_locators" in oee_gaps[0]
            assert len(oee_gaps[0]["sample_source_locators"]) <= 3


# =========================================================================
# 3. EvidenceRef 缺失测试
# =========================================================================
class TestEvidenceRefMissing:
    def test_no_placeholder_evidence(self):
        """v0.1.3: 不得有 EV:no_evidence、EV:*:no_provenance 等占位证据。"""
        di = make_full_decision_input()
        result = build_production_result(di)
        all_refs = list(result.get("evidence_refs", []))
        for m in result.get("metrics", []):
            all_refs.extend(m.get("evidence_refs", []))
        for c in result.get("causes", []):
            all_refs.extend(c.get("evidence_refs", []))
        for a in result.get("recommended_actions", []):
            all_refs.extend(a.get("evidence_refs", []))
        for ref in all_refs:
            assert ref.startswith("EVREF-v1:"), f"证据 {ref} 不是 EVREF-v1 形式"
            low = ref.lower()
            for tok in ("no_evidence", "no_provenance", "placeholder", "dummy", "fake", "unknown", "todo", "tbd"):
                assert tok not in low, f"证据 {ref} 包含占位令牌 {tok}"

    def test_bare_record_key_rejected(self):
        """v0.1.3: 不得使用裸 semantic_record_key 作为证据。"""
        di = make_full_decision_input()
        result = build_production_result(di)
        all_refs = list(result.get("evidence_refs", []))
        for m in result.get("metrics", []):
            all_refs.extend(m.get("evidence_refs", []))
        for ref in all_refs:
            assert not ref.startswith("REC-"), f"裸 record_key 被用作证据: {ref}"
            assert ":" not in ref or ref.startswith("EVREF-v1:"), f"非 EVREF-v1 证据: {ref}"


# =========================================================================
# 4. 删除事实后结论同步消失的变异测试
# =========================================================================
class TestMutationFactRemoval:
    def test_oee_source_removal(self):
        di = make_full_decision_input()
        result = build_production_result(di)
        original_has_oee_metric = any(
            m.get("semantic_field") == "oee_source"
            for m in result.get("metrics", [])
        )
        assert original_has_oee_metric, "原始结果应有 oee_source metric"

        mutated_di = copy.deepcopy(di)
        mutated_di["normalized_facts"] = [
            f for f in mutated_di["normalized_facts"]
            if f["semantic_field"] != "oee_source"
        ]
        mutated_result = build_production_result(mutated_di)
        mutated_has_oee_metric = any(
            m.get("semantic_field") == "oee_source"
            for m in mutated_result.get("metrics", [])
        )
        assert not mutated_has_oee_metric, "删除 oee_source 后不应有对应 metric"

    def test_availability_removal(self):
        di = make_full_decision_input()
        result = build_production_result(di)
        original_has_driver = any(
            c.get("category") == "oee_direct_driver" and "availability=" in str(c.get("statement", ""))
            for c in result.get("causes", [])
        )

        mutated_di = copy.deepcopy(di)
        mutated_di["normalized_facts"] = [
            f for f in mutated_di["normalized_facts"]
            if f["semantic_field"] != "availability"
        ]
        mutated_result = build_production_result(mutated_di)
        mutated_has_driver = any(
            c.get("category") == "oee_direct_driver" and "availability=" in str(c.get("statement", ""))
            for c in mutated_result.get("causes", [])
        )
        # availability 被删除后，三因子不完整，OEE 直接驱动因子不应出现
        assert original_has_driver, "原始应有 availability 驱动"
        assert not mutated_has_driver, "删除 availability 后驱动应消失"


# =========================================================================
# 5. 禁止硬编码业务数值扫描
# =========================================================================
class TestNoHardcodedValues:
    def test_no_hardcoded_business_values(self):
        di = make_full_decision_input()
        result = build_production_result(di)
        scan = scan_hardcoded_business_values(result)
        assert scan["clean"], f"检测到硬编码业务数值: {scan['issues']}"


# =========================================================================
# 6. 禁止越权关联测试
# =========================================================================
class TestNoCrossEntityAssociation:
    def test_material_not_oee_direct_cause(self):
        """物料缺口不得进入 OEE 直接驱动 causes。"""
        di = make_full_decision_input()
        # 添加物料缺口
        di["normalized_facts"].append(
            make_fact("material_gap_qty", GV["material_gap_qty"], dt="integer")
        )
        di["normalized_facts"].append(
            make_fact("material_gap_material_code", GV["material_gap_material_code"], dt="string")
        )
        result = build_production_result(di)
        for cause in result.get("causes", []):
            if cause.get("category") == "oee_direct_driver":
                assert "物料" not in cause.get("statement", "")
                assert "material" not in cause.get("statement", "").lower()


# =========================================================================
# 7. 高风险动作禁止执行测试
# =========================================================================
class TestHighRiskActionGate:
    def test_high_risk_needs_confirmation(self):
        """v0.1.3: 高风险动作存在时，非 blocked 结果必须为 needs_confirmation。"""
        di = make_full_decision_input()
        result = build_production_result(di)
        high_risk = [a for a in result.get("recommended_actions", []) if a.get("is_high_risk")]
        if high_risk:
            assert result["status"] == "needs_confirmation", \
                f"高风险动作存在但 status={result['status']}"
            for a in high_risk:
                assert a["needs_human_confirmation"] is True
                assert a["prohibited_auto_execute"] is True
                assert a["actor_can_execute"] is False
            assert result["actor_can_execute"] is False

    def test_no_auto_execute(self):
        di = make_full_decision_input()
        result = build_production_result(di)
        assert result["actor_can_execute"] is False
        for a in result.get("recommended_actions", []):
            assert a.get("actor_can_execute") is False


# =========================================================================
# 8. 输出合同独立校验
# =========================================================================
class TestOutputContractValidation:
    def test_shared_validator_passes(self):
        di = make_full_decision_input()
        result = build_production_result(di)
        ok, errs = scv.validate_output(result)
        assert ok, f"共享验证器失败: {errs}"

    def test_external_validator_passes(self):
        di = make_full_decision_input()
        result = build_production_result(di)
        ext = validate_specialist_result_external(result)
        assert ext["valid"], f"外部验证器失败: {ext['errors']}"

    def test_internal_validator_passes(self):
        di = make_full_decision_input()
        result = build_production_result(di)
        v = validate_specialist_result_contract(result)
        assert v["valid"], f"内部验证器失败: {v['errors']}"

    def test_contract_version_v013(self):
        di = make_full_decision_input()
        result = build_production_result(di)
        assert result["contract_version"] == "BIFROST-SPECIALIST-RESULT-v0.1.3"

    def test_contract_versions_has_logical(self):
        di = make_full_decision_input()
        result = build_production_result(di)
        assert result["contract_versions"]["specialist_logical_version"] == "0.1.2"

    def test_validate_against_input(self):
        """v0.1.3: metrics/causes/actions 证据必须通过 validate_specialist_result_against_input。"""
        di = make_full_decision_input()
        result = build_production_result(di)
        ok, errs = scv.validate_specialist_result_against_input(result, di)
        assert ok, f"validate_against_input 失败: {errs}"


# =========================================================================
# 9. v0.1.3 变异测试：必须失败的用例
# =========================================================================
class TestMutationMustFail:
    """v0.1.3 新增变异测试：以下篡改后的结果必须被验证器拒绝。"""

    def _base_result(self):
        di = make_full_decision_input()
        return build_production_result(di)

    def test_wrong_field_evref_must_fail(self):
        """错误字段 EVREF：篡改 metric 的 evidence_refs 指向不存在的字段。"""
        di = make_full_decision_input()
        result = copy.deepcopy(build_production_result(di))
        if result["metrics"]:
            result["metrics"][0]["evidence_refs"] = ["EVREF-v1:0000000000000000000000000000000000000000000000000000000000000000"]
        # validate_against_input 会检查 EVREF 是否可解析到输入事实
        ok, errs = scv.validate_specialist_result_against_input(result, di)
        assert not ok, f"错误字段 EVREF 应被 validate_against_input 拒绝，但通过"

    def test_bare_record_key_as_evidence_must_fail(self):
        """裸 record_key：用裸 semantic_record_key 作为 evidence_ref。"""
        result = copy.deepcopy(self._base_result())
        if result["metrics"]:
            result["metrics"][0]["evidence_refs"] = ["REC-PROD-S03-001"]
        # 外部验证器检查 EVREF-v1 前缀
        ext = validate_specialist_result_external(result)
        assert not ext["valid"], f"外部验证器应拒绝裸 record_key"

        # validate_against_input 也会拒绝
        di = make_full_decision_input()
        ok2, errs2 = scv.validate_specialist_result_against_input(result, di)
        assert not ok2, f"validate_against_input 应拒绝裸 record_key"

    def test_placeholder_evidence_must_fail(self):
        """占位证据：使用 EV:no_evidence:xxx 作为 evidence_ref。"""
        result = copy.deepcopy(self._base_result())
        if result["metrics"]:
            result["metrics"][0]["evidence_refs"] = ["EV:no_evidence:REC-PROD-S03-001"]
        ok, errs = scv.validate_output(result)
        assert not ok, f"占位证据应被拒绝，但验证通过"

        ext = validate_specialist_result_external(result)
        assert not ext["valid"], f"外部验证器应拒绝占位证据"

    def test_high_risk_warning_must_fail(self):
        """高风险+warning：有高风险动作但 status=warning，必须被拒绝。"""
        result = copy.deepcopy(self._base_result())
        # 确保有高风险动作
        has_high = any(a.get("is_high_risk") for a in result.get("recommended_actions", []))
        if has_high:
            result["status"] = "warning"  # 篡改为 warning
            ok, errs = scv.validate_output(result)
            assert not ok, f"高风险+warning 应被拒绝，但验证通过"

            ext = validate_specialist_result_external(result)
            assert not ext["valid"], f"外部验证器应拒绝高风险+warning"

    def test_high_risk_completed_must_fail(self):
        """高风险+completed：有高风险动作但 status=completed，必须被拒绝。"""
        result = copy.deepcopy(self._base_result())
        has_high = any(a.get("is_high_risk") for a in result.get("recommended_actions", []))
        if has_high:
            result["status"] = "completed"
            result["data_gaps"] = []
            ok, errs = scv.validate_output(result)
            assert not ok, f"高风险+completed 应被拒绝，但验证通过"

    def test_fabricated_id_must_fail(self):
        """禁止虚构 ID：加入 DecisionID / RunID 字段。"""
        result = copy.deepcopy(self._base_result())
        result["DecisionID"] = "DEC-FAKE-001"
        ok, errs = scv.validate_output(result)
        assert not ok, f"虚构 ID 应被拒绝"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

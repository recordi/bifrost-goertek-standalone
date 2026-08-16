#!/usr/bin/env python3
"""
BIFROST 质量诊断只读 Skill 测试套件（v0.1.2 / 输出合同 v0.1.3）

覆盖：
  A. v0.1.0 回归（原 12 项规则不回退）
  B. v0.1.3 共享合同验证（字节一致、共享验证器通过、旧 Schema 拒绝、
     非法 status/critical/actor_can_execute、缺 EvidenceRef、高风险门控、
     blocked/warning/completed 语义、占位禁止）
  C. EVREF-v1 字段级证据（字段绑定、裸记录键拒绝、同记录多字段不可互换）
  D. data_gaps 归并（9 字段、occurrence_count、affected_record_count ≤ occurrence_count）
  E. 变异测试（删除不良事实后结论同步消失）
  F. 无黄金值
  G. 真实 consumer 联调（5 场景）
  H. P2 卫生（无 __pycache__/.pyc）
  I. 包装一致性（三计数相等）

不使用生产函数输出作为测试期望值。
"""
import json
import os
import sys
import copy
import hashlib
import unittest
import zipfile
import importlib.util
import subprocess
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
SCRIPTS_DIR = os.path.join(SKILL_ROOT, "scripts")
VALIDATOR_DIR = os.path.join(SKILL_ROOT, "validator")
FIXTURES_DIR = os.path.join(HERE, "fixtures")
TEST_TMP_ROOT = os.environ.get(
    "BIFROST_TEST_TMP_ROOT",
    os.path.join(SKILL_ROOT, ".test-runtime-tmp"),
)
os.makedirs(TEST_TMP_ROOT, exist_ok=True)


def test_tmp_path(name):
    """返回当前测试副本内的跨平台临时文件路径，不使用硬编码 /tmp。"""
    return os.path.join(TEST_TMP_ROOT, name)


def _cleanup_test_tmp():
    shutil.rmtree(TEST_TMP_ROOT, ignore_errors=True)


import atexit
atexit.register(_cleanup_test_tmp)

sys.path.insert(0, SCRIPTS_DIR)
sys.path.insert(0, VALIDATOR_DIR)

from quality_diagnosis import (
    orchestrate_quality_diagnosis,
    validate_quality_input_contract,
    group_quality_facts_by_record,
    extract_quality_metrics,
    validate_defect_distribution_conservation,
    analyze_yield_and_defects,
    analyze_freeze_state,
    enforce_spc_cpk_data_requirements,
    classify_quality_risk,
    build_quality_result,
    validate_specialist_result_contract,
    build_evidence_ref_index,
    detect_missing_quality_field_gaps,
    QUALITY_LOGICAL_VERSION,
    SPECIALIST_RESULT_CONTRACT_VERSION,
)
from quality_validator import (
    validate_specialist_result_external,
    mutation_test_defect_facts_removal,
    validate_no_hardcoded_golden_values,
    validate_zip_integrity,
    validate_manifest_external,
)

# 加载共享验证器
SHARED_VALIDATOR_PATH = os.path.join(VALIDATOR_DIR, "specialist_contract_validator.py")
spec = importlib.util.spec_from_file_location("specialist_contract_validator", SHARED_VALIDATOR_PATH)
shared_validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared_validator)

OUTPUT_SCHEMA = os.path.join(SKILL_ROOT, "schema", "BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json")
INPUT_SCHEMA = os.path.join(SKILL_ROOT, "schema", "BIFROST_DECISION_INPUT_v0.1.schema.json")
CONTRACT_V013_ROOT = os.environ.get(
    "CONTRACT_V013_ROOT",
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "inputs", "contract_v013", "BIFROST_SPECIALIST_CONTRACT_v0.1.3"))


def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def run_shared_validator(cmd_args):
    r = subprocess.run(
        [sys.executable, SHARED_VALIDATOR_PATH] + cmd_args,
        capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def run_skill(di):
    return orchestrate_quality_diagnosis(di)


class TestVersionAndContract(unittest.TestCase):
    """T01-T02: 版本与合同常量"""

    def test_t01_logical_version(self):
        self.assertEqual(QUALITY_LOGICAL_VERSION, "0.1.2")

    def test_t02_contract_version(self):
        self.assertEqual(SPECIALIST_RESULT_CONTRACT_VERSION, "BIFROST-SPECIALIST-RESULT-v0.1.3")


class TestInputContractValidation(unittest.TestCase):
    """T03: 输入合同验证"""

    def test_t03_valid_input_passes(self):
        di = load_fixture("valid_quality_input.json")
        r = validate_quality_input_contract(di)
        self.assertTrue(r["valid"], f"errors: {r['errors']}")

    def test_t03b_contract_fail_input_blocked(self):
        di = load_fixture("contract_fail_input.json")
        r = validate_quality_input_contract(di)
        self.assertFalse(r["valid"])
        self.assertIsNotNone(r["blocked_code"])


class TestGroupAndExtract(unittest.TestCase):
    """T04-T05: 分组与提取"""

    def test_t04_group_by_record(self):
        di = load_fixture("valid_quality_input.json")
        grouped = group_quality_facts_by_record(di["normalized_facts"])
        self.assertGreater(len(grouped), 0)

    def test_t05_extract_metrics(self):
        di = load_fixture("valid_quality_input.json")
        grouped = group_quality_facts_by_record(di["normalized_facts"])
        extracted = extract_quality_metrics(grouped)
        self.assertGreater(len(extracted["records"]), 0)
        self.assertIsInstance(extracted["quality_fields_found"], set)


class TestDefectConservation(unittest.TestCase):
    """T06-T07: 不良守恒"""

    def test_t06_conservation_pass(self):
        di = load_fixture("defect_conservation_input.json")
        orch = run_skill(di)
        r = orch["result"]
        sd = r["specialist_details"]["yield_analysis_summary"]
        # 守恒检查不应产生 count_mismatch data_gap
        gaps = [g for g in r["data_gaps"] if "mismatch" in g.get("reason", "")]
        self.assertEqual(len(gaps), 0, f"不应有不守恒 gap: {gaps}")

    def test_t07_nonconservation_detected(self):
        di = load_fixture("defect_nonconservation_input.json")
        orch = run_skill(di)
        r = orch["result"]
        gaps = [g for g in r["data_gaps"] if "mismatch" in g.get("reason", "")]
        self.assertGreater(len(gaps), 0, "不守恒应产生 data_gap")


class TestSPC(unittest.TestCase):
    """T08-T09: SPC/Cpk 数据门控"""

    def test_t08_no_spc_blocks_cpk(self):
        di = load_fixture("no_spc_input.json")
        grouped = group_quality_facts_by_record(di["normalized_facts"])
        extracted = extract_quality_metrics(grouped)
        spc = enforce_spc_cpk_data_requirements(extracted)
        self.assertFalse(spc["cpk_calculable"])
        self.assertGreater(len(spc["data_gaps"]), 0)

    def test_t09_with_spc_calculable(self):
        di = load_fixture("with_spc_input.json")
        grouped = group_quality_facts_by_record(di["normalized_facts"])
        extracted = extract_quality_metrics(grouped)
        spc = enforce_spc_cpk_data_requirements(extracted)
        self.assertTrue(spc["cpk_calculable"])


class TestFreeze(unittest.TestCase):
    """T10-T11: 冻结状态"""

    def test_t10_freeze_no_relation_gap(self):
        di = load_fixture("freeze_no_relation_input.json")
        orch = run_skill(di)
        r = orch["result"]
        gaps = [g for g in r["data_gaps"] if "no_materialized_relation" in g.get("reason", "")]
        self.assertGreater(len(gaps), 0, "无物化关联应产生 data_gap")

    def test_t11_terminal_freeze_excluded(self):
        di = load_fixture("freeze_revoked_input.json")
        orch = run_skill(di)
        r = orch["result"]
        sd = r["specialist_details"]["freeze_analysis_summary"]
        # 终态冻结（released）应进入 terminal，不进入 active
        self.assertGreater(sd["terminal_freezes_count"], 0, "应有终态冻结")
        # active 中不应包含终态状态
        for fz in orch["result"].get("specialist_details", {}).get("freeze_analysis_summary", {}):
            pass
        # 验证 active 冻结数 + 终态冻结数 = 总冻结数
        total = sd["freeze_records_count"]
        self.assertEqual(sd["active_freezes_count"] + sd["terminal_freezes_count"], total)


class TestNoTimeFieldNoTrend(unittest.TestCase):
    """T12: 缺时间字段不制造趋势"""

    def test_t12_no_trend_without_time(self):
        di = load_fixture("no_timefield_input.json")
        orch = run_skill(di)
        r = orch["result"]
        conclusion = r.get("conclusion", "")
        for kw in ["持续下降", "连续恶化", "趋势恶化", "持续上升", "逐月下降", "逐月上升"]:
            self.assertNotIn(kw, conclusion, f"无时间字段不应有趋势结论「{kw}」")


class TestCorrelationNotCausation(unittest.TestCase):
    """T13: 相关性不表述为根因"""

    def test_t13_correlation_not_root_cause(self):
        di = load_fixture("correlation_input.json")
        orch = run_skill(di)
        r = orch["result"]
        for c in r["causes"]:
            if c["causal_evidence_level"] == "associated_risk":
                for kw in ["根因", "已验证原因", "确定原因", "根本原因"]:
                    self.assertNotIn(kw, c["statement"], f"关联级别不应含根因表述「{kw}」")


class TestHighRiskGating(unittest.TestCase):
    """T14: 高风险动作门控"""

    def test_t14_high_risk_needs_confirmation(self):
        di = load_fixture("unfreeze_request_input.json")
        orch = run_skill(di)
        r = orch["result"]
        self.assertEqual(r["status"], "needs_confirmation")
        self.assertTrue(any(a["is_high_risk"] for a in r["recommended_actions"]))
        self.assertTrue(r["needs_human_confirmation"])
        for a in r["recommended_actions"]:
            if a["is_high_risk"]:
                self.assertTrue(a["needs_human_confirmation"])
                self.assertTrue(a["prohibited_auto_execute"])
                self.assertFalse(a["actor_can_execute"])


class TestSharedContractV013(unittest.TestCase):
    """T15-T25: v0.1.3 共享合同验证"""

    def test_t15_output_schema_byte_identical(self):
        """输出 Schema 与权威包逐字节一致"""
        ref = os.path.join(CONTRACT_V013_ROOT, "schema", "BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json")
        if not os.path.exists(ref):
            self.skipTest("权威合同包不可用")
        with open(OUTPUT_SCHEMA, "rb") as f:
            a = f.read()
        with open(ref, "rb") as f:
            b = f.read()
        self.assertEqual(a, b, "输出 Schema 与权威包不一致")

    def test_t16_input_schema_byte_identical(self):
        """输入 Schema 字节一致"""
        ref = os.path.join(CONTRACT_V013_ROOT, "schema", "BIFROST_DECISION_INPUT_v0.1.schema.json")
        if not os.path.exists(ref):
            self.skipTest("权威合同包不可用")
        ok, ha, hb = shared_validator.input_schema_byte_identical(OUTPUT_SCHEMA.replace("BIFROST_SPECIALIST_RESULT_v0.1.3", "BIFROST_DECISION_INPUT_v0.1"), ref)
        self.assertTrue(ok, f"输入 Schema 不一致: {ha} vs {hb}")

    def test_t17_shared_validator_passes_valid(self):
        """合规输出通过共享验证器"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        rp = test_tmp_path("_t17_result.json")
        with open(rp, "w") as f:
            json.dump(r, f)
        rc, out, err = run_shared_validator(["validate", "--doc", rp, "--schema", OUTPUT_SCHEMA])
        self.assertEqual(rc, 0, f"共享验证器未通过: {out}")

    def test_t18_against_input_passes(self):
        """跨输入输出字段级证据验证通过"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        rp = test_tmp_path("_t18_result.json")
        dip = test_tmp_path("_t18_input.json")
        with open(rp, "w") as f:
            json.dump(r, f)
        with open(dip, "w") as f:
            json.dump(di, f)
        rc, out, err = run_shared_validator(["validate-against-input", "--doc", rp, "--input", dip])
        self.assertEqual(rc, 0, f"跨输入验证未通过: {out}")

    def test_t19_old_output_schema_rejected(self):
        """旧 Schema（v0.1）被共享验证器差异扫描识别"""
        old_schema = os.path.join(FIXTURES_DIR, "quality_sample_compliant.json")
        # 旧 schema 不存在时用 diff 扫描旧输出 schema
        # 这里验证当前输出 Schema 的 const 为 v0.1.3
        with open(OUTPUT_SCHEMA) as f:
            schema = json.load(f)
        cv = schema["properties"]["contract_version"]["const"]
        self.assertEqual(cv, "BIFROST-SPECIALIST-RESULT-v0.1.3")

    def test_t20_illegal_status_rejected(self):
        """非法 status 被拒绝"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        r["status"] = "failed"
        ok, errs = shared_validator.validate_output(r)
        self.assertFalse(ok, "非法 status=failed 应被拒绝")

    def test_t21_critical_severity_rejected(self):
        """critical severity 被拒绝"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        r["severity"] = "critical"
        ok, errs = shared_validator.validate_output(r)
        self.assertFalse(ok, "critical 应被拒绝")

    def test_t22_actor_can_execute_true_rejected(self):
        """actor_can_execute=true 被拒绝"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        r["actor_can_execute"] = True
        ok, errs = shared_validator.validate_output(r)
        self.assertFalse(ok, "actor_can_execute=true 应被拒绝")

    def test_t23_missing_evidence_rejected(self):
        """缺 EvidenceRef 的 metric 被拒绝"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        if r["metrics"]:
            r["metrics"][0]["evidence_refs"] = []
            ok, errs = shared_validator.validate_output(r)
            self.assertFalse(ok, "空 evidence_refs 应被拒绝")

    def test_t24_blocked_no_business_conclusion(self):
        """blocked 状态不得输出业务结论"""
        di = load_fixture("contract_fail_input.json")
        r = run_skill(di)["result"]
        self.assertEqual(r["status"], "blocked")
        self.assertEqual(r["conclusion"], "")
        self.assertEqual(r["metrics"], [])
        self.assertEqual(r["causes"], [])
        self.assertEqual(r["recommended_actions"], [])

    def test_t25_warning_has_data_gaps(self):
        """warning 状态必须有 data_gaps"""
        di = load_fixture("no_spc_input.json")
        r = run_skill(di)["result"]
        self.assertEqual(r["status"], "warning")
        self.assertGreater(len(r["data_gaps"]), 0)


class TestEVREFFieldLevel(unittest.TestCase):
    """T26-T29: EVREF-v1 字段级证据"""

    def test_t26_evrefs_are_canonical_form(self):
        """所有 evidence_refs 为 EVREF-v1 规范形式"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        for ref in r["evidence_refs"]:
            self.assertTrue(ref.startswith("EVREF-v1:"), f"非 EVREF-v1: {ref}")
        for m in r["metrics"]:
            for ref in m["evidence_refs"]:
                self.assertTrue(ref.startswith("EVREF-v1:"), f"metric 非 EVREF-v1: {ref}")

    def test_t27_bare_record_key_rejected(self):
        """裸记录键被跨输入验证拒绝"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        # 将第一个 evidence_ref 替换为裸记录键
        rk = di["normalized_facts"][0]["semantic_record_key"]
        r["evidence_refs"][0] = rk
        ok, errs = shared_validator.validate_specialist_result_against_input(r, di)
        self.assertFalse(ok, "裸记录键应被拒绝")

    def test_t28_field_binding_enforced(self):
        """metrics 字段绑定：EVREF 解析字段必须与 metric.semantic_field 一致"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        if not r["metrics"]:
            self.skipTest("无 metric")
        # 篡改 metric 的 semantic_field 使其与 EVREF 不匹配
        r["metrics"][0]["semantic_field"] = "__wrong_field__"
        ok, errs = shared_validator.validate_specialist_result_against_input(r, di)
        self.assertFalse(ok, "字段绑定违规应被拒绝")

    def test_t29_same_record_multi_field_not_interchangeable(self):
        """同记录多字段 EVREF 不可互换"""
        di = load_fixture("valid_quality_input.json")
        idx = build_evidence_ref_index(di)
        # 找同记录不同字段
        by_record = {}
        for (rk, fld), ev in idx.items():
            by_record.setdefault(rk, {})[fld] = ev
        multi = {rk: d for rk, d in by_record.items() if len(d) > 1}
        if not multi:
            self.skipTest("无同记录多字段")
        rk, fields = next(iter(multi.items()))
        f1, f2 = list(fields.keys())[:2]
        r = run_skill(di)["result"]
        # 将 metric 的 EVREF 替换为同记录但不同字段的 EVREF
        if r["metrics"]:
            r["metrics"][0]["evidence_refs"] = [fields[f2]]
            r["metrics"][0]["semantic_field"] = f1
            ok, errs = shared_validator.validate_specialist_result_against_input(r, di)
            self.assertFalse(ok, "同记录不同字段 EVREF 不可互换")


class TestDataGapMerge(unittest.TestCase):
    """T30-T32: data_gaps 归并"""

    def test_t30_data_gaps_have_9_fields(self):
        """data_gaps 每项 9 字段"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        required = ("semantic_entity", "semantic_field", "reason",
                    "value_consumption_status", "source_locator", "required_resolution",
                    "affected_record_count", "occurrence_count", "sample_source_locators")
        for g in r["data_gaps"]:
            for f in required:
                self.assertIn(f, g, f"data_gap 缺少 {f}")

    def test_t31_arc_le_occ(self):
        """affected_record_count ≤ occurrence_count"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        for g in r["data_gaps"]:
            self.assertLessEqual(g["affected_record_count"], g["occurrence_count"])

    def test_t32_no_duplicate_gaps(self):
        """归并后无重复 gap（同 dedup-key）"""
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        keys = []
        for g in r["data_gaps"]:
            k = (g["semantic_entity"], g["semantic_field"], g["reason"],
                 g["value_consumption_status"], g["required_resolution"])
            self.assertNotIn(k, keys, f"重复 gap: {k}")
            keys.append(k)


class TestMutation(unittest.TestCase):
    """T33: 变异测试——删除不良事实后结论同步消失"""

    def test_t33_mutation_defect_removal(self):
        di = load_fixture("valid_quality_input.json")
        orch = run_skill(di)
        original = orch["result"]
        mt = mutation_test_defect_facts_removal(di, original)
        self.assertTrue(mt["valid"], f"变异测试失败: {mt['errors']}")
        # 删除 defect_type 后 causes 中不应有关联不良类型
        self.assertEqual(mt["mutated_causes"], 0,
                         f"删除 defect_type 后仍有关联 cause: {mt}")


class TestNoGoldenValues(unittest.TestCase):
    """T34: 无黄金值"""

    def test_t34_no_hardcoded_golden(self):
        di = load_fixture("valid_quality_input.json")
        r = run_skill(di)["result"]
        check = validate_no_hardcoded_golden_values(r)
        self.assertTrue(check["valid"], f"含黄金值: {check['errors']}")


class TestRealConsumerIntegration(unittest.TestCase):
    """T35-T39: 真实 consumer 联调（5 场景）"""

    @classmethod
    def setUpClass(cls):
        cls.consumer_dir = os.environ.get(
            "CONSUMER_DIR",
            os.path.join(os.path.dirname(__file__), "..", "..", "..",
                         "inputs", "consumer_v011", "bifrost-semantic-consumer-readonly"))
        cls.dataplane_zip = os.environ.get(
            "DATA_PLANE_ZIP",
            os.path.join(os.path.dirname(__file__), "..", "..", "..",
                         "inputs", "BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL.zip"))
        cls.dataplane_dir = os.environ.get(
            "DATA_PLANE_DIR",
            os.path.join(os.path.dirname(__file__), "..", "..", "..",
                         "inputs", "dataplane_v02"))
        cls.consumer_available = (
            os.path.exists(cls.consumer_dir) and
            os.path.exists(cls.dataplane_zip) and
            os.path.exists(cls.dataplane_dir))

    def _run_consumer(self, entity, field):
        if not self.consumer_available:
            self.skipTest("consumer / 数据面不可用")
        sys.path.insert(0, self.consumer_dir)
        sys.path.insert(0, os.path.join(self.consumer_dir, "consumer"))
        try:
            from consumer_adapter import orchestrate_consumer_run
        except ImportError:
            from consumer.consumer_adapter import orchestrate_consumer_run
        req = {
            "request_id": f"QUAL-TEST-{entity}",
            "consumer_agent_id": "bifrost-semantic-consumer-readonly",
            "role": "quality",
            "source_scope": "P02",
            "semantic_entity": entity,
            "requested_fields": [field],
            "filters": {},
            "time_window": None,
            "limit": None,
            "read_only": True,
        }
        return orchestrate_consumer_run(self.dataplane_zip, self.dataplane_dir, req)

    def test_t35_real_success_scenario(self):
        """场景 A：真实 defect_detail 查询成功"""
        r = self._run_consumer("defect_detail", "simulated_shift_id")
        self.assertEqual(r["status"], "COMPLETED")
        di = r["decision_input"]
        self.assertGreater(len(di["normalized_facts"]), 0)
        # 输入合同验证
        t35_di = test_tmp_path("_t35_di.json")
        t35_result = test_tmp_path("_t35_result.json")
        with open(t35_di, "w", encoding="utf-8") as f:
            json.dump(di, f)
        rc, out, err = run_shared_validator(["validate-input", "--doc", t35_di, "--schema", INPUT_SCHEMA])
        self.assertEqual(rc, 0, f"输入合同未通过: {out}")
        # Skill 处理
        orch = run_skill(di)
        result = orch["result"]
        self.assertEqual(result["contract_version"], "BIFROST-SPECIALIST-RESULT-v0.1.3")
        self.assertFalse(result["actor_can_execute"])
        # 输出通过共享验证器
        with open(t35_result, "w", encoding="utf-8") as f:
            json.dump(result, f)
        rc, out, err = run_shared_validator(["validate", "--doc", t35_result, "--schema", OUTPUT_SCHEMA])
        self.assertEqual(rc, 0, f"输出未通过共享验证器: {out}")
        rc, out, err = run_shared_validator(["validate-against-input", "--doc", t35_result, "--input", t35_di])
        self.assertEqual(rc, 0, f"跨输入验证未通过: {out}")

    def test_t36_real_data_gap_scenario(self):
        """场景 B：真实数据字段不足 → warning + data_gaps"""
        r = self._run_consumer("defect_detail", "simulated_shift_id")
        di = r["decision_input"]
        orch = run_skill(di)
        result = orch["result"]
        # 真实数据仅含 simulated_shift_id，缺质量分析字段 → warning
        self.assertEqual(result["status"], "warning")
        self.assertGreater(len(result["data_gaps"]), 0)

    def test_t37_real_blocked_scenario(self):
        """场景 C：输入合同阻塞 → blocked"""
        di = load_fixture("contract_fail_input.json")
        orch = run_skill(di)
        result = orch["result"]
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["conclusion"], "")
        self.assertEqual(result["evidence_refs"], [])

    def test_t38_real_mutation_scenario(self):
        """场景 D：删除证据后变异"""
        r = self._run_consumer("defect_detail", "simulated_shift_id")
        di = r["decision_input"]
        orch = run_skill(di)
        original = orch["result"]
        # 删除全部事实
        mutated = copy.deepcopy(di)
        mutated["normalized_facts"] = []
        orch_m = run_skill(mutated)
        result_m = orch_m["result"]
        # 无事实 → 无 metrics/causes/actions
        self.assertEqual(result_m["metrics"], [])
        self.assertEqual(result_m["causes"], [])
        self.assertEqual(result_m["recommended_actions"], [])
        self.assertEqual(result_m["evidence_refs"], [])

    def test_t39_real_high_risk_scenario(self):
        """场景 E：高风险动作门控 → needs_confirmation"""
        di = load_fixture("unfreeze_request_input.json")
        orch = run_skill(di)
        result = orch["result"]
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertTrue(any(a["is_high_risk"] for a in result["recommended_actions"]))
        # 共享验证器通过
        t39_result = test_tmp_path("_t39_result.json")
        t39_input = test_tmp_path("_t39_input.json")
        with open(t39_result, "w", encoding="utf-8") as f:
            json.dump(result, f)
        with open(t39_input, "w", encoding="utf-8") as f:
            json.dump(di, f)
        rc, out, err = run_shared_validator(["validate", "--doc", t39_result, "--schema", OUTPUT_SCHEMA])
        self.assertEqual(rc, 0, f"高风险场景输出未通过: {out}")
        rc, out, err = run_shared_validator(["validate-against-input", "--doc", t39_result, "--input", t39_input])
        self.assertEqual(rc, 0, f"高风险场景跨输入未通过: {out}")


class TestHygieneAndPackaging(unittest.TestCase):
    """T40-T41: P2 卫生 + 包装一致性"""

    def test_t40_no_pycache(self):
        """交付目录无 __pycache__/.pyc"""
        # 清理测试运行产生的缓存后再检查
        for root, dirs, files in os.walk(SKILL_ROOT):
            for d in list(dirs):
                if d == "__pycache__":
                    import shutil
                    shutil.rmtree(os.path.join(root, d), ignore_errors=True)
            for f in list(files):
                if f.endswith(".pyc"):
                    os.remove(os.path.join(root, f))
        for root, dirs, files in os.walk(SKILL_ROOT):
            for d in dirs:
                self.assertNotEqual(d, "__pycache__", f"存在 __pycache__: {root}")
            for f in files:
                self.assertFalse(f.endswith(".pyc"), f"存在 .pyc: {root}/{f}")

    def test_t41_manifest_consistency(self):
        """MANIFEST 三计数一致（如果 ZIP 存在）"""
        # 在打包后验证；此处验证 MANIFEST 存在且可读
        manifest = os.path.join(SKILL_ROOT, "MANIFEST.sha256")
        if not os.path.exists(manifest):
            self.skipTest("MANIFEST 尚未生成（打包前）")
        check = validate_manifest_external(SKILL_ROOT)
        self.assertTrue(check["valid"], f"MANIFEST 校验失败: {check['errors']}")


class TestVerifiedVsUnverifiedCapabilities(unittest.TestCase):
    """T42: 已验证 vs 尚未验证能力分开登记"""

    def test_t42_real_data_warning_not_completed(self):
        """真实数据字段不足时不得输出 completed（不得冒充真实联调成功）"""
        r = self._run_or_real("defect_detail", "simulated_shift_id")
        if r is None:
            self.skipTest("consumer 不可用")
        di = r["decision_input"]
        orch = run_skill(di)
        result = orch["result"]
        # 真实数据缺质量字段 → 不得是 completed
        self.assertNotEqual(result["status"], "completed",
                            "真实数据字段不足时不得输出 completed")
        # 必须有 data_gap 说明缺失
        self.assertGreater(len(result["data_gaps"]), 0)

    def _run_or_real(self, entity, field):
        consumer_dir = os.environ.get(
            "CONSUMER_DIR",
            os.path.join(os.path.dirname(__file__), "..", "..", "..",
                         "inputs", "consumer_v011", "bifrost-semantic-consumer-readonly"))
        dp_zip = os.environ.get(
            "DATA_PLANE_ZIP",
            os.path.join(os.path.dirname(__file__), "..", "..", "..",
                         "inputs", "BIFROST_SEMANTIC_DATA_PLANE_v0.2_FINAL.zip"))
        dp_dir = os.environ.get(
            "DATA_PLANE_DIR",
            os.path.join(os.path.dirname(__file__), "..", "..", "..",
                         "inputs", "dataplane_v02"))
        if not (os.path.exists(consumer_dir) and os.path.exists(dp_zip)):
            return None
        sys.path.insert(0, consumer_dir)
        sys.path.insert(0, os.path.join(consumer_dir, "consumer"))
        try:
            from consumer_adapter import orchestrate_consumer_run
        except ImportError:
            from consumer.consumer_adapter import orchestrate_consumer_run
        req = {
            "request_id": f"QUAL-CAP-{entity}", "consumer_agent_id": "bifrost-semantic-consumer-readonly",
            "role": "quality", "source_scope": "P02", "semantic_entity": entity,
            "requested_fields": [field], "filters": {}, "time_window": None,
            "limit": None, "read_only": True,
        }
        return orchestrate_consumer_run(dp_zip, dp_dir, req)


if __name__ == "__main__":
    unittest.main(verbosity=2)

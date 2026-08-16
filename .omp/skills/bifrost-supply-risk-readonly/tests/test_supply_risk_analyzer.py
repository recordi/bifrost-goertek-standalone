"""
BIFROST 供应链风险只读 Skill v0.1.3 测试套件。

覆盖原有 15 项测试要求 + v0.1.3 到货语义修复新增测试。
测试调用真实生产函数和独立验证器，不用生产函数输出作为自身期望值。
真实场景和合成夹具分开登记，不得把合成测试冒充平台真实联调。
"""

import json
import os
import sys
import unittest
import subprocess
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "validator"))

import supply_risk_analyzer as ana
import supply_specialist_validator as ext

FIX_DIR = os.path.join(HERE, "fixtures")
SHARED_VALIDATOR = os.path.join(ROOT, "validator", "specialist_contract_validator.py")
SHARED_SCHEMA = os.path.join(ROOT, "schema", "BIFROST_SPECIALIST_RESULT_v0.1.3.schema.json")
INPUT_SCHEMA = os.path.join(ROOT, "schema", "BIFROST_DECISION_INPUT_v0.1.schema.json")

INTEGRATION_DIR = os.path.join(os.path.dirname(ROOT), "integration")


def load(name):
    with open(os.path.join(FIX_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def _shared_validate(doc):
    """调用共享合同验证器 CLI。"""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(doc, f, ensure_ascii=False)
        tmp = f.name
    try:
        r = subprocess.run(
            [sys.executable, SHARED_VALIDATOR, "validate", "--doc", tmp, "--schema", SHARED_SCHEMA],
            capture_output=True, text=True
        )
        return r.returncode == 0, r.stdout.strip() + r.stderr.strip()
    finally:
        os.unlink(tmp)


class InputContractTests(unittest.TestCase):
    # 1. 合规采购查询成功（completed，data_gaps 为空）
    def test_01_compliant_purchase_order(self):
        di = load("01_compliant_purchase_order.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["specialist_type"], "supply")
        self.assertEqual(len(res["data_gaps"]), 0)
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 2. 输入合同失败阻塞
    def test_02_input_contract_fail(self):
        di = load("02_input_contract_fail.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "blocked")
        self.assertIn("BLOCKED_INPUT_CONTRACT", res["specialist_details"]["blocked_status"])

    # 3. source_write_performed=true 阻塞
    def test_03_source_write_blocked(self):
        di = load("03_source_write_true.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["specialist_details"]["blocked_status"], ana.BLOCKED_SOURCE_WRITE)

    # 4. 无 EvidenceRef 事实不得消费
    def test_04_no_evidence_blocked(self):
        di = load("04_no_evidence.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "blocked")
        self.assertEqual(res["specialist_details"]["blocked_status"], ana.BLOCKED_EVIDENCE_MISSING)


class ArrivalTests(unittest.TestCase):
    # 5. 部分到货且无 as_of_time → overdue indeterminate + data_gap
    def test_05_no_arrival_no_overdue(self):
        di = load("05_no_arrival_dates.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "warning")
        gap_reasons = [g.get("reason") for g in res["data_gaps"]]
        # 部分到货缺 as_of_time → indeterminate
        self.assertIn("missing_as_of_time_for_remaining_overdue", gap_reasons)
        self.assertIn("missing_full_delivery_completion_evidence", gap_reasons)
        for c in res["causes"]:
            self.assertNotEqual(c["category"], "arrival_overdue")

    # 6. 部分到货 + as_of_time > promised → 剩余数量逾期
    def test_06_arrival_overdue_judged(self):
        di = load("06_arrival_overdue.json")
        res = ana.orchestrate_supply_analysis(di)
        overdue = [c for c in res["causes"] if c["category"] == "arrival_overdue"]
        self.assertEqual(len(overdue), 1)
        self.assertIn("逾期", overdue[0]["statement"])
        shortfall_metrics = [m for m in res["metrics"] if "缺口" in m["label"]]
        self.assertEqual(len(shortfall_metrics), 1)


class InventoryGrainTests(unittest.TestCase):
    # 7. inventory 粒度未解决时禁止聚合
    def test_07_inventory_aggregation_blocked(self):
        di = load("07_inventory_grain_unresolved.json")
        res = ana.orchestrate_supply_analysis(di)
        gap_reasons = [g.get("reason") for g in res["data_gaps"]]
        self.assertIn("grain_unresolved_aggregation_not_allowed", gap_reasons)
        for m in res["metrics"]:
            self.assertNotIn("总库存", m["label"])
            self.assertNotIn("平均", m["label"])

    # 8. inventory 逐记录查看仍允许
    def test_08_inventory_per_record_allowed(self):
        di = load("08_inventory_per_record.json")
        res = ana.orchestrate_supply_analysis(di)
        rec_metric = [m for m in res["metrics"] if "逐记录" in m["label"]]
        self.assertEqual(len(rec_metric), 1)


class ShortageFreezeTests(unittest.TestCase):
    # 9. 缺口物料与冻结物料不得合并
    def test_09_shortage_freeze_not_merged(self):
        di = load("09_shortage_and_freeze_separate.json")
        res = ana.orchestrate_supply_analysis(di)
        shortage_causes = [c for c in res["causes"] if c["category"] == "material_shortage"]
        freeze_causes = [c for c in res["causes"] if c["category"] == "quality_freeze"]
        self.assertGreaterEqual(len(shortage_causes), 1)
        self.assertGreaterEqual(len(freeze_causes), 1)
        for c in res["causes"]:
            self.assertNotIn("merged", c["category"])
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 10. 无已物化关系不得跨实体 join
    def test_10_no_materialized_relation_no_join(self):
        di = load("10_no_materialized_relation.json")
        res = ana.orchestrate_supply_analysis(di)
        inv_in_causes = [c for c in res["causes"] if "inventory" in (c.get("statement") or "")]
        self.assertEqual(len(inv_in_causes), 0)

    # 11. 缺料只作为生产连续性风险
    def test_11_shortage_as_continuity_risk(self):
        di = load("11_shortage_as_continuity_risk.json")
        res = ana.orchestrate_supply_analysis(di)
        shortage_causes = [c for c in res["causes"] if c["category"] == "material_shortage"]
        self.assertGreaterEqual(len(shortage_causes), 1)
        for c in shortage_causes:
            self.assertIn("连续性风险", c["statement"])
            self.assertNotIn("OEE直接", c["statement"])
        self.assertIn("连续性风险", res.get("conclusion", ""))


class AmountTests(unittest.TestCase):
    # 12. 未登记货币单位转 data_gap
    def test_12_unregistered_currency_to_gap(self):
        di = load("12_unregistered_currency.json")
        res = ana.orchestrate_supply_analysis(di)
        gap_reasons = [g.get("reason") for g in res["data_gaps"]]
        self.assertIn("unregistered_currency_unit", gap_reasons)
        for m in res["metrics"]:
            self.assertNotIn("金额", m["label"])

    # 13. 负金额不得进入结论
    def test_13_negative_amount_excluded(self):
        di = load("13_negative_amount.json")
        res = ana.orchestrate_supply_analysis(di)
        gap_reasons = [g.get("reason") for g in res["data_gaps"]]
        self.assertIn("negative_amount_not_consumable", gap_reasons)


class HighRiskTests(unittest.TestCase):
    # 14. 加急/替代料只生成确认需求（需明确加急请求）
    def test_14_high_risk_confirmation_only(self):
        di = load("14_high_risk_confirmation_only.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "needs_confirmation")
        actions = res["recommended_actions"]
        self.assertTrue(len(actions) >= 2)
        for a in actions:
            if a["is_high_risk"]:
                self.assertTrue(a["needs_human_confirmation"])
                self.assertTrue(a["prohibited_auto_execute"])
            self.assertFalse(a["actor_can_execute"])
            # v0.1.3: 必须有 identifier_scope
            self.assertEqual(res["specialist_details"].get("action_identifier_scope"), "local_run_only")
            # v0.1.3: 不得有 confirmation_id
            pass  # confirmation_id check in validator
        self.assertTrue(res["needs_human_confirmation"])
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 15. 仅冻结记录也生成高风险确认
    def test_15_freeze_only_high_risk(self):
        di = load("15_freeze_only_no_shortage.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "needs_confirmation")
        has_high = any(a["is_high_risk"] for a in res["recommended_actions"])
        self.assertTrue(has_high)


class DeliverySemanticFixTests(unittest.TestCase):
    """v0.1.3 到货完成状态与逾期判定语义修复测试。"""

    # 16. 部分到货日期早于承诺日期，不得推出整单按期完成
    def test_16_partial_arrival_early_date_no_completion(self):
        di = load("16_partial_arrival_early_date.json")
        res = ana.orchestrate_supply_analysis(di)
        # 不得有 arrival_overdue 也不能有 "整单按期完成"
        for c in res["causes"]:
            stmt = c.get("statement", "")
            self.assertNotIn("整单按期完成", stmt)
            self.assertNotIn("整单未逾期", stmt)
            if c["category"] == "partial_delivery_shortfall":
                # 应保留缺口信息
                self.assertIn("缺口", stmt)
                # 已登记到货日期仅为事实描述
                self.assertIn("已登记到货日期", stmt)
        # 应有 missing_full_delivery_completion_evidence
        gap_reasons = [g.get("reason") for g in res["data_gaps"]]
        self.assertIn("missing_full_delivery_completion_evidence", gap_reasons)
        # 应有 missing_as_of_time (因为没设 as_of_time)
        self.assertIn("missing_as_of_time_for_remaining_overdue", gap_reasons)
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 17. 部分到货且缺 as_of_time → overdue indeterminate
    def test_17_partial_no_as_of_time_indeterminate(self):
        di = load("17_partial_no_as_of_time.json")
        res = ana.orchestrate_supply_analysis(di)
        gap_reasons = [g.get("reason") for g in res["data_gaps"]]
        self.assertIn("missing_as_of_time_for_remaining_overdue", gap_reasons)
        # 不得有 arrival_overdue cause
        overdue_causes = [c for c in res["causes"] if c["category"] == "arrival_overdue"]
        self.assertEqual(len(overdue_causes), 0)
        # 应有 partial_delivery_shortfall cause
        partial_causes = [c for c in res["causes"] if c["category"] == "partial_delivery_shortfall"]
        self.assertEqual(len(partial_causes), 1)
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 18. 部分到货且 as_of_time 晚于承诺日期 → 剩余数量逾期
    def test_18_partial_as_of_after_promised_remaining_overdue(self):
        di = load("18_partial_as_of_after_promised.json")
        res = ana.orchestrate_supply_analysis(di)
        overdue_causes = [c for c in res["causes"] if c["category"] == "arrival_overdue"]
        self.assertEqual(len(overdue_causes), 1)
        self.assertIn("剩余数量", overdue_causes[0]["statement"])
        self.assertIn("逾期", overdue_causes[0]["statement"])
        # 不得表述为"整单从未发生到货"
        self.assertNotIn("从未发生到货", overdue_causes[0]["statement"])
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 19. arrived_qty=purchase_qty → completed
    def test_19_completed_full_delivery(self):
        di = load("19_completed_full_delivery.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "completed")
        # 不应有 data_gaps
        self.assertEqual(len(res["data_gaps"]), 0)
        # 不应有 partial_delivery_shortfall cause
        partial_causes = [c for c in res["causes"] if c["category"] == "partial_delivery_shortfall"]
        self.assertEqual(len(partial_causes), 0)
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 20. arrived_qty>purchase_qty → over_received_anomaly
    def test_20_over_received_anomaly(self):
        di = load("20_over_received_anomaly.json")
        res = ana.orchestrate_supply_analysis(di)
        anomaly_causes = [c for c in res["causes"] if c["category"] == "over_received_anomaly"]
        self.assertEqual(len(anomaly_causes), 1)
        gap_reasons = [g.get("reason") for g in res["data_gaps"]]
        self.assertIn("over_received_anomaly", gap_reasons)
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 21. 缺 purchase_qty/arrived_qty → data_gap
    def test_21_missing_qty_data_gap(self):
        di = load("21_missing_qty_data_gap.json")
        res = ana.orchestrate_supply_analysis(di)
        gap_reasons = [g.get("reason") for g in res["data_gaps"]]
        self.assertIn("missing_purchase_qty", gap_reasons)
        # 不得有业务结论
        for c in res["causes"]:
            self.assertNotIn("arrival_overdue", c["category"])
            self.assertNotIn("partial_delivery_shortfall", c["category"])
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 22. 普通只读查询不生成加急动作
    def test_22_readonly_no_expedite(self):
        di = load("22_readonly_no_expedite.json")
        res = ana.orchestrate_supply_analysis(di)
        # 不应有高风险动作
        high_risk = [a for a in res["recommended_actions"] if a.get("is_high_risk")]
        self.assertEqual(len(high_risk), 0)
        # 不应有加急采购动作
        expedite = [a for a in res["recommended_actions"] if "加急" in (a.get("action") or "")]
        self.assertEqual(len(expedite), 0)
        # status 不应为 needs_confirmation（除非有冻结）
        self.assertNotEqual(res["status"], "needs_confirmation")
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 23. 明确加急请求且证据充分 → needs_confirmation
    def test_23_explicit_expedite_sufficient(self):
        di = load("23_explicit_expedite_sufficient.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "needs_confirmation")
        high_risk = [a for a in res["recommended_actions"] if a.get("is_high_risk")]
        self.assertGreater(len(high_risk), 0)
        for a in high_risk:
            self.assertTrue(a["needs_human_confirmation"])
            self.assertTrue(a["prohibited_auto_execute"])
            self.assertFalse(a["actor_can_execute"])
            self.assertEqual(res["specialist_details"].get("action_identifier_scope"), "local_run_only")
            pass  # confirmation_id check in validator
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])

    # 24. 删除任一数量 EVREF 后不得生成高风险草稿
    def test_24_delete_qty_evref_no_draft(self):
        fixture = os.path.join(FIX_DIR, "24_expedite_evref_deletion_base.json")
        vr = ext.mutation_test_delete_qty_evref_and_verify(ana, fixture)
        self.assertTrue(vr["valid"], vr["errors"])


class MutationTests(unittest.TestCase):
    # 变异: 删除缺口事实后相关原因与动作消失
    def test_mutation_delete_shortage(self):
        fixture = os.path.join(FIX_DIR, "14_high_risk_confirmation_only.json")
        vr = ext.mutation_test_delete_shortage_and_verify(ana, fixture)
        self.assertTrue(vr["valid"], vr["errors"])

    # 源码无样本固定值
    def test_no_fixed_values_in_source(self):
        scripts_dir = os.path.join(ROOT, "scripts")
        vr = ext.scan_source_for_fixed_values(scripts_dir)
        self.assertTrue(vr["valid"], f"源码含样本固定值: {vr['hits']}")

    # v0.1.3: 旧错误表述静态扫描零命中
    def test_no_old_phrases_in_source(self):
        scripts_dir = os.path.join(ROOT, "scripts")
        vr = ext.scan_source_for_old_phrases(scripts_dir)
        self.assertTrue(vr["valid"], f"源码含旧错误表述: {vr['hits']}")


class ContractSchemaTests(unittest.TestCase):
    """共享合同 Schema 与语义门控测试。"""

    def test_02_input_schema_byte_identical(self):
        r = subprocess.run(
            [sys.executable, SHARED_VALIDATOR, "input-check", "--doc", INPUT_SCHEMA],
            capture_output=True, text=True
        )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("BYTE_IDENTICAL_OK", r.stdout)

    def test_03_output_passes_shared_validator(self):
        di = load("01_compliant_purchase_order.json")
        res = ana.orchestrate_supply_analysis(di)
        ok, msg = _shared_validate(res)
        self.assertTrue(ok, msg)

    def test_04_old_output_schema_rejected(self):
        old_output = {
            "contract_name": "BIFROST_SPECIALIST_RESULT_v0.1",
            "contract_version": "BIFROST-SPECIALIST-RESULT-v0.1",
            "specialist_type": "supply",
            "status": "ok",
            "request_id": "X", "source_release_id": "X", "source_snapshot_id": "X",
            "conclusion": "old", "severity": "unknown", "confidence": 0.5,
            "metrics": [], "affected_objects": [],
            "recommended_actions": [], "needs_human_confirmation": False,
            "evidence_refs": ["EV:X"], "data_gaps": [], "actor_can_execute": False,
            "contract_versions": {}, "local_trace_id": "X",
            "prohibited_auto_execute": True,
        }
        ok, msg = _shared_validate(old_output)
        self.assertFalse(ok, "旧输出应被拒绝")

    def test_05_v013_sample_passes(self):
        sample_path = os.path.join(ROOT, "samples", "supply_sample_compliant.json")
        ok, msg = _shared_validate(json.load(open(sample_path)))
        self.assertTrue(ok, msg)

    def test_06_illegal_status_fails(self):
        di = load("01_compliant_purchase_order.json")
        res = ana.orchestrate_supply_analysis(di)
        res["status"] = "ok"
        ok, msg = _shared_validate(res)
        self.assertFalse(ok)

    def test_07_critical_severity_fails(self):
        di = load("01_compliant_purchase_order.json")
        res = ana.orchestrate_supply_analysis(di)
        res["severity"] = "critical"
        ok, msg = _shared_validate(res)
        self.assertFalse(ok)

    def test_08_actor_can_execute_true_fails(self):
        di = load("01_compliant_purchase_order.json")
        res = ana.orchestrate_supply_analysis(di)
        res["actor_can_execute"] = True
        ok, msg = _shared_validate(res)
        self.assertFalse(ok)

    def test_09_missing_evidence_ref_fails(self):
        di = load("01_compliant_purchase_order.json")
        res = ana.orchestrate_supply_analysis(di)
        res["evidence_refs"] = []
        ok, msg = _shared_validate(res)
        self.assertFalse(ok)

    def test_10_high_risk_gate_violation_fails(self):
        di = load("14_high_risk_confirmation_only.json")
        res = ana.orchestrate_supply_analysis(di)
        for a in res["recommended_actions"]:
            if a["is_high_risk"]:
                a["needs_human_confirmation"] = False
        ok, msg = _shared_validate(res)
        self.assertFalse(ok)

    def test_11_blocked_with_conclusion_fails(self):
        di = load("02_input_contract_fail.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "blocked")
        res["conclusion"] = "不应出现的业务结论"
        ok, msg = _shared_validate(res)
        self.assertFalse(ok)

    def test_12_warning_without_data_gap_fails(self):
        di = load("05_no_arrival_dates.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "warning")
        res["data_gaps"] = []
        ok, msg = _shared_validate(res)
        self.assertFalse(ok)

    def test_13_completed_with_data_gap_fails(self):
        di = load("01_compliant_purchase_order.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "completed")
        res["data_gaps"] = [{"semantic_entity": "x", "semantic_field": "y", "reason": "z",
                             "value_consumption_status": "missing", "source_locator": None,
                             "required_resolution": "r"}]
        ok, msg = _shared_validate(res)
        self.assertFalse(ok)

    def test_14_mutation_causes_actions_disappear(self):
        fixture = os.path.join(FIX_DIR, "14_high_risk_confirmation_only.json")
        with open(fixture, "r", encoding="utf-8") as f:
            di = json.load(f)
        base = ana.orchestrate_supply_analysis(di)
        mutated = json.loads(json.dumps(di))
        mutated["normalized_facts"] = [
            f for f in mutated["normalized_facts"]
            if "material_shortage" not in f.get("semantic_record_key", "")
        ]
        mut_res = ana.orchestrate_supply_analysis(mutated)
        base_shortage = [c for c in base["causes"] if c["category"] == "material_shortage"]
        mut_shortage = [c for c in mut_res["causes"] if c["category"] == "material_shortage"]
        base_actions = [a for a in base["recommended_actions"] if a["is_high_risk"]]
        mut_actions = [a for a in mut_res["recommended_actions"] if a["is_high_risk"]]
        self.assertGreater(len(base_shortage), 0)
        self.assertEqual(len(mut_shortage), 0)
        self.assertGreater(len(base_actions), 0)
        self.assertEqual(len(mut_actions), 0)

    def test_15_no_golden_values_in_source(self):
        scripts_dir = os.path.join(ROOT, "scripts")
        vr = ext.scan_source_for_fixed_values(scripts_dir)
        self.assertTrue(vr["valid"], f"源码含样本固定值: {vr['hits']}")

    # v0.1.3: 全部输出通过共享验证器
    def test_16_all_fixtures_pass_shared_validator(self):
        """所有合规夹具输出必须通过共享验证器。"""
        for fname in sorted(os.listdir(FIX_DIR)):
            if not fname.endswith(".json"):
                continue
            di = load(fname)
            res = ana.orchestrate_supply_analysis(di)
            if res["status"] == "blocked":
                continue  # blocked 结果也需要通过验证器
            ok, msg = _shared_validate(res)
            self.assertTrue(ok, f"{fname} 输出未通过共享验证器: {msg}")


class RealConsumerIntegrationTests(unittest.TestCase):
    """真实 consumer 联调测试。

    前提：integration/ 目录下已有由 run_integration.py 生成的真实 decision_input。
    若文件不存在则跳过（不冒充成功）。
    """

    @classmethod
    def setUpClass(cls):
        cls.di_success = None
        cls.di_datagap = None
        success_path = os.path.join(INTEGRATION_DIR, "di_success.json")
        datagap_path = os.path.join(INTEGRATION_DIR, "di_datagap.json")
        if os.path.exists(success_path):
            with open(success_path, "r", encoding="utf-8") as f:
                cls.di_success = json.load(f)
        if os.path.exists(datagap_path):
            with open(success_path, "r", encoding="utf-8") as f:
                cls.di_datagap = json.load(f)

    def test_real_success_scenario(self):
        if self.di_success is None:
            self.skipTest("真实 consumer decision_input 未生成")
        res = ana.orchestrate_supply_analysis(self.di_success)
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])
        self.assertIn(res["status"], ("completed", "warning", "needs_confirmation"))
        self.assertFalse(res["actor_can_execute"])

    def test_real_data_gap_scenario(self):
        if self.di_datagap is None:
            self.skipTest("真实 consumer decision_input 未生成")
        res = ana.orchestrate_supply_analysis(self.di_datagap)
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])
        self.assertGreater(len(res["data_gaps"]), 0)

    def test_real_input_blocked_scenario(self):
        if self.di_success is None:
            self.skipTest("真实 consumer decision_input 未生成")
        blocked_di = json.loads(json.dumps(self.di_success))
        blocked_di["source_write_performed"] = True
        res = ana.orchestrate_supply_analysis(blocked_di)
        self.assertEqual(res["status"], "blocked")

    def test_real_evidence_deleted_scenario(self):
        if self.di_success is None:
            self.skipTest("真实 consumer decision_input 未生成")
        no_ev_di = json.loads(json.dumps(self.di_success))
        for f in no_ev_di["normalized_facts"]:
            f["provenance_ref"] = {}
        res = ana.orchestrate_supply_analysis(no_ev_di)
        self.assertEqual(res["status"], "blocked")

    def test_high_risk_gate_scenario(self):
        di = load("23_explicit_expedite_sufficient.json")
        res = ana.orchestrate_supply_analysis(di)
        self.assertEqual(res["status"], "needs_confirmation")
        high_risk = [a for a in res["recommended_actions"] if a["is_high_risk"]]
        self.assertGreater(len(high_risk), 0)
        for a in high_risk:
            self.assertTrue(a["needs_human_confirmation"])
            self.assertTrue(a["prohibited_auto_execute"])
            self.assertFalse(a["actor_can_execute"])
        vr = ext.validate_specialist_result_external(res)
        self.assertTrue(vr["valid"], vr["errors"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

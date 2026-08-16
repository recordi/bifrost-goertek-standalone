import json
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rules"))
from rule_engine import RuleError, build_input_schema, calculate, evaluate_formula, simulate_change
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))
import serve_bifrost_ui as bridge  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "rule_definitions_v1.json"


class RuleEngineTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{
            "availability": 0.85,
            "performance_rate": 0.78,
            "quality_rate": 0.912867,
            "good_qty": 950,
            "input_qty": 1000,
            "actual_changeover_minutes": 22,
            "standard_changeover_minutes": 15,
        }]

    def test_formulas_and_thresholds(self):
        result = calculate(RULES, self.rows, calculation_id="CALC-TEST")
        self.assertAlmostEqual(result["results"]["oee"]["value"], 0.605231, places=6)
        self.assertEqual(result["results"]["oee"]["status"], "warning")
        self.assertEqual(result["results"]["yield_rate"]["status"], "warning")
        self.assertEqual(result["results"]["changeover_overrun_minutes"]["value"], 7)
        self.assertEqual(result["results"]["changeover_overrun_minutes"]["status"], "warning")
        self.assertTrue(result["readonly"])
        self.assertFalse(result["source_write_performed"])

    def test_simulation_shows_impact_without_writing(self):
        source_before = hashlib.sha256(RULES.read_bytes()).hexdigest()
        baseline = json.loads(RULES.read_text(encoding="utf-8"))
        candidate = json.loads(RULES.read_text(encoding="utf-8"))
        candidate["rule_version"] = "1.1.0-draft"
        candidate["status"] = "draft"
        candidate["metrics"]["oee"]["thresholds"]["warning"] = 0.60
        candidate["metrics"]["oee"]["thresholds"]["critical"] = 0.50
        simulation = simulate_change(baseline, candidate, self.rows)
        self.assertEqual(simulation["baseline_version"], "1.0.0")
        self.assertEqual(simulation["candidate_version"], "1.1.0-draft")
        self.assertEqual(simulation["changed_metrics"]["oee"]["after"]["status"], "pass")
        self.assertTrue(simulation["publishable"])
        self.assertEqual(simulation["data_gaps"], simulation["candidate"]["data_gaps"])
        self.assertEqual(len(simulation["candidate_sha256"]), 64)
        self.assertEqual(len(simulation["baseline_sha256"]), 64)
        self.assertTrue(simulation["readonly"])
        self.assertFalse(simulation["source_write_performed"])
        self.assertEqual(hashlib.sha256(RULES.read_bytes()).hexdigest(), source_before)

    def test_candidate_isolated_from_baseline_and_formal_rules(self):
        source_before = RULES.read_bytes()
        baseline = json.loads(source_before.decode("utf-8"))
        candidate = json.loads(source_before.decode("utf-8"))
        candidate["rule_version"] = "1.1.0-draft"
        candidate["status"] = "draft"
        candidate["metrics"]["yield_rate"]["thresholds"]["warning"] = 0.995
        simulation = simulate_change(baseline, candidate, self.rows)
        candidate["metrics"]["yield_rate"]["thresholds"]["warning"] = 0.0
        self.assertEqual(simulation["candidate_version"], "1.1.0-draft")
        self.assertFalse(simulation["source_write_performed"])
        self.assertTrue(simulation["readonly"])
        self.assertEqual(RULES.read_bytes(), source_before)

    def test_formula_simulation_has_no_publish_route(self):
        bridge_source = (ROOT / "integration" / "serve_bifrost_ui.py").read_text(encoding="utf-8")
        self.assertIn('"/api/rule-simulate"', bridge_source)
        self.assertNotIn('"/api/rule-publish"', bridge_source)
        self.assertIn('"actor_can_execute": False', bridge_source)

    def test_governance_action_is_human_gated_and_readonly(self):
        draft = bridge.submit_governance_action_draft({
            "id": "DQ-001",
            "evidence_ref": "SRC-abc:Sheet1:2",
            "suggested_action": "核对该条来源记录",
        }, role="quality")
        self.assertTrue(draft["draft_id"].startswith("DRAFT-DQ-"))
        self.assertTrue(draft["requires_human_confirmation"])
        self.assertTrue(draft["readonly"])
        self.assertFalse(draft["source_write_performed"])
        self.assertFalse(draft["actor_can_execute"])

    def test_rule_simulation_ui_rejects_non_finite_and_requires_readonly_contract(self):
        pages_source = (ROOT.parent / "output" / "bifrost-ui-runtime" / "src" / "pages.jsx").read_text(encoding="utf-8")
        self.assertIn("Number.isFinite", pages_source)
        self.assertIn("试算契约未通过只读门禁", pages_source)
        self.assertIn("setSimulation(null)", pages_source)

    def test_rule_draft_submission_is_human_gated_and_hash_bound(self):
        candidate = json.loads(RULES.read_text(encoding="utf-8"))
        candidate["status"] = "draft"
        candidate["rule_version"] = "1.1.0-draft"
        source_before = RULES.read_bytes()
        simulation = simulate_change(json.loads(source_before.decode("utf-8")), candidate, self.rows)
        draft = bridge.submit_rule_draft(candidate, simulation)
        self.assertTrue(draft["draft_id"].startswith("DRAFT-RULE-"))
        self.assertEqual(draft["baseline_sha256"], hashlib.sha256(source_before).hexdigest())
        self.assertTrue(draft["requires_human_confirmation"])
        self.assertTrue(draft["readonly"])
        self.assertFalse(draft["source_write_performed"])
        self.assertFalse(draft["actor_can_execute"])
        self.assertEqual(RULES.read_bytes(), source_before)
        missing_sim_candidate = json.loads(source_before.decode("utf-8"))
        missing_sim_candidate["status"] = "draft"
        missing_sim_candidate["rule_version"] = "1.2.0-draft"
        with self.assertRaises(RuleError):
            bridge.submit_rule_draft(missing_sim_candidate)
        candidate["status"] = "published"
        with self.assertRaises(RuleError):
            bridge.submit_rule_draft(candidate)

    def test_rule_draft_rejects_nonpublishable_simulation_when_bound(self):
        candidate = json.loads(RULES.read_text(encoding="utf-8"))
        candidate["status"] = "draft"
        candidate["rule_version"] = "1.1.0-draft"
        with self.assertRaises(RuleError):
            bridge.submit_rule_draft(candidate, {
                "readonly": True,
                "source_write_performed": False,
                "publishable": False,
                "data_gaps": [{"reason": "formula_error"}],
            })

    def test_rule_draft_rejects_simulation_for_different_candidate(self):
        baseline = json.loads(RULES.read_text(encoding="utf-8"))
        candidate_a = json.loads(RULES.read_text(encoding="utf-8"))
        candidate_a["status"] = "draft"; candidate_a["rule_version"] = "1.1.0-draft"
        candidate_b = json.loads(json.dumps(candidate_a))
        candidate_b["metrics"]["oee"]["thresholds"]["warning"] = 0.5
        simulation = simulate_change(baseline, candidate_a, self.rows)
        with self.assertRaises(RuleError):
            bridge.submit_rule_draft(candidate_b, simulation)

    def test_minimum_sample_is_a_data_gap(self):
        rules = json.loads(RULES.read_text(encoding="utf-8"))
        rules["metrics"]["oee"]["min_sample_size"] = 2
        result = calculate(rules, self.rows)
        self.assertEqual(result["results"]["oee"]["status"], "insufficient_data")
        self.assertTrue(result["data_gaps"])

    def test_unsafe_formula_is_rejected(self):
        with self.assertRaises(RuleError):
            evaluate_formula("__import__('os').system('whoami')", self.rows)
        with self.assertRaises(RuleError):
            evaluate_formula("availability ** 2", self.rows)

    def test_nested_aggregate_formula(self):
        rows = [
            {"good_qty": 90, "input_qty": 100},
            {"good_qty": 45, "input_qty": 50},
        ]
        self.assertAlmostEqual(evaluate_formula("sum(good_qty) / sum(input_qty)", rows), 0.9)

    def test_input_schema_is_derived_from_formula_dependencies(self):
        schema = build_input_schema(RULES)
        self.assertEqual(schema["oee"]["fields"], ["availability", "performance_rate", "quality_rate"])
        self.assertEqual(schema["yield_rate"]["min_sample_size"], 1)
        self.assertEqual(schema["changeover_overrun_minutes"]["direction"], "lower_is_better")

    def test_simulation_receipt_is_reproducible_and_context_bound(self):
        baseline = json.loads(RULES.read_text(encoding="utf-8"))
        candidate = json.loads(json.dumps(baseline))
        candidate["status"] = "draft"
        candidate["rule_version"] = "1.1.0-draft"
        first = simulate_change(baseline, candidate, self.rows, context={"dataset_id": "TEAM_ENGINEERED_SIMULATION", "time_window": "last_7_shifts"})
        second = simulate_change(baseline, candidate, self.rows, context={"dataset_id": "TEAM_ENGINEERED_SIMULATION", "time_window": "last_7_shifts"})
        self.assertEqual(first["simulation_id"], second["simulation_id"])
        self.assertEqual(first["sample_sha256"], second["sample_sha256"])
        self.assertEqual(first["context"]["dataset_id"], "TEAM_ENGINEERED_SIMULATION")

    def test_rule_draft_rejects_stale_baseline_receipt(self):
        baseline = json.loads(RULES.read_text(encoding="utf-8"))
        candidate = json.loads(json.dumps(baseline))
        candidate["status"] = "draft"; candidate["rule_version"] = "1.1.0-draft"
        simulation = simulate_change(baseline, candidate, self.rows)
        simulation["baseline_sha256"] = "0" * 64
        with self.assertRaises(RuleError):
            bridge.submit_rule_draft(candidate, simulation)


if __name__ == "__main__":
    unittest.main()

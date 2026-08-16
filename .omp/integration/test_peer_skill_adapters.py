#!/usr/bin/env python3
"""Regression tests for peer skill execution and role projections."""

from __future__ import annotations

import copy
import json
import subprocess
import unittest
from pathlib import Path

from peer_skill_adapters import attach_formal_derived_insights, build_peer_enhancements, promote_validated_enhancements, validate_peer_enhancements
from peer_skill_contract import validate_output

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / ".omp" / "integration" / "run_peer_adapters.py"
PYTHON = Path(r"D:\anaconda3\envs\langchain\python.exe")


def _fixture() -> dict:
    ref = "EVREF-v1:test"
    return {
        "status": "PASS", "event_id": "EVT-TEST-001",
        "source_write_performed": False, "actor_can_execute": False,
        "tasks": [
            {"event_id": "EVT-TEST-001", "task_id": "TASK-PROD-001", "agent_id": "production-specialist",
             "metrics": [{"semantic_field": "oee_source", "value": 0.6, "evidence_refs": [ref]}],
             "causes": [{"category": "availability_loss", "statement": "verified", "evidence_refs": [ref]}],
             "data_gaps": [], "evidence_refs": [ref], "status": "warning"},
            {"event_id": "EVT-TEST-001", "task_id": "TASK-QUAL-001", "agent_id": "quality-specialist",
             "metrics": [{"semantic_field": "yield", "value": 0.95, "evidence_refs": [ref]}],
             "causes": [], "data_gaps": [{"semantic_field": "usl", "value_consumption_status": "missing"}],
             "evidence_refs": [ref], "status": "warning"},
            {"event_id": "EVT-TEST-001", "task_id": "TASK-SUP-001", "agent_id": "supply-specialist",
             "metrics": [], "causes": [], "data_gaps": [], "evidence_refs": [], "status": "completed"},
        ],
    }


class PeerAdapterTests(unittest.TestCase):
    def test_source_unchanged_and_contract_passes(self):
        original = _fixture(); before = copy.deepcopy(original)
        adapted = build_peer_enhancements(original)
        self.assertEqual(original, before); self.assertEqual(adapted["tasks"], before["tasks"])
        self.assertEqual(validate_peer_enhancements(original, adapted), [])
        self.assertTrue(all(not x.get("validation_errors") for x in adapted["peer_skill_outputs"]))

    def test_gates(self):
        adapted = build_peer_enhancements(_fixture())
        spc = next(x for x in adapted["peer_skill_outputs"] if x["skill_id"] == "a03-spc-rules")
        supply = next(x for x in adapted["peer_skill_outputs"] if x["skill_id"] == "a08-supply-chain-gap")
        self.assertEqual(spc["status"], "blocked"); self.assertIsNone(spc["cpk"])
        self.assertEqual(supply["oee_attribution"], "forbidden")

    def test_six_roles_and_spc_propagation(self):
        adapted = build_peer_enhancements(_fixture()); projections = adapted["role_projections"]
        expected = {"\u5382\u957f", "\u7ebf\u957f", "\u8d28\u91cf", "\u8bbe\u5907", "\u5de5\u827a", "\u4f9b\u5e94\u94fe"}
        self.assertEqual(set(projections), expected)
        self.assertEqual(projections["\u8d28\u91cf"]["status"], "blocked")
        self.assertEqual(projections["\u5de5\u827a"]["status"], "blocked")
        self.assertEqual(projections["\u4f9b\u5e94\u94fe"]["allowed_skill_ids"], ["a08-supply-chain-gap"])
        self.assertEqual(adapted["peer_integration"]["role_projection_errors"], [])

    def test_only_evidence_bound_peer_findings_promote_as_derived_insights(self):
        original = _fixture()
        adapted = build_peer_enhancements(original)
        source_sha = adapted["peer_integration"]["source_payload_sha256"]
        adapted["physical_evidence_bindings"] = [{
            "evidence_ref": "EVREF-v1:test",
            "dataset_id": "TEST-DATASET",
            "source_table": "12_班次",
            "record_id": "SHIFT-001",
            "adapter_payload_sha256": source_sha,
            "physical_source_sha256": "b" * 64,
        }]
        promoted = promote_validated_enhancements(
            original,
            adapted,
            ["a01-oee-loss-tree", "a02-pareto", "a07-yield-funnel"],
            approval={
                "approval_id": "TEST-APPROVAL",
                "approved_by": "test",
                "approval_source": "unit_test",
                "event_id": original["event_id"],
            },
        )
        self.assertEqual(promoted["promotion_status"], "approved")
        self.assertTrue(promoted["derived_insights"])
        self.assertTrue(all(item["metric_effect"] == "none" for item in promoted["derived_insights"]))
        self.assertTrue(all(item["does_not_replace_authoritative_metrics"] for item in promoted["derived_insights"]))
        self.assertTrue(all(item["evidence_provenance"] == "physical_source_record" for item in promoted["derived_insights"]))

    def test_promotion_blocks_without_physical_source_binding(self):
        original = _fixture()
        adapted = build_peer_enhancements(original)
        result = promote_validated_enhancements(
            original, adapted, ["a01-oee-loss-tree"],
            approval={"approval_id": "TEST", "approved_by": "test", "approval_source": "unit_test", "event_id": original["event_id"]},
        )
        self.assertEqual(result["promotion_status"], "pending_evidence_binding")
        self.assertIn("physical_evidence_binding_required", result["errors"])
        self.assertFalse(result["derived_insights"])

    def test_partial_source_task_cannot_be_formally_promoted(self):
        original = _fixture()
        adapted = build_peer_enhancements(original)
        source_sha = adapted["peer_integration"]["source_payload_sha256"]
        adapted["physical_evidence_bindings"] = [{
            "evidence_ref": "EVREF-v1:test", "dataset_id": "D", "source_table": "T",
            "record_id": "R", "adapter_payload_sha256": source_sha, "physical_source_sha256": "c" * 64,
        }]
        for item in adapted["analysis_enhancements"]:
            if item.get("skill_id") == "a07-yield-funnel":
                item["source_task_status"] = "partial"
        result = promote_validated_enhancements(
            original, adapted, ["a07-yield-funnel"],
            approval={"approval_id": "A", "approved_by": "tester", "approval_source": "unit", "event_id": original["event_id"]},
        )
        self.assertEqual(result["promotion_status"], "no_promotable_findings")
        self.assertFalse(result["derived_insights"])

    def test_formal_projection_requires_approved_payload_scope(self):
        event = {"event_id": "EVT-TEST-001", "tasks": [{"task_id": "TASK-1"}], "authoritative_metrics": {"oee": 0.6}}
        pending = attach_formal_derived_insights(event, {"promotion_status": "pending_evidence_binding"})
        self.assertEqual(pending["formal_derived_insights"]["formal_integration_status"], "not_attached")
        item = {
            "status": "approved", "promotion_scope": "approved-payload",
            "does_not_replace_authoritative_metrics": True,
            "event_id": "EVT-TEST-001",
            "approval": {"approval_id": "A-1", "approved_by": "tester", "approval_source": "test", "event_id": "EVT-TEST-001"},
            "physical_evidence_refs": [{"dataset_id": "D", "source_table": "T", "record_id": "R", "physical_source_sha256": "a" * 64}],
        }
        attached = attach_formal_derived_insights(event, {"promotion_status": "approved", "requires_human_confirmation": False, "source_write_performed": False, "derived_insights": [item]})
        self.assertEqual(attached["formal_derived_insights"]["formal_integration_status"], "attached_additive")
        self.assertEqual(attached["authoritative_metrics"], event["authoritative_metrics"])
        mismatched = dict(item, event_id="EVT-OTHER")
        rejected = attach_formal_derived_insights(event, {"promotion_status": "approved", "requires_human_confirmation": False, "source_write_performed": False, "derived_insights": [mismatched]})
        self.assertEqual(rejected["formal_derived_insights"]["formal_integration_status"], "not_attached")

    def test_promotion_requires_explicit_approval(self):
        original = _fixture()
        adapted = build_peer_enhancements(original)
        result = promote_validated_enhancements(original, adapted, ["a01-oee-loss-tree"])
        self.assertEqual(result["promotion_status"], "pending_human_confirmation")
        self.assertTrue(result["requires_human_confirmation"])

    def test_pareto_rejects_mixed_metrics(self):
        bad = {"contract_version": "BIFROST_PEER_SKILL_OUTPUT_v1", "skill_id": "a02-pareto", "status": "available",
               "event_id": "E", "task_id": "T", "evidence_refs": ["R"], "data_gaps": [],
               "pareto": {"dimension": "mixed", "unit": "mixed", "items": [{"label": "total_output", "value": 10, "unit": "count"}, {"label": "unplanned_downtime_minutes", "value": 5, "unit": "minutes"}]}}
        errors = validate_output(bad)
        self.assertIn("pareto_mixes_units", errors); self.assertIn("pareto_contains_non_categorical_metric", errors)

    def test_runner(self):
        completed = subprocess.run([str(PYTHON), str(RUNNER)], cwd=ROOT, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))
        payload = json.loads(completed.stdout.decode("utf-8", errors="replace"))
        self.assertEqual(payload["peer_integration"]["status"], "PASS")
        self.assertEqual(len(payload["role_projections"]), 6)
        self.assertEqual(payload["formal_derived_insights"]["promotion_status"], "approved")
        self.assertEqual(payload["formal_derived_insights"]["formal_integration_status"], "attached_additive")
        self.assertGreaterEqual(len(payload["formal_derived_insights"]["derived_insights"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

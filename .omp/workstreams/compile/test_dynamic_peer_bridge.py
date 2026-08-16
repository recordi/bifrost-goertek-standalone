import unittest
from pathlib import Path
from unittest.mock import patch
import sys

from dynamic_peer_bridge import build_formal_derived_insights, build_peer_task_payload

ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(ROOT / ".omp" / "workstreams" / "autoadapt"))
sys.path.insert(0, str(ROOT / ".omp" / "workstreams"))
from autoadapt.pipeline import AutoAdaptPipeline  # noqa: E402
from peer_pipeline.peer_postprocessor import run_peer_postprocessors  # noqa: E402


class DynamicPeerBridgeTests(unittest.TestCase):
    def test_builds_stable_readonly_tasks_with_evidence(self):
        payload = {
            "overview": {
                "source_profile": {"source_sha256": "a" * 64},
                "metrics": {"oee": {"value": 0.72, "value_mode": "observed_source"}},
                "evidence_index": [{"evidence_ref": "SRC:sheet:2", "source_sha256": "b" * 64}],
            },
            "event": {
                "roles": [
                    {"role": "factory", "status": "ready", "scope": {"mode": "all_lines", "line_ids": ["L1", "L2"]}, "kpis": [{"metric_code": "OEE", "value": 0.72}], "data_gaps": []},
                    {"role": "quality", "status": "partial", "scope": {"mode": "all_lines", "line_ids": ["L1", "L2"]}, "kpis": [{"metric_code": "YIELD", "value": 0.95}], "data_gaps": [{"metric": "spc", "missing_fields": ["usl"]}]},
                    {"role": "supply", "status": "partial", "scope": {"mode": "all_lines", "line_ids": ["L1", "L2"]}, "kpis": [], "data_gaps": [{"metric": "supply_risk", "missing_fields": ["material_id"]}]},
                ]
            },
        }
        result = build_peer_task_payload(payload)
        self.assertEqual(result["event_id"], "EVT-DYNAMIC-" + "a" * 16)
        self.assertEqual(len(result["tasks"]), 3)
        self.assertTrue(all(task["event_id"] == result["event_id"] for task in result["tasks"]))
        self.assertEqual([task["agent_id"] for task in result["tasks"]], ["production-specialist", "quality-specialist", "supply-specialist"])
        self.assertTrue(all(task["source_write_performed"] is False and task["actor_can_execute"] is False for task in result["tasks"]))
        self.assertTrue(all("SRC:sheet:2" in task["evidence_refs"] for task in result["tasks"]))
        self.assertEqual(result["tasks"][1]["data_gaps"], ["usl"])
        self.assertTrue(result["tasks"][1]["needs_human_confirmation"])

    def test_no_evidence_is_explicitly_blocked_input(self):
        result = build_peer_task_payload({"overview": {}, "event": {"roles": [{"role": "factory", "status": "ready", "kpis": [{"metric_code": "OEE", "value": 0.7}]}]}})
        self.assertEqual(result["tasks"][0]["evidence_refs"], [])
        self.assertTrue(result["tasks"][0]["needs_human_confirmation"])
        self.assertFalse(result["source_write_performed"])

    def test_drilldown_scope_is_passed_to_peer_tasks(self):
        payload = {
            "overview": {
                "source_profile": {"source_sha256": "c" * 64},
                "evidence_index": [{"evidence_ref": "SRC:L1", "line_id": "L1"}],
            },
            "event": {"event_id": "EVT-DD-1", "roles": [
                {"role": "factory", "status": "ready", "scope": {"mode": "all_lines", "line_ids": ["L1", "L2"]}, "kpis": []},
                {"role": "quality", "status": "ready", "scope": {"mode": "all_lines", "line_ids": ["L1", "L2"]}, "kpis": []},
                {"role": "supply", "status": "ready", "scope": {"mode": "all_lines", "line_ids": ["L1", "L2"]}, "kpis": []},
            ]},
        }
        drilldown = {
            "filters": {"line": "L1", "work_order": "WO-1"},
            "facts": {"record_count": 2, "output": {"sum": 100.0, "average": 50.0, "count": 2}, "downtime": {"sum": 12.0, "average": 12.0, "count": 1}},
            "root_cause_candidates": [{"category": "停机原因", "label": "setup", "record_count": 1, "impact_score": 12.0, "evidence_refs": ["SRC:L1"]}],
            "evidence_refs": ["SRC:L1"],
        }
        result = build_peer_task_payload(payload, drilldown_result=drilldown, drilldown_filters=drilldown["filters"])
        self.assertTrue(all(task["analysis_scope"]["source"] == "drilldown_result" for task in result["tasks"]))
        self.assertTrue(all(task["affected_objects"] == [{"line_id": "L1"}] for task in result["tasks"]))
        self.assertTrue(all(any(metric["semantic_field"] == "downtime_minutes" for metric in task["metrics"]) for task in result["tasks"]))
        self.assertTrue(all(task["causes"][0]["interpretation"] == "association_only" for task in result["tasks"]))
        self.assertTrue(all("DD-" in task["task_id"] for task in result["tasks"]))

    def test_role_scope_does_not_inherit_other_line_evidence(self):
        result = build_peer_task_payload({
            "overview": {
                "source_profile": {"source_sha256": "d" * 64},
                "evidence_index": [
                    {"evidence_ref": "SRC:A", "line_id": "L1"},
                    {"evidence_ref": "SRC:B", "line_id": "L2"},
                ],
            },
            "event": {"roles": [
                {"role": "factory", "status": "ready", "scope": {"mode": "single_line", "line_ids": ["L1"]}, "kpis": [{"metric_code": "OEE", "value": 0.8}]},
                {"role": "quality", "status": "partial", "scope": {"mode": "single_line", "line_ids": ["L2"]}, "kpis": []},
                {"role": "supply", "status": "partial", "scope": {"mode": "single_line", "line_ids": ["L2"]}, "kpis": []},
            ]},
        })
        self.assertEqual(result["tasks"][0]["evidence_refs"], ["SRC:A"])
        self.assertEqual(result["tasks"][1]["evidence_refs"], ["SRC:B"])

    def test_real_xlsx_sources_reach_readonly_peer_analysis(self):
        """Both supported workbooks cross mapping, bridge, and peer gates."""
        workbook_sources = [path for path in (ROOT / "test-inputs").iterdir() if path.suffix.lower() == ".xlsx"]
        sources = [
            next(path for path in workbook_sources if "SIM-v2.2" in path.name),
            next(path for path in workbook_sources if "SIM-v2.2" not in path.name),
        ]
        for index, source in enumerate(sources):
            with self.subTest(source=source.name):
                with patch("autoadapt.pipeline._run_mapper", return_value={"status": "blocked", "data_gaps": ["mapper_no_response"]}):
                    pending = AutoAdaptPipeline().run(source, f"BRIDGE-REAL-{index}")
                    # The UI preview is intentionally capped for readability;
                    # the confirmation contract must use the complete ID list.
                    mapping_ids = pending["mapping_manifest"]["pending_mapping_ids"]
                    approved = AutoAdaptPipeline().run(source, f"BRIDGE-REAL-{index}", mapping_ids)
                self.assertEqual(approved["mapping_status"], "approved")
                dynamic = approved["generated_payloads"]
                drilldown = approved.get("drilldown_manifest") or dynamic["overview"].get("drilldown_manifest")
                self.assertEqual(drilldown["contract_version"], "BIFROST_DRILLDOWN_MANIFEST_v1")
                self.assertTrue(drilldown["record_count"] > 0)
                self.assertIn("line", drilldown["available_dimensions"])
                self.assertEqual(
                    drilldown["active_line_ids"],
                    dynamic["overview"]["view_coverage"]["lines"],
                )
                self.assertNotEqual(
                    drilldown["active_line_ids"],
                    drilldown.get("source_line_ids", []),
                    msg="source-lineage IDs must not be offered as active drilldown lines",
                )
                self.assertTrue(any(level["level"] == "overview" and level["available"] for level in drilldown["levels"]))
                self.assertTrue(dynamic["event"]["event_id"])
                self.assertEqual(len(dynamic["event"]["line_ids"]), len(dynamic["overview"]["view_coverage"]["lines"]))
                self.assertTrue(all(role.get("scope", {}).get("line_ids") for role in dynamic["event"]["roles"]))
                self.assertTrue(any(role.get("evidence_refs") for role in dynamic["event"]["roles"]))
                peer_input = build_peer_task_payload(dynamic)
                self.assertEqual(peer_input["event_id"], dynamic["event"]["event_id"])
                self.assertEqual(len(peer_input["tasks"]), 3)
                self.assertTrue(all(task["evidence_refs"] for task in peer_input["tasks"]))
                analysis = run_peer_postprocessors(peer_input)
                self.assertTrue(analysis["source_tasks_unchanged"])
                self.assertTrue(analysis["source_payload_unchanged"])
                self.assertFalse(analysis["source_write_performed"])
                self.assertTrue(analysis["peer_results"])
                self.assertTrue(all(item.get("does_not_replace_authoritative_metrics") is True for item in analysis["peer_results"]))
                formal = build_formal_derived_insights(
                    analysis,
                    event_id=dynamic["event"]["event_id"],
                    dataset_id=dynamic["overview"].get("dataset_id") or dynamic["overview"].get("source_profile", {}).get("source_sha256"),
                )
                self.assertEqual(formal["formal_integration_status"], "attached_additive")
                self.assertTrue(formal["derived_insights"])
                self.assertTrue(all(item["event_id"] == dynamic["event"]["event_id"] for item in formal["derived_insights"]))
                self.assertTrue(all(item["does_not_replace_authoritative_metrics"] for item in formal["derived_insights"]))

    def test_partial_or_mismatched_peer_result_never_enters_formal_section(self):
        analysis = {
            "peer_results": [{
                "skill_id": "a01-oee-loss-tree",
                "status": "available",
                "source_task_status": "partial",
                "event_id": "EVT-A",
                "evidence_refs": ["SRC:A"],
                "evidence_gate": {"status": "passed"},
            }]
        }
        formal = build_formal_derived_insights(analysis, event_id="EVT-A", dataset_id="DS-A")
        self.assertEqual(formal["formal_integration_status"], "not_attached")
        self.assertEqual(formal["derived_insights"], [])


if __name__ == "__main__":
    unittest.main()

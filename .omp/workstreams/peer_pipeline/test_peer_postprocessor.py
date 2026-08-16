import unittest

from peer_postprocessor import list_candidate_skills, run_peer_postprocessors


class PeerPostprocessorTests(unittest.TestCase):
    def test_peer_results_are_additive_and_role_scoped(self):
        payload = {
            "tasks": [{
                "agent_id": "production-specialist", "event_id": "EVT-1", "task_id": "TASK-1",
                "metrics": [
                    {"semantic_field": "availability", "value": 0.85, "unit": "ratio", "evidence_refs": ["REC-1"]},
                    {"semantic_field": "performance_rate", "value": 0.78, "unit": "ratio", "evidence_refs": ["REC-1"]},
                ],
                "causes": [{"category": "downtime", "duration_minutes": 45, "evidence_refs": ["REC-2"]}],
                "evidence_refs": ["REC-1", "REC-2"],
            }],
            "authoritative_metrics": {"oee": 0.609567},
        }
        result = run_peer_postprocessors(payload, "factory")
        self.assertTrue(result["source_tasks_unchanged"])
        self.assertTrue(result["authoritative_metrics_unchanged"])
        self.assertTrue(any(item["skill_id"] == "a01-oee-loss-tree" for item in result["peer_results"]))
        self.assertTrue(result["source_write_performed"] is False)
        self.assertEqual(result["postprocessor_contract"]["mode"], "additive_readonly_postprocessor")
        self.assertTrue(result["source_payload_unchanged"])
        self.assertEqual(result["candidate_skills_enabled"], [])

    def test_candidates_are_advertised_but_not_enabled(self):
        candidates = list_candidate_skills()
        self.assertIn("a04-correlation-heatmap", candidates)
        self.assertTrue(all(item["enabled_by_default"] is False for item in candidates.values()))

    def test_spc_evidence_gate_blocks_without_field_evidence(self):
        payload = {
            "tasks": [{
                "agent_id": "quality-specialist", "event_id": "EVT-2", "task_id": "TASK-2",
                "metrics": [
                    {"semantic_field": field, "value": 1, "evidence_refs": []}
                    for field in ("spc_measurement_points", "usl", "lsl", "sample_rule")
                ],
                "data_gaps": [],
            }],
            "authoritative_metrics": {"yield": 0.9},
        }
        result = run_peer_postprocessors(payload, "quality")
        spc = next(item for item in result["peer_results"] if item["skill_id"] == "a03-spc-rules")
        self.assertEqual(spc["status"], "blocked")
        self.assertEqual(spc["spc_gate"]["status"], "blocked")
        self.assertTrue(spc["spc_gate"]["evidence_missing_fields"])
        self.assertIn("spc_evidence_refs", spc["data_gaps"])


if __name__ == "__main__":
    unittest.main()

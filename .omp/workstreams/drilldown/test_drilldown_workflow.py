import unittest

from drilldown_workflow import build_drilldown_manifest, query_drilldown


class DrilldownWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"line_id": "L-01", "shift_date": "2026-08-01", "shift_id": "NIGHT", "work_order_id": "WO-1", "equipment_id": "EQ-7", "stop_reason": "mechanical", "downtime_minutes": 45, "evidence_ref": "SRC:1"},
            {"line_id": "L-01", "shift_date": "2026-08-01", "shift_id": "NIGHT", "work_order_id": "WO-1", "defect_type": "appearance", "defect_count": 12, "evidence_ref": "SRC:2"},
            {"line_id": "L-02", "shift_date": "2026-08-02", "shift_id": "DAY", "work_order_id": "WO-2", "material_id": "MAT-3", "evidence_ref": "SRC:3"},
        ]

    def test_manifest_is_dataset_agnostic(self):
        result = build_drilldown_manifest(self.rows, source_sha256="a" * 64)
        self.assertEqual(result["contract_version"], "BIFROST_DRILLDOWN_MANIFEST_v1")
        self.assertIn("line", result["available_dimensions"])
        self.assertIn("shift", result["available_dimensions"])
        self.assertTrue(any(level["level"] == "event_evidence" and level["available"] for level in result["levels"]))
        self.assertIn("missing_process", result["data_gaps"])

    def test_query_returns_facts_candidates_and_evidence(self):
        result = query_drilldown(self.rows, filters={"line": "L-01", "shift": "NIGHT"})
        self.assertEqual(result["facts"]["record_count"], 2)
        self.assertEqual(result["facts"]["downtime"]["sum"], 45.0)
        self.assertEqual(result["facts"]["defect_count"]["sum"], 12.0)
        self.assertEqual(result["evidence_refs"], ["SRC:1", "SRC:2"])
        self.assertTrue(result["root_cause_candidates"])
        self.assertEqual(result["source_write_performed"], False)
        self.assertEqual(result["actor_can_execute"], False)

    def test_no_matching_records_is_explicit(self):
        result = query_drilldown(self.rows, filters={"line": "UNKNOWN"})
        self.assertEqual(result["facts"]["record_count"], 0)
        self.assertEqual(result["confidence"], "no_matching_records")
        self.assertEqual(result["root_cause_candidates"], [])

    def test_unseen_source_aliases_are_normalized_without_dataset_rules(self):
        rows = [{
            "production_line": "PX-9",
            "production_date": "2026-08-15",
            "quantity": "200",
            "bad_qty": "7",
            "stop_minutes": "12",
            "reason_code": "setup",
            "evidence_id": "EXT:1",
        }]
        result = query_drilldown(rows, filters={"line": "PX-9"})
        self.assertEqual(result["facts"]["record_count"], 1)
        self.assertEqual(result["facts"]["output"]["sum"], 200.0)
        self.assertEqual(result["facts"]["defect_count"]["sum"], 7.0)
        self.assertEqual(result["facts"]["downtime"]["sum"], 12.0)
        self.assertEqual(result["evidence_refs"], ["EXT:1"])
        self.assertTrue(result["root_cause_candidates"])


if __name__ == "__main__":
    unittest.main()

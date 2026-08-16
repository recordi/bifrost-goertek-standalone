#!/usr/bin/env python3
import unittest

from governance_precheck import (
    CONTRACT_NAME,
    GOVERNANCE_CATEGORIES,
    REPORT_CONTRACT_NAME,
    build_governance_report,
    run_governance_precheck,
    validate_governance_report,
    validate_governance_result,
)


class GovernancePrecheckTests(unittest.TestCase):
    def test_missing_raw_rows_is_not_run(self):
        result = run_governance_precheck({
            "contract_name": CONTRACT_NAME,
            "source_write_performed": False,
            "actor_can_execute": False,
        })
        self.assertEqual(result["status"], "not_run")
        self.assertEqual(validate_governance_result(result), [])

    def test_detects_defects_without_mutating_rows(self):
        rows = [
            {"id": "A", "duration": 12, "unit": "min", "date": "2026-08-01", "line": "S01"},
            {"id": "A", "duration": 120, "unit": "hour", "date": "bad-date", "line": "S99"},
        ]
        before = [dict(row) for row in rows]
        result = run_governance_precheck({
            "contract_name": CONTRACT_NAME,
            "source_write_performed": False,
            "actor_can_execute": False,
            "raw_rows": rows,
            "schema": {
                "primary_key": "id",
                "unit_fields": {"unit": "min"},
                "time_field": "date",
                "reference_field": "line",
                "allowed_values": ["S01", "S02", "S03"],
                "business_exception_rules": [{"field": "duration", "max": 60, "impact": "duration too high"}],
            },
        })
        self.assertEqual(rows, before)
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["defect_count"], 5)
        self.assertEqual(validate_governance_result(result), [])

    def test_write_boundary_blocks(self):
        result = run_governance_precheck({
            "contract_name": CONTRACT_NAME,
            "source_write_performed": True,
            "actor_can_execute": False,
            "raw_rows": [{"id": "A"}],
        })
        self.assertEqual(result["status"], "blocked")

    def test_unapproved_mapping_blocks_all_six_categories(self):
        result = build_governance_report(
            source_profile={"file_name": "sample.csv", "source_sha256": "a" * 64},
            rows=[],
            mapping_status="needs_confirmation",
        )
        self.assertEqual(result["contract_name"], REPORT_CONTRACT_NAME)
        self.assertEqual(set(result["categories"]), set(GOVERNANCE_CATEGORIES))
        self.assertTrue(all(item["status"] == "not_tested" for item in result["categories"].values()))
        self.assertIn("mapping_not_approved", result["data_gaps"])

    def test_report_detects_logic_and_format_issues_without_write(self):
        rows = [
            {"line_id": "S01", "shift_date": "2026-08-01", "total_output": 100, "good_output": 110, "quality_rate": 0.8, "normalization_notes": ["quality_rate:percent_to_ratio"], "evidence_ref": "SRC-1"},
            {"line_id": "S01", "shift_date": "2026-08-01", "total_output": 100, "good_output": 90, "quality_rate": 0.9, "evidence_ref": "SRC-2"},
        ]
        result = build_governance_report(
            source_profile={"file_name": "sample.csv", "source_sha256": "b" * 64},
            rows=rows,
            mapping_status="approved",
        )
        self.assertEqual(result["status"], "warning")
        self.assertGreater(result["health_score"], 0)
        self.assertGreater(result["categories"]["logic_conflict"]["issue_count"], 0)
        self.assertGreater(result["categories"]["format_inconsistent"]["issue_count"], 0)
        self.assertFalse(result["source_write_performed"])
        self.assertFalse(result["actor_can_execute"])
        self.assertEqual(validate_governance_report(result), [])

    def test_freshness_is_not_tested_without_explicit_policy(self):
        result = build_governance_report(
            source_profile={"file_name": "snapshot.csv", "source_sha256": "c" * 64},
            rows=[{"line_id": "S01", "shift_date": "2026-08-01", "evidence_ref": "SRC-1"}],
            mapping_status="approved",
        )
        self.assertEqual(result["categories"]["stale"]["status"], "not_tested")
        self.assertIn("freshness_sla_not_provided", result["data_gaps"])

    def test_freshness_uses_update_timestamp_and_sla(self):
        result = build_governance_report(
            source_profile={"file_name": "live.csv", "source_sha256": "d" * 64},
            rows=[
                {"line_id": "S01", "shift_date": "2026-08-01", "updated_at": "2026-08-14T08:00:00Z", "evidence_ref": "SRC-1"},
                {"line_id": "S02", "shift_date": "2026-08-01", "updated_at": "2026-08-13T00:00:00Z", "evidence_ref": "SRC-2"},
            ],
            mapping_status="approved",
            freshness_policy={"timestamp_field": "updated_at", "sla_hours": 24, "as_of": "2026-08-14T12:00:00Z"},
        )
        self.assertEqual(result["categories"]["stale"]["status"], "detected")
        self.assertEqual(result["categories"]["stale"]["issue_count"], 1)
        self.assertEqual(validate_governance_report(result), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

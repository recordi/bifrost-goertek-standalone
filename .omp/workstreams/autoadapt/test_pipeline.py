import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from pipeline import AutoAdaptPipeline, _deterministic_mapping_draft, _profile


class AutoAdaptPipelineTests(unittest.TestCase):
    def test_json_profile_and_safe_contract(self):
        path = Path(__file__).parents[2] / "skills" / "bifrost-data-mapper-readonly" / "tests" / "fixtures" / "missing_fields_fixture.json"
        result = AutoAdaptPipeline().run(path, "TEST-JSON")
        self.assertEqual(result["contract_version"], "BIFROST_AUTO_ADAPT_v1")
        self.assertEqual(result["source_profile"]["format"], "json")
        self.assertFalse(result["source_write_performed"])
        self.assertIn("oee", result["capability_manifest"])

    def test_missing_source_is_rejected(self):
        with self.assertRaises(FileNotFoundError):
            AutoAdaptPipeline().run("does-not-exist.csv")

    def test_local_fallback_is_review_only_for_team_and_official_sources(self):
        """Provider outage yields drafts, never auto-approved rows or KPI values."""
        root = Path(__file__).parents[3]
        sources = [
            root / "test-inputs" / "BIFROST_飞书导入数据包_v3_P0修复版_SIM-v2.2.xlsx",
            root / "test-inputs" / "歌尔可脱敏企业测试数据集.xlsx",
        ]
        for source in sources:
            self.assertTrue(source.exists(), source)
            profile = _profile(source)
            draft = _deterministic_mapping_draft(profile)
            self.assertEqual(draft["status"], "needs_confirmation")
            self.assertTrue(draft["fallback_used"])
            self.assertTrue(draft["mapping_draft"])
            self.assertTrue(all(item["fallback_requires_confirmation"] for item in draft["mapping_draft"]))
            with patch("pipeline._run_mapper", return_value={"status": "blocked", "data_gaps": ["mapper_no_response"]}):
                result = AutoAdaptPipeline().run(source, "FALLBACK-TEST")
            self.assertEqual(result["mapping_status"], "needs_confirmation")
            self.assertTrue(result["needs_confirmation"])
            self.assertEqual(result["mapping_manifest"]["approved_count"], 0)
            self.assertEqual(result["canonical_dataset"]["record_count"], 0)
            self.assertEqual(result["generated_payloads"]["overview"]["metrics"], {})
            self.assertIn("deterministic_fallback_requires_confirmation", result["data_gaps"])

    def test_explicit_fallback_confirmation_transitions_to_approved(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as handle:
            handle.write("availability,performance_rate,quality_rate,total_output,good_output\n0.8,0.9,0.95,100,95\n")
            source = Path(handle.name)
        try:
            blocked = {"status": "blocked", "data_gaps": ["mapper_no_response"]}
            with patch("pipeline._run_mapper", return_value=blocked):
                draft = AutoAdaptPipeline().run(source, "CONFIRM-TEST")
                ids = [item["mapping_id"] for item in draft["mapping_manifest"]["preview"]]
                confirmed = AutoAdaptPipeline().run(source, "CONFIRM-TEST", ids)
            self.assertEqual(confirmed["mapping_status"], "approved")
            self.assertFalse(confirmed["needs_confirmation"])
            self.assertEqual(confirmed["mapping_manifest"]["status"], "approved")
            self.assertGreater(confirmed["canonical_dataset"]["record_count"], 0)
            self.assertEqual(confirmed["governance_report"]["mapping_status"], "approved")
            self.assertIn("data_quality_summary", confirmed["generated_payloads"]["overview"])
            self.assertEqual(confirmed["generated_payloads"]["overview"]["data_quality_summary"]["source_write_performed"], False)
        finally:
            source.unlink(missing_ok=True)

    def test_explicit_fallback_confirmation_materializes_payload(self):
        root = Path(__file__).parents[3]
        source = next((root / "test-inputs").glob("*SIM-v2.2.xlsx"))
        with patch("pipeline._run_mapper", return_value={"status": "blocked", "data_gaps": ["mapper_no_response"]}):
            pending = AutoAdaptPipeline().run(source, "FALLBACK-CONFIRM")
            # The preview is intentionally capped.  A publishable read-only
            # preview requires confirmation of the complete manifest, not
            # only the first page shown in the UI.
            mapping_ids = pending["mapping_manifest"]["pending_mapping_ids"]
            self.assertEqual(pending["canonical_dataset"]["record_count"], 0)
            confirmed = AutoAdaptPipeline().run(source, "FALLBACK-CONFIRM", mapping_ids)
        self.assertEqual(confirmed["mapping_status"], "approved")
        self.assertGreater(confirmed["canonical_dataset"]["record_count"], 0)
        self.assertTrue(confirmed["generated_payloads"]["overview"]["view_snapshots"])

    def test_optional_drilldown_query_returns_evidence_facts(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as handle:
            handle.write("line_id,shift_date,total_output,good_output,availability,performance_rate,quality_rate\n")
            handle.write("L-01,2026-08-01,100,95,0.85,0.78,0.95\n")
            source = Path(handle.name)
        try:
            blocked = {"status": "blocked", "data_gaps": ["mapper_no_response"]}
            with patch("pipeline._run_mapper", return_value=blocked):
                draft = AutoAdaptPipeline().run(source, "DRILLDOWN-TEST")
                ids = [item["mapping_id"] for item in draft["mapping_manifest"]["preview"]]
                confirmed = AutoAdaptPipeline().run(source, "DRILLDOWN-TEST", ids, {"line": "L-01"})
            self.assertEqual(confirmed["mapping_status"], "approved")
            self.assertEqual(confirmed["drilldown_result"]["facts"]["record_count"], 1)
            self.assertEqual(confirmed["drilldown_result"]["facts"]["output"]["sum"], 100.0)
        finally:
            source.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

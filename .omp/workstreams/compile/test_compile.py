import unittest

from canonical_dataset import _canonical_target, materialize_canonical_dataset
from mapping_confirmation import build_mapping_manifest
from payload_compiler import compile_payloads


class CompileTests(unittest.TestCase):
    def test_confirmation_gate_and_payload_compilation(self):
        response = {
            "source_identity": {"detected_source_family": "TEST"},
            "mapping_draft": [
                {"source_table": "t", "source_field": "A", "target_field": "availability", "mapping_status": "confirmed", "confidence": 0.99},
                {"source_table": "t", "source_field": "P", "target_field": "performance_rate", "mapping_status": "confirmed", "confidence": 0.99},
                {"source_table": "t", "source_field": "Q", "target_field": "quality_rate", "mapping_status": "confirmed", "confidence": 0.99},
            ],
        }
        manifest = build_mapping_manifest(response)
        self.assertEqual(manifest["status"], "approved")
        canonical = {"records": [{"availability": 0.9, "performance_rate": 0.8, "quality_rate": 0.95, "evidence_ref": "REC-1"}], "record_count": 1, "evidence_index": [{"evidence_ref": "REC-1"}]}
        payloads = compile_payloads({"format": "json"}, manifest, canonical)
        self.assertIn("oee", payloads["overview"]["metrics"])
        self.assertFalse(payloads["overview"]["source_write_performed"])

    def test_observed_oee_is_exposed_without_faking_components(self):
        manifest = build_mapping_manifest({"mapping_draft": []})
        canonical = {
            "records": [{"oee_source": 0.759, "line_id": "SMT-A", "shift_date": "2026-06-30", "evidence_ref": "REC-OEE-1"}],
            "record_count": 1,
            "evidence_index": [{"evidence_ref": "REC-OEE-1"}],
        }
        payloads = compile_payloads({"format": "xlsx"}, manifest, canonical)
        metric = payloads["overview"]["metrics"]["oee"]
        self.assertEqual(metric["value_mode"], "observed_source")
        self.assertFalse(metric["calculation_allowed"])
        self.assertEqual(metric["value"], 0.759)
        self.assertEqual(payloads["overview"]["view_coverage"]["lines"], ["SMT-A"])

    def test_yield_is_compiled_from_total_and_good_output(self):
        manifest = build_mapping_manifest({"mapping_draft": []})
        canonical = {"records": [{"total_output": 1000, "good_output": 950, "evidence_ref": "REC-Y-1"}], "record_count": 1, "evidence_index": [{"evidence_ref": "REC-Y-1"}]}
        payloads = compile_payloads({"format": "xlsx"}, manifest, canonical)
        self.assertAlmostEqual(payloads["overview"]["metrics"]["yield"]["value"], 0.95)

    def test_public_percent_aliases_are_exact_domain_approved(self):
        response = {"mapping_draft": [
            {"source_table": "产", "source_field": "良率(%)", "target_field": "quality_rate", "mapping_status": "proposed", "confidence": 0.8},
            {"source_table": "产", "source_field": "OEE(%)", "target_field": "oee_source", "mapping_status": "proposed", "confidence": 0.8},
            {"source_table": "产", "source_field": "产线", "target_field": "line_id", "mapping_status": "proposed", "confidence": 0.8},
        ]}
        manifest = build_mapping_manifest(response)
        self.assertEqual(manifest["status"], "approved")
        self.assertEqual(manifest["approved_count"], 3)

    def test_cross_source_dimension_aliases_share_one_canonical_target(self):
        self.assertEqual(_canonical_target("line_name"), "line_name")
        self.assertEqual(_canonical_target("production_date"), "shift_date")
        self.assertEqual(_canonical_target("actual_qty"), "total_output")

    def test_physical_line_header_is_not_downgraded_to_display_name(self):
        manifest = build_mapping_manifest({"mapping_draft": [
            {"source_table": "产", "source_field": "产线", "target_field": "line_name", "confidence": 0.99},
            {"source_table": "产", "source_field": "产线名称", "target_field": "line_id", "confidence": 0.99},
        ]})
        by_field = {item["source_field"]: item["target_field"] for item in manifest["entries"]}
        self.assertEqual(by_field["产线"], "line_id")
        self.assertEqual(by_field["产线名称"], "line_name")

    def test_dynamic_event_contains_all_role_slices_and_dimensions(self):
        manifest = build_mapping_manifest({"mapping_draft": []})
        canonical = {"records": [
            {"line_id": "LINE-A", "oee_source": 0.75, "evidence_ref": "REC-1"},
            {"line_id": "LINE-B", "oee_source": 0.81, "evidence_ref": "REC-2"},
        ], "record_count": 2, "evidence_index": [{"evidence_ref": "REC-1"}, {"evidence_ref": "REC-2"}]}
        payloads = compile_payloads({"format": "xlsx"}, manifest, canonical)
        self.assertEqual({item["role"] for item in payloads["event"]["roles"]}, {"factory", "line", "quality", "equipment", "process", "supply"})
        self.assertEqual(payloads["overview"]["dimensions"]["lines"][0]["line_id"], "LINE-A")
        line_dimension = next(item for item in payloads["overview"]["dimensions"]["roles"] if item["role"] == "line")
        self.assertEqual(line_dimension["allowed_line_ids"], ["LINE-A", "LINE-B"])
        for role in payloads["event"]["roles"]:
            self.assertIn(role["scope"]["mode"], {"all_lines", "single_line"})
            self.assertIsInstance(role["scope"]["line_ids"], list)

        specialist = next(item for item in payloads["event"]["roles"] if item["role"] == "quality")
        self.assertEqual(specialist["status"], "partial")
        self.assertEqual(specialist["role_projection"], "shared_production_evidence")
        self.assertTrue(specialist["data_gaps"])


if __name__ == "__main__":
    unittest.main()

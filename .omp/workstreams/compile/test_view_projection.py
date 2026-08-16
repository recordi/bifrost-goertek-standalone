import unittest

from view_projection import build_view_projection


class ViewProjectionTests(unittest.TestCase):
    def test_only_observed_line_dimensions_are_projected(self):
        result = build_view_projection([
            {"line_id": "LINE-A", "oee_recomputed": 0.8, "yield_recompute": 0.98},
            {"line_id": "LINE-B", "oee_recomputed": 0.7, "yield_recompute": 0.97},
        ])
        self.assertEqual(result["view_coverage"]["lines"], ["LINE-A", "LINE-B"])
        self.assertIn("factory", result["view_coverage"]["roles"])
        self.assertIn("line|LINE-A|full_history", {item["view_key"] for item in result["view_snapshots"]})

    def test_missing_dimensions_do_not_create_fake_lines(self):
        result = build_view_projection([{"oee_recomputed": 0.8}])
        self.assertEqual(result["view_coverage"]["lines"], [])
        self.assertEqual(result["view_coverage"]["roles"], ["factory"])
        self.assertEqual(len(result["view_snapshots"]), 1)

    def test_date_windows_and_improvement_split_require_observed_fields(self):
        rows = [
            {"line_id": "LINE-A", "shift_date": f"2026-08-{day:02d}", "phase": "改善前" if day <= 4 else "改善后", "oee_recomputed": 0.70 + day / 1000, "yield_recompute": 0.95}
            for day in range(1, 9)
        ]
        result = build_view_projection(rows)
        coverage = result["view_coverage"]
        self.assertEqual(coverage["time_windows"], ["full_history", "recent_7_shifts", "recent_30_shifts", "before_improvement", "after_improvement"])
        keys = {item["view_key"] for item in result["view_snapshots"]}
        self.assertIn("line|LINE-A|recent_7_shifts", keys)
        self.assertIn("factory|ALL_LINES|before_improvement", keys)
        recent = next(item for item in result["view_snapshots"] if item["view_key"] == "line|LINE-A|recent_7_shifts")
        self.assertEqual(recent["time_window"]["actual_record_count"], 7)

    def test_omitted_windows_explain_missing_source_dimensions(self):
        result = build_view_projection([{"line_id": "LINE-A", "shift_date": "2026-08-01", "oee_recomputed": 0.8}])
        omitted = result["view_coverage"]["omitted_windows"]
        self.assertIn("before_improvement", omitted)
        self.assertIn("改善前", omitted["before_improvement"])
        self.assertEqual(result["view_coverage"]["projection_policy"], "只投影证据充分的窗口；缺失窗口保留省略原因")

    def test_missing_date_does_not_fabricate_recent_windows(self):
        result = build_view_projection([{"line_id": "LINE-A", "oee_recomputed": 0.8}])
        self.assertEqual(result["view_coverage"]["time_windows"], ["full_history"])

    def test_snapshots_keep_line_scoped_evidence_refs(self):
        result = build_view_projection([
            {"line_id": "LINE-A", "oee_recomputed": 0.8, "evidence_ref": "SRC:A:1"},
            {"line_id": "LINE-B", "oee_recomputed": 0.7, "evidence_ref": "SRC:B:1"},
        ])
        a = next(item for item in result["view_snapshots"] if item["view_key"] == "line|LINE-A|full_history")
        b = next(item for item in result["view_snapshots"] if item["view_key"] == "line|LINE-B|full_history")
        self.assertEqual(a["evidence_refs"], ["SRC:A:1"])
        self.assertEqual(b["evidence_refs"], ["SRC:B:1"])

    def test_source_lineage_is_not_an_active_comparison_line(self):
        result = build_view_projection([
            {"line_id": "LINE-R01", "oee_recomputed": 0.61, "evidence_ref": "SRC:R:1"},
            {"line_id": "LINE-S01", "oee_recomputed": 0.70, "evidence_ref": "SRC:S1:1"},
            {"line_id": "LINE-S02", "oee_recomputed": 0.72, "evidence_ref": "SRC:S2:1"},
            {"line_id": "LINE-S03", "oee_recomputed": 0.68, "evidence_ref": "SRC:S3:1"},
        ])
        coverage = result["view_coverage"]
        self.assertEqual(coverage["lines"], ["LINE-S01", "LINE-S02", "LINE-S03"])
        self.assertEqual(coverage["source_line_ids"], ["LINE-R01"])
        self.assertEqual(coverage["observed_line_ids"], ["LINE-R01", "LINE-S01", "LINE-S02", "LINE-S03"])
        all_lines = next(item for item in result["view_snapshots"] if item["view_key"] == "factory|ALL_LINES|full_history")
        self.assertNotIn("SRC:R:1", all_lines["evidence_refs"])
        self.assertEqual({item["scope"]["line_ids"][0] for item in result["view_snapshots"] if item["role"] == "line"}, {"LINE-S01", "LINE-S02", "LINE-S03"})

    def test_official_named_lines_remain_active(self):
        result = build_view_projection([
            {"line_id": "SMT-A线", "oee_recomputed": 0.81},
            {"line_id": "SMT-B线", "oee_recomputed": 0.79},
        ])
        self.assertEqual(result["view_coverage"]["lines"], ["SMT-A线", "SMT-B线"])
        self.assertEqual(result["view_coverage"]["source_line_ids"], [])


if __name__ == "__main__":
    unittest.main()

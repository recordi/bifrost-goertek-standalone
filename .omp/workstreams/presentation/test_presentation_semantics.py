import unittest

from presentation_semantics import humanize, metric_display


class PresentationSemanticsTests(unittest.TestCase):
    def test_business_labels_are_chinese(self):
        self.assertEqual(humanize("performance_rate"), "性能率")
        self.assertEqual(humanize("not_observable", kind="status"), "暂无足够数据判定")

    def test_raw_field_is_evidence_only(self):
        item = metric_display("quality_rate", 0.98, "ratio")
        self.assertEqual(item["label"], "质量率")
        self.assertFalse(item["show_raw_field"])
        self.assertTrue(item["raw_field_in_evidence"])


if __name__ == "__main__":
    unittest.main()

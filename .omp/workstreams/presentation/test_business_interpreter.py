import unittest

from business_interpreter import build_business_interpretation


class BusinessInterpreterTests(unittest.TestCase):
    def test_explains_kpi_and_defect_distribution_without_root_cause_claim(self):
        payload = {
            "dataset_id": "TEAM_ENGINEERED_SIMULATION",
            "data_nature": "团队模拟数据",
            "view": {
                "view_key": "line|LINE-S01|last_7_shifts",
                "time_window": {"window_id": "last_7_shifts"},
                "kpis": [{"metric_code": "OEE", "value": 0.677, "target": 0.76, "value_type": "ratio"}],
                "tables": [{"table_id": "defect_LINE-S01", "rows": [
                    {"label": "尺寸超差", "count": 1183, "evidence_refs": ["E1"]},
                    {"label": "外观不良", "count": 709, "evidence_refs": ["E2"]},
                ],}],
                "evidence_refs": ["E1", "E2"],
            },
        }
        result = build_business_interpretation(payload, role="line", scope="LINE-S01")
        self.assertEqual(result["contract_version"], "BIFROST-BUSINESS-INTERPRETATION-v1")
        self.assertTrue(result["authoritative_metrics_unchanged"])
        self.assertEqual(len(result["findings"]), 2)
        defect = next(item for item in result["findings"] if item["type"] == "quality")
        self.assertIn("不等于已经确认的根因", defect["meaning"])
        self.assertAlmostEqual(defect["metrics"][0]["share"], 1183 / 1892, places=4)

    def test_adapter_task_contract_is_explained_but_not_promoted(self):
        result = build_business_interpretation({
            "dataset_id": "GOERTEK_OFFICIAL_SIMULATION",
            "data_nature": "官方脱敏测试数据",
            "tasks": [{
                "metrics": [
                    {"semantic_field": "oee", "value": 0.61, "unit": "ratio", "value_mode": "observed_source", "evidence_refs": ["E1"]},
                    {"semantic_field": "defect_total", "value": 50, "unit": "count", "evidence_refs": ["E2"]},
                ],
            }],
        }, role="factory")
        self.assertEqual(result["source"]["data_nature"], "官方脱敏测试数据")
        self.assertTrue(result["findings"])
        self.assertTrue(result["authoritative_metrics_unchanged"])


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path


class DynamicAdapterUiTests(unittest.TestCase):
    def test_config_page_exposes_readonly_adaptation_flow(self):
        source = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "pages.jsx").read_text(encoding="utf-8")
        self.assertIn("DynamicDataAdapterPanel", source)
        self.assertIn("/api/data-adapt", source)
        self.assertIn("不会修改原始文件", source)
        data_layer = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "data.jsx").read_text(encoding="utf-8")
        self.assertIn("applyDynamicPayloads", data_layer)
        self.assertIn("bifrost:data-updated", data_layer)
        self.assertIn("const adaptedResult = payload.result || payload", source)

    def test_runtime_consumes_payload_window_and_line_coverage(self):
        data_layer = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "data.jsx").read_text(encoding="utf-8")
        app_layer = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "app.jsx").read_text(encoding="utf-8")
        i18n_layer = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "i18n.jsx").read_text(encoding="utf-8")
        self.assertIn("view_coverage?.time_windows", data_layer)
        self.assertIn("view_coverage?.lines", data_layer)
        self.assertIn("view_coverage?.window_labels", i18n_layer)
        self.assertIn("setTimeWindow((current)", app_layer)

    def test_user_facing_adapter_copy_is_chinese_and_hides_internal_ids(self):
        page = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "pages.jsx").read_text(encoding="utf-8")
        i18n = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "i18n.jsx").read_text(encoding="utf-8")
        self.assertIn("请至少选择一条字段映射", page)
        self.assertIn("t_field(item.target_field)", page)
        self.assertIn("t_field(metricId)", page)
        self.assertIn("fields:", i18n)
        self.assertNotIn("Select at least one mapping", page)

    def test_dynamic_bridge_and_peer_analysis_are_visible_but_additive(self):
        page = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "pages.jsx").read_text(encoding="utf-8")
        server = (Path(__file__).parents[1] / "integration" / "serve_bifrost_ui.py").read_text(encoding="utf-8")
        self.assertIn("build_peer_task_payload", server)
        self.assertIn("run_peer_postprocessors", server)
        self.assertIn("result.peer_analysis", page)
        self.assertIn("不改变正式指标", page)

    def test_drilldown_is_user_selectable_and_readonly(self):
        page = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "pages.jsx").read_text(encoding="utf-8")
        server = (Path(__file__).parents[1] / "integration" / "serve_bifrost_ui.py").read_text(encoding="utf-8")
        self.assertIn("drilldown_filters", page)
        self.assertIn("active_line_ids", page)
        self.assertIn("selectedDrilldownValues", page)
        self.assertIn("查看事实", page)
        self.assertIn("drilldown_filters", server)
        self.assertIn("source_write_performed", server)

    def test_business_interpretation_is_readable_and_evidence_first(self):
        page = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "pages.jsx").read_text(encoding="utf-8")
        data_layer = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "data.jsx").read_text(encoding="utf-8")
        self.assertIn("ReadableBusinessInterpretationCard", page)
        self.assertIn("业务解读与下一步", page)
        self.assertIn("质量问题分类回答“检测发现了什么”", page)
        self.assertIn("buildBusinessViewBrief", data_layer)
        self.assertIn("不等于已经确认的根因", data_layer)

    def test_rule_inputs_use_schema_and_current_source_context(self):
        page = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "pages.jsx").read_text(encoding="utf-8")
        self.assertIn("payload.input_schema", page)
        self.assertIn("sampleFields", page)
        self.assertIn("source_payload_sha256", page)
        self.assertIn("rows: sampleRows", page)
        self.assertIn("sampleRows.slice(1)", page)
        self.assertIn("ruleBinding", page)

    def test_events_and_governance_respect_scope_and_status_aliases(self):
        page = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "pages.jsx").read_text(encoding="utf-8")
        i18n = (Path(__file__).parents[2] / "output" / "bifrost-ui-runtime" / "src" / "i18n.jsx").read_text(encoding="utf-8")
        self.assertIn("const scopedEvents = useMemo", page)
        self.assertIn("resolveScopeForRole(role, scope)", page)
        self.assertIn("const isResolvedIssue = (issue)", page)
        self.assertIn('unit_inconsistent: "单位不一致"', i18n)


if __name__ == "__main__":
    unittest.main()

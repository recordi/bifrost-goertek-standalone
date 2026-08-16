#!/usr/bin/env python3
"""Regression tests for the BIFROST AI Result Contract v1."""

from __future__ import annotations

import sys
import unittest
import copy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, ".omp/integration")
import serve_bifrost_ui as bridge  # noqa: E402


class AIResultContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = bridge.run_adapter(peer=False)
        cls.answer = "结论：基于固定只读适配器结果。"

    def build(self, role: str) -> dict:
        return bridge.build_result_contract(
            self.answer,
            {"role": role, "scope": "ALL_LINES", "time_window": "last_7_shifts"},
            self.adapter,
        )

    def test_contract_has_stable_shape(self) -> None:
        result = self.build("factory")
        required = {
            "contract_version", "run_id", "status", "role", "scope", "time_window",
            "headline", "kpis", "risks", "evidence_refs", "recommended_actions",
            "needs_human_confirmation", "data_gaps", "business_findings", "source",
        }
        self.assertTrue(required.issubset(result))
        self.assertEqual(result["contract_version"], "BIFROST-AI-RESULT-v1")
        self.assertTrue(result["headline"])

    def test_all_roles_are_scoped_without_losing_evidence(self) -> None:
        for role in ("factory", "line", "quality", "equipment", "process", "supply"):
            with self.subTest(role=role):
                result = self.build(role)
                self.assertEqual(result["role"], role)
                self.assertGreaterEqual(len(result["kpis"]), 1)
                self.assertGreaterEqual(len(result["evidence_refs"]), 1)

    def test_high_risk_boundary_is_preserved(self) -> None:
        result = self.build("factory")
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertTrue(result["needs_human_confirmation"])
        self.assertTrue(any(action["prohibited_auto_execute"] for action in result["recommended_actions"]))

    def test_result_is_read_only(self) -> None:
        result = self.build("factory")
        self.assertTrue(result["source"]["readonly"])
        self.assertFalse(result["source"]["source_write_performed"])

    def test_context_gate_rejects_invalid_scope_window_and_event(self) -> None:
        with self.assertRaisesRegex(ValueError, "INVALID_SCOPE"):
            bridge.validate_ai_context(
                role="quality", scope="LINE/../../", time_window="last_7_shifts"
            )
        with self.assertRaisesRegex(ValueError, "INVALID_TIME_WINDOW"):
            bridge.validate_ai_context(
                role="quality", scope="LINE-S01", time_window="all_time"
            )
        with self.assertRaisesRegex(ValueError, "INVALID_EVENT_ID"):
            bridge.validate_ai_context(
                role="quality", scope="LINE-S01", time_window="last_7_shifts", event_id="bad id"
            )
        bridge.validate_ai_context(
            role="quality", scope="LINE-S01", time_window="last_7_shifts", event_id="EVT-20251009-0001"
        )

    def test_context_adapter_is_role_scoped_and_does_not_mutate_input(self) -> None:
        before = copy.deepcopy(self.adapter)
        scoped = bridge.adapter_for_context(self.adapter, role="quality", scope="ALL_LINES")
        self.assertTrue(scoped.get("tasks"))
        self.assertTrue(all(task.get("agent_id") == "quality-specialist" for task in scoped["tasks"]))
        self.assertEqual(scoped.get("context_role"), "quality")
        self.assertEqual(self.adapter, before)

    def test_line_scope_drops_unattributed_tasks(self) -> None:
        scoped = bridge.adapter_for_context(self.adapter, role="quality", scope="LINE-S01")
        self.assertEqual(scoped.get("tasks"), [])
        scoped_line = bridge.adapter_for_context(self.adapter, role="line", scope="LINE-S03")
        self.assertTrue(scoped_line.get("tasks"))
        self.assertTrue(all(
            any(item.get("id") == "LINE-S03" for item in task.get("affected_objects", []))
            for task in scoped_line["tasks"]
        ))

    def test_result_contract_preserves_selected_event_context(self) -> None:
        scoped = bridge.adapter_for_context(self.adapter, role="factory", scope="ALL_LINES")
        result = bridge.build_result_contract(
            self.answer,
            {
                "role": "factory",
                "scope": "ALL_LINES",
                "time_window": "last_7_shifts",
                "event_id": "EVT-CONTEXT-1",
            },
            scoped,
        )
        self.assertEqual(result["event_id"], "EVT-CONTEXT-1")

    def test_mismatched_event_context_blocks_unrelated_payload(self) -> None:
        canonical = self.adapter.get("event", {}).get("event_id")
        scoped = bridge.adapter_for_context(
            self.adapter,
            role="factory",
            scope="ALL_LINES",
            event_id="EVT-UNRELATED-CONTEXT",
        )
        self.assertNotEqual(canonical, "EVT-UNRELATED-CONTEXT")
        self.assertEqual(scoped.get("tasks"), [])
        self.assertFalse(scoped.get("event_context_match"))

    def test_ui_ai_context_uses_selected_event_state(self) -> None:
        runtime = Path(__file__).resolve().parents[2] / "output" / "bifrost-ui-runtime" / "src"
        app = (runtime / "app.jsx").read_text(encoding="utf-8")
        pages = (runtime / "pages.jsx").read_text(encoding="utf-8")
        self.assertIn("const [selectedEventId, setSelectedEventId]", app)
        self.assertIn("eventId: currentPage === \"events\" ? selectedEventId : null", app)
        self.assertNotIn('eventId: currentPage === "events" ? "EVT-20251009-0001"', app)
        self.assertIn("onEventChange", app)
        self.assertIn("onClick={() => onEventChange(evt.event_id)}", pages)

    def test_all_roles_have_quick_questions_and_context_fields(self) -> None:
        runtime = Path(__file__).resolve().parents[2] / "output" / "bifrost-ui-runtime" / "src"
        i18n = (runtime / "i18n.jsx").read_text(encoding="utf-8")
        components = (runtime / "components.jsx").read_text(encoding="utf-8")
        for role in ("factory", "line", "quality", "equipment", "process", "supply"):
            self.assertIn(f"    {role}: [", i18n)
        for field in ("role", "scope", "time_window", "event_id"):
            self.assertIn(field, components)
        self.assertIn("workflow_snapshot", components)
        self.assertIn("formal_findings", components)

    def test_ui_sanitizes_provider_failure_details(self) -> None:
        runtime = Path(__file__).resolve().parents[2] / "output" / "bifrost-ui-runtime" / "src"
        components = (runtime / "components.jsx").read_text(encoding="utf-8")
        self.assertIn("function formatAIError", components)
        self.assertIn("OMP_PROVIDER_FAILED", components)
        self.assertIn('text: formatAIError(error)', components)

    def test_bridge_only_bypasses_known_dead_loopback_proxy(self) -> None:
        with patch.dict(bridge.os.environ, {"HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "https://proxy.example:8443"}, clear=False):
            env = bridge.normalized_child_env()
        self.assertNotIn("HTTP_PROXY", env)
        self.assertEqual(env.get("HTTPS_PROXY"), "https://proxy.example:8443")


if __name__ == "__main__":
    unittest.main(verbosity=2)

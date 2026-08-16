#!/usr/bin/env python3
"""Static regression checks for generated peer overlay runtime."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "output" / "bifrost-ui-runtime"
BASELINE = ROOT / "artifacts" / "ui-baseline-v3.2.1"
ASSETS = ROOT / ".omp" / "skills" / "bifrost-decision-readonly" / "references" / "runtime_assets"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PeerOverlayRuntimeTests(unittest.TestCase):
    def test_manifest_marks_adapter_only(self):
        manifest = json.loads((RUNTIME / "BIFROST_UI_RUNTIME_MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["ui_baseline"], "v3.2.1")
        self.assertEqual(manifest["peer_overlay"]["mode"], "adapter-test-only")

    def test_overlay_artifact_has_contract(self):
        payload = json.loads((RUNTIME / "artifacts" / "BIFROST_PEER_OVERLAY_adapter-test.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["payload_version"], "PEER-OVERLAY-v1.0")
        self.assertEqual(payload["peer_overlay"]["target"], "adapter-test-only")
        self.assertTrue(payload["peer_overlay"]["read_only"])
        self.assertEqual(payload["governance_findings"]["status"], "not_run")
        self.assertIn("role_projections", payload)

    def test_runtime_data_loads_overlay_only_in_test_mode(self):
        source = (RUNTIME / "src" / "data.jsx").read_text(encoding="utf-8")
        self.assertIn('get("mode") === "adapter-test"', source)
        self.assertIn('BIFROST_PEER_OVERLAY_adapter-test.json', source)
        self.assertIn('peer_overlay: null', source)

    def test_runtime_page_has_role_scoped_overlay_and_safety_copy(self):
        source = (RUNTIME / "src" / "pages.jsx").read_text(encoding="utf-8")
        self.assertIn("PeerOverlayPanel", source)
        self.assertIn("不改变原始指标和正式载荷", source)
        self.assertIn("不计算 Cpk，不宣称过程失控", source)
        self.assertIn("供应链缺口单独展示，不作为 OEE 原因", source)
        for role in ("factory", "line", "quality", "equipment", "process", "supply"):
            self.assertIn(f'"{role}"', source if role == "factory" else (RUNTIME / "artifacts" / "BIFROST_PEER_OVERLAY_adapter-test.json").read_text(encoding="utf-8"))

    def test_approved_payload_hashes_unchanged(self):
        manifest = json.loads((RUNTIME / "BIFROST_UI_RUNTIME_MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["payloads"]["BIFROST_OVERVIEW_PAYLOAD_v2.1.json"]["sha256"], "2697683f461a555b954bd7e8bf7b0c37a4e9844d82cbcc20ffa1ed2300ef76bd")
        self.assertEqual(manifest["payloads"]["BIFROST_EVENT_PAYLOAD_v1.4.json"]["sha256"], "53fdc970d7f7ec7b0c46fe9d60f8ee472340ff16ed98a333719f996d67f0ad7b")


if __name__ == "__main__":
    unittest.main(verbosity=2)

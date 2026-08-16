import json
import sys
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(ROOT / ".omp" / "integration"))
from serve_bifrost_ui import Handler  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402


class AdaptiveApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def post(self, route, payload):
        request = urllib.request.Request(
            self.base + route,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_presentation_contract(self):
        with urllib.request.urlopen(self.base + "/api/presentation-semantics") as response:
            result = json.loads(response.read().decode("utf-8"))
        self.assertEqual(result["contract_version"], "BIFROST-PRESENTATION-SEMANTICS-v1")
        self.assertFalse(result["raw_fields_visible_in_business_view"])

    def test_data_adapt_contract(self):
        fixture = ROOT / ".omp" / "skills" / "bifrost-data-mapper-readonly" / "tests" / "fixtures" / "missing_fields_fixture.json"
        result = self.post("/api/data-adapt", {"source_path": str(fixture), "source_id": "API-SMOKE"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"]["contract_version"], "BIFROST_AUTO_ADAPT_v1")
        self.assertIn("overview", result["result"]["generated_payloads"])

    def test_peer_contract(self):
        payload = {"tasks": [{"agent_id": "production-specialist", "event_id": "EVT-API", "task_id": "TASK-API", "metrics": [{"semantic_field": "availability", "value": 0.85, "evidence_refs": ["REC-1"]}], "causes": [{"category": "downtime", "duration_minutes": 45, "evidence_refs": ["REC-1"]}], "evidence_refs": ["REC-1"]}]}
        result = self.post("/api/peer-postprocess", {"role": "factory", "payload": payload})
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["result"]["authoritative_metrics_unchanged"])
        self.assertFalse(result["result"]["source_write_performed"])


if __name__ == "__main__":
    unittest.main()

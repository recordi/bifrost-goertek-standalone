#!/usr/bin/env python3
"""Contract-only tests for the optional classmate daemon bridge."""

from __future__ import annotations

import unittest
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from peer_daemon_bridge import BridgeConfig, build_run_request, execute_bridge, map_daemon_result


class _MockDaemonState:
    def __init__(self):
        self.requests = []
        self.poll_count = 0


def _make_mock_daemon(state: _MockDaemonState):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 - stdlib callback name
            path = urlparse(self.path).path
            if path == "/health":
                return self._json(200, {"status": "ok"})
            if path == "/api/runs/run_mock":
                state.poll_count += 1
                return self._json(200, {"status": "done", "artifacts": {"factset": {"id": "fs-1"}}})
            if path.endswith("/reviews"):
                return self._json(200, {"factReview": {"findings": []}})
            if path.endswith("/gates"):
                return self._json(200, {"gates": [{"id": "gate-1", "status": "pass"}]})
            return self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802 - stdlib callback name
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            state.requests.append((self.path, json.loads(raw)))
            return self._json(201, {"runId": "run_mock"})

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    return server


class PeerDaemonBridgeTests(unittest.TestCase):
    def test_request_contains_only_public_fields(self):
        request = build_run_request(role="厂长", brief="分析产线OEE风险", dataset_ids=["ds_test"], project_id="p1")
        self.assertEqual(request["role_id"], "plant_manager")
        self.assertEqual(set(request), {"brief", "role_id", "dataset_ids"})
        self.assertNotIn("metrics", request)
        self.assertNotIn("factset", request)
        self.assertNotIn("payload", request)

    def test_invalid_dataset_id_is_rejected_before_http(self):
        with self.assertRaises(ValueError):
            build_run_request(role="厂长", brief="分析产线OEE风险", dataset_ids=["ds-official-sim"], project_id="p1")

    def test_unregistered_bifrost_role_is_rejected_before_http(self):
        with self.assertRaises(ValueError):
            build_run_request(role="质量", brief="分析质量风险", dataset_ids=["ds_test"], project_id="p1")

    def test_daemon_result_is_non_authoritative_and_read_only(self):
        result = map_daemon_result("run_test", {"status": "done", "artifacts": {}, "error": {"code": "E_TEST"}}, {"factReview": {"findings": []}}, {"gates": []})
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["non_authoritative"])
        self.assertTrue(result["read_only"])
        self.assertIn("factset_not_returned", result["data_gaps"])
        self.assertEqual(result["daemon_error"]["code"], "E_TEST")

    def test_unfinished_daemon_is_not_claimed_as_success(self):
        result = map_daemon_result("run_test", {"status": "running", "artifacts": {}})
        self.assertEqual(result["status"], "warning")
        self.assertIn("gates_not_returned", result["data_gaps"])

    def test_execute_bridge_uses_read_only_public_flow(self):
        state = _MockDaemonState()
        server = _make_mock_daemon(state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = execute_bridge(
                BridgeConfig(base_url=f"http://127.0.0.1:{server.server_port}", timeout_seconds=1, poll_seconds=0),
                role="厂长",
                brief="只读验证三条产线风险",
                dataset_ids=["ds_test"],
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(result["status"], "available")
        self.assertTrue(result["read_only"])
        self.assertTrue(result["non_authoritative"])
        self.assertEqual(state.poll_count, 1)
        self.assertEqual(len(state.requests), 1)
        path, body = state.requests[0]
        self.assertTrue(path.endswith("/api/projects/demo_goertek_m6/runs"))
        self.assertEqual(set(body), {"brief", "role_id", "dataset_ids"})
        self.assertEqual(body["role_id"], "plant_manager")
        self.assertNotIn("params", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Loopback-only OpenAI-compatible adapter backed by OMP/custom-grok.

This is a development/test adapter, not a general proxy. It accepts only chat
completion requests, disables OMP tools/extensions/skills/sessions, and never
forwards the daemon's API key to OMP. The daemon sees a local OpenAI-compatible
endpoint; OMP remains the only model runtime.
"""

from __future__ import annotations

import json
import base64
import binascii
import os
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
OMP = Path(os.environ.get("OMP_EXE", r"D:\Codex\智能体\oh-my-pi\omp-windows-x64.exe"))
HOST = "127.0.0.1"
PORT = int(os.environ.get("OMP_BRIDGE_PORT", "8000"))
BRIDGE_KEY = os.environ.get("OMP_BRIDGE_API_KEY", "omp-local-bridge-key")
MODEL = os.environ.get("OMP_BRIDGE_MODEL", "custom-grok/grok-4.6")
MAX_BODY = 2 * 1024 * 1024
CALL_LOCK = threading.Lock()


def _text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            item.get("text", "")
            for item in value
            if isinstance(item, dict) and item.get("type") in {"text", "input_text"}
        )
    return ""


def _messages_to_prompt(messages: Any) -> tuple[str, list[tuple[str, bytes]]]:
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty array")
    blocks: list[str] = []
    attachments: list[tuple[str, bytes]] = []
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("each message must be an object")
        role = message.get("role")
        raw_content = message.get("content")
        content = _text_content(raw_content)
        if isinstance(raw_content, list):
            for item in raw_content:
                if not isinstance(item, dict) or item.get("type") != "image_url":
                    continue
                image = item.get("image_url")
                url = image.get("url") if isinstance(image, dict) else None
                if not isinstance(url, str) or not url.startswith("data:image/") or ";base64," not in url:
                    raise ValueError("only base64 data:image attachments are supported")
                header, encoded = url.split(";base64,", 1)
                mime = header.removeprefix("data:")
                try:
                    image_bytes = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise ValueError("invalid base64 image attachment") from exc
                if not image_bytes or len(image_bytes) > 8 * 1024 * 1024:
                    raise ValueError("image attachment must be between 1 byte and 8 MiB")
                attachments.append((mime, image_bytes))
            if attachments:
                content = (content + "\n" if content else "") + "[已附加本轮截图，按附件顺序阅读]"
        if role not in {"system", "user", "assistant", "developer"} or not content:
            raise ValueError("messages must contain supported roles and text content")
        blocks.append(f"[{role}]\n{content}")
    return "\n\n".join(blocks), attachments


def _extract_text(raw: bytes) -> str:
    last_text = ""
    for line in raw.decode("utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "message_end":
            message = event.get("message") or {}
            if message.get("role") == "assistant":
                content = message.get("content") or []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        last_text = part.get("text", "")
    if not last_text:
        raise RuntimeError("OMP returned no assistant text")
    return last_text


def call_omp(prompt: str, attachments: list[tuple[str, bytes]] | None = None, timeout: float = 180.0) -> str:
    if not OMP.is_file():
        raise RuntimeError(f"OMP executable not found: {OMP}")
    prompt_file: Path | None = None
    attachment_files: list[Path] = []
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False, dir=ROOT / ".omp") as handle:
            handle.write(prompt)
            prompt_file = Path(handle.name)
        for index, (mime, image_bytes) in enumerate(attachments or [], start=1):
            suffix = ".png" if mime == "image/png" else ".jpg" if mime in {"image/jpeg", "image/jpg"} else ".webp"
            with tempfile.NamedTemporaryFile("wb", suffix=suffix, prefix=f"omp-image-{index}-", delete=False, dir=ROOT / ".omp") as image_handle:
                image_handle.write(image_bytes)
                attachment_files.append(Path(image_handle.name))
        env = os.environ.copy()
        completed = subprocess.run(
            [
                str(OMP), "--model", MODEL, "--mode", "json", "--no-session",
                "--no-tools", "--no-extensions", "--no-skills", "--no-rules",
                "--max-time", str(int(timeout)), "-p", f"@{prompt_file}",
                *[f"@{path}" for path in attachment_files],
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            timeout=timeout + 15,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(f"OMP exited with {completed.returncode}: {detail}")
        return _extract_text(completed.stdout)
    finally:
        if prompt_file:
            prompt_file.unlink(missing_ok=True)
        for attachment_file in attachment_files:
            attachment_file.unlink(missing_ok=True)


def _completion(text: str, model: str, request_id: str) -> dict[str, Any]:
    return {
        "id": request_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "BIFROST-OMP-Bridge/0.1"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        return self.headers.get("Authorization", "") == f"Bearer {BRIDGE_KEY}"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            return self._send_json(200, {"status": "ok", "service": "omp-openai-bridge", "model": MODEL})
        if self.path == "/v1/models":
            return self._send_json(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "owned_by": "omp"}]})
        self._send_json(404, {"error": {"message": "Not found", "type": "invalid_request_error"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            return self._send_json(404, {"error": {"message": "Not found", "type": "invalid_request_error"}})
        if not self._authorized():
            return self._send_json(401, {"error": {"message": "Invalid bridge key", "type": "authentication_error"}})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("request body is empty or too large")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            prompt, attachments = _messages_to_prompt(body.get("messages"))
            stream = bool(body.get("stream", False))
            request_id = f"chatcmpl-omp-{uuid.uuid4().hex}"
            with CALL_LOCK:
                text = call_omp(prompt, attachments=attachments)
            if not stream:
                return self._send_json(200, _completion(text, body.get("model", MODEL), request_id))
            chunks = [text[i : i + 1200] for i in range(0, len(text), 1200)] or [""]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for chunk in chunks:
                event = {"id": request_id, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL, "choices": [{"index": 0, "delta": {"role": "assistant", "content": chunk}, "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception as exc:
            self._send_json(502, {"error": {"message": str(exc), "type": "upstream_error"}})

    def log_message(self, *_args: Any) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"OMP OpenAI bridge on http://{HOST}:{PORT}/v1 using {MODEL}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

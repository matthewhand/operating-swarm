"""Issue #303 — Hermes send polls the job; ACK is not the chat reply."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from swarm.blueprints.remote_harness.blueprint_remote_harness import _render_operate
from swarm.core import remotes as remotes_core


def _cfg(host: str, port: int) -> dict:
    return {
        "llm": {},
        "remotes": {"hermes": {"base_url": f"http://{host}:{port}", "api_key": "hermes-secret"}},
    }


class _Router(BaseHTTPRequestHandler):
    routes: dict = {}

    def _handle(self, method: str) -> None:
        key = (method, self.path.split("?", 1)[0])
        status_body = type(self).routes.get(key, (404, {"error": "no route"}))
        if callable(status_body):
            status_body = status_body()
        status, body = status_body
        payload = json.dumps(body).encode("utf-8") if not isinstance(body, str) else body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def hermes_http():
    _Router.routes = {}
    server = HTTPServer(("127.0.0.1", 0), _Router)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "127.0.0.1", server.server_address[1], _Router
    server.shutdown()
    _Router.routes = {}


def test_hermes_send_polls_job_output(hermes_http, monkeypatch):
    host, port, router = hermes_http
    monkeypatch.setattr(remotes_core, "_HERMES_POLL_INTERVAL_S", 0.01)
    state = {"n": 0}

    def jobs():
        state["n"] += 1
        if state["n"] < 3:
            return 200, [{"id": "run_1", "status": "running"}]
        return 200, [{"id": "run_1", "status": "completed", "output": "job text from hermes"}]

    router.routes = {
        ("POST", "/v1/runs"): (202, {"run_id": "run_1", "status": "started"}),
        ("GET", "/api/jobs"): jobs,
        ("GET", "/api/jobs/run_1"): jobs,
        ("GET", "/v1/runs/run_1"): (404, {"error": "nope"}),
        ("GET", "/api/sessions"): (200, {"sessions": []}),
    }
    sent = remotes_core.operate(
        "hermes", "send", prompt="hello", config=_cfg(host, port), timeout=2.0
    )
    assert sent.ok is True
    assert sent.data["text"] == "job text from hermes"
    assert sent.data["run_id"] == "run_1"
    assert "started Hermes run" not in sent.detail
    assert _render_operate(sent) == "job text from hermes"


def test_hermes_send_timeout_is_named_not_ack(hermes_http, monkeypatch):
    host, port, router = hermes_http
    monkeypatch.setattr(remotes_core, "_HERMES_POLL_INTERVAL_S", 0.01)
    router.routes = {
        ("POST", "/v1/runs"): (200, {"run_id": "run_9", "status": "started"}),
        ("GET", "/api/jobs"): (200, [{"id": "run_9", "status": "running"}]),
        ("GET", "/api/jobs/run_9"): (200, {"id": "run_9", "status": "running"}),
        ("GET", "/v1/runs/run_9"): (200, {"run_id": "run_9", "status": "started"}),
        ("GET", "/api/sessions"): (200, {"sessions": []}),
    }
    sent = remotes_core.operate(
        "hermes", "send", prompt="hello", config=_cfg(host, port), timeout=0.25
    )
    assert sent.ok is False
    assert "timed out" in sent.detail
    assert "started Hermes run" not in sent.detail
    rendered = _render_operate(sent)
    assert "timed out" in rendered
    assert "started Hermes run" not in rendered
    assert sent.gap == "hermes_reply_timeout"

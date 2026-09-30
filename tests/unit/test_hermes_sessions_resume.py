"""Hermes sessions: nested list envelope, resume send, and transcript hydration.

Live probe (2026-09-26): ``GET /api/sessions`` returns
``{"object":"list","data":[…]}` under the list slice (nested one level deeper
than TrueForge's flat ``data.sessions``), and ``POST /v1/runs`` with
``session_id`` continues the *same* gateway session while minting a fresh
run wrapper. ``GET /api/sessions/{sid}/messages`` returns the turn transcript
that backs chat hydration.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from swarm.core import remotes as remotes_core
from functools import partial

SID = "run_1"


def _cfg(host: str, port: int) -> dict:
    return {
        "llm": {},
        "remotes": {"hermes": {"base_url": f"http://{host}:{port}", "api_key": "hermes-secret"}},
    }


class _Router(BaseHTTPRequestHandler):
    routes: dict = {}
    posts: list = []

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

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            parsed = json.loads(raw.decode() or "{}")
        except Exception:
            parsed = {}
        type(self).posts.append(parsed)
        return parsed

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._read_body()
        self._handle("POST")

    def log_message(self, *args) -> None:
        pass

# NOTE: `serve_forever`'s default poll_interval is 0.5s. It parks in
# `selector.select(0.5)`, and `shutdown()` blocks on `__is_shut_down`, which
# the serve loop can only set on its next wake -- so each fixture teardown
# below paid a flat 500ms parked in a selector. Measured on this box:
# 500.6ms at the default, 50.2ms at 0.05, 10.1ms at 0.01. pytest
# --durations=0 attributes 106s of suite teardown to this pattern across 36
# files -- 28% of the suite's wall clock. A test-fixture cost, not a
# behaviour change: the thread still runs the same serve loop.

@pytest.fixture
def hermes_http():
    _Router.routes = {}
    _Router.posts = []
    server = HTTPServer(("127.0.0.1", 0), _Router)
    threading.Thread(target=partial(server.serve_forever, poll_interval=0.02), daemon=True).start()
    yield "127.0.0.1", server.server_address[1], _Router
    server.shutdown()
    server.server_close()
    _Router.routes = {}
    _Router.posts = []


def _routes() -> dict:
    return {
        ("GET", "/v1/models"): (200, {"object": "list", "data": [{"id": "hermes-agent"}]}),
        ("GET", "/api/jobs"): (200, {"jobs": []}),
        ("GET", "/api/sessions"): (
            200,
            {"object": "list", "data": [{"id": SID, "title": "Reply with OK"}]},
        ),
        ("GET", f"/api/sessions/{SID}/messages"): (
            200,
            {
                "object": "list",
                "session_id": SID,
                "data": [
                    {"role": "user", "content": "Remember ZEBRA-42"},
                    {"role": "assistant", "content": "STORED"},
                    {"role": "tool", "tool_name": "terminal", "content": '{"ok": true}'},
                ],
            },
        ),
        ("POST", "/v1/runs"): (200, {"run_id": SID, "status": "completed", "output": "reply"}),
    }


def test_hermes_list_exposes_nested_sessions(hermes_http):
    host, port, router = hermes_http
    router.routes = _routes()
    res = remotes_core.operate("hermes", "list", config=_cfg(host, port), timeout=2.0)
    assert res.ok is True
    sessions = res.data["sessions"]
    assert sessions["data"][0]["id"] == SID
    # The frontend parser reads the same nested slice.
    from swarm.core.remote_harness import sessions_from_operate

    rows = sessions_from_operate(res)
    assert [row.id for row in rows] == [SID]


def test_hermes_send_carries_session_id_and_resumes_same_session(hermes_http):
    host, port, router = hermes_http
    router.routes = _routes()
    first = remotes_core.operate(
        "hermes", "send", prompt="Remember ZEBRA-42", config=_cfg(host, port), timeout=2.0
    )
    second = remotes_core.operate(
        "hermes",
        "send",
        prompt="What codeword?",
        session_id=SID,
        config=_cfg(host, port),
        timeout=2.0,
    )
    assert first.ok is True and second.ok is True
    assert first.data["text"] == "reply"
    assert router.posts[0].get("session_id") is None
    # The follow-up continues the SAME gateway session — never a new one.
    assert router.posts[1].get("session_id") == SID


def test_read_hermes_recent_turns_maps_user_and_assistant_only(hermes_http):
    host, port, router = hermes_http
    router.routes = _routes()
    from swarm.core.remote_impls.hermes import read_hermes_recent_turns

    turns = read_hermes_recent_turns("hermes", SID, config=_cfg(host, port), timeout=2.0)
    assert turns == [
        {"role": "user", "content": "Remember ZEBRA-42"},
        {"role": "assistant", "content": "STORED"},
    ]


def test_read_hermes_recent_turns_is_honest_when_unreachable(hermes_http):
    host, port, router = hermes_http
    router.routes = {("GET", f"/api/sessions/{SID}/messages"): (500, {"error": "boom"})}
    from swarm.core.remote_impls.hermes import read_hermes_recent_turns

    assert read_hermes_recent_turns("hermes", SID, config=_cfg(host, port), timeout=2.0) == []

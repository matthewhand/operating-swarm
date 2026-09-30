"""#1358 — a TrueForge send reuses the existing session instead of minting one.

Regression: every send with no ``session_id`` called ``POST /api/v1/sessions``
and started a brand-new TrueForge conversation, so follow-up turns lost their
TrueForge context. ``operate(send)`` must resume the newest existing session on
the remote (scoped to the wired agent), and degrade to a fresh session only
when no session is available.

Hermetic: loopback HTTP only, agent settings kept off the real XDG tree.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from swarm.core import agent_settings as settings_store
from swarm.core import remotes as remotes_core
from functools import partial


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], Any] = {}
    route_hits: dict[tuple[str, str], int] = {}
    received_bodies: list[tuple[str, str, Any]] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = None
        if content_len > 0:
            raw = self.rfile.read(content_len).decode("utf-8")
            try:
                body = json.loads(raw)
            except Exception:
                body = raw
            self.received_bodies.append((method, path, body))

        key = (method, path)
        entry = self.routes.get(key, (404, {"error": f"no route for {method} {path}"}))
        if isinstance(entry, list):
            idx = self.route_hits.get(key, 0)
            status, response_body = entry[min(idx, len(entry) - 1)]
            self.route_hits[key] = idx + 1
        else:
            status, response_body = entry
            self.route_hits[key] = self.route_hits.get(key, 0) + 1
        payload = (
            json.dumps(response_body).encode("utf-8")
            if not isinstance(response_body, str)
            else response_body.encode("utf-8")
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def log_message(self, *args) -> None:
        pass


@pytest.fixture(autouse=True)
def _isolate_agent_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    settings_store.reset_agent_settings_cache()
    yield
    settings_store.reset_agent_settings_cache()

# NOTE: `serve_forever`'s default poll_interval is 0.5s. It parks in
# `selector.select(0.5)`, and `shutdown()` blocks on `__is_shut_down`, which
# the serve loop can only set on its next wake -- so each fixture teardown
# below paid a flat 500ms parked in a selector. Measured on this box:
# 500.6ms at the default, 50.2ms at 0.05, 10.1ms at 0.01. pytest
# --durations=0 attributes 106s of suite teardown to this pattern across 36
# files -- 28% of the suite's wall clock. A test-fixture cost, not a
# behaviour change: the thread still runs the same serve loop.

@pytest.fixture
def tf_server():
    _Router.routes = {}
    _Router.route_hits = {}
    _Router.received_bodies = []
    server = HTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=partial(server.serve_forever, poll_interval=0.02), daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield host, port, _Router
    server.shutdown()
    server.server_close()
    _Router.routes = {}
    _Router.route_hits = {}
    _Router.received_bodies = []


def _turn_routes(session_id: str, reply: str, turn_id: str = "turn-1") -> dict:
    """Routes to post one turn on *session_id* and read its reply."""
    return {
        ("POST", f"/api/v1/sessions/{session_id}/turns"): (
            202,
            {"data": {"id": turn_id, "state": "running"}},
        ),
        ("GET", f"/api/v1/sessions/{session_id}/turns/{turn_id}"): (
            200,
            {"data": {"id": turn_id, "state": "done"}},
        ),
        ("GET", f"/api/v1/sessions/{session_id}/turns/{turn_id}/events"): (
            200,
            {"data": [{"type": "model.message", "content": reply}]},
        ),
    }


def _cfg(host: str, port: int, **remote_extra: Any) -> dict:
    block: dict[str, Any] = {"base_url": f"http://{host}:{port}"}
    block.update(remote_extra)
    return {"remotes": {"trueforge": block}}


def test_second_turn_reuses_session_created_by_the_first(tf_server):
    """Original report: a fresh TrueForge seat minted a session per turn.

    First turn sees an empty session list and creates ``sess-created``; the
    next turn must find that session and resume it instead of minting again.
    """
    host, port, router = tf_server
    router.routes = {
        # Empty on the first read; the newly created session is visible after.
        ("GET", "/api/v1/sessions"): [
            (200, {"sessions": []}),
            (
                200,
                {
                    "sessions": [
                        {
                            "id": "sess-created",
                            "agent": "orchestrator",
                            "updated_at": "2026-02-01T00:00:00Z",
                        }
                    ]
                },
            ),
        ],
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-created"}}),
        **_turn_routes("sess-created", "same conversation"),
    }
    cfg = _cfg(host, port)

    first = remotes_core.operate("trueforge", "send", prompt="hello", config=cfg)
    second = remotes_core.operate("trueforge", "send", prompt="again", config=cfg)

    assert first.ok is True, first.detail
    assert second.ok is True, second.detail
    assert first.data["session_id"] == "sess-created"
    assert second.data["session_id"] == "sess-created"
    assert router.route_hits.get(("POST", "/api/v1/sessions"), 0) == 1


def test_send_reuses_newest_existing_session(tf_server):
    """The regression: two turns, one TrueForge session — never a second mint."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/sessions"): (
            200,
            {
                "sessions": [
                    {
                        "id": "sess-older",
                        "agent": "orchestrator",
                        "updated_at": "2026-01-01T00:00:00Z",
                    },
                    {
                        "id": "sess-newer",
                        "agent": "orchestrator",
                        "updated_at": "2026-02-01T00:00:00Z",
                    },
                ]
            },
        ),
        # A fresh-session route exists so the test can prove it is NEVER called.
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-brand-new"}}),
        **_turn_routes("sess-newer", "continued context"),
    }
    cfg = _cfg(host, port)

    first = remotes_core.operate("trueforge", "send", prompt="hello", config=cfg)
    second = remotes_core.operate(
        "trueforge", "send", prompt="and again", config=cfg
    )

    assert first.ok is True, first.detail
    assert second.ok is True, second.detail
    assert first.data["session_id"] == "sess-newer"
    assert second.data["session_id"] == "sess-newer"
    # The whole point: no new TrueForge session was created on either turn.
    assert ("POST", "/api/v1/sessions") not in router.route_hits
    assert router.route_hits[("POST", "/api/v1/sessions/sess-newer/turns")] == 2


def test_send_degrades_to_fresh_session_when_list_is_down(tf_server):
    """Failure mode: an unreachable session list must not fail the send."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/sessions"): (500, {"error": "boom"}),
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-fresh"}}),
        **_turn_routes("sess-fresh", "fresh answer"),
    }
    cfg = _cfg(host, port)

    sent = remotes_core.operate("trueforge", "send", prompt="hi", config=cfg)

    assert sent.ok is True, sent.detail
    assert sent.detail == "fresh answer"
    assert sent.data["session_id"] == "sess-fresh"
    assert ("POST", "/api/v1/sessions") in router.route_hits


def test_send_does_not_resume_another_agents_session(tf_server):
    """Namespace: a seat wired to an agent never resumes a different agent."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/sessions"): (
            200,
            {
                "sessions": [
                    {
                        "id": "sess-foreign",
                        "agent": "other_agent",
                        "updated_at": "2026-02-01T00:00:00Z",
                    }
                ]
            },
        ),
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-orchestrator"}}),
        **_turn_routes("sess-orchestrator", "started for orchestrator"),
    }
    cfg = _cfg(host, port, agent="orchestrator")

    sent = remotes_core.operate("trueforge", "send", prompt="hi", config=cfg)

    assert sent.ok is True, sent.detail
    assert sent.data["session_id"] == "sess-orchestrator"
    sess_req = next(b for m, p, b in router.received_bodies if p == "/api/v1/sessions")
    assert sess_req["agent"]["name"] == "orchestrator"


def test_send_explicit_session_still_wins_over_auto_resume(tf_server):
    """An operator-picked session is honoured; auto-resume never overrides it."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/sessions"): (
            200,
            {"sessions": [{"id": "sess-newest", "agent": "orchestrator", "updated_at": "2026-02-01T00:00:00Z"}]},
        ),
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-brand-new"}}),
        **_turn_routes("sess-picked", "picked reply"),
    }
    cfg = _cfg(host, port)

    sent = remotes_core.operate(
        "trueforge", "send", prompt="hi", session_id="sess-picked", config=cfg
    )

    assert sent.ok is True, sent.detail
    assert sent.data["session_id"] == "sess-picked"
    assert ("POST", "/api/v1/sessions") not in router.route_hits


def test_new_chat_per_task_does_not_auto_resume(tf_server):
    """REQ-65 on-mode: an explicit fresh-task agent still mints a new session."""
    host, port, router = tf_server
    settings_store.update_settings("trueforge", {"new_chat_per_task": True})
    router.routes = {
        ("GET", "/api/v1/sessions"): (
            200,
            {"sessions": [{"id": "sess-existing", "agent": "orchestrator", "updated_at": "2026-02-01T00:00:00Z"}]},
        ),
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-task"}}),
        **_turn_routes("sess-task", "fresh task"),
    }
    cfg = _cfg(host, port)

    sent = remotes_core.operate("trueforge", "send", prompt="one task", config=cfg)

    assert sent.ok is True, sent.detail
    assert sent.data["session_id"] == "sess-task"
    assert ("POST", "/api/v1/sessions") in router.route_hits

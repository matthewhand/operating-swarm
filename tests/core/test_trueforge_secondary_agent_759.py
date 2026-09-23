"""#759 — a secondary TrueForge agent referenced by ULID id must be startable.

``_trueforge_create_session`` used to put the raw key into
``{"agent": {"name": ...}}``. When the key is an agent *id* (ULID), TrueForge
rejects the create with HTTP 400: the create schema wants the agent's name
(or agent.id), not a ULID pretending to be a name.

Contract: id-shaped keys are resolved to the agent's display name via the
agent list (``GET /api/v1/agents``) before the create; name-shaped keys
(including plain ids like ``agent-1`` pinned by #425) pass through unchanged
so the #425 recovery keeps its exact wire behavior.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from swarm.core import remotes as remotes_core
from swarm.core.remotes import RemoteSpec, _trueforge_agent_id_shape, _trueforge_create_session

ULID = "01m2gs2kw8tqk21a81s1zaema5"


class _TrueForgeRouter(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], Any] = {}
    route_hits: dict[tuple[str, str], int] = {}
    received_bodies: list[tuple[str, str, Any]] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = None
        if content_len > 0:
            raw_body = self.rfile.read(content_len).decode("utf-8")
            try:
                body = json.loads(raw_body)
            except Exception:
                body = raw_body
            self.received_bodies.append((method, path, body))
        entry = self.routes.get((method, path), (404, {"error": "no route"}))
        status, response_body = entry
        payload = json.dumps(response_body).encode("utf-8")
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


@pytest.fixture
def tf_server():
    _TrueForgeRouter.routes = {}
    _TrueForgeRouter.route_hits = {}
    _TrueForgeRouter.received_bodies = []
    server = HTTPServer(("127.0.0.1", 0), _TrueForgeRouter)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield host, port, _TrueForgeRouter
    server.shutdown()
    _TrueForgeRouter.routes = {}
    _TrueForgeRouter.route_hits = {}
    _TrueForgeRouter.received_bodies = []


def test_ulid_is_detected_as_an_agent_id():
    assert _trueforge_agent_id_shape(ULID) is True
    assert _trueforge_agent_id_shape("Garruk") is False
    assert _trueforge_agent_id_shape("agent-1") is False
    assert _trueforge_agent_id_shape("") is False


def test_create_session_resolves_ulid_to_the_agent_name(tf_server, monkeypatch):
    """The #759 wire contract: id in, name out, create succeeds."""
    host, port, router = tf_server
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    router.routes = {
        ("GET", "/api/v1/agents"): (
            200,
            {
                "data": [
                    {"id": ULID, "name": "Garruk"},
                    {"id": "agent-2", "name": "orchestrator"},
                ]
            },
        ),
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-garruk"}}),
    }
    spec = RemoteSpec(
        id="trueforge",
        title="TrueForge",
        host_label="trueforge",
        base_url=f"http://{host}:{port}",
    )

    sess_id, err = _trueforge_create_session(spec, f"http://{host}:{port}", ULID, 5.0)

    assert err is None
    assert sess_id == "sess-garruk"
    sess_req = next(b for m, p, b in router.received_bodies if p == "/api/v1/sessions")
    assert sess_req["agent"]["name"] == "Garruk"


def test_create_session_falls_back_to_agent_id_field_when_lookup_fails(
    tf_server, monkeypatch
):
    """No agents endpoint / no match → send agent.id (schema-honest); the 400
    then surfaces as the normal unreachable detail."""
    host, port, router = tf_server
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    router.routes = {
        ("GET", "/api/v1/agents"): (404, {"error": "nope"}),
        ("POST", "/api/v1/sessions"): (400, {"error": "bad agent"}),
    }
    spec = RemoteSpec(
        id="trueforge",
        title="TrueForge",
        host_label="trueforge",
        base_url=f"http://{host}:{port}",
    )

    sess_id, err = _trueforge_create_session(spec, f"http://{host}:{port}", ULID, 5.0)

    assert sess_id == ""
    assert err is not None
    sess_req = next(b for m, p, b in router.received_bodies if p == "/api/v1/sessions")
    assert "id" in sess_req["agent"]
    assert sess_req["agent"]["name"] == ULID  # echo the key for server logs


def test_create_session_keeps_plain_names_untouched(tf_server, monkeypatch):
    host, port, router = tf_server
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    router.routes = {
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-ok"}}),
    }
    spec = RemoteSpec(
        id="trueforge",
        title="TrueForge",
        host_label="trueforge",
        base_url=f"http://{host}:{port}",
    )

    sess_id, err = _trueforge_create_session(spec, f"http://{host}:{port}", "Garruk", 5.0)

    assert err is None
    assert sess_id == "sess-ok"
    sess_req = next(b for m, p, b in router.received_bodies if p == "/api/v1/sessions")
    assert sess_req == {"agent": {"name": "Garruk"}, "metadata": {}}
    assert ("GET", "/api/v1/agents") not in router.route_hits


def test_end_to_end_send_to_secondary_agent_by_ulid(tf_server, monkeypatch):
    """#759 acceptance: send to a listed secondary agent (ULID resume key)
    creates the session via its display name and completes the turn."""
    host, port, router = tf_server
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    router.routes = {
        ("POST", f"/api/v1/sessions/{ULID}/turns"): (
            404,
            {"error": "Session not found"},
        ),
        ("GET", "/api/v1/agents"): (
            200,
            {"data": [{"id": ULID, "name": "Garruk"}]},
        ),
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-garruk-2"}}),
        ("POST", "/api/v1/sessions/sess-garruk-2/turns"): (
            202,
            {"data": {"id": "turn-9", "state": "running"}},
        ),
        ("GET", "/api/v1/sessions/sess-garruk-2/turns/turn-9"): (
            200,
            {"data": {"id": "turn-9", "state": "completed"}},
        ),
        ("GET", "/api/v1/sessions/sess-garruk-2/turns/turn-9/events"): (
            200,
            {"data": [{"type": "model.message", "content": "Garruk online."}]},
        ),
    }
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}

    sent = remotes_core.operate(
        "trueforge", "send", prompt="hi", session_id=ULID, config=cfg
    )

    assert sent.ok is True, sent.detail
    assert sent.detail == "Garruk online."
    assert sent.data["session_id"] == "sess-garruk-2"
    sess_req = next(b for m, p, b in router.received_bodies if p == "/api/v1/sessions")
    assert sess_req["agent"]["name"] == "Garruk"

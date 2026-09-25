"""REQ-850 / ADR-011: TrueForge Remote harness implementation.

Tests healthz, list agents, send job (sessions/turns/events poll), auth,
and blueprint as_tool specialist.
Hermetic tests — no live LAN, loopback defaults only.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from swarm.blueprints.remote_harness.blueprint_remote_harness import RemoteHarnessBlueprint
from swarm.core import remotes as remotes_core
from swarm.core.agent_kind import classify_agent_kind
from swarm.core.agent_types import agent_type_for_kind
from swarm.core.remote_harness import (
    BoundRemoteHarness,
    RemoteCapabilities,
    RemoteHarness,
    capabilities_for,
    get_harness,
    is_remote_impl_id,
    normalize_impl_id,
    user_facing_kind,
)


class _TrueForgeRouter(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], Any] = {}
    route_hits: dict[tuple[str, str], int] = {}
    received_headers: list[dict[str, str]] = []
    received_bodies: list[tuple[str, str, Any]] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        self.received_headers.append(dict(self.headers))
        content_len = int(self.headers.get("Content-Length", 0))
        body = None
        if content_len > 0:
            raw_body = self.rfile.read(content_len).decode("utf-8")
            try:
                body = json.loads(raw_body)
            except Exception:
                body = raw_body
            self.received_bodies.append((method, path, body))

        key = (method, path)
        entry = self.routes.get(key, (404, {"error": f"no route for {method} {path}"}))
        if isinstance(entry, list):
            idx = self.route_hits.get(key, 0)
            status, response_body = entry[min(idx, len(entry) - 1)]
            self.route_hits[key] = idx + 1
        else:
            status, response_body = entry
        payload = json.dumps(response_body).encode("utf-8") if not isinstance(response_body, str) else response_body.encode("utf-8")
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
    _TrueForgeRouter.received_headers = []
    _TrueForgeRouter.received_bodies = []
    server = HTTPServer(("127.0.0.1", 0), _TrueForgeRouter)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield host, port, _TrueForgeRouter
    server.shutdown()
    _TrueForgeRouter.routes = {}
    _TrueForgeRouter.route_hits = {}
    _TrueForgeRouter.received_headers = []
    _TrueForgeRouter.received_bodies = []


def test_trueforge_catalog_and_capabilities():
    """ADR-011: trueforge is a Remote implementation, not a new kind."""
    assert "trueforge" in remotes_core.REMOTE_IDS
    assert "trueforge" in remotes_core.REMOTE_KIND_IDS
    assert user_facing_kind("trueforge") == "remote"
    assert agent_type_for_kind("trueforge") == "remote"
    assert classify_agent_kind("trueforge") == "remote"
    assert classify_agent_kind("true_forge") == "remote"
    assert is_remote_impl_id("trueforge")
    assert normalize_impl_id("true_forge") == "trueforge"
    assert normalize_impl_id("true-forge") == "trueforge"

    caps = capabilities_for("trueforge")
    assert isinstance(caps, RemoteCapabilities)
    assert caps.list is True
    assert caps.send is True
    assert caps.health is True
    assert caps.operate is False
    assert caps.interrogate is False
    assert caps.routines is True
    assert caps.transport == "http"

    assert capabilities_for("hermes").routines is False
    assert capabilities_for("omb").routines is False
    assert capabilities_for("rakazo").routines is False
    assert capabilities_for("herdr").routines is False
    assert capabilities_for("swarm").routines is False

    harness = get_harness("trueforge")
    assert harness is not None
    assert isinstance(harness, RemoteHarness)
    assert isinstance(harness, BoundRemoteHarness)
    assert harness.impl_id == "trueforge"
    assert harness.label == "TrueForge"
    assert harness.capabilities.routines is True


def test_trueforge_default_spec_is_loopback():
    """Zero sensitive host data: default base_url must be loopback :8791."""
    spec = remotes_core.default_spec("trueforge")
    assert spec.id == "trueforge"
    assert spec.base_url == "http://127.0.0.1:8791"
    assert "10.0.0." not in spec.base_url
    assert "192.168." not in spec.base_url
    assert spec.health_path == "/healthz"
    assert spec.version_path == "/healthz"
    assert spec.api_key == "${TRUEFORGE_API_KEY}"

    pub = spec.public_dict()
    assert pub["kind"] == "trueforge"
    assert pub["impl"] == "trueforge"
    assert pub["user_kind"] == "remote"
    assert pub["label"] == "TrueForge"
    assert pub["capabilities"]["routines"] is True
    assert pub["member"]["talk"] == "consult_trueforge"
    assert pub["member"]["via"] == "as_tool"


def test_trueforge_not_configured_errors_honestly():
    """Unconfigured TrueForge gives clear, actionable 'not added' guidance."""
    empty_cfg = {"llm": {}, "remotes": {}}
    assert not remotes_core.is_configured("trueforge", empty_cfg)

    health = remotes_core.check_health("trueforge", config=empty_cfg, timeout=0.2)
    assert health.ok is False
    assert health.state == "UNKNOWN"
    assert remotes_core.NOT_ADDED_MARKER in health.detail
    assert "swarm-cli remotes set trueforge" in health.detail

    listed = remotes_core.operate("trueforge", "list", config=empty_cfg)
    assert listed.ok is False
    assert remotes_core.NOT_ADDED_MARKER in listed.detail

    sent = remotes_core.operate("trueforge", "send", prompt="ping", config=empty_cfg)
    assert sent.ok is False
    assert remotes_core.NOT_ADDED_MARKER in sent.detail


def test_trueforge_health_probe_success(tf_server, monkeypatch):
    """GET /healthz returning 200 -> UP with version extracted."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/healthz"): (200, {"status": "ok", "version": "0.2.0-rc.10"}),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
                "api_key": "${TRUEFORGE_API_KEY}",
            }
        }
    }
    health = remotes_core.check_health("trueforge", config=cfg, timeout=2.0)
    assert health.ok is True
    assert health.state == "UP"
    assert health.http_status == 200
    assert health.version == {"version": "0.2.0-rc.10"}
    assert "/healthz" in health.url


def test_trueforge_health_probe_auth_required(tf_server, monkeypatch):
    """GET /healthz returning 401 counts as UP (auth required — endpoint is alive)."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/healthz"): (401, {"error": "unauthorized"}),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }
    health = remotes_core.check_health("trueforge", config=cfg, timeout=2.0)
    assert health.ok is True
    assert health.state == "UP"
    assert health.http_status == 401
    assert "auth required" in health.detail


def test_trueforge_health_probe_degraded_on_500(tf_server, monkeypatch):
    """GET /healthz returning 500 -> DEGRADED."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/healthz"): (500, {"error": "internal error"}),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }
    health = remotes_core.check_health("trueforge", config=cfg, timeout=2.0)
    assert health.ok is False
    assert health.state == "DEGRADED"
    assert health.http_status == 500


def test_trueforge_list_agents(tf_server, monkeypatch):
    """GET /api/v1/agents -> lists available agents."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/agents"): (
            200,
            {
                "data": [
                    {"id": "agent-1", "name": "orchestrator"},
                    {"id": "agent-2", "name": "code_specialist"},
                ]
            },
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }
    listed = remotes_core.operate("trueforge", "list", config=cfg)
    assert listed.ok is True
    assert listed.op == "list"
    assert "2 agent(s)" in listed.detail
    assert listed.http_status == 200
    assert len(listed.data["data"]) == 2


# --- #425: a list row is an agent id, not a session to resume -------------------


def test_trueforge_list_documents_the_resume_key(tf_server, monkeypatch):
    """#425: the list must name which field send resumes on (session, not agent)."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/agents"): (
            200,
            {"data": [{"id": "agent-1", "name": "orchestrator"}]},
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}

    listed = remotes_core.operate("trueforge", "list", config=cfg)

    assert listed.ok is True
    assert listed.data["rows_are"] == "agents"
    assert listed.data["resume_key"] == "session_id"
    assert "agent" in listed.detail.lower() and "session" in listed.detail.lower()


def test_trueforge_send_recovers_when_the_key_is_an_agent_id(tf_server, monkeypatch):
    """#425: the SPA forwards a list row id as ``session_id``, and the rows are
    agents, so ``404 Session not found`` must recover by starting a session for
    that agent instead of failing the send."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions/agent-1/turns"): (
            404,
            {"error": "Session not found"},
        ),
        ("POST", "/api/v1/sessions"): (201, {"data": {"id": "sess-new"}}),
        ("POST", "/api/v1/sessions/sess-new/turns"): (
            202,
            {"data": {"id": "turn-1", "state": "running"}},
        ),
        ("GET", "/api/v1/sessions/sess-new/turns/turn-1"): (
            200,
            {"data": {"id": "turn-1", "state": "completed"}},
        ),
        ("GET", "/api/v1/sessions/sess-new/turns/turn-1/events"): (
            200,
            {"data": [{"type": "model.message", "content": "Recovered."}]},
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}

    sent = remotes_core.operate(
        "trueforge", "send", prompt="hi", session_id="agent-1", config=cfg
    )

    assert sent.ok is True, sent.detail
    assert sent.detail == "Recovered."
    assert sent.data["session_id"] == "sess-new"
    assert sent.data["session_created_for"] == "agent-1"
    sess_req = next(b for m, p, b in router.received_bodies if p == "/api/v1/sessions")
    assert sess_req["agent"]["name"] == "agent-1"


def test_trueforge_send_says_no_session_to_resume_instead_of_a_raw_404(
    tf_server, monkeypatch
):
    """#425: when no session can be started either, answer in words."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions/agent-1/turns"): (
            404,
            {"error": "Session not found"},
        ),
        ("POST", "/api/v1/sessions"): (401, {"error": "unauthorized"}),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}

    sent = remotes_core.operate(
        "trueforge", "send", prompt="hi", session_id="agent-1", config=cfg
    )

    assert sent.ok is False
    assert sent.gap == "trueforge_no_session"
    assert "404" not in sent.detail
    assert "Session not found" not in sent.detail
    assert "agent-1" in sent.detail


def test_trueforge_send_uses_a_real_session_id_as_is(tf_server, monkeypatch):
    """#425 regression: a genuine session id is resumed, not replaced."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions/sess-real/turns"): (
            202,
            {"data": {"id": "turn-real", "state": "running"}},
        ),
        ("GET", "/api/v1/sessions/sess-real/turns/turn-real"): (
            200,
            {"data": {"id": "turn-real", "state": "completed"}},
        ),
        ("GET", "/api/v1/sessions/sess-real/turns/turn-real/events"): (
            200,
            {"data": [{"type": "model.message", "content": "Resumed."}]},
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}

    sent = remotes_core.operate(
        "trueforge", "send", prompt="hi", session_id="sess-real", config=cfg
    )

    assert sent.ok is True, sent.detail
    assert sent.data["session_id"] == "sess-real"
    assert "session_created_for" not in sent.data
    assert ("POST", "/api/v1/sessions") not in router.route_hits


def test_trueforge_send_turn_and_poll_events(tf_server, monkeypatch):
    """Send: POST /sessions -> POST /turns -> poll /turns/{id} -> GET /events."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions"): (
            200,
            {"data": {"id": "sess-tf-42"}},
        ),
        ("POST", "/api/v1/sessions/sess-tf-42/turns"): (
            200,
            {"data": {"id": "turn-tf-101", "state": "RUNNING"}},
        ),
        ("GET", "/api/v1/sessions/sess-tf-42/turns/turn-tf-101"): (
            200,
            {"data": {"id": "turn-tf-101", "state": "done"}},
        ),
        ("GET", "/api/v1/sessions/sess-tf-42/turns/turn-tf-101/events"): (
            200,
            {
                "data": [
                    {"type": "user.message", "content": "What is the status?"},
                    {"type": "model.message", "content": "All systems operational."},
                ]
            },
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }
    sent = remotes_core.operate("trueforge", "send", prompt="What is the status?", config=cfg)
    assert sent.ok is True
    assert sent.op == "send"
    assert sent.detail == "All systems operational."
    assert sent.data["session_id"] == "sess-tf-42"
    assert sent.data["turn_id"] == "turn-tf-101"

    # Check request payloads
    sess_req = next(b for m, p, b in router.received_bodies if p == "/api/v1/sessions")
    assert sess_req["agent"]["name"] == "orchestrator"

    turn_req = next(b for m, p, b in router.received_bodies if "/turns" in p and m == "POST")
    assert turn_req["input"][0]["type"] == "user.message"
    assert turn_req["input"][0]["content"] == "What is the status?"
    assert turn_req["stream"] is False


def test_trueforge_send_with_custom_target_and_auth(tf_server, monkeypatch):
    """Send with specific target agent and verifies Authorization header."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions"): (
            201,
            {"data": {"id": "sess-target-99"}},
        ),
        ("POST", "/api/v1/sessions/sess-target-99/turns"): (
            201,
            {"data": {"id": "turn-target-202", "state": "RUNNING"}},
        ),
        ("GET", "/api/v1/sessions/sess-target-99/turns/turn-target-202"): (
            200,
            {"data": {"id": "turn-target-202", "state": "done"}},
        ),
        ("GET", "/api/v1/sessions/sess-target-99/turns/turn-target-202/events"): (
            200,
            {
                "data": [
                    {"type": "model.message", "content": "Code generated."},
                ]
            },
        ),
    }
    monkeypatch.setenv("TRUEFORGE_API_KEY", "secret-bearer-token")
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
                "api_key": "${TRUEFORGE_API_KEY}",
            }
        }
    }
    sent = remotes_core.operate(
        "trueforge",
        "send",
        prompt="Write a sort function",
        target="coder",
        config=cfg,
    )
    assert sent.ok is True
    assert sent.detail == "Code generated."

    sess_req = next(b for m, p, b in router.received_bodies if p == "/api/v1/sessions")
    assert sess_req["agent"]["name"] == "coder"

    # Verify Bearer token was sent in headers
    assert any(h.get("authorization") == "Bearer secret-bearer-token" or h.get("Authorization") == "Bearer secret-bearer-token" for h in router.received_headers)


def test_trueforge_send_turn_error_state(tf_server, monkeypatch):
    """Turn ending in error state reports honest failure without crashing."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions"): (
            200,
            {"data": {"id": "sess-err-1"}},
        ),
        ("POST", "/api/v1/sessions/sess-err-1/turns"): (
            200,
            {"data": {"id": "turn-err-1", "state": "RUNNING"}},
        ),
        ("GET", "/api/v1/sessions/sess-err-1/turns/turn-err-1"): (
            200,
            {"data": {"id": "turn-err-1", "state": "error", "error": "Model quota exhausted"}},
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }
    sent = remotes_core.operate("trueforge", "send", prompt="test error", config=cfg)
    assert sent.ok is False
    assert "Model quota exhausted" in sent.detail


def test_trueforge_send_turn_crashed_state_extracts_nested_detail(tf_server, monkeypatch):
    """Turn ending in 'crashed' state terminates immediately and extracts nested detail."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions"): (
            200,
            {"data": {"id": "sess-crash-1"}},
        ),
        ("POST", "/api/v1/sessions/sess-crash-1/turns"): (
            200,
            {"data": {"id": "turn-crash-1", "state": "RUNNING"}},
        ),
        ("GET", "/api/v1/sessions/sess-crash-1/turns/turn-crash-1"): (
            200,
            {"data": {"id": "turn-crash-1", "state": {"status": "crashed", "detail": "Container killed by OOM"}}},
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }
    sent = remotes_core.operate("trueforge", "send", prompt="test crash", config=cfg)
    assert sent.ok is False
    assert "Container killed by OOM" in sent.detail


def test_trueforge_turn_state_parses_dict_and_string():
    """TrueForge returns state as {"status": ...}; str(dict) must not be used."""
    assert remotes_core._trueforge_turn_state({"state": {"status": "running"}}) == "running"
    assert remotes_core._trueforge_turn_state({"state": {"status": "completed"}}) == "completed"
    assert remotes_core._trueforge_turn_state({"state": {"state": "finished"}}) == "finished"
    assert remotes_core._trueforge_turn_state({"state": "done"}) == "done"
    assert remotes_core._trueforge_turn_state({"status": "success"}) == "success"
    assert remotes_core._trueforge_turn_state({"state": {"status": "RUNNING"}}) == "running"
    # The bug: stringifying the dict never matches done/completed.
    raw = {"state": {"status": "completed"}}
    assert str(raw["state"]).strip().lower() not in remotes_core._TRUEFORGE_DONE_STATES
    assert remotes_core._trueforge_turn_state(raw) in remotes_core._TRUEFORGE_DONE_STATES


def test_trueforge_send_timeout_resolution(monkeypatch):
    """Send uses 180s (or env/spec) instead of the 8s operate default."""
    monkeypatch.delenv("SWARM_TRUEFORGE_TIMEOUT", raising=False)
    assert remotes_core._trueforge_send_timeout_s(None) == 180.0
    assert remotes_core._trueforge_send_timeout_s(remotes_core._OPERATE_TIMEOUT_S) == 180.0
    assert remotes_core._trueforge_send_timeout_s(12.5) == 12.5
    monkeypatch.setenv("SWARM_TRUEFORGE_TIMEOUT", "90")
    assert remotes_core._trueforge_send_timeout_s(None) == 90.0
    assert remotes_core._trueforge_send_timeout_s(remotes_core._OPERATE_TIMEOUT_S) == 90.0
    assert remotes_core._trueforge_send_timeout_s(12.5) == 12.5
    monkeypatch.delenv("SWARM_TRUEFORGE_TIMEOUT", raising=False)
    spec = remotes_core.default_spec("trueforge")
    spec.timeout = 45.0
    assert remotes_core._trueforge_send_timeout_s(spec=spec) == 45.0
    assert remotes_core._trueforge_send_timeout_s(remotes_core._OPERATE_TIMEOUT_S, spec) == 45.0


def test_trueforge_send_dict_state_running_then_completed(tf_server, monkeypatch):
    """operate(send) accepts state {status: running} -> {status: completed}."""
    host, port, router = tf_server
    turn_path = "/api/v1/sessions/sess-dict-1/turns/turn-dict-1"
    router.routes = {
        ("POST", "/api/v1/sessions"): (
            200,
            {"data": {"id": "sess-dict-1"}},
        ),
        ("POST", "/api/v1/sessions/sess-dict-1/turns"): (
            200,
            {"data": {"id": "turn-dict-1", "state": {"status": "running"}}},
        ),
        ("GET", turn_path): [
            (200, {"data": {"id": "turn-dict-1", "state": {"status": "running"}}}),
            (200, {"data": {"id": "turn-dict-1", "state": {"status": "completed"}}}),
        ],
        ("GET", f"{turn_path}/events"): (
            200,
            {
                "data": [
                    {"type": "model.message", "content": "Dict-state turn finished."},
                ]
            },
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    monkeypatch.delenv("SWARM_TRUEFORGE_TIMEOUT", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }
    sent = remotes_core.operate("trueforge", "send", prompt="hi", config=cfg)
    assert sent.ok is True
    assert sent.detail == "Dict-state turn finished."
    assert sent.data["session_id"] == "sess-dict-1"
    assert sent.data["turn_id"] == "turn-dict-1"
    assert router.route_hits[("GET", turn_path)] >= 2


def test_trueforge_operate_send_uses_long_timeout(tf_server, monkeypatch):
    """Shipped operate() send path remaps the 8s default to the TrueForge budget."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions"): (200, {"data": {"id": "sess-to"}}),
        ("POST", "/api/v1/sessions/sess-to/turns"): (
            200,
            {"data": {"id": "turn-to", "state": {"status": "running"}}},
        ),
        ("GET", "/api/v1/sessions/sess-to/turns/turn-to"): (
            200,
            {"data": {"id": "turn-to", "state": {"status": "completed"}}},
        ),
        ("GET", "/api/v1/sessions/sess-to/turns/turn-to/events"): (
            200,
            {"data": [{"type": "model.message", "content": "ok"}]},
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    monkeypatch.delenv("SWARM_TRUEFORGE_TIMEOUT", raising=False)
    seen: dict[str, float] = {}
    orig = remotes_core._trueforge_send

    def _spy(spec, prompt, target="", timeout=None, **kwargs):
        seen["arg"] = timeout
        seen["resolved"] = remotes_core._trueforge_send_timeout_s(timeout, spec)
        return orig(spec, prompt, target, timeout, **kwargs)

    monkeypatch.setattr(remotes_core, "_trueforge_send", _spy)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}
    sent = remotes_core.operate("trueforge", "send", prompt="hi", config=cfg)
    assert sent.ok is True
    assert seen["arg"] == remotes_core._OPERATE_SEND_TIMEOUT_S
    assert seen["resolved"] == 180.0


def test_trueforge_send_dict_error_state(tf_server, monkeypatch):
    """Dict error status is reported, not polled until timeout."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions"): (200, {"data": {"id": "sess-derr"}}),
        ("POST", "/api/v1/sessions/sess-derr/turns"): (
            200,
            {"data": {"id": "turn-derr", "state": {"status": "running"}}},
        ),
        ("GET", "/api/v1/sessions/sess-derr/turns/turn-derr"): (
            200,
            {
                "data": {
                    "id": "turn-derr",
                    "state": {"status": "error"},
                    "error": "quota exhausted",
                }
            },
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}
    sent = remotes_core.operate("trueforge", "send", prompt="fail", config=cfg)
    assert sent.ok is False
    assert "quota exhausted" in sent.detail


def test_trueforge_send_honors_explicit_short_timeout(tf_server, monkeypatch):
    """Explicit send timeout is kept; dict running state is what the timeout reports."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions"): (200, {"data": {"id": "sess-short"}}),
        ("POST", "/api/v1/sessions/sess-short/turns"): (
            200,
            {"data": {"id": "turn-short", "state": {"status": "running"}}},
        ),
        ("GET", "/api/v1/sessions/sess-short/turns/turn-short"): (
            200,
            {"data": {"id": "turn-short", "state": {"status": "running"}}},
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}
    sent = remotes_core.operate(
        "trueforge", "send", prompt="hang", config=cfg, timeout=0.4
    )
    assert sent.ok is False
    assert "timed out after 0.4s" in sent.detail
    assert "running" in sent.detail
    assert "{'status'" not in sent.detail


def test_trueforge_list_keeps_fast_timeout(tf_server, monkeypatch):
    """Health/list probes stay on the short operate timeout."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/agents"): (200, {"data": [{"name": "orchestrator"}]}),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    seen: dict[str, float] = {}
    orig = remotes_core._trueforge_list

    def _spy(spec, timeout):
        seen["timeout"] = timeout
        return orig(spec, timeout)

    monkeypatch.setattr(remotes_core, "_trueforge_list", _spy)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}
    listed = remotes_core.operate("trueforge", "list", config=cfg)
    assert listed.ok is True
    assert seen["timeout"] == remotes_core._OPERATE_TIMEOUT_S


def test_trueforge_config_timeout_loaded_on_spec(monkeypatch):
    monkeypatch.delenv("SWARM_TRUEFORGE_TIMEOUT", raising=False)
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": "http://127.0.0.1:8791",
                "timeout": 75,
            }
        }
    }
    spec = remotes_core.load_remote("trueforge", cfg)
    assert spec.timeout == 75.0
    assert remotes_core._trueforge_send_timeout_s(spec=spec) == 75.0


def test_trueforge_blueprint_grammar_and_specialist(tf_server, monkeypatch):
    """RemoteHarnessBlueprint includes TrueForge specialist and deterministic grammar."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/healthz"): (200, {"status": "ok", "version": "0.2.0"}),
        ("GET", "/api/v1/agents"): (200, {"data": [{"name": "orchestrator"}]}),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "agent_team": {"members": ["hermes", "omb", "rakazo", "trueforge"]},
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        },
    }
    bp = RemoteHarnessBlueprint(config=cfg)
    agents = bp._build_agents()
    if agents:
        assert "trueforge" in agents
        assert hasattr(agents["trueforge"], "as_tool")

    # Deterministic parse
    op, name, prompt, target = bp._parse([{"role": "user", "content": "health trueforge"}])
    assert op == "health"
    assert name == "trueforge"

    op, name, prompt, target = bp._parse([{"role": "user", "content": "list trueforge"}])
    assert op == "list"
    assert name == "trueforge"

    op, name, prompt, target = bp._parse([{"role": "user", "content": "send trueforge hello world"}])
    assert op == "send"
    assert name == "trueforge"
    assert prompt == "hello world"


def test_trueforge_routines_success(tf_server, monkeypatch):
    """TrueForge schedules and runs endpoint integration (REQ-852)."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/schedules"): (
            200,
            {
                "data": [
                    {
                        "id": "sched-1",
                        "agent_name": "daily-brief",
                        "name": "Daily Briefing",
                        "manifest": {
                            "task": "Summarize top headlines and emails",
                            "cron": "0 9 * * 1-5",
                            "timezone": "America/New_York",
                            "status": "active",
                        },
                        "created_at": "2026-09-10T12:00:00Z",
                    },
                    {
                        "id": "sched-2",
                        "agent_name": "health-check",
                        "name": "Hourly Ping",
                        "manifest": {
                            "task": "Ping services",
                            "cron": "0 * * * *",
                            "timezone": "UTC",
                            "status": "paused",
                        },
                        "created_at": "2026-09-11T12:00:00Z",
                    },
                ]
            },
        ),
        ("GET", "/api/v1/schedules/sched-1/runs"): (
            200,
            {
                "data": [
                    {
                        "id": "run-101",
                        "name": "daily-briefing-run-101",
                        "scheduled_for": "2026-09-15T09:00:00Z",
                        "status": "scheduled",
                    }
                ]
            },
        ),
        ("GET", "/api/v1/schedules/sched-2/runs"): (
            200,
            {
                "data": [
                    {
                        "id": "run-201",
                        "name": "hourly-ping-run-201",
                        "scheduled_for": "2026-09-14T20:00:00Z",
                        "status": "triggered",
                    }
                ]
            },
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }

    # Test through remotes_core.operate
    res = remotes_core.operate("trueforge", "routines", config=cfg)
    assert res.ok is True
    assert res.op == "routines"
    assert res.remote == "trueforge"
    assert "2 routine(s)" in res.detail
    routines = res.data["routines"]
    assert len(routines) == 2

    r1 = routines[0]
    assert r1["id"] == "sched-1"
    assert r1["name"] == "Daily Briefing"
    assert r1["agent"] == "daily-brief"
    assert r1["cron"] == "0 9 * * 1-5"
    assert r1["timezone"] == "America/New_York"
    assert r1["task"] == "Summarize top headlines and emails"
    assert r1["status"] == "active"
    assert r1["last_run"] == {
        "id": "run-101",
        "name": "daily-briefing-run-101",
        "scheduled_for": "2026-09-15T09:00:00Z",
        "status": "scheduled",
    }

    r2 = routines[1]
    assert r2["id"] == "sched-2"
    assert r2["name"] == "Hourly Ping"
    assert r2["agent"] == "health-check"
    assert r2["cron"] == "0 * * * *"
    assert r2["timezone"] == "UTC"
    assert r2["status"] == "paused"
    assert r2["last_run"] == {
        "id": "run-201",
        "name": "hourly-ping-run-201",
        "scheduled_for": "2026-09-14T20:00:00Z",
        "status": "triggered",
    }

    # Also test via RemoteHarness protocol
    harness = get_harness("trueforge")
    spec = remotes_core.load_remote("trueforge", cfg)
    h_res = harness.routines(spec, timeout=5.0)
    assert h_res.ok is True
    assert len(h_res.data["routines"]) == 2


def test_trueforge_routines_empty(tf_server, monkeypatch):
    """TrueForge schedules returns empty list when no routines exist."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/schedules"): (200, {"data": []}),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }
    res = remotes_core.operate("trueforge", "routines", config=cfg)
    assert res.ok is True
    assert res.data["routines"] == []
    assert "0 routine(s)" in res.detail


def test_trueforge_routines_auth_error(tf_server, monkeypatch):
    """TrueForge schedules endpoint surfaces auth required honestly."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/schedules"): (401, {"error": "Unauthorized"}),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
            }
        }
    }
    res = remotes_core.operate("trueforge", "routines", config=cfg)
    assert res.ok is False
    assert "requires auth" in res.detail


def test_other_remotes_routines_unsupported():
    """Harnesses without routines capability return unsupported result."""
    cfg = {
        "remotes": {
            "hermes": {"base_url": "http://127.0.0.1:9"},
            "omb": {"base_url": "http://127.0.0.1:9"},
            "rakazo": {"base_url": "http://127.0.0.1:9"},
            "swarm": {"base_url": "http://127.0.0.1:9"},
            "herdr": {"base_url": "http://127.0.0.1:9"},
            "letta": {"base_url": "http://127.0.0.1:9"},
        }
    }
    for rid in ("hermes", "omb", "rakazo", "swarm", "herdr", "letta"):
        res = remotes_core.operate(rid, "routines", config=cfg)
        assert res.ok is False
        assert "does not support routines" in res.detail
        assert res.data["routines"] == []


def test_localhost_base_url_prefers_ipv4(monkeypatch):
    monkeypatch.setenv("SWARM_REWRITE_LOOPBACK", "0")
    spec = remotes_core.load_remote(
        "trueforge",
        config={"remotes": {"trueforge": {"base_url": "http://localhost:8791"}}},
    )
    assert spec.base_url == "http://127.0.0.1:8791"


def test_container_rewrites_loopback_trueforge_not_listen_port(monkeypatch):
    monkeypatch.setenv("SWARM_REWRITE_LOOPBACK", "1")
    monkeypatch.setenv("SWARM_HOST_GATEWAY", "host.docker.internal")
    monkeypatch.setenv("PORT", "8000")
    spec = remotes_core.load_remote(
        "trueforge",
        config={"remotes": {"trueforge": {"base_url": "http://127.0.0.1:8791"}}},
    )
    assert spec.base_url == "http://host.docker.internal:8791"


def test_container_preserves_ui_url_loopback(monkeypatch):
    monkeypatch.setenv("SWARM_REWRITE_LOOPBACK", "1")
    monkeypatch.setenv("SWARM_HOST_GATEWAY", "host.docker.internal")
    monkeypatch.setenv("PORT", "8000")
    spec = remotes_core.load_remote(
        "trueforge",
        config={
            "remotes": {
                "trueforge": {
                    "base_url": "http://127.0.0.1:8791",
                    "ui_url": "http://127.0.0.1:8791",
                }
            }
        },
    )
    assert spec.base_url == "http://host.docker.internal:8791"
    assert spec.ui_url == "http://127.0.0.1:8791"

    all_remotes = remotes_core.load_all_remotes(
        config={
            "remotes": {
                "trueforge": {
                    "base_url": "http://127.0.0.1:8791",
                    "ui_url": "http://127.0.0.1:8791",
                }
            }
        }
    )
    assert all_remotes["trueforge"].ui_url == "http://127.0.0.1:8791"


def test_trueforge_send_refused_names_url(monkeypatch):
    from swarm.blueprints.remote_harness.blueprint_remote_harness import _render_operate

    monkeypatch.setenv("SWARM_REWRITE_LOOPBACK", "0")
    sent = remotes_core.operate(
        "trueforge",
        "send",
        prompt="hi",
        config={"remotes": {"trueforge": {"base_url": "http://127.0.0.1:9"}}},
    )
    assert sent.ok is False
    assert "127.0.0.1:9" in sent.detail
    assert "refused" in sent.detail.lower()
    out = _render_operate(sent)
    assert "trueforge send: FAIL" in out
    assert out.rstrip().endswith('""') is False


def test_normalize_base_url_ipv6_brackets(monkeypatch):
    monkeypatch.setenv("SWARM_REWRITE_LOOPBACK", "0")
    spec = remotes_core.load_remote(
        "trueforge",
        config={"remotes": {"trueforge": {"base_url": "http://[2001:db8::1]:8791"}}},
    )
    assert spec.base_url == "http://[2001:db8::1]:8791"


def test_normalize_base_url_keeps_basic_auth_userinfo(monkeypatch):
    """#463: bracketing an IPv6 host must not drop the ``user:pass@`` prefix.

    ``urlunparse`` joins ``netloc`` verbatim, so the separator has to be part
    of ``userinfo``; without it a credentialed base_url silently collapses to
    ``http://alice:s3cret2001:db8::5:8791`` and every request 404s.
    """
    monkeypatch.setenv("SWARM_REWRITE_LOOPBACK", "0")
    assert (
        remotes_core._normalize_base_url("http://alice:s3cret@[2001:db8::5]:8791/")
        == "http://alice:s3cret@[2001:db8::5]:8791"
    )
    assert (
        remotes_core._normalize_base_url("http://alice:s3cret@example.com:8791")
        == "http://alice:s3cret@example.com:8791"
    )


def test_hermes_send_refused_names_url(monkeypatch):
    monkeypatch.setenv("SWARM_REWRITE_LOOPBACK", "0")
    sent = remotes_core.operate(
        "hermes",
        "send",
        prompt="hi",
        config={"remotes": {"hermes": {"base_url": "http://127.0.0.1:9"}}},
    )
    assert sent.ok is False
    assert "127.0.0.1:9" in sent.detail
    assert "refused" in sent.detail.lower()



# ---------------------------------------------------------------------------
# REQ-916 / #515: reverse map — container-gateway alias → external host
# ---------------------------------------------------------------------------


def _gateway_reset(monkeypatch):
    """Isolate the reverse-map env surface for one test."""
    monkeypatch.setenv("SWARM_REWRITE_LOOPBACK", "0")
    monkeypatch.delenv("SWARM_HOST_GATEWAY_EXTERNAL", raising=False)
    monkeypatch.setattr(remotes_core, "_EXTERNAL_GATEWAY_WARNED", False)


def test_gateway_alias_rewrites_to_external_fqdn_keeping_port(monkeypatch):
    _gateway_reset(monkeypatch)
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "trueforge.example.test")
    assert (
        remotes_core._normalize_base_url("http://host.docker.internal:8791")
        == "http://trueforge.example.test:8791"
    )


def test_gateway_override_with_port_wins(monkeypatch):
    _gateway_reset(monkeypatch)
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "trueforge.example.test:8443")
    assert (
        remotes_core._normalize_base_url("http://host.docker.internal:8791")
        == "http://trueforge.example.test:8443"
    )


def test_gateway_alias_untouched_inside_container(monkeypatch):
    # In a container the alias IS the correct name — the forward mapping's own
    # output must not be undone by the reverse map.
    monkeypatch.setenv("SWARM_REWRITE_LOOPBACK", "1")
    monkeypatch.delenv("SWARM_HOST_GATEWAY_EXTERNAL", raising=False)
    monkeypatch.setattr(remotes_core, "_EXTERNAL_GATEWAY_WARNED", False)
    monkeypatch.setenv("SWARM_HOST_GATEWAY", "host.docker.internal")
    monkeypatch.setenv("PORT", "8000")
    assert (
        remotes_core._normalize_base_url("http://127.0.0.1:8791")
        == "http://host.docker.internal:8791"
    )


def test_gateway_alias_untouched_when_override_unset(monkeypatch):
    _gateway_reset(monkeypatch)
    assert (
        remotes_core._normalize_base_url("http://host.docker.internal:8791")
        == "http://host.docker.internal:8791"
    )


def test_all_gateway_aliases_rewrite(monkeypatch):
    _gateway_reset(monkeypatch)
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "box.example.test")
    for alias in (
        "host.docker.internal",
        "gateway.docker.internal",
        "host.containers.internal",
    ):
        assert remotes_core._normalize_base_url(
            f"http://{alias}:8791"
        ) == "http://box.example.test:8791", alias


def test_gateway_alias_rewrites_in_ui_url_too(monkeypatch):
    # The browser cannot resolve gateway aliases either — the loopback
    # asymmetry must NOT carry over to the reverse map.
    _gateway_reset(monkeypatch)
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "trueforge.example.test")
    assert (
        remotes_core._normalize_ui_url("http://host.docker.internal:8791/ui")
        == "http://trueforge.example.test:8791/ui"
    )


def test_gateway_normalization_is_idempotent(monkeypatch):
    _gateway_reset(monkeypatch)
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "trueforge.example.test")
    once = remotes_core._normalize_base_url("http://host.docker.internal:8791/ui#frag")
    twice = remotes_core._normalize_base_url(once)
    assert once == twice == "http://trueforge.example.test:8791/ui#frag"


def test_gateway_rewrite_preserves_userinfo_path_query(monkeypatch):
    _gateway_reset(monkeypatch)
    monkeypatch.setenv("SWARM_HOST_GATEWAY_EXTERNAL", "box.example.test")
    out = remotes_core._normalize_base_url(
        "http://user:pw@gateway.docker.internal:9000/a/b?x=1&y=2"
    )
    assert out == "http://user:pw@box.example.test:9000/a/b?x=1&y=2"


def test_unreachable_copy_names_gateway_override(monkeypatch):
    result = remotes_core.HttpResult(status=None, error="Connection refused", url="http://x:1")
    detail = remotes_core._unreachable_detail(result, "Chat")
    assert "SWARM_HOST_GATEWAY_EXTERNAL" in detail


def test_unreachable_copy_covers_dns_failure_722():
    """#722: 'Name or service not known' is the live failure a container hits
    when a spec's gateway alias does not resolve — the copy must name the fix,
    not echo a bare URLError."""
    result = remotes_core.HttpResult(
        status=None, error="<urlopen error [Errno -2] Name or service not known>", url="http://host.docker.internal:8791/api/v1/sessions"
    )
    detail = remotes_core._unreachable_detail(result, "TrueForge session create")
    assert "Name or service not known" not in detail
    assert "host.docker.internal" in detail
    assert "SWARM_HOST_GATEWAY" in detail


def test_trueforge_send_reply_is_parsed_not_dumped_as_json(tf_server, monkeypatch):
    """#686: a successful TrueForge send renders ONLY the human reply.

    The chat canvas must never show the transport payload (turn dict + every
    event). The reply comes from data.text/detail; the turn/events stay
    inspectable data, never message text.
    """
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions"): (200, {"data": {"id": "sess-tf-686"}}),
        ("POST", "/api/v1/sessions/sess-tf-686/turns"): (
            200,
            {"data": {"id": "turn-tf-686", "state": "RUNNING"}},
        ),
        ("GET", "/api/v1/sessions/sess-tf-686/turns/turn-tf-686"): (
            200,
            {"data": {"id": "turn-tf-686", "state": "done"}},
        ),
        ("GET", "/api/v1/sessions/sess-tf-686/turns/turn-tf-686/events"): (
            200,
            {
                "data": [
                    {"type": "user.message", "content": "hello"},
                    {
                        "type": "model.message",
                        "content": [{"type": "text", "text": "Clean human reply."}],
                    },
                ]
            },
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}
    sent = remotes_core.operate("trueforge", "send", prompt="hello", config=cfg)
    assert sent.ok is True
    assert sent.data["text"] == "Clean human reply."

    from swarm.blueprints.remote_harness.blueprint_remote_harness import _render_operate

    rendered = _render_operate(sent)
    assert rendered == "Clean human reply."
    # No transport JSON anywhere in the message text.
    assert "turn-tf-686" not in rendered
    assert '"events"' not in rendered
    assert "user.message" not in rendered


def test_trueforge_send_with_no_reply_text_never_renders_payload_json(tf_server, monkeypatch):
    """#686: even with an empty reply, the send render stays a sentence."""
    host, port, router = tf_server
    router.routes = {
        ("POST", "/api/v1/sessions"): (200, {"data": {"id": "sess-tf-687"}}),
        ("POST", "/api/v1/sessions/sess-tf-687/turns"): (
            200,
            {"data": {"id": "turn-tf-687", "state": "RUNNING"}},
        ),
        ("GET", "/api/v1/sessions/sess-tf-687/turns/turn-tf-687"): (
            200,
            {"data": {"id": "turn-tf-687", "state": "done"}},
        ),
        ("GET", "/api/v1/sessions/sess-tf-687/turns/turn-tf-687/events"): (
            200,
            {"data": [{"type": "tool.call", "content": "{}"}]},
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}
    sent = remotes_core.operate("trueforge", "send", prompt="hi", config=cfg)
    assert sent.ok is True

    from swarm.blueprints.remote_harness.blueprint_remote_harness import _render_operate

    rendered = _render_operate(sent)
    # No JSON, no payload keys — just the adapter's completion sentence.
    assert "{" not in rendered
    assert '"events"' not in rendered
    assert "user.message" not in rendered
    assert rendered == "TrueForge turn completed"


# --- #810: the session switcher needs real sessions, not agent names ----------


def test_trueforge_list_attaches_real_sessions(tf_server, monkeypatch):
    """#810: list keeps the agent rows AND attaches GET /api/v1/sessions
    under data.sessions so the navbar History picker resumes real threads
    instead of writing an agent name into ?session= (which 404s)."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/agents"): (
            200,
            {"data": [{"id": "agent-1", "name": "orchestrator"}]},
        ),
        ("GET", "/api/v1/sessions"): (
            200,
            {
                "data": [
                    {
                        "id": "sess-9",
                        "agent": {"type": "reference", "id": "a1", "name": "orchestrator"},
                        "metadata": {"title": "refactor the parser"},
                        "created_at": "2026-09-21T10:00:00Z",
                        "updated_at": "2026-09-22T08:30:00Z",
                    },
                    {"id": "sess-4", "agent": "coder", "created_at": "2026-09-20T09:00:00Z"},
                ]
            },
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}

    listed = remotes_core.operate("trueforge", "list", config=cfg)

    assert listed.ok is True
    assert listed.data["rows_are"] == "agents"
    sessions = listed.data["sessions"]
    assert isinstance(sessions, list) and len(sessions) == 2
    first = sessions[0]
    assert first["id"] == "sess-9"
    assert first["agent"] == "orchestrator"
    assert "refactor the parser" in str(first.get("title") or first.get("metadata"))
    assert first.get("created_at")
    # #1100: the API exposes updated_at — surface it so the picker can show
    # recent activity instead of an epoch-0 stamp.
    assert first.get("updated_at") == "2026-09-22T08:30:00Z"
    # #1099 sibling: a nested agent object (real API shape) must normalize to
    # its name, not str()-ed dict garbage.
    assert first.get("agent") == "orchestrator"


def test_trueforge_list_survives_a_sessions_endpoint_failure(tf_server, monkeypatch):
    """#810: a broken /api/v1/sessions must not fail the whole list — the
    agents payload still stands, sessions are honestly absent."""
    host, port, router = tf_server
    router.routes = {
        ("GET", "/api/v1/agents"): (
            200,
            {"data": [{"id": "agent-1", "name": "orchestrator"}]},
        ),
        ("GET", "/api/v1/sessions"): (500, {"error": "boom"}),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = {"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}}

    listed = remotes_core.operate("trueforge", "list", config=cfg)

    assert listed.ok is True
    assert len(listed.data["data"]) == 1
    assert listed.data.get("sessions") in (None, [])


# ---------------------------------------------------------------------------
# #1159 — no agent wired: fail fast with actionable copy; gateway 400s name
# the schema hint (agent: {name}).
# ---------------------------------------------------------------------------


def test_trueforge_send_without_agent_fails_fast_with_rebind_copy(tf_server, monkeypatch):
    """A trueforge seat that would use the remote's OWN name as agent refuses BEFORE the wire (#1159)."""
    host, port, router = tf_server
    hits = []

    def counting(method, url, **kwargs):
        hits.append(url)
        raise AssertionError("no HTTP call expected when no agent is wired")

    monkeypatch.setattr("swarm.core.remotes.http_json", counting)
    result = remotes_core.operate(
        "trueforge",
        "send",
        prompt="hi",
        target="trueforge",
        config={"remotes": {"trueforge": {"base_url": f"http://{host}:{port}"}}},
        timeout=2.0,
    )
    assert result.ok is False
    assert "no agent wired" in result.detail
    assert "Settings → Remotes" in result.detail
    assert hits == [], "must not hit the gateway without an agent"


def test_trueforge_session_create_400_names_the_schema_hint(tf_server):
    """Gateway 400 on session create surfaces the agent:{name} schema hint."""
    host, port, router = tf_server
    router.routes[("POST", "/api/v1/sessions")] = (
        400,
        {"error": "Invalid input", "detail": "at agent"},
    )
    from swarm.core import remotes as R
    from swarm.core.remote_impls import trueforge as tf

    spec = R.RemoteSpec(
        id="tf",
        title="TrueForge",
        host_label="trueforge",
        kind="trueforge",
        base_url=f"http://{host}:{port}",
    )
    sess_id, err = tf._trueforge_create_session(spec, f"http://{host}:{port}", "nope-agent", 2.0)
    assert sess_id == ""
    assert err is not None and err.ok is False
    assert "agent" in err.detail and ('"name"' in err.detail or "'name'" in err.detail)
    assert "nope-agent" in err.detail

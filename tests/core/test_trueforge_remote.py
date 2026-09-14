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
    routes: dict[tuple[str, str], tuple[int, dict | list | str]] = {}
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
        status, response_body = self.routes.get(key, (404, {"error": f"no route for {method} {path}"}))
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
    _TrueForgeRouter.received_headers = []
    _TrueForgeRouter.received_bodies = []
    server = HTTPServer(("127.0.0.1", 0), _TrueForgeRouter)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield host, port, _TrueForgeRouter
    server.shutdown()
    _TrueForgeRouter.routes = {}
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
    assert caps.transport == "http"

    harness = get_harness("trueforge")
    assert harness is not None
    assert isinstance(harness, RemoteHarness)
    assert isinstance(harness, BoundRemoteHarness)
    assert harness.impl_id == "trueforge"
    assert harness.label == "TrueForge"


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

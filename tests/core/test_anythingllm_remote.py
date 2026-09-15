"""Unit tests for the AnythingLLM remote kind (REQ: threads as sessions).

Covers: kind registries, opt-in add/persist, health, list (workspace threads
normalized to sessions with ``workspace:thread`` resume keys), and send into an
existing thread (never mints new threads). All HTTP is mocked via a local
threading HTTP server — no LAN, no docker, no secrets.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from swarm.core import remotes as remotes_core
from swarm.core.remote_harness import (
    REMOTE_IMPL_IDS,
    all_harnesses,
    capabilities_for,
    get_harness,
    is_remote_impl_id,
    sessions_from_operate,
)


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, dict | list | str]] = {}

    def _handle(self, method: str) -> None:
        key = (method, self.path.split("?", 1)[0])
        status, body = self.routes.get(key, (404, {"error": "no route"}))
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
def http_router():
    server = HTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield host, port, _Router
    server.shutdown()
    _Router.routes = {}


def _cfg(host: str, port: int, **extra: dict) -> dict:
    base = f"http://{host}:{port}"
    block = {"base_url": base, "api_key": "allm-key"}
    block.update(extra)
    return {"llm": {}, "remotes": {"anythingllm": block}}


_WORKSPACES = {
    "workspaces": [
        {
            "slug": "teamstinky",
            "name": "TeamStinky",
            "threads": [
                {"slug": "f8c17211-9d11-4fc7-879a-42c19975b130", "name": "latest hacker news?"},
                {"slug": "aaa11111-0000-0000-0000-000000000000", "name": "onboarding docs"},
            ],
        },
        {"slug": "empty-ws", "name": "Empty", "threads": []},
    ]
}


def test_anythingllm_is_a_catalog_remote_kind():
    assert "anythingllm" in REMOTE_IMPL_IDS
    assert is_remote_impl_id("anythingllm")
    assert is_remote_impl_id("AnythingLLM")  # aliases are case-insensitive ids
    assert remotes_core.kind_label("anythingllm") == "AnythingLLM"
    kinds = {k["id"]: k for k in remotes_core.list_remote_kinds()}
    row = kinds["anythingllm"]
    assert row["kind"] == "remote"
    assert row["impl"] == "anythingllm"
    assert row["label"] == "AnythingLLM"
    caps = row["capabilities"]
    assert caps["list"] is True and caps["send"] is True and caps["health"] is True
    assert caps["operate"] is False
    assert capabilities_for("anythingllm").transport == "http"


def test_anythingllm_is_opt_in_not_auto_placed(monkeypatch):
    # Hermetic: the host may export OMB_BASE_URL / HERMES_BASE_URL etc., which
    # legitimately auto-place those kinds. This test is about anythingllm only.
    for var in ("ANYTHINGLLM_BASE_URL", "OMB_BASE_URL", "HERMES_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert "anythingllm" in remotes_core.OPT_IN_REMOTE_IDS
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.is_configured("anythingllm", cfg) is False
    assert "anythingllm" not in remotes_core.added_remote_ids(cfg)
    # REQ-11 default roster does not include it.
    assert "anythingllm" not in remotes_core.load_placed_members(cfg)
    # Not configured ⇒ honest "not configured", no LAN probe.
    assert remotes_core.operate("anythingllm", "list", config=cfg).ok is False
    health = remotes_core.check_health("anythingllm", config=cfg, timeout=0.2)
    assert health.state == "UNKNOWN"
    assert "not configured" in health.detail


def test_add_and_remove_anythingllm(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    monkeypatch.delenv("ANYTHINGLLM_BASE_URL", raising=False)
    monkeypatch.delenv("ANYTHINGLLM_API_KEY", raising=False)
    spec, path = remotes_core.add_remote(
        "anythingllm",
        base_url="http://127.0.0.1:3001",
        api_key_env="ANYTHINGLLM_API_KEY",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "anythingllm"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["anythingllm"]["base_url"] == "http://127.0.0.1:3001"
    assert data["remotes"]["anythingllm"]["api_key"] == "${ANYTHINGLLM_API_KEY}"
    assert data["remotes"]["anythingllm"]["api_key_env"] == "ANYTHINGLLM_API_KEY"
    assert remotes_core.is_configured("anythingllm", data)
    rid, _ = remotes_core.remove_remote("anythingllm", config_path=cfg)
    assert rid == "anythingllm"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "anythingllm" not in (data.get("remotes") or {})


def test_env_bootstrap_shows_anythingllm(monkeypatch):
    monkeypatch.setenv("ANYTHINGLLM_BASE_URL", "http://127.0.0.1:3001")
    monkeypatch.delenv("ANYTHINGLLM_API_KEY", raising=False)
    ids = remotes_core.added_remote_ids({"llm": {}, "remotes": {}})
    assert "anythingllm" in ids
    spec = remotes_core.load_remote("anythingllm", {"llm": {}, "remotes": {}})
    assert spec.base_url == "http://127.0.0.1:3001"
    assert spec.source == "env"


def test_default_spec_is_sanitized_and_has_no_secret():
    """Default is env-pointable with no baked private host (sanitization gate)."""
    spec = remotes_core.default_spec("anythingllm")
    assert spec.base_url == "http://127.0.0.1:3001"
    assert "10.0.0." not in spec.base_url and "192.168." not in spec.base_url
    assert remotes_core._ENV_BASE["anythingllm"] == "ANYTHINGLLM_BASE_URL"
    assert remotes_core._ENV_KEY["anythingllm"] == "ANYTHINGLLM_API_KEY"
    assert spec.health_path == "/api/v1/workspaces"
    assert spec.api_key == "${ANYTHINGLLM_API_KEY}"
    pub = spec.public_dict()
    assert pub["api_key_set"] is False  # unresolved placeholder, never a secret


def test_list_threads_as_sessions(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/workspaces")] = (200, _WORKSPACES)
    result = remotes_core.operate("anythingllm", "list", config=_cfg(host, port))
    assert result.ok is True
    assert result.op == "list"
    assert result.http_status == 200
    sessions = sessions_from_operate(result)
    ids = [s.id for s in sessions]
    assert ids == [
        "teamstinky:f8c17211-9d11-4fc7-879a-42c19975b130",
        "teamstinky:aaa11111-0000-0000-0000-000000000000",
    ]
    first = sessions[0]
    assert first.title == "latest hacker news?"
    assert first.source == "anythingllm"
    assert first.channel == "TeamStinky"
    assert first.thread_ts == "f8c17211-9d11-4fc7-879a-42c19975b130"
    # Empty workspaces produce no sessions.
    assert len(sessions) == 2


def test_list_auth_required_is_honest(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/workspaces")] = (401, {"detail": "Unauthorized"})
    result = remotes_core.operate("anythingllm", "list", config=_cfg(host, port))
    assert result.ok is False
    assert result.http_status == 401
    assert "API key" in result.detail
    assert "ANYTHINGLLM_API_KEY" in result.detail


def test_send_requires_existing_thread(http_router):
    host, port, _router = http_router
    result = remotes_core.operate(
        "anythingllm", "send", prompt="hi", config=_cfg(host, port), session_id=None
    )
    assert result.ok is False
    assert result.gap == "anythingllm_thread_required"
    assert "does not mint new" in result.detail
    # Malformed id (no colon) is the same gap, not a 404 request.
    result2 = remotes_core.operate(
        "anythingllm", "send", prompt="hi", config=_cfg(host, port), session_id="teamstinky"
    )
    assert result2.ok is False
    assert result2.gap == "anythingllm_thread_required"


def test_send_into_existing_thread(http_router):
    host, port, router = http_router
    key = ("POST", "/api/v1/workspace/teamstinky/thread/f8c17211-9d11-4fc7-879a-42c19975b130/chat")
    router.routes[key] = (200, {"textResponse": "PONG from AnythingLLM", "sources": []})
    result = remotes_core.operate(
        "anythingllm",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id="teamstinky:f8c17211-9d11-4fc7-879a-42c19975b130",
    )
    assert result.ok is True
    assert result.http_status == 200
    assert result.data["response"] == "PONG from AnythingLLM"
    assert result.data["thread"] == "teamstinky:f8c17211-9d11-4fc7-879a-42c19975b130"


def test_send_surfaces_gateway_error(http_router):
    host, port, router = http_router
    key = ("POST", "/api/v1/workspace/teamstinky/thread/f8c17211-9d11-4fc7-879a-42c19975b130/chat")
    # AnythingLLM returns HTTP 200 with an abort/error body when its chat
    # model is misconfigured — we must surface that, never fake a reply.
    router.routes[key] = (
        200,
        {"type": "abort", "textResponse": None, "sources": [], "close": True, "error": "Connection error."},
    )
    result = remotes_core.operate(
        "anythingllm",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id="teamstinky:f8c17211-9d11-4fc7-879a-42c19975b130",
    )
    assert result.ok is False
    assert "Connection error" in result.detail


def test_harness_registered_and_callable(http_router):
    harness = get_harness("anythingllm")
    assert harness is not None
    assert harness.label == "AnythingLLM"
    assert harness.impl_id == "anythingllm"
    assert {h.impl_id for h in all_harnesses()} == set(REMOTE_IMPL_IDS)
    # Advertises resumable sessions (threads).
    assert capabilities_for("anythingllm").sessions is True
    # The bound wrapper must route to the real adapter (not a stub): a live
    # list call through the harness returns the workspace thread sessions.
    host, port, router = http_router
    router.routes[("GET", "/api/v1/workspaces")] = (200, _WORKSPACES)
    spec = remotes_core.load_remote(
        "anythingllm", {"llm": {}, "remotes": {"anythingllm": {"base_url": f"http://{host}:{port}", "api_key": "k"}}}
    )
    result = harness.list(spec, timeout=3)
    assert result.ok is True
    assert sessions_from_operate(result)[0].id.startswith("teamstinky:")
    # Health is config-aware (see test_req203_remote_harness patterns): the
    # harness resolves the target from config, so pass the same config used
    # for the list call above.
    health = harness.health(spec, timeout=0.3, config=_cfg(host, port))
    assert health.ok is True
    assert health.state == "UP"


def test_session_id_passes_sanitize():
    """Resume keys (workspace:thread) must survive the session-id sanitizer."""
    from swarm.core.cli_sessions import sanitize_cli_session_id

    sid = "teamstinky:f8c17211-9d11-4fc7-879a-42c19975b130"
    assert sanitize_cli_session_id(sid) == sid
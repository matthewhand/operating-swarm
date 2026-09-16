"""Unit tests for the Flowise remote kind (flows + chat sessions).

Covers: kind registries, opt-in add/persist, health, list (chatflows plus
chat sessions normalized to ``flowId`` / ``flowId:chatId`` resume keys),
search, and send into an existing session (never mints a random thread).
Streaming uses SSE token events with a JSON fallback. All HTTP is mocked
via a local threading HTTP server — no LAN, no docker, no secrets.
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
        ctype = "application/json"
        if isinstance(body, str) and body.lstrip().startswith(("data:", "event:")):
            ctype = "text/event-stream"
        self.send_header("Content-Type", ctype)
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
    block = {"base_url": base, "api_key": "flowise-key"}
    block.update(extra)
    return {"llm": {}, "remotes": {"flowise": block}}


_FLOWS = [
    {"id": "support-bot", "name": "Support Bot", "type": "CHATFLOW"},
    {"id": "empty-flow", "name": "Empty", "type": "AGENTFLOW"},
]

_SUPPORT_MESSAGES = [
    {
        "id": "m1",
        "role": "userMessage",
        "content": "latest hacker news?",
        "chatId": "chat-hn",
        "sessionId": "chat-hn",
        "createdDate": "2026-01-01T00:00:00Z",
    },
    {
        "id": "m2",
        "role": "apiMessage",
        "content": "Here are today's stories.",
        "chatId": "chat-hn",
        "sessionId": "chat-hn",
    },
    {
        "id": "m3",
        "role": "userMessage",
        "content": "onboarding docs",
        "chatId": "chat-onboard",
        "sessionId": "chat-onboard",
    },
]


def test_flowise_is_a_catalog_remote_kind():
    assert "flowise" in REMOTE_IMPL_IDS
    assert is_remote_impl_id("flowise")
    assert is_remote_impl_id("FlowiseAI")
    assert remotes_core.kind_label("flowise") == "Flowise"
    kinds = {k["id"]: k for k in remotes_core.list_remote_kinds()}
    row = kinds["flowise"]
    assert row["kind"] == "remote"
    assert row["impl"] == "flowise"
    assert row["label"] == "Flowise"
    caps = row["capabilities"]
    assert caps["list"] is True and caps["send"] is True and caps["health"] is True
    assert caps["operate"] is False
    assert caps["sessions"] is True
    assert capabilities_for("flowise").transport == "http"


def test_flowise_is_opt_in_not_auto_placed(monkeypatch):
    for var in ("FLOWISE_BASE_URL", "OMB_BASE_URL", "HERMES_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert "flowise" in remotes_core.OPT_IN_REMOTE_IDS
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.is_configured("flowise", cfg) is False
    assert "flowise" not in remotes_core.added_remote_ids(cfg)
    assert "flowise" not in remotes_core.load_placed_members(cfg)
    assert remotes_core.operate("flowise", "list", config=cfg).ok is False
    health = remotes_core.check_health("flowise", config=cfg, timeout=0.2)
    assert health.state == "UNKNOWN"
    assert "not configured" in health.detail


def test_add_and_remove_flowise(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    monkeypatch.delenv("FLOWISE_BASE_URL", raising=False)
    monkeypatch.delenv("FLOWISE_API_KEY", raising=False)
    spec, path = remotes_core.add_remote(
        "flowise",
        base_url="http://127.0.0.1:3000",
        api_key_env="FLOWISE_API_KEY",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "flowise"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["flowise"]["base_url"] == "http://127.0.0.1:3000"
    assert data["remotes"]["flowise"]["api_key"] == "${FLOWISE_API_KEY}"
    assert data["remotes"]["flowise"]["api_key_env"] == "FLOWISE_API_KEY"
    assert remotes_core.is_configured("flowise", data)
    rid, _ = remotes_core.remove_remote("flowise", config_path=cfg)
    assert rid == "flowise"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "flowise" not in (data.get("remotes") or {})


def test_env_bootstrap_shows_flowise(monkeypatch):
    monkeypatch.setenv("FLOWISE_BASE_URL", "http://127.0.0.1:3000")
    monkeypatch.delenv("FLOWISE_API_KEY", raising=False)
    ids = remotes_core.added_remote_ids({"llm": {}, "remotes": {}})
    assert "flowise" in ids
    spec = remotes_core.load_remote("flowise", {"llm": {}, "remotes": {}})
    assert spec.base_url == "http://127.0.0.1:3000"
    assert spec.source == "env"


def test_default_spec_is_sanitized_and_has_no_secret():
    spec = remotes_core.default_spec("flowise")
    assert spec.base_url == "http://127.0.0.1:3000"
    assert "10.0.0." not in spec.base_url and "192.168." not in spec.base_url
    assert remotes_core._ENV_BASE["flowise"] == "FLOWISE_BASE_URL"
    assert remotes_core._ENV_KEY["flowise"] == "FLOWISE_API_KEY"
    assert spec.health_path == "/api/v1/chatflows"
    assert spec.api_key == "${FLOWISE_API_KEY}"
    pub = spec.public_dict()
    assert pub["api_key_set"] is False


def test_list_flows_and_sessions(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/chatflows")] = (200, _FLOWS)
    router.routes[("GET", "/api/v1/chatmessage/support-bot")] = (200, _SUPPORT_MESSAGES)
    router.routes[("GET", "/api/v1/chatmessage/empty-flow")] = (200, [])
    result = remotes_core.operate("flowise", "list", config=_cfg(host, port))
    assert result.ok is True
    assert result.op == "list"
    assert result.http_status == 200
    sessions = sessions_from_operate(result)
    ids = [s.id for s in sessions]
    assert "support-bot" in ids
    assert "empty-flow" in ids
    assert "support-bot:chat-hn" in ids
    assert "support-bot:chat-onboard" in ids
    thread = next(s for s in sessions if s.id == "support-bot:chat-hn")
    assert thread.title == "latest hacker news?"
    assert thread.source == "flowise"
    assert thread.channel == "Support Bot"
    assert thread.thread_ts == "chat-hn"
    assert len(sessions) == 4


def test_list_auth_required_is_honest(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/chatflows")] = (401, {"message": "Unauthorized"})
    result = remotes_core.operate("flowise", "list", config=_cfg(host, port))
    assert result.ok is False
    assert result.http_status == 401
    assert "API key" in result.detail
    assert "FLOWISE_API_KEY" in result.detail


def test_send_requires_existing_session(http_router):
    host, port, _router = http_router
    result = remotes_core.operate(
        "flowise", "send", prompt="hi", config=_cfg(host, port), session_id=None
    )
    assert result.ok is False
    assert result.gap == "flowise_session_required"
    assert "does not mint" in result.detail
    result2 = remotes_core.operate(
        "flowise", "send", prompt="hi", config=_cfg(host, port), session_id=""
    )
    assert result2.ok is False
    assert result2.gap == "flowise_session_required"


def test_list_sessions_are_searchable(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/chatflows")] = (200, _FLOWS)
    router.routes[("GET", "/api/v1/chatmessage/support-bot")] = (200, _SUPPORT_MESSAGES)
    router.routes[("GET", "/api/v1/chatmessage/empty-flow")] = (200, [])
    listed = remotes_core.operate("flowise", "list", config=_cfg(host, port))
    filtered = remotes_core.filter_flowise_sessions(listed.data["sessions"], "onboarding")
    assert [row["id"] for row in filtered] == ["support-bot:chat-onboard"]
    result = remotes_core.operate(
        "flowise", "list", config=_cfg(host, port), query="hacker"
    )
    assert result.ok is True
    sessions = sessions_from_operate(result)
    assert [s.id for s in sessions] == ["support-bot:chat-hn"]


def test_send_into_existing_session(http_router):
    host, port, router = http_router
    router.routes[("POST", "/api/v1/prediction/support-bot")] = (
        200,
        {"text": "PONG from Flowise", "chatId": "chat-hn"},
    )
    result = remotes_core.operate(
        "flowise",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id="support-bot:chat-hn",
    )
    assert result.ok is True
    assert result.http_status == 200
    assert result.data["response"] == "PONG from Flowise"
    assert result.data["thread"] == "support-bot:chat-hn"


def test_send_into_flow_main_chat(http_router):
    host, port, router = http_router
    router.routes[("POST", "/api/v1/prediction/support-bot")] = (
        200,
        {"text": "flow pong", "chatId": "support-bot"},
    )
    result = remotes_core.operate(
        "flowise",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id="support-bot",
    )
    assert result.ok is True
    assert result.data["response"] == "flow pong"
    assert result.data["thread"] == "support-bot"


def test_send_surfaces_gateway_error(http_router):
    host, port, router = http_router
    router.routes[("POST", "/api/v1/prediction/support-bot")] = (
        200,
        {"error": "Connection error.", "text": ""},
    )
    result = remotes_core.operate(
        "flowise",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id="support-bot:chat-hn",
    )
    assert result.ok is False
    assert "Connection error" in result.detail


def test_stream_chat_yields_deltas(http_router):
    host, port, router = http_router
    sse = (
        "event: token\n"
        "data: Hel\n\n"
        "event: token\n"
        "data: {\"token\": \"lo\"}\n\n"
        "event: end\n"
        "data: [DONE]\n\n"
    )
    router.routes[("POST", "/api/v1/prediction/support-bot")] = (200, sse)
    result = remotes_core.operate(
        "flowise",
        "send",
        prompt="hi",
        config=_cfg(host, port),
        session_id="support-bot:chat-hn",
    )
    assert result.ok is True
    assert result.data["response"] == "Hello"


def test_harness_registered_and_callable(http_router):
    harness = get_harness("flowise")
    assert harness is not None
    assert harness.label == "Flowise"
    assert harness.impl_id == "flowise"
    assert {h.impl_id for h in all_harnesses()} == set(REMOTE_IMPL_IDS)
    assert capabilities_for("flowise").sessions is True
    host, port, router = http_router
    router.routes[("GET", "/api/v1/chatflows")] = (200, _FLOWS)
    router.routes[("GET", "/api/v1/chatmessage/support-bot")] = (200, _SUPPORT_MESSAGES)
    router.routes[("GET", "/api/v1/chatmessage/empty-flow")] = (200, [])
    spec = remotes_core.load_remote(
        "flowise",
        {"llm": {}, "remotes": {"flowise": {"base_url": f"http://{host}:{port}", "api_key": "k"}}},
    )
    result = harness.list(spec, timeout=3)
    assert result.ok is True
    ids = [s.id for s in sessions_from_operate(result)]
    assert "support-bot" in ids
    assert any(sid.startswith("support-bot:") for sid in ids)
    health = harness.health(spec, timeout=0.3, config=_cfg(host, port))
    assert health.ok is True
    assert health.state == "UP"


def test_session_id_passes_sanitize():
    from swarm.core.cli_sessions import sanitize_cli_session_id

    sid = "support-bot:chat-hn"
    assert sanitize_cli_session_id(sid) == sid
    assert sanitize_cli_session_id("support-bot") == "support-bot"

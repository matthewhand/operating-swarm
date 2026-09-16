"""Unit tests for the external Open WebUI remote kind (issue #90).

Covers: catalog/opt-in, list (chats as sessions + search), resume send into an
existing chat (never mints), stream-chat with sync fallback. All HTTP is mocked
via a local threading server — no LAN, no docker, no secrets. This remote is
not Operating Swarm's own WebUI (os-webui).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

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
    posts: list[tuple[str, dict | list | str | None]] = []

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        key = (method, parsed.path)
        status, body = self.routes.get(key, (404, {"error": "no route"}))
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                posted = json.loads(raw.decode("utf-8")) if raw else None
            except json.JSONDecodeError:
                posted = raw.decode("utf-8", errors="replace")
            self.posts.append((parsed.path, posted))
        sse = isinstance(body, str) and body.lstrip().startswith("data:")
        payload = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream" if sse else "application/json")
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
    _Router.posts = []


def _cfg(host: str, port: int, **extra) -> dict:
    base = f"http://{host}:{port}"
    block = {"base_url": base, "api_key": "owui-key"}
    block.update(extra)
    return {"llm": {}, "remotes": {"openwebui": block}}


_CHAT_A = "550e8400-e29b-41d4-a716-446655440000"
_CHAT_B = "660f9511-f3ac-52e5-b827-557766551111"

_CHATS = [
    {"id": _CHAT_A, "title": "latest hacker news?", "updated_at": 1709251200},
    {"id": _CHAT_B, "title": "onboarding docs", "updated_at": 1709164800},
]

_CHAT_DETAIL = {
    "id": _CHAT_A,
    "title": "latest hacker news?",
    "chat": {
        "title": "latest hacker news?",
        "models": ["llama3"],
        "messages": [
            {"role": "user", "content": "what's on hn?"},
            {"role": "assistant", "content": "Here are today's stories."},
        ],
    },
}


def test_openwebui_is_a_catalog_remote_kind():
    assert "openwebui" in REMOTE_IMPL_IDS
    assert is_remote_impl_id("openwebui")
    assert is_remote_impl_id("Open WebUI".replace(" ", "").lower() or "openwebui")
    assert is_remote_impl_id("open-webui")
    assert remotes_core.kind_label("openwebui") == "Open WebUI"
    kinds = {k["id"]: k for k in remotes_core.list_remote_kinds()}
    row = kinds["openwebui"]
    assert row["kind"] == "remote"
    assert row["impl"] == "openwebui"
    assert row["label"] == "Open WebUI"
    caps = row["capabilities"]
    assert caps["list"] is True and caps["send"] is True and caps["health"] is True
    assert caps["operate"] is False
    assert caps["sessions"] is True
    assert capabilities_for("openwebui").transport == "http"


def test_openwebui_is_opt_in_not_auto_placed(monkeypatch):
    for var in ("OPENWEBUI_BASE_URL", "OMB_BASE_URL", "HERMES_BASE_URL", "ANYTHINGLLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert "openwebui" in remotes_core.OPT_IN_REMOTE_IDS
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.is_configured("openwebui", cfg) is False
    assert "openwebui" not in remotes_core.added_remote_ids(cfg)
    assert "openwebui" not in remotes_core.load_placed_members(cfg)
    assert remotes_core.operate("openwebui", "list", config=cfg).ok is False
    health = remotes_core.check_health("openwebui", config=cfg, timeout=0.2)
    assert health.state == "UNKNOWN"
    assert "not configured" in health.detail


def test_add_and_remove_openwebui(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    monkeypatch.delenv("OPENWEBUI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENWEBUI_API_KEY", raising=False)
    spec, path = remotes_core.add_remote(
        "openwebui",
        base_url="http://127.0.0.1:8080",
        api_key_env="OPENWEBUI_API_KEY",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "openwebui"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["openwebui"]["base_url"] == "http://127.0.0.1:8080"
    assert data["remotes"]["openwebui"]["api_key"] == "${OPENWEBUI_API_KEY}"
    assert remotes_core.is_configured("openwebui", data)
    rid, _ = remotes_core.remove_remote("openwebui", config_path=cfg)
    assert rid == "openwebui"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "openwebui" not in (data.get("remotes") or {})


def test_env_bootstrap_shows_openwebui(monkeypatch):
    monkeypatch.setenv("OPENWEBUI_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.delenv("OPENWEBUI_API_KEY", raising=False)
    ids = remotes_core.added_remote_ids({"llm": {}, "remotes": {}})
    assert "openwebui" in ids
    spec = remotes_core.load_remote("openwebui", {"llm": {}, "remotes": {}})
    assert spec.base_url == "http://127.0.0.1:8080"
    assert spec.source == "env"


def test_default_spec_is_sanitized_and_has_no_secret():
    spec = remotes_core.default_spec("openwebui")
    assert spec.base_url == "http://127.0.0.1:8080"
    assert "10.0.0." not in spec.base_url and "192.168." not in spec.base_url
    assert remotes_core._ENV_BASE["openwebui"] == "OPENWEBUI_BASE_URL"
    assert remotes_core._ENV_KEY["openwebui"] == "OPENWEBUI_API_KEY"
    assert spec.health_path == "/health"
    assert spec.api_key == "${OPENWEBUI_API_KEY}"
    pub = spec.public_dict()
    assert pub["api_key_set"] is False
    assert "os-webui" in spec.notes.lower()
    assert "not operating swarm's own webui" in spec.notes.lower()


def test_list_chats_as_sessions(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/chats/")] = (200, _CHATS)
    result = remotes_core.operate("openwebui", "list", config=_cfg(host, port))
    assert result.ok is True
    assert result.op == "list"
    sessions = sessions_from_operate(result)
    ids = [s.id for s in sessions]
    assert ids == [_CHAT_A, _CHAT_B]
    first = sessions[0]
    assert first.title == "latest hacker news?"
    assert first.source == "openwebui"
    assert first.channel == "Open WebUI"


def test_list_search_filters_when_many(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/chats/search")] = (
        200,
        [{"id": _CHAT_B, "title": "onboarding docs", "updated_at": 1}],
    )
    result = remotes_core.operate(
        "openwebui", "list", config=_cfg(host, port), query="onboarding"
    )
    assert result.ok is True
    sessions = sessions_from_operate(result)
    assert [s.id for s in sessions] == [_CHAT_B]


def test_list_search_falls_back_to_local_filter(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/chats/search")] = (404, {"detail": "not found"})
    router.routes[("GET", "/api/v1/chats/")] = (200, _CHATS)
    result = remotes_core.operate(
        "openwebui", "list", config=_cfg(host, port), query="hacker"
    )
    assert result.ok is True
    sessions = sessions_from_operate(result)
    assert [s.id for s in sessions] == [_CHAT_A]


def test_list_auth_required_is_honest(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/chats/")] = (401, {"detail": "Unauthorized"})
    result = remotes_core.operate("openwebui", "list", config=_cfg(host, port))
    assert result.ok is False
    assert result.http_status == 401
    assert "API key" in result.detail
    assert "OPENWEBUI_API_KEY" in result.detail
    assert "Operating Swarm's WebUI" in result.detail or "not Operating Swarm" in result.detail


def test_send_requires_existing_chat(http_router):
    host, port, _router = http_router
    result = remotes_core.operate(
        "openwebui", "send", prompt="hi", config=_cfg(host, port), session_id=None
    )
    assert result.ok is False
    assert result.gap == "openwebui_chat_required"
    assert "does not mint" in result.detail


def test_send_into_existing_chat_streams(http_router):
    host, port, router = http_router
    router.routes[("GET", f"/api/v1/chats/{_CHAT_A}")] = (200, _CHAT_DETAIL)
    router.routes[("POST", "/api/chat/completions")] = (
        200,
        'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":" from Open WebUI"}}]}\n\n'
        "data: [DONE]\n\n",
    )
    router.routes[("POST", "/api/chat/completed")] = (200, {"ok": True})
    result = remotes_core.operate(
        "openwebui",
        "send",
        prompt="say hello",
        config=_cfg(host, port),
        session_id=_CHAT_A,
    )
    assert result.ok is True
    assert result.data["response"] == "Hello from Open WebUI"
    assert result.data["chat_id"] == _CHAT_A
    paths = [path for path, _ in router.posts]
    assert "/api/chat/completions" in paths
    assert "/api/chat/completed" in paths
    completed = next(body for path, body in router.posts if path == "/api/chat/completed")
    assert completed["chat_id"] == _CHAT_A
    assert completed["messages"][-1]["content"] == "Hello from Open WebUI"
    completions = next(body for path, body in router.posts if path == "/api/chat/completions")
    assert completions["chat_id"] == _CHAT_A
    assert completions["stream"] is True
    assert completions["messages"][-1] == {"role": "user", "content": "say hello"}


def test_send_json_completions_body(http_router):
    host, port, router = http_router
    router.routes[("GET", f"/api/v1/chats/{_CHAT_A}")] = (200, _CHAT_DETAIL)
    router.routes[("POST", "/api/chat/completions")] = (
        200,
        {"choices": [{"message": {"content": "PONG from Open WebUI"}}]},
    )
    router.routes[("POST", "/api/chat/completed")] = (200, {"ok": True})
    result = remotes_core.operate(
        "openwebui",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id=_CHAT_A,
    )
    assert result.ok is True
    assert result.data["response"] == "PONG from Open WebUI"


def test_send_missing_chat_is_honest(http_router):
    host, port, router = http_router
    router.routes[("GET", f"/api/v1/chats/{_CHAT_A}")] = (404, {"detail": "Not found"})
    result = remotes_core.operate(
        "openwebui",
        "send",
        prompt="hi",
        config=_cfg(host, port),
        session_id=_CHAT_A,
    )
    assert result.ok is False
    assert "not found" in result.detail.lower() or "404" in result.detail


def test_harness_registered_and_callable(http_router):
    harness = get_harness("openwebui")
    assert harness is not None
    assert harness.label == "Open WebUI"
    assert harness.impl_id == "openwebui"
    assert {h.impl_id for h in all_harnesses()} == set(REMOTE_IMPL_IDS)
    assert capabilities_for("openwebui").sessions is True
    host, port, router = http_router
    router.routes[("GET", "/api/v1/chats/")] = (200, _CHATS)
    spec = remotes_core.load_remote(
        "openwebui",
        {"llm": {}, "remotes": {"openwebui": {"base_url": f"http://{host}:{port}", "api_key": "k"}}},
    )
    result = harness.list(spec, timeout=3)
    assert result.ok is True
    assert sessions_from_operate(result)[0].id == _CHAT_A
    router.routes[("GET", "/health")] = (200, {"status": True})
    health = harness.health(spec, timeout=0.3, config=_cfg(host, port))
    assert health.ok is True
    assert health.state == "UP"


def test_session_id_passes_sanitize():
    from swarm.core.cli_sessions import sanitize_cli_session_id

    assert sanitize_cli_session_id(_CHAT_A) == _CHAT_A


def test_alias_open_webui_resolves():
    assert remotes_core.kind_of_instance("open-webui") == "openwebui"
    assert remotes_core.kind_of_instance("open_webui") == "openwebui"
    assert remotes_core.kind_of_instance("owui") == "openwebui"
    assert remotes_core.kind_of_instance("openwebui-lab") == "openwebui"

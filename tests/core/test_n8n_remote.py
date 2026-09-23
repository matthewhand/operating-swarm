"""Unit tests for the n8n remote kind (REQ: workflows as chat sessions).

Covers: kind registries, opt-in add/persist, health, list (chat/webhook
workflows normalized to sessions with ``workflow:webhook`` resume keys),
search filter, and send into an existing flow (never mints new workflows).
All HTTP is mocked via a local threading HTTP server — no LAN, no secrets.
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
    posts: list[tuple[str, bytes]] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        key = (method, path)
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            self.posts.append((path, raw))
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
    _Router.posts = []


def _cfg(host: str, port: int, **extra: dict) -> dict:
    base = f"http://{host}:{port}"
    block = {"base_url": base, "api_key": "n8n-key"}
    block.update(extra)
    return {"llm": {}, "remotes": {"n8n": block}}


_WORKFLOWS = {
    "data": [
        {
            "id": "wfSupport",
            "name": "Support Bot",
            "active": True,
            "updatedAt": "2026-09-01T00:00:00.000Z",
            "nodes": [
                {
                    "id": "chat-1",
                    "name": "Chat Trigger",
                    "type": "n8n-nodes-langchain.chatTrigger",
                    "webhookId": "chat-hook-1",
                    "parameters": {"public": True},
                }
            ],
        },
        {
            "id": "wfOnboard",
            "name": "Customer Onboarding",
            "active": True,
            "nodes": [
                {
                    "id": "hook-1",
                    "name": "Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "webhookId": "onboard-hook",
                    "parameters": {"path": "onboard"},
                }
            ],
        },
        {
            "id": "wfCron",
            "name": "Nightly cron",
            "active": True,
            "nodes": [
                {
                    "id": "cron-1",
                    "name": "Schedule",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "parameters": {},
                }
            ],
        },
    ]
}


def test_n8n_is_a_catalog_remote_kind():
    assert "n8n" in REMOTE_IMPL_IDS
    assert is_remote_impl_id("n8n")
    assert is_remote_impl_id("n8n-io")
    assert remotes_core.kind_label("n8n") == "n8n"
    kinds = {k["id"]: k for k in remotes_core.list_remote_kinds()}
    row = kinds["n8n"]
    assert row["kind"] == "remote"
    assert row["impl"] == "n8n"
    assert row["label"] == "n8n"
    caps = row["capabilities"]
    assert caps["list"] is True and caps["send"] is True and caps["health"] is True
    assert caps["operate"] is False
    assert caps["sessions"] is True
    assert capabilities_for("n8n").transport == "http"


def test_n8n_is_opt_in_not_auto_placed(monkeypatch):
    for var in ("N8N_BASE_URL", "OMB_BASE_URL", "HERMES_BASE_URL", "ANYTHINGLLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert "n8n" in remotes_core.OPT_IN_REMOTE_IDS
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.is_configured("n8n", cfg) is False
    assert "n8n" not in remotes_core.added_remote_ids(cfg)
    assert "n8n" not in remotes_core.load_placed_members(cfg)
    assert remotes_core.operate("n8n", "list", config=cfg).ok is False
    health = remotes_core.check_health("n8n", config=cfg, timeout=0.2)
    assert health.state == "UNKNOWN"
    assert "not configured" in health.detail


def test_add_and_remove_n8n(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    monkeypatch.delenv("N8N_BASE_URL", raising=False)
    monkeypatch.delenv("N8N_API_KEY", raising=False)
    spec, path = remotes_core.add_remote(
        "n8n",
        base_url="http://127.0.0.1:5678",
        api_key_env="N8N_API_KEY",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "n8n"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["n8n"]["base_url"] == "http://127.0.0.1:5678"
    assert data["remotes"]["n8n"]["api_key"] == "${N8N_API_KEY}"
    assert data["remotes"]["n8n"]["api_key_env"] == "N8N_API_KEY"
    assert remotes_core.is_configured("n8n", data)
    rid, _ = remotes_core.remove_remote("n8n", config_path=cfg)
    assert rid == "n8n"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "n8n" not in (data.get("remotes") or {})


def test_env_bootstrap_shows_n8n(monkeypatch):
    monkeypatch.setenv("N8N_BASE_URL", "http://127.0.0.1:5678")
    monkeypatch.delenv("N8N_API_KEY", raising=False)
    ids = remotes_core.added_remote_ids({"llm": {}, "remotes": {}})
    assert "n8n" in ids
    spec = remotes_core.load_remote("n8n", {"llm": {}, "remotes": {}})
    assert spec.base_url == "http://127.0.0.1:5678"
    assert spec.source == "env"


def test_default_spec_is_sanitized_and_has_no_secret():
    spec = remotes_core.default_spec("n8n")
    assert spec.base_url == "http://127.0.0.1:5678"
    assert "10.0.0." not in spec.base_url and "192.168." not in spec.base_url
    assert remotes_core._ENV_BASE["n8n"] == "N8N_BASE_URL"
    assert remotes_core._ENV_KEY["n8n"] == "N8N_API_KEY"
    assert spec.health_path == "/healthz"
    assert spec.api_key == "${N8N_API_KEY}"
    pub = spec.public_dict()
    assert pub["api_key_set"] is False


def test_list_chat_workflows_as_sessions(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/workflows")] = (200, _WORKFLOWS)
    result = remotes_core.operate("n8n", "list", config=_cfg(host, port))
    assert result.ok is True
    assert result.op == "list"
    assert result.http_status == 200
    sessions = sessions_from_operate(result)
    ids = [s.id for s in sessions]
    assert ids == ["wfSupport:chat-hook-1", "wfOnboard:onboard"]
    first = sessions[0]
    assert first.title == "Support Bot"
    assert first.source == "n8n"
    assert first.channel == "Support Bot"
    assert first.thread_ts == "chat-hook-1"
    assert len(sessions) == 2


def test_list_is_searchable(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/workflows")] = (200, _WORKFLOWS)
    result = remotes_core.operate("n8n", "list", config=_cfg(host, port), query="onboard")
    sessions = sessions_from_operate(result)
    assert [s.id for s in sessions] == ["wfOnboard:onboard"]


def test_list_auth_required_is_honest(http_router):
    host, port, router = http_router
    router.routes[("GET", "/api/v1/workflows")] = (401, {"message": "Unauthorized"})
    result = remotes_core.operate("n8n", "list", config=_cfg(host, port))
    assert result.ok is False
    assert result.http_status == 401
    assert "API key" in result.detail
    assert "N8N_API_KEY" in result.detail


def test_send_requires_existing_workflow(http_router):
    host, port, _router = http_router
    result = remotes_core.operate(
        "n8n", "send", prompt="hi", config=_cfg(host, port), session_id=None
    )
    assert result.ok is False
    assert result.gap == "n8n_workflow_required"
    assert "does not mint new" in result.detail
    result2 = remotes_core.operate(
        "n8n", "send", prompt="hi", config=_cfg(host, port), session_id="wfSupport"
    )
    assert result2.ok is False
    assert result2.gap == "n8n_workflow_required"


def test_send_into_existing_chat_flow(http_router):
    host, port, router = http_router
    router.routes[("POST", "/webhook/chat-hook-1")] = (200, {"output": "PONG from n8n"})
    result = remotes_core.operate(
        "n8n",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id="wfSupport:chat-hook-1",
    )
    assert result.ok is True
    assert result.http_status == 200
    assert result.data["response"] == "PONG from n8n"
    assert result.data["thread"] == "wfSupport:chat-hook-1"
    assert router.posts
    path, raw = router.posts[-1]
    assert path == "/webhook/chat-hook-1"
    payload = json.loads(raw.decode("utf-8"))
    assert payload["action"] == "sendMessage"
    assert payload["chatInput"] == "say pong"
    assert payload["sessionId"] == "wfSupport:chat-hook-1"


def test_send_falls_back_to_webhook_test(http_router):
    host, port, router = http_router
    router.routes[("POST", "/webhook-test/chat-hook-1")] = (200, {"text": "test-mode hi"})
    result = remotes_core.operate(
        "n8n",
        "send",
        prompt="hello",
        config=_cfg(host, port),
        session_id="wfSupport:chat-hook-1",
    )
    assert result.ok is True
    assert result.data["response"] == "test-mode hi"


def test_send_uses_x_n8n_api_key(http_router):
    host, port, _router = http_router
    spec = remotes_core.load_remote("n8n", _cfg(host, port))
    headers = remotes_core._auth_headers(spec)
    assert headers["X-N8N-API-KEY"] == "n8n-key"
    assert headers["Authorization"] == "Bearer n8n-key"


def test_harness_registered_and_callable(http_router):
    harness = get_harness("n8n")
    assert harness is not None
    assert harness.label == "n8n"
    assert harness.impl_id == "n8n"
    assert {h.impl_id for h in all_harnesses()} == set(REMOTE_IMPL_IDS)
    assert capabilities_for("n8n").sessions is True
    host, port, router = http_router
    router.routes[("GET", "/api/v1/workflows")] = (200, _WORKFLOWS)
    router.routes[("GET", "/healthz")] = (200, {"status": "ok"})
    spec = remotes_core.load_remote(
        "n8n", {"llm": {}, "remotes": {"n8n": {"base_url": f"http://{host}:{port}", "api_key": "k"}}}
    )
    result = harness.list(spec, timeout=3)
    assert result.ok is True
    assert sessions_from_operate(result)[0].id.startswith("wfSupport:")
    health = harness.health(spec, timeout=0.3, config=_cfg(host, port))
    assert health.ok is True
    assert health.state == "UP"


def test_session_id_passes_sanitize():
    from swarm.core.cli_sessions import sanitize_cli_session_id

    sid = "wfSupport:chat-hook-1"
    assert sanitize_cli_session_id(sid) == sid

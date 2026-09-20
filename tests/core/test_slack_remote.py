"""Unit tests for the Slack (NemoHermes) remote kind (REQ-814 / #97).

Covers: kind registries, opt-in add/persist, health (auth.test), list
(channel threads normalized to sessions with ``channel_id:thread_ts`` resume
keys), and send into an existing thread (never mints new threads). All HTTP
is mocked via a local threading HTTP server — no Slack, no LAN, no secrets.
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
        status, body = self.routes.get(key, (404, {"ok": False, "error": "no route"}))
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


def _cfg(host: str, port: int, **extra) -> dict:
    base = f"http://{host}:{port}"
    block = {"base_url": base, "api_key": "xoxb-test-token"}
    block.update(extra)
    return {"llm": {}, "remotes": {"slack": block}}


_CHANNELS = {
    "ok": True,
    "channels": [
        {"id": "C0123456789", "name": "general"},
        {"id": "C000EMPTY00", "name": "empty"},
    ],
}

_HISTORY_GENERAL = {
    "ok": True,
    "messages": [
        {
            "type": "message",
            "ts": "1712345678.123456",
            "thread_ts": "1712345678.123456",
            "text": "latest hacker news?",
            "reply_count": 3,
            "latest_reply": "1712345999.000111",
        },
        {
            "type": "message",
            "ts": "1712345800.000001",
            "text": "standalone channel message",
        },
        {
            "type": "message",
            "ts": "1712345900.222222",
            "thread_ts": "1712345900.222222",
            "text": "onboarding docs",
            "reply_count": 1,
        },
    ],
}

def test_slack_is_a_catalog_remote_kind():
    assert "slack" in REMOTE_IMPL_IDS
    assert is_remote_impl_id("slack")
    assert is_remote_impl_id("Slack")
    assert is_remote_impl_id("slackbot")
    assert is_remote_impl_id("nemo-slack")
    assert remotes_core.kind_label("slack") == "Slack"
    kinds = {k["id"]: k for k in remotes_core.list_remote_kinds()}
    row = kinds["slack"]
    assert row["kind"] == "remote"
    assert row["impl"] == "slack"
    assert row["label"] == "Slack"
    caps = row["capabilities"]
    assert caps["list"] is True and caps["send"] is True and caps["health"] is True
    assert caps["operate"] is False
    assert caps["sessions"] is True
    assert capabilities_for("slack").transport == "http"
    assert remotes_core.kind_of_instance("slack-2") == "slack"


def test_slack_is_opt_in_not_auto_placed(monkeypatch):
    for var in ("SLACK_BASE_URL", "SLACK_BOT_TOKEN", "OMB_BASE_URL", "HERMES_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert "slack" in remotes_core.OPT_IN_REMOTE_IDS
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.is_configured("slack", cfg) is False
    assert "slack" not in remotes_core.added_remote_ids(cfg)
    assert "slack" not in remotes_core.load_placed_members(cfg)
    assert remotes_core.operate("slack", "list", config=cfg).ok is False
    health = remotes_core.check_health("slack", config=cfg, timeout=0.2)
    assert health.state == "UNKNOWN"
    assert "not configured" in health.detail or remotes_core.NOT_ADDED_MARKER in health.detail


def test_add_and_remove_slack(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    monkeypatch.delenv("SLACK_BASE_URL", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    spec, path = remotes_core.add_remote(
        "slack",
        base_url="https://slack.com/api",
        api_key_env="SLACK_BOT_TOKEN",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "slack"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    # The serialiser keeps the default https port explicit.
    assert data["remotes"]["slack"]["base_url"] in ("https://slack.com/api", "https://slack.com:443/api")
    assert data["remotes"]["slack"]["api_key"] == "${SLACK_BOT_TOKEN}"
    assert data["remotes"]["slack"]["api_key_env"] == "SLACK_BOT_TOKEN"
    assert remotes_core.is_configured("slack", data)
    rid, _ = remotes_core.remove_remote("slack", config_path=cfg)
    assert rid == "slack"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "slack" not in (data.get("remotes") or {})


def test_env_bootstrap_shows_slack(monkeypatch):
    monkeypatch.setenv("SLACK_BASE_URL", "http://127.0.0.1:4391")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    ids = remotes_core.added_remote_ids({"llm": {}, "remotes": {}})
    assert "slack" in ids
    spec = remotes_core.load_remote("slack", {"llm": {}, "remotes": {}})
    assert spec.base_url == "http://127.0.0.1:4391"
    assert spec.source == "env"


def test_default_spec_is_sanitized_and_has_no_secret():
    spec = remotes_core.default_spec("slack")
    assert spec.base_url == "https://slack.com/api"
    assert "10.0.0." not in spec.base_url and "192.168." not in spec.base_url
    assert remotes_core._ENV_BASE["slack"] == "SLACK_BASE_URL"
    assert remotes_core._ENV_KEY["slack"] == "SLACK_BOT_TOKEN"
    assert spec.health_path == "/auth.test"
    assert spec.api_key == "${SLACK_BOT_TOKEN}"
    pub = spec.public_dict()
    assert pub["api_key_set"] is False
    assert pub["user_kind"] == "remote"
    assert pub["kind"] == "slack"


def test_list_threads_as_sessions(http_router):
    host, port, router = http_router
    router.routes[("POST", "/conversations.list")] = (200, _CHANNELS)
    router.routes[("POST", "/conversations.history")] = (200, _HISTORY_GENERAL)
    result = remotes_core.operate("slack", "list", config=_cfg(host, port))
    assert result.ok is True
    assert result.op == "list"
    assert result.http_status == 200
    sessions = sessions_from_operate(result)
    ids = [s.id for s in sessions]
    # Mock history is path-keyed (one payload for every channel). Both
    # channels therefore contribute the same two thread parents.
    assert "C0123456789:1712345678.123456" in ids
    assert "C0123456789:1712345900.222222" in ids
    assert all(":1712345800.000001" not in sid for sid in ids)
    first = sessions[0]
    assert first.title == "latest hacker news?"
    assert first.source == "slack"
    assert first.channel == "general"
    assert first.thread_ts == "1712345678.123456"
    # Standalone messages (no reply_count) are not sessions.
    assert all(s.thread_ts for s in sessions)


def test_list_auth_required_is_honest(http_router):
    host, port, router = http_router
    router.routes[("POST", "/conversations.list")] = (200, {"ok": False, "error": "invalid_auth"})
    result = remotes_core.operate("slack", "list", config=_cfg(host, port))
    assert result.ok is False
    assert "bot token" in result.detail
    assert "SLACK_BOT_TOKEN" in result.detail


def test_send_requires_existing_thread(http_router):
    host, port, _router = http_router
    result = remotes_core.operate(
        "slack", "send", prompt="hi", config=_cfg(host, port), session_id=None
    )
    assert result.ok is False
    assert result.gap == "slack_thread_required"
    assert "does not mint new" in result.detail
    result2 = remotes_core.operate(
        "slack", "send", prompt="hi", config=_cfg(host, port), session_id="C0123456789"
    )
    assert result2.ok is False
    assert result2.gap == "slack_thread_required"


def test_send_into_existing_thread(http_router):
    host, port, router = http_router
    router.routes[("POST", "/chat.postMessage")] = (
        200,
        {"ok": True, "ts": "1712346000.000333", "channel": "C0123456789"},
    )
    router.routes[("POST", "/conversations.replies")] = (
        200,
        {
            "ok": True,
            "messages": [
                {"ts": "1712345678.123456", "text": "latest hacker news?"},
                {"ts": "1712346000.000333", "text": "say pong"},
                {
                    "ts": "1712346001.000444",
                    "text": "PONG from NemoHermes",
                    "bot_id": "B0NEMOHERMES",
                },
            ],
        },
    )
    result = remotes_core.operate(
        "slack",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id="C0123456789:1712345678.123456",
    )
    assert result.ok is True
    assert result.http_status == 200
    assert result.data["response"] == "PONG from NemoHermes"
    assert result.data["thread"] == "C0123456789:1712345678.123456"


def test_send_posted_without_bot_reply_is_honest(http_router):
    host, port, router = http_router
    router.routes[("POST", "/chat.postMessage")] = (
        200,
        {"ok": True, "ts": "1712346000.000333", "channel": "C0123456789"},
    )
    router.routes[("POST", "/conversations.replies")] = (
        200,
        {
            "ok": True,
            "messages": [
                {"ts": "1712345678.123456", "text": "parent"},
                {"ts": "1712346000.000333", "text": "say pong"},
            ],
        },
    )
    result = remotes_core.operate(
        "slack",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id="C0123456789:1712345678.123456",
    )
    assert result.ok is True
    assert "no NemoHermes reply yet" in result.detail
    assert "response" not in result.data


def test_send_surfaces_slack_error(http_router):
    host, port, router = http_router
    router.routes[("POST", "/chat.postMessage")] = (
        200,
        {"ok": False, "error": "not_in_channel"},
    )
    result = remotes_core.operate(
        "slack",
        "send",
        prompt="say pong",
        config=_cfg(host, port),
        session_id="C0123456789:1712345678.123456",
    )
    assert result.ok is False
    assert "not_in_channel" in result.detail


def test_harness_registered_and_callable(http_router):
    harness = get_harness("slack")
    assert harness is not None
    assert harness.label == "Slack"
    assert harness.impl_id == "slack"
    assert {h.impl_id for h in all_harnesses()} == set(REMOTE_IMPL_IDS)
    assert capabilities_for("slack").sessions is True
    host, port, router = http_router
    router.routes[("POST", "/conversations.list")] = (200, _CHANNELS)
    router.routes[("POST", "/conversations.history")] = (200, _HISTORY_GENERAL)
    router.routes[("POST", "/auth.test")] = (
        200,
        {"ok": True, "team": "Nemo", "user": "open-swarm", "bot_id": "B0NEMO"},
    )
    spec = remotes_core.load_remote(
        "slack",
        {"llm": {}, "remotes": {"slack": {"base_url": f"http://{host}:{port}", "api_key": "k"}}},
    )
    result = harness.list(spec, timeout=3)
    assert result.ok is True
    assert sessions_from_operate(result)[0].id.startswith("C0123456789:")
    health = harness.health(spec, timeout=0.3, config=_cfg(host, port))
    assert health.ok is True
    assert health.state == "UP"


def test_session_id_passes_sanitize():
    from swarm.core.cli_sessions import sanitize_cli_session_id

    sid = "C0123456789:1712345678.123456"
    assert sanitize_cli_session_id(sid) == sid

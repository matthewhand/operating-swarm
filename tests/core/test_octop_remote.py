"""#1365 — Tencent Octop as one opt-in remote (HTTP health/list, WS send).

AgentTeams stay inside Octop. No live server: HTTP is a local router and
the dashboard socket is a fake connection.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from swarm.core import remotes as remotes_core
from swarm.core.remote_harness import (
    REMOTE_IMPL_IDS,
    capabilities_for,
    is_remote_impl_id,
    normalize_impl_id,
    sessions_from_operate,
)
from swarm.core.remote_impls.octop import (
    _octop_apply_frame,
    _octop_new_state,
    _octop_turn_text,
)
from functools import partial


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, dict | list | str]] = {}
    seen_auth: list[str] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        self.seen_auth.append(self.headers.get("Authorization") or "")
        status, body = self.routes.get((method, path), (404, {"error": "no route"}))
        payload = (
            json.dumps(body).encode("utf-8")
            if not isinstance(body, str)
            else body.encode()
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def log_message(self, *args) -> None:
        pass


class _FakeWS:
    def __init__(self, frames: list[str], sent: list[str]):
        self._frames = list(frames)
        self.sent = sent

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False

    def send(self, message: str) -> None:
        self.sent.append(message)

    def recv(self, timeout: float | None = None) -> str:
        if timeout is not None and timeout <= 0:
            raise TimeoutError("idle")
        if not self._frames:
            raise TimeoutError("idle")
        return self._frames.pop(0)

# NOTE: `serve_forever`'s default poll_interval is 0.5s. It parks in
# `selector.select(0.5)`, and `shutdown()` blocks on `__is_shut_down`, which
# the serve loop can only set on its next wake -- so each fixture teardown
# below paid a flat 500ms parked in a selector. Measured on this box:
# 500.6ms at the default, 50.2ms at 0.05, 10.1ms at 0.01. pytest
# --durations=0 attributes 106s of suite teardown to this pattern across 36
# files -- 28% of the suite's wall clock. A test-fixture cost, not a
# behaviour change: the thread still runs the same serve loop.

def _serve():
    server = HTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=partial(server.serve_forever, poll_interval=0.02), daemon=True)
    thread.start()
    return server


def _cfg(base: str, **extra) -> dict:
    block = {"base_url": base, "api_key": "octop-jwt-token", "kind": "octop"}
    block.update(extra)
    return {"llm": {}, "remotes": {"octop": block}}


def test_octop_is_a_catalog_remote_kind():
    assert "octop" in REMOTE_IMPL_IDS
    assert "octop" in remotes_core.REMOTE_IDS
    assert "octop" in remotes_core.OPT_IN_REMOTE_IDS
    assert is_remote_impl_id("octop")
    assert is_remote_impl_id("tencent-octop")
    assert normalize_impl_id("tencentoctop") == "octop"
    assert normalize_impl_id("octop-lab") == "octop"
    assert remotes_core.kind_of_instance("octop-lab") == "octop"
    assert remotes_core.kind_of_instance("tencent-octop") == "octop"
    assert remotes_core.kind_label("octop") == "Tencent Octop"
    spec = remotes_core.default_spec("octop")
    assert spec.health_path == "/api/health"
    # Documentation address, not 127.0.0.1:8088: on this host :8088 is a
    # llama.cpp server, so /api/health 404s against the wrong app.
    assert spec.base_url == "http://192.0.2.1:8088"
    assert remotes_core.is_placeholder_base_url(spec.base_url) is True
    caps = capabilities_for("octop")
    assert caps.sessions is True
    assert caps.server_managed_context is True
    assert caps.elicit_questions is False
    assert caps.operate is False
    assert caps.routines is False
    kinds = {k["id"]: k for k in remotes_core.list_remote_kinds()}
    assert kinds["octop"]["kind"] == "remote"
    assert kinds["octop"]["label"] == "Tencent Octop"


def test_octop_is_opt_in_not_auto_placed(monkeypatch):
    monkeypatch.delenv("OCTOP_BASE_URL", raising=False)
    monkeypatch.delenv("OCTOP_API_KEY", raising=False)
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.is_configured("octop", cfg) is False
    assert "octop" not in remotes_core.load_placed_members(cfg)
    assert remotes_core.operate("octop", "list", config=cfg).ok is False
    health = remotes_core.check_health("octop", config=cfg, timeout=0.2)
    assert health.state == "UNKNOWN"


def test_add_and_remove_octop(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    monkeypatch.delenv("OCTOP_BASE_URL", raising=False)
    monkeypatch.delenv("OCTOP_API_KEY", raising=False)
    spec, path = remotes_core.add_remote(
        "octop",
        base_url="http://127.0.0.1:8088",
        api_key_env="OCTOP_API_KEY",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "octop"
    assert spec.kind == "octop"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["octop"]["api_key"] == "${OCTOP_API_KEY}"
    rid, _ = remotes_core.remove_remote("octop", config_path=cfg)
    assert rid == "octop"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "octop" not in (data.get("remotes") or {})


def test_health_and_list_agents_with_threads():
    server = _serve()
    try:
        host, port = server.server_address
        _Router.routes = {
            ("GET", "/api/health"): (
                200,
                {"ok": True, "db": True, "agents_running": 1},
            ),
            ("GET", "/api/agents"): (
                200,
                [
                    {
                        "id": 12,
                        "agent_id": "main",
                        "name": "Main",
                        "kind": "expert",
                        "default_model": "qwen",
                    },
                    {
                        "agent_id": "crew",
                        "name": "Crew",
                        "kind": "team",
                        "default_model": "qwen",
                    },
                ],
            ),
            ("GET", "/api/agents/main/threads"): (
                200,
                [
                    {
                        "thread_id": "thread1",
                        "title": "Hello",
                        "last_active": "2026-09-27T00:00:00Z",
                    }
                ],
            ),
            ("GET", "/api/agents/crew/threads"): (200, []),
        }
        _Router.seen_auth = []
        cfg = _cfg(f"http://{host}:{port}")
        health = remotes_core.check_health("octop", config=cfg, timeout=2.0)
        assert health.ok is True
        assert health.state == "UP"
        listed = remotes_core.operate("octop", "list", config=cfg, timeout=3.0)
        assert listed.ok is True
        assert listed.data["rows_are"] == "agents"
        assert listed.data["resume_key"] == "agent_id:thread_id"
        kinds = {row["agent_id"]: row["kind"] for row in listed.data["agents"]}
        assert kinds == {"main": "expert", "crew": "team"}
        # Navbar pickers send `id`. Octop's numeric primary key must not win.
        assert listed.data["agents"][0]["id"] == "main"
        sessions = sessions_from_operate(listed)
        assert [s.id for s in sessions] == ["main:thread1"]
        assert any(header == "Bearer octop-jwt-token" for header in _Router.seen_auth)
    finally:
        server.shutdown()
        server.server_close()
        _Router.routes = {}
        _Router.seen_auth = []


def test_list_auth_gap_names_the_env_var():
    server = _serve()
    try:
        host, port = server.server_address
        _Router.routes = {("GET", "/api/agents"): (401, {"error": "auth"})}
        cfg = _cfg(f"http://{host}:{port}", api_key="")
        listed = remotes_core.operate("octop", "list", config=cfg, timeout=2.0)
        assert listed.ok is False
        assert listed.gap == "octop_auth"
        assert "OCTOP_API_KEY" in listed.detail
        assert "api_key" not in listed.detail or "OCTOP_API_KEY" in listed.detail
    finally:
        server.shutdown()
        server.server_close()
        _Router.routes = {}


def test_frame_reducer_keeps_host_text_and_stops_on_host_done():
    state = _octop_new_state()
    frames = [
        {"type": "token", "content": "mem", "agent_id": "crew"},
        {"type": "done", "agent_id": "crew"},
        {"type": "token", "content": "Hello ", "agent_id": "main"},
        {"type": "token", "content": "there"},
        {"type": "done", "team_wrapup": True},
        {"type": "done", "thread_id": "thread9"},
        {"type": "token", "content": "IGNORED"},
    ]
    # A member done and a team_wrapup done must not seal the host turn.
    for frame in frames[:5]:
        _octop_apply_frame(state, frame, "main")
        assert state["done"] is False
    assert _octop_turn_text(state) == "Hello there"
    _octop_apply_frame(state, frames[5], "main")
    assert state["done"] is True
    assert state["thread_id"] == "thread9"
    _octop_apply_frame(state, frames[6], "main")
    assert _octop_turn_text(state) == "Hello there"


def test_frame_reducer_hitl_and_error():
    hitl = _octop_new_state()
    _octop_apply_frame(
        hitl, {"type": "hitl_required", "request": {"tools": ["rm"]}}, "main"
    )
    assert hitl["gap"] == "octop_approval_required"
    assert hitl["done"] is True
    err = _octop_new_state()
    _octop_apply_frame(err, {"type": "error", "message": "model down"}, "main")
    assert err["gap"] == "octop_reply_failed"
    assert "model down" in err["error"]


def test_send_collects_ws_tokens(monkeypatch):
    sent: list[str] = []
    frames = [
        json.dumps({"type": "turn_status", "thread_id": "thread1", "active": True}),
        json.dumps({"type": "token", "content": "pong"}),
        json.dumps({"type": "done", "thread_id": "thread1"}),
    ]

    def _connect(url: str, _timeout: float):
        assert "token=octop-jwt-token" in url
        assert "/api/agents/main/chat/ws" in url
        assert url.startswith("ws://")
        return _FakeWS(frames, sent)

    monkeypatch.setattr("swarm.core.remote_impls.octop._octop_connect", _connect)
    cfg = _cfg("http://127.0.0.1:8088")
    sent_result = remotes_core.operate(
        "octop",
        "send",
        prompt="ping",
        target="main",
        config=cfg,
        timeout=2.0,
    )
    assert sent_result.ok is True
    assert sent_result.data["text"] == "pong"
    assert sent_result.data["session_id"] == "main:thread1"
    body = json.loads(sent[0])
    assert body == {"type": "user_turn", "text": "ping"}
    assert "octop-jwt-token" not in sent_result.detail


def test_send_resumes_thread_and_reports_approval(monkeypatch):
    sent: list[str] = []

    def _connect(_url: str, _timeout: float):
        return _FakeWS(
            [json.dumps({"type": "hitl_required", "request": {}})],
            sent,
        )

    monkeypatch.setattr("swarm.core.remote_impls.octop._octop_connect", _connect)
    cfg = _cfg("http://127.0.0.1:8088")
    result = remotes_core.operate(
        "octop",
        "send",
        prompt="go",
        session_id="main:thread1",
        config=cfg,
        timeout=2.0,
    )
    assert result.ok is False
    assert result.gap == "octop_approval_required"
    body = json.loads(sent[0])
    assert body["thread_id"] == "thread1"
    assert result.data["session_id"] == "main:thread1"


def test_list_query_matches_a_thread_title_when_the_agent_does_not():
    server = _serve()
    try:
        host, port = server.server_address
        _Router.routes = {
            ("GET", "/api/agents"): (
                200,
                [{"agent_id": "main", "name": "Main", "kind": "expert"}],
            ),
            ("GET", "/api/agents/main/threads"): (
                200,
                [{"thread_id": "thread1", "title": "Hello"}],
            ),
        }
        cfg = _cfg(f"http://{host}:{port}")
        listed = remotes_core.operate(
            "octop", "list", query="Hello", config=cfg, timeout=3.0
        )
        assert listed.ok is True
        assert listed.data["agents"] == []
        assert [row["id"] for row in listed.data["sessions"]] == ["main:thread1"]
    finally:
        server.shutdown()
        server.server_close()
        _Router.routes = {}


def test_send_resumes_when_only_the_target_is_the_resume_key(monkeypatch):
    sent: list[str] = []

    def _connect(url: str, _timeout: float):
        assert "/api/agents/main/chat/ws" in url
        return _FakeWS(
            [
                json.dumps({"type": "token", "content": "resumed"}),
                json.dumps({"type": "done", "thread_id": "thread1"}),
            ],
            sent,
        )

    monkeypatch.setattr("swarm.core.remote_impls.octop._octop_connect", _connect)
    cfg = _cfg("http://127.0.0.1:8088")
    result = remotes_core.operate(
        "octop",
        "send",
        prompt="go",
        target="main:thread1",
        config=cfg,
        timeout=2.0,
    )
    assert result.ok is True
    assert result.data["thread_id"] == "thread1"
    assert json.loads(sent[0])["thread_id"] == "thread1"


def test_list_strips_a_bearer_prefix_from_the_env_token():
    server = _serve()
    try:
        host, port = server.server_address
        _Router.routes = {("GET", "/api/agents"): (200, [])}
        _Router.seen_auth = []
        cfg = _cfg(f"http://{host}:{port}", api_key="Bearer octop-jwt-token")
        listed = remotes_core.operate("octop", "list", config=cfg, timeout=2.0)
        assert listed.ok is True
        assert _Router.seen_auth == ["Bearer octop-jwt-token"]
    finally:
        server.shutdown()
        server.server_close()
        _Router.routes = {}
        _Router.seen_auth = []


def test_send_requires_agent_and_redacts_token(monkeypatch):
    cfg = _cfg("http://127.0.0.1:8088")
    missing = remotes_core.operate(
        "octop", "send", prompt="hi", config=cfg, timeout=1.0
    )
    assert missing.ok is False
    assert missing.gap == "octop_agent_required"

    def _boom(url: str, _timeout: float):
        raise RuntimeError(f"dial failed {url}")

    monkeypatch.setattr("swarm.core.remote_impls.octop._octop_connect", _boom)
    failed = remotes_core.operate(
        "octop", "send", prompt="hi", target="main", config=cfg, timeout=1.0
    )
    assert failed.ok is False
    assert failed.gap == "octop_reply_failed"
    assert "octop-jwt-token" not in failed.detail
    assert "redacted" in failed.detail


def test_send_uses_configured_agent_when_target_is_the_remote_name(monkeypatch):
    sent: list[str] = []

    def _connect(url: str, _timeout: float):
        assert "/api/agents/main/chat/ws" in url
        return _FakeWS(
            [
                json.dumps({"type": "token", "content": "ok"}),
                json.dumps({"type": "done"}),
            ],
            sent,
        )

    monkeypatch.setattr("swarm.core.remote_impls.octop._octop_connect", _connect)
    cfg = _cfg("http://127.0.0.1:8088", agent="main")
    result = remotes_core.operate(
        "octop", "send", prompt="hi", target="octop", config=cfg, timeout=1.0
    )
    assert result.ok is True
    assert result.data["agent_id"] == "main"
    assert result.data["text"] == "ok"


def test_registry_routes_octop():
    from swarm.remotes.octop import OctopAdapter
    from swarm.remotes.registry import REMOTE_ADAPTER_REGISTRY, create_remote_adapter

    assert REMOTE_ADAPTER_REGISTRY["octop"] is OctopAdapter
    spec = remotes_core.RemoteSpec(
        id="octop",
        title="Tencent Octop",
        host_label="octop",
        base_url="http://127.0.0.1:8088",
        kind="octop",
    )
    assert isinstance(create_remote_adapter(spec), OctopAdapter)

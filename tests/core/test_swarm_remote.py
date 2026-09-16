"""First-class nested Operating Swarm (OS-peer) remote — stubbed peer, no live LAN."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from swarm.core import remotes as remotes_core
from swarm.core.agent_kind import classify_agent_kind, resolve_chat_blueprint_id
from swarm.core.remote_harness import is_remote_impl_id, normalize_impl_id
from swarm.core.swarm_peer import (
    KIND_LABEL,
    PEER_NICK,
    extract_completion_text,
    health_payload,
    members_from_agents,
    peer_version_warning,
    version_string,
)


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, dict | list | str]] = {}
    captured_auth: list[str] = []

    def _handle(self, method: str) -> None:
        self.captured_auth.append(self.headers.get("Authorization") or "")
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
    _Router.captured_auth = []
    server = HTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield host, port, _Router
    server.shutdown()
    _Router.routes = {}
    _Router.captured_auth = []


def _cfg(host: str, port: int, instance: str = "swarm") -> dict:
    return {
        "llm": {},
        "remotes": {
            instance: {
                "kind": "swarm",
                "base_url": f"http://{host}:{port}",
                "api_key": "peer-secret",
            }
        },
    }


def test_os_peer_branding_and_aliases():
    assert remotes_core.kind_label("swarm") == KIND_LABEL
    assert remotes_core.kind_label("os-peer") == KIND_LABEL
    assert remotes_core.kind_label("operating-swarm") == KIND_LABEL
    assert remotes_core.kind_label("open-swarm") == KIND_LABEL
    spec = remotes_core.load_remote("os-peer", {"llm": {}, "remotes": {}})
    assert spec.id == "swarm"
    assert spec.kind == "swarm"
    assert spec.title == PEER_NICK
    assert spec.public_dict()["member"]["talk"] == "consult_swarm"
    assert spec.public_dict()["label"] == KIND_LABEL


def test_named_instances_and_env_slugs(tmp_path: Path, monkeypatch):
    """Named OS-peers reuse the catalog named-instance env slug convention."""
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.setenv("SWARM_2_BASE_URL", "http://127.0.0.1:8001")
    monkeypatch.setenv("SWARM_2_API_KEY", "peer-secret-2")
    spec, _ = remotes_core.persist_remote(
        "swarm-2",
        api_key_env="SWARM_2_API_KEY",
        config_path=cfg,
    )
    assert spec.id == "swarm-2"
    assert spec.kind == "swarm"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["swarm-2"]["kind"] == "swarm"
    assert data["remotes"]["swarm-2"]["api_key"] == "${SWARM_2_API_KEY}"
    loaded = remotes_core.load_remote("swarm-2", data)
    assert loaded.base_url == "http://127.0.0.1:8001"
    assert loaded.api_key_env == "SWARM_2_API_KEY"
    assert loaded.api_key == "peer-secret-2"
    gpu, _ = remotes_core.persist_remote(
        "swarm_gpu",
        base_url="http://127.0.0.1:8002",
        config_path=cfg,
    )
    assert gpu.id == "swarm_gpu"
    assert gpu.kind == "swarm"
    configured = remotes_core.load_configured_remotes(json.loads(cfg.read_text(encoding="utf-8")))
    assert set(configured) >= {"swarm-2", "swarm_gpu"}


def test_custom_instance_id_with_explicit_kind(tmp_path: Path):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    spec, _ = remotes_core.persist_remote(
        "lab-swarm",
        kind="swarm",
        base_url="http://127.0.0.1:9",
        api_key="${CHANGE_ME}",
        config_path=cfg,
    )
    assert spec.id == "lab-swarm"
    assert spec.kind == "swarm"
    assert (
        remotes_core.kind_of_instance("lab-swarm", json.loads(cfg.read_text(encoding="utf-8")))
        == "swarm"
    )


def test_refuse_self_loop_on_named_instance(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.setenv("PORT", "8000")
    monkeypatch.delenv("SWARM_LISTEN_URL", raising=False)
    with pytest.raises(remotes_core.RemoteError, match="own remote"):
        remotes_core.persist_remote(
            "swarm-2",
            base_url="http://127.0.0.1:8000",
            config_path=cfg,
        )


def test_classifier_named_os_peer_is_remote_bare_swarm_is_api():
    assert classify_agent_kind("swarm") == "api"
    assert classify_agent_kind("open-swarm") == "remote"
    assert classify_agent_kind("os-peer") == "remote"
    assert classify_agent_kind("remote:swarm") == "remote"
    # Underscore ids are named instances; hyphen ``swarm-*`` stays designer
    # slug space (address it as ``remote:swarm-2``).
    assert classify_agent_kind("swarm_gpu") == "remote"
    assert classify_agent_kind("remote:swarm-2") == "remote"
    assert not is_remote_impl_id("swarm")
    assert not is_remote_impl_id("swarm-2")
    assert is_remote_impl_id("os-peer")
    assert is_remote_impl_id("swarm_gpu")
    assert normalize_impl_id("swarm_gpu") == "swarm"
    assert normalize_impl_id("os-peer") == "swarm"
    assert resolve_chat_blueprint_id("remote:swarm") == "remote_harness"
    assert resolve_chat_blueprint_id("remote:swarm-2") == "remote_harness"
    assert resolve_chat_blueprint_id("os-peer") == "remote_harness"


def test_list_sessions_teams_agents_and_send_text(http_router, monkeypatch):
    host, port, router = http_router
    monkeypatch.setenv("SWARM_REMOTE_API_KEY", "peer-secret")
    router.routes = {
        ("GET", "/health"): (
            200,
            {"status": "ok", "app": "operating-swarm", "version": "0.5.4", "peer": "OS-peer"},
        ),
        (
            "GET",
            "/v1/blueprints/",
        ): (
            200,
            {"object": "list", "data": [{"id": "echo", "object": "blueprint", "name": "echo"}]},
        ),
        (
            "GET",
            "/api/sessions/",
        ): (200, {"sessions": [{"id": "sess-1", "agent": "echo"}]}),
        (
            "GET",
            "/v1/agent-team/",
        ): (200, {"object": "agent_team", "members": ["hermes"]}),
        (
            "POST",
            "/v1/chat/completions/",
        ): (
            200,
            {
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "pong from child"}}],
            },
        ),
    }
    cfg = _cfg(host, port)
    health = remotes_core.check_health("swarm", config=cfg, timeout=2.0)
    assert health.ok is True
    assert health.state == "UP"
    listed = remotes_core.operate("swarm", "list", config=cfg)
    assert listed.ok is True
    assert listed.data["agents"][0]["id"] == "echo"
    assert listed.data["sessions"][0]["id"] == "sess-1"
    assert listed.data["teams"] == ["hermes"]
    assert listed.data["members"][0]["kind"] == "swarm"
    sent = remotes_core.operate(
        "swarm", "send", prompt="ping", target="echo", config=cfg
    )
    assert sent.ok is True
    assert sent.data["text"] == "pong from child"
    assert any(header == "Bearer peer-secret" for header in router.captured_auth)


def test_named_instance_list_send(http_router):
    host, port, router = http_router
    router.routes = {
        ("GET", "/v1/blueprints/"): (
            200,
            {"object": "list", "data": [{"id": "support"}]},
        ),
        ("POST", "/v1/chat/completions/"): (
            200,
            {"choices": [{"message": {"content": "from swarm-2"}}]},
        ),
    }
    cfg = _cfg(host, port, instance="swarm-2")
    listed = remotes_core.operate("swarm-2", "list", config=cfg)
    assert listed.ok is True
    assert listed.remote == "swarm-2"
    sent = remotes_core.operate(
        "swarm-2", "send", prompt="hi", target="support", config=cfg
    )
    assert sent.ok is True
    assert sent.remote == "swarm-2"
    assert sent.data["text"] == "from swarm-2"


def test_auth_401_is_honest(http_router):
    host, port, router = http_router
    router.routes = {
        ("GET", "/v1/blueprints/"): (401, {"error": "auth"}),
        ("POST", "/v1/chat/completions/"): (401, {"error": "auth"}),
    }
    cfg = _cfg(host, port)
    listed = remotes_core.operate("swarm", "list", config=cfg)
    assert listed.ok is False
    assert "Bearer" in listed.detail
    sent = remotes_core.operate("swarm", "send", prompt="hi", target="echo", config=cfg)
    assert sent.ok is False
    assert "API_AUTH_TOKEN" in sent.detail


def test_incompatible_peer_version_warns(http_router, monkeypatch):
    host, port, router = http_router
    router.routes = {
        ("GET", "/health"): (200, {"status": "ok", "version": "9.0.0", "app": "operating-swarm"}),
    }
    monkeypatch.setattr("swarm.core.app_version.get_app_version", lambda: "0.5.4")
    cfg = _cfg(host, port)
    health = remotes_core.check_health("swarm", config=cfg, timeout=2.0)
    assert health.ok is True
    assert health.warning
    assert "incompatible" in health.warning
    assert "9.0.0" in health.detail


def test_missing_peer_version_warns(http_router, monkeypatch):
    host, port, router = http_router
    router.routes = {("GET", "/health"): (200, {"status": "ok"})}
    monkeypatch.setattr("swarm.core.app_version.get_app_version", lambda: "0.5.4")
    health = remotes_core.check_health("swarm", config=_cfg(host, port), timeout=2.0)
    assert health.ok is True
    assert "did not advertise" in (health.warning or "")


def test_peer_helpers():
    assert version_string({"status": "ok", "version": "0.5.4"}) == "0.5.4"
    assert peer_version_warning("", "0.5.4")
    assert "incompatible" in peer_version_warning("9.1.0", "0.5.4")
    assert peer_version_warning("0.9.1", "0.5.4") == ""
    assert extract_completion_text(
        {"choices": [{"message": {"content": " hi "}}]}
    ) == "hi"
    members = members_from_agents([{"id": "echo", "name": "Echo"}], remote="swarm-2")
    assert members[0]["kind"] == "swarm"
    assert members[0]["remote"] == "swarm-2"
    payload = health_payload("0.5.4")
    assert payload["status"] == "ok"
    assert payload["app"] == "operating-swarm"
    assert payload["version"] == "0.5.4"
    assert payload["peer"] == PEER_NICK


def test_agent_first_send_renders_child_text():
    from swarm.blueprints.remote_harness.blueprint_remote_harness import _render_operate
    from swarm.core.remotes import OperateResult

    rendered = _render_operate(
        OperateResult(
            remote="swarm",
            op="send",
            ok=True,
            detail="sent",
            data={"text": "pong from child", "response": {"choices": []}},
        )
    )
    assert rendered == "pong from child"


@pytest.mark.asyncio
async def test_seat_chat_sends_to_os_peer(monkeypatch):
    from swarm.blueprints.remote_harness.blueprint_remote_harness import (
        RemoteHarnessBlueprint,
    )
    from swarm.core.remotes import OperateResult

    calls: list[tuple] = []

    def fake_operate(name, op, **kwargs):
        calls.append((name, op, kwargs.get("prompt")))
        return OperateResult(
            remote=name,
            op=op,
            ok=True,
            detail="sent",
            data={"text": "hello from OS-peer"},
        )

    monkeypatch.setattr(
        "swarm.blueprints.remote_harness.blueprint_remote_harness.remotes_core.operate",
        fake_operate,
    )
    bp = RemoteHarnessBlueprint(config={"llm": {}})
    bp.set_params({"remote_id": "swarm"})
    chunks = [c async for c in bp.run([{"role": "user", "content": "ping the child"}])]
    text = ""
    for chunk in chunks:
        msgs = chunk.get("messages") if isinstance(chunk, dict) else None
        if msgs:
            text = msgs[0].get("content") or text
    assert calls == [("swarm", "send", "ping the child")]
    assert text == "hello from OS-peer"

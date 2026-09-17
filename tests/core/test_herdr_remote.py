"""REQ-64: Herdr is an opt-in remotes kind. No live LAN. No tokens."""

from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from swarm.core import remotes as remotes_core
from swarm.herdr import (
    HERDR_NOT_CONFIGURED,
    HerdrClient,
    cli_remote_from_base,
    is_localhost_base,
)
from swarm.herdr.remote import KIND_ID


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


def test_kind_id_is_herdr():
    assert KIND_ID == "herdr"
    assert "herdr" in remotes_core.REMOTE_IDS
    assert "herdr" in remotes_core.OPT_IN_REMOTE_IDS
    labels = {item["id"]: item["label"] for item in remotes_core.remote_kind_catalog()}
    assert labels["herdr"] == "Herdr"
    assert labels["omb"] == "OpenMousBot"


def test_unconfigured_herdr_is_absent_and_errors():
    cfg = {"llm": {}, "remotes": {}}
    assert "herdr" not in remotes_core.load_all_remotes(cfg)
    assert remotes_core.load_placed_members(cfg) == ["hermes", "omb", "rakazo"]
    with pytest.raises(remotes_core.RemoteError, match="not configured"):
        remotes_core.load_remote("herdr", cfg)
    health = remotes_core.check_health("herdr", config=cfg, timeout=0.2)
    assert health.ok is False
    assert "not configured" in health.detail
    assert "10.0.0." not in health.detail
    listed = remotes_core.operate("herdr", "list", config=cfg)
    assert listed.ok is False
    assert "not configured" in listed.detail


def test_herdr_default_is_not_a_lan_host():
    spec = remotes_core.default_spec("herdr")
    assert spec.base_url == ""
    assert "10.0.0." not in spec.base_url
    assert "10.0.0." not in spec.notes or "No baked LAN" in spec.notes


def test_persist_herdr_then_it_appears(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    spec, path = remotes_core.persist_remote(
        "herdr",
        base_url="http://127.0.0.1:9",
        api_key="${HERDR_API_KEY}",
        config_path=cfg,
    )
    assert path == cfg
    assert spec.id == "herdr"
    assert spec.base_url == "http://127.0.0.1:9"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["remotes"]["herdr"]["base_url"] == "http://127.0.0.1:9"
    assert data["remotes"]["herdr"]["api_key"] == "${HERDR_API_KEY}"
    assert "sk-" not in cfg.read_text(encoding="utf-8")
    loaded = remotes_core.load_all_remotes(data)
    assert "herdr" in loaded
    pub = loaded["herdr"].public_dict()
    assert pub["kind"] == "herdr"
    assert pub["api_key_set"] is False


def test_cli_remote_uses_configured_base_localhost_omits_flag():
    assert is_localhost_base("http://127.0.0.1:9")
    assert cli_remote_from_base("http://127.0.0.1:9") == ""
    assert cli_remote_from_base("http://localhost:9") == ""
    assert cli_remote_from_base("http://herdr.example.test:9") == "http://herdr.example.test:9"
    with pytest.raises(ValueError, match="not configured"):
        cli_remote_from_base("")


def test_from_remote_config_uses_configured_base(monkeypatch):
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        return __import__("subprocess").CompletedProcess(argv, 0, '{"ok":true}', "")

    cfg = {"remotes": {"herdr": {"base_url": "http://127.0.0.1:9"}}}
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    HerdrClient.from_remote_config(cfg, runner=runner).agent_list()
    assert calls[0] == ["herdr", "agent", "list"]
    assert "--remote" not in calls[0]

    calls.clear()
    from swarm.herdr.ssh import SSHNotConfiguredError

    cfg = {"remotes": {"herdr": {"base_url": "http://herdr.example.test:9"}}}
    with pytest.raises(SSHNotConfiguredError, match="SSH-shaped"):
        HerdrClient.from_remote_config(cfg, runner=runner)

    with pytest.raises(remotes_core.RemoteError, match="not configured"):
        HerdrClient.from_remote_config({"remotes": {}}, runner=runner)


def test_herdr_health_and_list_stub_http(http_router, monkeypatch):
    host, port, router = http_router
    router.routes = {
        ("GET", "/health"): (200, {"status": "ok", "app": "herdr"}),
        (
            "GET",
            "/agents",
        ): (
            200,
            {"agents": [{"pane_id": "w3:p1", "state": "idle", "name": "grok"}]},
        ),
    }
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    cfg = {
        "llm": {},
        "remotes": {"herdr": {"base_url": f"http://{host}:{port}", "api_key": "${HERDR_API_KEY}"}},
    }
    health = remotes_core.check_health("herdr", config=cfg, timeout=2.0)
    assert health.ok is True
    assert health.state == "UP"
    listed = remotes_core.operate("herdr", "list", config=cfg)
    assert listed.ok is True
    names = [item["name"] for item in listed.data["members"]]
    assert names == ["w3:p1"]
    assert listed.data["members"][0]["kind"] == "herdr"


def test_operate_send_uses_from_remote_config_exact_argv(monkeypatch):
    """C-H4: operate send is HerdrClient.from_remote_config, not a stub / 'prompt' in argv."""
    import subprocess
    from unittest.mock import patch

    calls: list[list[str]] = []
    from_remote_calls: list[object] = []

    def runner(argv, timeout=None):
        del timeout
        calls.append(list(argv))
        if "get" in argv:
            return subprocess.CompletedProcess(argv, 0, '{"result":{"state":"idle"}}', "")
        if "read" in argv:
            return subprocess.CompletedProcess(argv, 0, "HERDR_PONG", "")
        return subprocess.CompletedProcess(argv, 0, '{"type":"agent_prompted"}', "")

    real = HerdrClient.from_remote_config

    def spy(config=None, **kwargs):
        from_remote_calls.append(config)
        kwargs.setdefault("runner", runner)
        return real(config, **kwargs)

    cfg = {"remotes": {"herdr": {"herdr_mode": "local"}}}
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    monkeypatch.delenv("HERDR_SSH_HOST", raising=False)
    with patch.object(HerdrClient, "from_remote_config", side_effect=spy):
        sent = remotes_core.operate(
            "herdr",
            "send",
            prompt="HERDR_PING_OK",
            target="w3:p1",
            config=cfg,
            timeout=1.0,
        )
    assert sent.ok is True
    assert sent.data["text"] == "HERDR_PONG"
    assert from_remote_calls == [cfg]
    assert calls == [
        ["herdr", "agent", "get", "w3:p1"],
        [
            "herdr",
            "agent",
            "prompt",
            "w3:p1",
            "HERDR_PING_OK",
            "--wait",
            # #470: idle | done | blocked — a turn that finishes settles in
            # ``done``, so ``--until idle`` alone could only expire.
            "--until",
            "idle",
            "--until",
            "done",
            "--until",
            "blocked",
            "--timeout",
            "1000",
        ],
        ["herdr", "agent", "read", "w3:p1", "--source", "recent", "--format", "text"],
    ]
    assert "--remote" not in calls[1]
    assert "gap" not in (sent.detail or "").lower()
    assert getattr(sent, "gap", None) in (None, "")


def _timed_out_prompt_runner(state: dict, *, moved_by: int, text: str):
    """Runner where ``agent prompt --wait`` expires but the pane may have moved.

    Live shape (#470): ``{"error":{"code":"timeout","message":"timed out
    waiting for agent status"}}`` on the prompt, while ``agent get`` later
    reports an advanced ``state_change_seq``.
    """

    def runner(argv, timeout=None):
        del timeout
        if "prompt" in argv:
            state["seq"] += moved_by
            return subprocess.CompletedProcess(
                argv,
                1,
                '{"error":{"code":"timeout","message":"timed out waiting for agent status"}}',
                "timed out waiting for agent status",
            )
        if "get" in argv:
            return subprocess.CompletedProcess(
                argv,
                0,
                json.dumps(
                    {"result": {"agent": {"agent_status": "done", "state_change_seq": state["seq"]}}}
                ),
                "",
            )
        if "read" in argv:
            return subprocess.CompletedProcess(argv, 0, text, "")
        return subprocess.CompletedProcess(argv, 0, "{}", "")

    return runner


def _run_herdr_send_with_runner(runner):
    from unittest.mock import patch

    real = HerdrClient.from_remote_config

    def spy(config=None, **kwargs):
        kwargs.setdefault("runner", runner)
        return real(config, **kwargs)

    cfg = {"remotes": {"herdr": {"herdr_mode": "local"}}}
    with patch.object(HerdrClient, "from_remote_config", side_effect=spy):
        return remotes_core.operate(
            "herdr",
            "send",
            prompt="HERDR_PING_OK",
            target="w3:p5",
            config=cfg,
            timeout=1.0,
        )


def test_herdr_send_recovers_the_reply_when_the_stopped_wait_expires(monkeypatch):
    """#470: a completed turn was reported as a timeout and its reply discarded."""
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    monkeypatch.delenv("HERDR_SSH_HOST", raising=False)
    state = {"seq": 100}
    sent = _run_herdr_send_with_runner(
        _timed_out_prompt_runner(state, moved_by=900, text="HERDR-PROOF-OK")
    )
    assert sent.ok is True
    assert sent.data["text"] == "HERDR-PROOF-OK"
    assert sent.data["target"] == "w3:p5"
    assert "recovered" in sent.detail
    assert getattr(sent, "gap", None) in (None, "")


def test_herdr_send_timeout_without_state_movement_stays_an_honest_gap(monkeypatch):
    """No state movement means nothing ran — never present stale pane text."""
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    monkeypatch.delenv("HERDR_SSH_HOST", raising=False)
    state = {"seq": 100}
    sent = _run_herdr_send_with_runner(
        _timed_out_prompt_runner(state, moved_by=0, text="STALE PREVIOUS REPLY")
    )
    assert sent.ok is False
    assert sent.gap == "herdr_reply_timeout"
    assert "text" not in (sent.data or {})
    assert "timed out" in sent.detail


def test_herdr_send_still_refuses_a_blocked_pane(monkeypatch):
    """The blocked guard moved out of ``check_blocked`` into the shared agent get."""
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    monkeypatch.delenv("HERDR_SSH_HOST", raising=False)

    def runner(argv, timeout=None):
        del timeout
        if "get" in argv:
            return subprocess.CompletedProcess(
                argv, 0, '{"result":{"agent":{"agent_status":"blocked"}}}', ""
            )
        raise AssertionError(f"must not submit to a blocked pane: {argv}")

    sent = _run_herdr_send_with_runner(runner)
    assert sent.ok is False
    assert "blocked" in sent.detail


def test_operate_list_uses_from_remote_config_exact_argv(monkeypatch):
    import subprocess
    from unittest.mock import patch

    calls: list[list[str]] = []
    from_remote_calls: list[object] = []

    def runner(argv, timeout=None):
        del timeout
        calls.append(list(argv))
        if argv[-2:] == ["agent", "list"]:
            return subprocess.CompletedProcess(
                argv, 0, '{"agents":[{"pane_id":"w3:p1","state":"idle"}]}', ""
            )
        if argv[-2:] == ["workspace", "list"]:
            return subprocess.CompletedProcess(argv, 0, '{"workspaces":[]}', "")
        return subprocess.CompletedProcess(argv, 0, "{}", "")

    real = HerdrClient.from_remote_config

    def spy(config=None, **kwargs):
        from_remote_calls.append(config)
        kwargs.setdefault("runner", runner)
        return real(config, **kwargs)

    cfg = {"remotes": {"herdr": {"herdr_mode": "local"}}}
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    with patch.object(HerdrClient, "from_remote_config", side_effect=spy):
        listed = remotes_core.operate("herdr", "list", config=cfg)
    assert listed.ok is True
    assert from_remote_calls == [cfg]
    assert calls == [
        ["herdr", "agent", "list"],
        ["herdr", "workspace", "list"],
    ]


def test_herdr_health_and_list_stub_http_sends_configured_auth(http_router, monkeypatch):
    host, port, router = http_router
    captured_auth: list[str] = []
    orig_handle = router._handle

    def _handle(self, method: str) -> None:
        captured_auth.append(self.headers.get("Authorization") or "")
        orig_handle(self, method)

    monkeypatch.setattr(router, "_handle", _handle)
    router.routes = {
        ("GET", "/health"): (200, {"status": "ok", "app": "herdr"}),
        (
            "GET",
            "/agents",
        ): (
            200,
            {"agents": [{"pane_id": "w3:p1", "state": "idle", "name": "grok"}]},
        ),
    }
    monkeypatch.setenv("HERDR_API_KEY", "test-herdr-token")
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    cfg = {
        "llm": {},
        "remotes": {"herdr": {"base_url": f"http://{host}:{port}", "api_key": "${HERDR_API_KEY}"}},
    }
    listed = remotes_core.operate("herdr", "list", config=cfg)
    assert listed.ok is True
    assert any(header == "Bearer test-herdr-token" for header in captured_auth)


def test_herdr_not_configured_constant_mentions_settings():
    assert "Settings" in HERDR_NOT_CONFIGURED
    assert "SSH" in HERDR_NOT_CONFIGURED
    assert "10.0.0." not in HERDR_NOT_CONFIGURED
    assert "OpenMousBot" in HERDR_NOT_CONFIGURED

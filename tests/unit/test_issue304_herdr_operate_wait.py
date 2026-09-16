"""Issue #304 — Herdr operate send waits like chat_herdr and returns pane text."""
from __future__ import annotations

import subprocess
from unittest.mock import patch

from swarm.core import remotes as remotes_core
from swarm.herdr.client import HerdrClient, HerdrCLIError


def test_operate_send_waits_and_returns_pane_text(monkeypatch):
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        del timeout
        calls.append(list(argv))
        if "get" in argv:
            return subprocess.CompletedProcess(argv, 0, '{"result":{"state":"idle"}}', "")
        if "read" in argv:
            return subprocess.CompletedProcess(argv, 0, "pane says hello", "")
        return subprocess.CompletedProcess(argv, 0, '{"type":"agent_prompted"}', "")

    real = HerdrClient.from_remote_config

    def spy(config=None, **kwargs):
        kwargs.setdefault("runner", runner)
        return real(config, **kwargs)

    cfg = {"remotes": {"herdr": {"herdr_mode": "local"}}}
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    monkeypatch.delenv("HERDR_SSH_HOST", raising=False)
    with patch.object(HerdrClient, "from_remote_config", side_effect=spy):
        sent = remotes_core.operate(
            "herdr",
            "send",
            prompt="do the thing",
            target="w7:p1",
            config=cfg,
            timeout=1.0,
        )
    assert sent.ok is True
    assert sent.data["text"] == "pane says hello"
    assert "agent_prompted" not in sent.detail
    assert calls == [
        ["herdr", "agent", "get", "w7:p1"],
        [
            "herdr",
            "agent",
            "prompt",
            "w7:p1",
            "do the thing",
            "--wait",
            "--until",
            "idle",
            "--timeout",
            "1000",
        ],
        ["herdr", "agent", "read", "w7:p1", "--source", "recent", "--format", "text"],
    ]
    assert calls[1].count("--until") == 1


def test_operate_send_timeout_is_named_error(monkeypatch):
    def runner(argv, timeout=None):
        del timeout
        if "get" in argv:
            return subprocess.CompletedProcess(argv, 0, '{"result":{"state":"idle"}}', "")
        raise subprocess.TimeoutExpired(argv, 1)

    real = HerdrClient.from_remote_config

    def spy(config=None, **kwargs):
        kwargs.setdefault("runner", runner)
        return real(config, **kwargs)

    cfg = {"remotes": {"herdr": {"herdr_mode": "local"}}}
    monkeypatch.delenv("HERDR_BASE_URL", raising=False)
    monkeypatch.delenv("HERDR_SSH_HOST", raising=False)
    with patch.object(HerdrClient, "from_remote_config", side_effect=spy):
        sent = remotes_core.operate(
            "herdr",
            "send",
            prompt="do the thing",
            target="w7:p1",
            config=cfg,
            timeout=1.0,
        )
    assert sent.ok is False
    assert "timed out" in sent.detail
    assert "agent_prompted" not in sent.detail
    assert sent.gap == "herdr_reply_timeout"


def test_herdr_cli_timeout_maps_to_named_error():
    err = HerdrCLIError("herdr timed out: ['herdr', 'agent', 'prompt']")
    assert "timed out" in str(err).lower()

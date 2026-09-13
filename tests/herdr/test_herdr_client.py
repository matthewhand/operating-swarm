"""REQ-21 Herdr CLI wrapper — mock only. Never talk to a live TUI.

Proven on-host shape (dev-worker-max 198.51.100.30):
``herdr agent prompt w3:p1 HERDR_PING_OK`` → JSON type ``agent_prompted``.

Do not target a WORKING grok pane. Cloud CI has no live herdr server.
"""

from __future__ import annotations

import subprocess

import pytest

from swarm.herdr import (
    AGENT_PROMPTED,
    MEMBER_KIND,
    HerdrBlockedError,
    HerdrCLIError,
    HerdrClient,
    extract_prompt_type,
    members_from_agent_list,
    members_from_workspace_list,
)


def _ok(argv, stdout):
    return subprocess.CompletedProcess(argv, 0, stdout, "")


def _fail(argv, stderr, code=1):
    return subprocess.CompletedProcess(argv, code, "", stderr)


def test_prompt_exact_shape_w3p1_is_one_argv_and_agent_prompted():
    """Live proof: herdr agent prompt w3:p1 HERDR_PING_OK → type agent_prompted."""
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        return _ok(argv, '{"type":"agent_prompted","ok":true}')

    result = HerdrClient(runner=runner).agent_prompt("w3:p1", "HERDR_PING_OK")
    assert calls == [["herdr", "agent", "prompt", "w3:p1", "HERDR_PING_OK"]]
    assert "--remote" not in calls[0]
    assert result["type"] == AGENT_PROMPTED
    assert extract_prompt_type(result) == AGENT_PROMPTED


def test_prompt_text_with_spaces_is_single_argv():
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        return _ok(argv, '{"type":"agent_prompted"}')

    HerdrClient(runner=runner).agent_prompt("w3:p1", "hello with spaces")
    assert calls == [["herdr", "agent", "prompt", "w3:p1", "hello with spaces"]]
    # The quoting bug split TEXT so herdr saw `unknown option: with`.
    assert "with" not in calls[0]
    assert calls[0][-1] == "hello with spaces"


def test_localhost_omits_remote_on_every_command():
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        return _ok(argv, '{"ok":true}')

    client = HerdrClient(remote="", runner=runner)
    client.workspace_list()
    client.agent_list()
    client.agent_read("w3:p1")
    client.wait_until("w3:p1", "idle")
    for argv in calls:
        assert argv[0] == "herdr"
        assert "--remote" not in argv


def test_optional_remote_prefixes_every_call():
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        return _ok(argv, '{"ok":true}')

    client = HerdrClient(remote="matthewh@198.51.100.36", runner=runner)
    client.workspace_list()
    client.agent_list()
    client.agent_prompt("w3:p1", "HERDR_PING_OK")
    for argv in calls:
        assert argv[:3] == ["herdr", "--remote", "matthewh@198.51.100.36"]
    assert calls[-1] == [
        "herdr",
        "--remote",
        "matthewh@198.51.100.36",
        "agent",
        "prompt",
        "w3:p1",
        "HERDR_PING_OK",
    ]


@pytest.mark.parametrize("remote", ["workbox", "ssh://you@server:2222"])
def test_remote_ssh_alias_and_url(remote):
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        return _ok(argv, "{}")

    HerdrClient(remote=remote, runner=runner).agent_list()
    assert calls[0] == ["herdr", "--remote", remote, "agent", "list"]


def test_blocked_prompt_is_rejected_without_sending():
    def runner(argv, timeout=None):
        if "get" in argv:
            return _ok(argv, '{"result":{"state":"blocked"}}')
        raise AssertionError("must not call prompt when blocked")

    with pytest.raises(HerdrBlockedError):
        HerdrClient(runner=runner).agent_prompt("w3:p1", "nope", check_blocked=True)


def test_blocked_cli_error_maps_to_herdr_blocked():
    def runner(argv, timeout=None):
        return _fail(argv, '{"error":{"code":"agent_blocked"}}')

    with pytest.raises(HerdrBlockedError):
        HerdrClient(runner=runner).agent_prompt("w3:p1", "hi")


def test_wait_until_idle_uses_documented_flag():
    calls: list[list[str]] = []

    def runner(argv, timeout=None):
        calls.append(list(argv))
        return _ok(argv, '{"ok":true}')

    HerdrClient(runner=runner).wait_until("w3:p1", "idle")
    assert calls == [["herdr", "agent", "wait", "w3:p1", "--until", "idle"]]


def test_wait_until_rejects_unknown_status():
    with pytest.raises(ValueError, match="status must be"):
        HerdrClient(runner=lambda *a, **k: _ok([], "{}")).wait_until("w3:p1", "unknown")


def test_members_from_agent_and_workspace_lists():
    agents = members_from_agent_list(
        {"result": {"agents": [{"pane_id": "w3:p1", "state": "idle", "name": "grok"}]}},
        remote="",
    )
    assert agents[0]["kind"] == MEMBER_KIND
    assert agents[0]["name"] == "w3:p1"
    assert agents[0]["remote"] == ""
    assert agents[0]["source"] == "agent"
    assert agents[0]["state"] == "idle"

    workspaces = members_from_workspace_list(
        {"result": {"workspaces": [{"workspace_id": "w3", "label": "demo"}]}},
        remote="",
    )
    assert workspaces[0]["kind"] == MEMBER_KIND
    assert workspaces[0]["name"] == "w3"
    assert workspaces[0]["source"] == "workspace"


def test_discover_members_localhost_no_remote():
    def runner(argv, timeout=None):
        assert "--remote" not in argv
        if argv[-2:] == ["agent", "list"]:
            return _ok(argv, '{"result":{"agents":[{"pane_id":"w3:p1","state":"idle"}]}}')
        if argv[-2:] == ["workspace", "list"]:
            return _ok(argv, '{"result":{"workspaces":[{"workspace_id":"w3"}]}}')
        raise AssertionError(argv)

    members = HerdrClient(runner=runner).discover_members()
    names = [m["name"] for m in members]
    assert names == ["w3:p1", "w3"]
    assert all(m["kind"] == "herdr" and m["remote"] == "" for m in members)


def test_missing_herdr_binary_is_cli_error():
    def runner(argv, timeout=None):
        raise FileNotFoundError("herdr")

    with pytest.raises(HerdrCLIError, match="not found"):
        HerdrClient(runner=runner).agent_list()

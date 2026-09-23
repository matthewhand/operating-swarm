"""Tests for REQ-889 BaseCliAgent, CliRegistry, candidate discovery, and probe."""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from swarm.core.cli_driver import (
    BaseCliAgent,
    ClaudeCliAgent,
    GrokCliAgent,
    GeminiCliAgent,
    CodexCliAgent,
    find_cli_candidates,
    split_cli_string,
    test_cli_binary as probe_cli_binary,
)
from swarm.core.cli_registry import (
    CliRegistry,
    get_cli_registry,
    get_driver,
    registered_cli_names,
    driver_catalog_descriptors,
)
from swarm.core.cli_scaffold import scaffold_cli_agent_driver


def test_split_cli_string():
    assert split_cli_string("claude --output-format json") == ["claude", "--output-format", "json"]
    assert split_cli_string('ag claude -p "hello world"') == ["ag", "claude", "-p", "hello world"]
    assert split_cli_string("") == []


def test_built_in_drivers_protocol():
    claude = get_driver("claude")
    assert isinstance(claude, ClaudeCliAgent)
    assert claude.name == "claude"
    assert claude.default_binary == "claude"
    exec_argv = claude.build_exec_argv("hello")
    assert "claude" in exec_argv[0]
    assert "-p=hello" in exec_argv
    assert "--output-format" in exec_argv
    assert claude.parse_output('{"result": "parsed text"}') == "parsed text"

    grok = get_driver("grok")
    assert isinstance(grok, GrokCliAgent)
    assert grok.name == "grok"
    grok_argv = grok.build_exec_argv("analyze", session_id="sess-123")
    assert "--resume" in grok_argv
    assert "sess-123" in grok_argv
    assert grok.parse_output('{"text": "grok reply"}') == "grok reply"


def test_find_cli_candidates_finds_python():
    # Python is guaranteed to exist in the current environment
    bin_name = "python3" if sys.platform != "win32" else "python"
    candidates = find_cli_candidates(bin_name)
    assert len(candidates) >= 1
    for p in candidates:
        assert os.path.isfile(p)
        assert os.access(p, os.X_OK)


def test_test_cli_binary_success():
    bin_name = sys.executable
    result = probe_cli_binary(bin_name)
    assert result["ok"] is True
    assert "Python" in result["version"] or "3." in result["version"]


def test_test_cli_binary_not_found():
    result = probe_cli_binary("non_existent_binary_xyz_12345")
    assert result["ok"] is False
    assert "not found" in result["message"].lower()


def test_driver_catalog_descriptors():
    descriptors = driver_catalog_descriptors()
    names = [d["name"] for d in descriptors]
    assert "claude" in names
    assert "grok" in names
    assert "gemini" in names
    assert "codex" in names


def test_scaffold_cli_agent_driver(tmp_path):
    dest = str(tmp_path / "custom_agents")
    res = scaffold_cli_agent_driver(
        name="testbot",
        display_name="Test Bot",
        default_binary="python3",
        exec_args=["-c", "print('{prompt}')"],
        destination_dir=dest,
        verify_probe=False,
    )
    assert res["ok"] is True
    assert res["name"] == "testbot"
    assert os.path.isfile(res["file_path"])

    # Verify dynamic registry loaded it
    registry = get_cli_registry()
    bot = registry.get("testbot")
    assert bot is not None
    assert bot.name == "testbot"
    assert bot.display_name == "Test Bot"
    argv = bot.build_exec_argv("ping")
    assert "ping" in argv[-1] or "ping" in argv[-2]


@pytest.mark.django_db
def test_cli_api_endpoints(client):
    # GET /v1/cli-agents/candidates
    resp = client.get("/v1/cli-agents/candidates?name=python3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "python3"
    assert isinstance(data["candidates"], list)
    assert len(data["candidates"]) >= 1

    # POST /v1/cli-agents/test
    resp = client.post(
        "/v1/cli-agents/test",
        data={"cli": sys.executable},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert "version" in resp.json()

    # GET /v1/cli-agents/drivers
    resp = client.get("/v1/cli-agents/drivers/")
    assert resp.status_code == 200
    drivers = resp.json()["drivers"]
    assert any(d["name"] == "claude" for d in drivers)
    assert any(d["name"] == "grok" for d in drivers)


@pytest.mark.django_db
def test_retention_api_endpoints(client):
    from django.contrib.auth import get_user_model
    # get_or_create, not create: a plain create collides with a "testuser" left
    # behind by an earlier test in the session (collection order is filesystem
    # order, so the UNIQUE violation only showed up in full-suite runs).
    user, _ = get_user_model().objects.get_or_create(
        username="testuser", defaults={"password": "password"}
    )
    client.force_login(user)

    # GET /v1/chat/retention/stats
    resp = client.get("/v1/chat/retention/stats/")
    assert resp.status_code == 200
    stats = resp.json()
    assert "active_count" in stats
    assert "trash_count" in stats
    assert "bytes_label" in stats
    assert "chats" in stats
    assert "trash" in stats

    # POST /v1/chat/retention/action with JSON payload
    resp = client.post(
        "/v1/chat/retention/action/",
        data={"action": "archive_all"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.django_db
def test_remote_probe_candidate_api(client):
    from django.contrib.auth import get_user_model
    user, _ = get_user_model().objects.get_or_create(username="remotetester", defaults={"password": "password"})
    client.force_login(user)

    resp = client.post(
        "/v1/remotes/test/",
        data={"kind": "omb", "base_url": "http://127.0.0.1:19999"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "remote" in data
    assert "ok" in data
    assert "state" in data




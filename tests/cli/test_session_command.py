"""REQ-871 workstream D — ``swarm-cli session list`` / ``session show``.

These read the existing stores: the chat store for Swarm-side records and the
provider's own store for a CLI's sessions. No parallel ``~/.cache/*/sessions``
DB is created or written (asserted below).

Plan: docs/qa/REQ-871-cli-blueprint-lifecycle.md
Source lock: tests/unit/test_req871_cli_blueprint_lifecycle.py
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from swarm.core import chat_store, swarm_cli

runner = CliRunner()


@pytest.fixture
def chat_dir(tmp_path, monkeypatch):
    """Point the chat store at a temp root via its documented env override."""
    root = tmp_path / "chats"
    monkeypatch.setenv("SWARM_CHAT_DIR", str(root))
    return root


def _seed(chat_dir, user_key="u1", agent_id="codey", cli_sessions=None):
    path = chat_store.save(
        user_key,
        agent_id,
        [{"role": "user", "content": "hi"}],
        cli_sessions=cli_sessions or {},
    )
    assert path is not None
    return path


def test_session_list_empty_state_is_not_an_error(chat_dir):
    result = runner.invoke(swarm_cli.app, ["session", "list"])

    assert result.exit_code == 0, result.stdout
    assert "No Swarm-side session records found" in result.stdout


def test_session_list_shows_agent_cli_ids_and_transcript(chat_dir):
    _seed(chat_dir, cli_sessions={"grok": "sess-abc"})

    result = runner.invoke(swarm_cli.app, ["session", "list"])

    assert result.exit_code == 0, result.stdout
    assert "codey" in result.stdout
    assert "grok=sess-abc" in result.stdout
    assert "transcript:" in result.stdout


def test_session_list_json_is_machine_readable(chat_dir):
    _seed(chat_dir, cli_sessions={"grok": "sess-abc"})

    result = runner.invoke(swarm_cli.app, ["session", "list", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["sessions"][0]["agent_id"] == "codey"
    assert payload["sessions"][0]["cli_sessions"] == {"grok": "sess-abc"}


def test_session_show_prints_record_and_transcript_path(chat_dir):
    path = _seed(chat_dir, cli_sessions={"grok": "sess-abc"})

    result = runner.invoke(swarm_cli.app, ["session", "show", "codey"])

    assert result.exit_code == 0, result.stdout
    assert "agent_id        : codey" in result.stdout
    assert "grok=sess-abc" in result.stdout
    assert f"transcript      : {path}" in result.stdout


def test_session_show_unknown_agent_exits_1(chat_dir):
    result = runner.invoke(swarm_cli.app, ["session", "show", "ghost"])

    assert result.exit_code == 1
    assert "No Swarm-side session record" in result.stdout


def test_session_show_names_a_provider_it_has_no_id_for(chat_dir):
    _seed(chat_dir, cli_sessions={"grok": "sess-abc"})

    result = runner.invoke(
        swarm_cli.app, ["session", "show", "codey", "--provider", "not_a_cli"]
    )

    assert result.exit_code == 0, result.stdout
    assert "no stored session id" in result.stdout


def test_session_show_marks_an_id_it_cannot_verify(chat_dir):
    """A CLI with no list argv must be named as such, not silently trusted."""
    _seed(chat_dir, cli_sessions={"not_a_cli": "sess-abc"})

    result = runner.invoke(
        swarm_cli.app, ["session", "show", "codey", "--provider", "not_a_cli"]
    )

    assert result.exit_code == 0, result.stdout
    assert "can't list sessions" in result.stdout
    assert "unverified" in result.stdout


def test_session_list_provider_without_a_lister_invents_nothing(chat_dir):
    result = runner.invoke(
        swarm_cli.app, ["session", "list", "--provider", "not_a_cli"]
    )

    assert result.exit_code == 0, result.stdout
    assert "can't list sessions" in result.stdout
    assert "(no provider sessions reported)" in result.stdout


def test_session_commands_never_write_a_cache_session_store(chat_dir, tmp_path, mocker):
    """The TODO's ``~/.cache/swarm/sessions`` path must stay unused."""
    cache = tmp_path / "cache"
    cache.mkdir()
    mocker.patch("swarm.core.paths.get_user_cache_dir_for_swarm", return_value=cache)
    _seed(chat_dir, cli_sessions={"grok": "sess-abc"})

    runner.invoke(swarm_cli.app, ["session", "list"])
    runner.invoke(swarm_cli.app, ["session", "show", "codey"])

    assert not (cache / "sessions").exists()
    assert list(cache.iterdir()) == []

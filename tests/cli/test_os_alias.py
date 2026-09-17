"""`os` is a shortcut for `os-cli`; bare invocation opens the TUI."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from swarm.core.swarm_cli import app

REPO = Path(__file__).resolve().parents[2]
runner = CliRunner(mix_stderr=False)


def test_pyproject_ships_os_as_os_cli_alias():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'os-cli = "swarm.core.swarm_cli:app"' in text
    assert 'os = "swarm.core.swarm_cli:app"' in text


def test_root_help_names_os_shortcut_and_lists_tui_and_chat():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.stderr
    out = result.stdout
    assert "shortcut" in out.lower() or "`os`" in out
    assert "tui" in out
    assert "chat" in out


def test_bare_os_cli_dispatches_to_tui(monkeypatch):
    called = {}

    def _fake_tui(**kwargs):
        called["kwargs"] = kwargs

    monkeypatch.setattr("swarm.tui.cli.tui_cmd", _fake_tui)
    result = runner.invoke(app, [])
    assert result.exit_code == 0, result.stderr
    assert called == {"kwargs": {}}


def test_chat_is_tui_alias(monkeypatch):
    called = {}

    def _fake_tui(**kwargs):
        called["once"] = kwargs.get("once")

    monkeypatch.setattr("swarm.tui.cli._non_interactive", lambda **kw: called.update(kw))
    monkeypatch.setattr("swarm.tui.cli._interactive", lambda **kw: called.update(kw))
    result = runner.invoke(app, ["chat", "--once", "--json"])
    assert result.exit_code == 0, result.stderr
    assert called.get("as_json") is True

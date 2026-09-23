"""Tests for `swarm-cli list-models` / `cli-agents --list-models` (REQ-44)."""

from __future__ import annotations

import json
import logging

import pytest
from typer.testing import CliRunner

from swarm.core.cli_models import ListModelsResult
from swarm.core.swarm_cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _quiet_logging():
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(logging.NOTSET)


def test_list_models_command_single_cli(monkeypatch):
    monkeypatch.setattr(
        "swarm.core.cli_models.list_models",
        lambda name, **_k: ListModelsResult(cli=name, models=["grok-4", "grok-3-mini"]),
    )
    result = runner.invoke(app, ["list-models", "grok"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {"cli": "grok", "models": ["grok-4", "grok-3-mini"]}


def test_list_models_command_unknown_cli(monkeypatch):
    monkeypatch.setattr(
        "swarm.core.cli_models.list_models",
        lambda name, **_k: ListModelsResult(
            cli=name, models=[], warning="unknown CLI 'nope-not-real'"
        ),
    )
    result = runner.invoke(app, ["list-models", "nope-not-real"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["cli"] == "nope-not-real"
    assert payload["models"] == []
    assert "unknown" in payload["warning"]


def test_cli_agents_list_models_flag_all(monkeypatch):
    monkeypatch.setattr(
        "swarm.core.cli_models.list_models_all",
        lambda **_k: [
            ListModelsResult(cli="claude", models=[], warning="not installed"),
            ListModelsResult(cli="grok", models=["grok-4"]),
        ],
    )
    result = runner.invoke(app, ["cli-agents", "--list-models"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["cli"] == "claude" and payload[0]["models"] == []
    assert payload[1] == {"cli": "grok", "models": ["grok-4"]}


def test_cli_agents_list_models_flag_one(monkeypatch):
    monkeypatch.setattr(
        "swarm.core.cli_models.list_models",
        lambda name, **_k: ListModelsResult(cli=name, models=["gemini-3-flash-preview"]),
    )
    result = runner.invoke(app, ["cli-agents", "--list-models", "--cli", "gemini"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "cli": "gemini",
        "models": ["gemini-3-flash-preview"],
    }

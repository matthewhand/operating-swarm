"""Tests for the `swarm-cli skills` command (list / --show / --json)."""

from __future__ import annotations

import json
import logging

import pytest
from typer.testing import CliRunner

from swarm.core.swarm_cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _quiet_logging():
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(logging.NOTSET)


SKILL_MD = """---
name: greeting
description: Says hello. Use when greeting.
---
Say hello politely.
"""


def _skill_dir(tmp_path):
    d = tmp_path / "greeting"
    d.mkdir()
    (d / "SKILL.md").write_text(SKILL_MD)
    (d / "helper.txt").write_text("x")
    return str(tmp_path)


def test_skills_list(tmp_path):
    result = runner.invoke(app, ["skills", "--dir", _skill_dir(tmp_path)])
    assert result.exit_code == 0
    assert "greeting" in result.stdout
    assert "1 skill(s)" in result.stdout  # the asset count column + footer


def test_skills_json(tmp_path):
    result = runner.invoke(app, ["skills", "--dir", _skill_dir(tmp_path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    names = [s["name"] for s in payload["skills"]]
    assert names == ["greeting"]
    assert payload["skills"][0]["assets"] == ["helper.txt"]


def test_skills_show(tmp_path):
    result = runner.invoke(app, ["skills", "--dir", _skill_dir(tmp_path), "--show", "greeting"])
    assert result.exit_code == 0
    assert "Say hello politely." in result.stdout
    assert "helper.txt" in result.stdout  # assets line


def test_skills_show_unknown_exits_nonzero(tmp_path):
    result = runner.invoke(app, ["skills", "--dir", _skill_dir(tmp_path), "--show", "nope"])
    assert result.exit_code == 1
    assert "No skill named 'nope'" in result.stdout


def test_bundled_skills_listed_from_default_dir():
    # No --dir: scans the repo's skills/ and finds the shipped skills.
    result = runner.invoke(app, ["skills", "--json"])
    assert result.exit_code == 0
    names = {s["name"] for s in json.loads(result.stdout)["skills"]}
    assert {"conventional-commit", "counting-lines"} <= names

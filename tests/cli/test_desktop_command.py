"""CLI smoke for ``swarm-desktop`` REQ-883 Phase 0 scaffold."""

from __future__ import annotations

import json
from pathlib import Path

from swarm.desktop.cli import build_parser, main


def test_help_lists_print_plan_and_req():
    help_text = build_parser().format_help()
    assert "REQ-883" in help_text
    assert "--print-plan" in help_text
    assert "8001" not in help_text


def test_print_plan_json(tmp_path: Path, capsys):
    rc = main(["--print-plan", "--profile", str(tmp_path), "--port", "9001"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["object"] == "desktop.plan"
    assert payload["product"] == "Operating Swarm"
    assert payload["host"] == "127.0.0.1"
    assert payload["url"] == "http://127.0.0.1:9001/"
    assert payload["window"] is False
    assert payload["vendored_clis"] is False
    assert payload["sqlite"].endswith("db.sqlite3")
    dumped = json.dumps(payload)
    assert "sk-" not in dumped


def test_default_launch_is_deferred_to_req883b(capsys):
    rc = main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "REQ-883B" in err
    assert "pywebview" in err
    assert "Operating Swarm" in err

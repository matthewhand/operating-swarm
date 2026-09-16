"""Tests for the cli_roundtable blueprint (group-chat debate)."""

from __future__ import annotations

import json
import sys

from swarm.blueprints.cli_roundtable.blueprint_cli_roundtable import (
    CliRoundtableBlueprint,
)

PY = sys.executable


def _debater(tag: str) -> dict:
    # Prints a fixed tag so its participation is visible in the transcript.
    return {"cmd": [PY, "-c", f"print({tag!r})", "{prompt}"], "parse": "text"}


def _moderator(done: bool, synthesis: str = "AGREED", next_prompt: str = "dig deeper") -> dict:
    payload = json.dumps({"done": done, "synthesis": synthesis, "next_prompt": next_prompt})
    return {"cmd": [PY, "-c", "import sys; print(sys.argv[2])", "{prompt}", payload], "parse": "text"}


def _boom() -> dict:
    return {"cmd": [PY, "-c", "import sys; sys.exit(1)", "{prompt}"]}


async def _collect(gen):
    return [c async for c in gen]


def _final(chunks):
    text = None
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = msgs[0]["content"]
    return text


def _progress(chunks):
    return "\n".join(c["content"] for c in chunks if isinstance(c, dict) and c.get("type") == "fusion_progress")


async def test_moderator_concludes_early():
    cfg = {
        "cli_agents": {"a": _debater("A"), "b": _debater("B"), "m": _moderator(True, "AGREED")},
        "cli_roundtable": {"debaters": ["a", "b"], "moderator": "m", "rounds": 3},
    }
    bp = CliRoundtableBlueprint(config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "debate this"}]))
    assert _final(chunks) == "AGREED"
    assert "concluded after round 1" in _progress(chunks)


async def test_runs_all_rounds_when_never_done():
    cfg = {
        "cli_agents": {"a": _debater("A"), "b": _debater("B"), "m": _moderator(False, "PARTIAL")},
        "cli_roundtable": {"debaters": ["a", "b"], "moderator": "m", "rounds": 2},
    }
    bp = CliRoundtableBlueprint(config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "debate this"}]))
    assert _final(chunks) == "PARTIAL"  # last synthesis carried forward
    assert "Round 2/2" in _progress(chunks)


async def test_no_moderator_concatenates_last_positions():
    cfg = {
        "cli_agents": {"a": _debater("ALPHA"), "b": _debater("BETA")},
        "cli_roundtable": {"debaters": ["a", "b"], "rounds": 1},
    }
    bp = CliRoundtableBlueprint(config=cfg)
    final = _final(await _collect(bp.run([{"role": "user", "content": "q"}])))
    assert "ALPHA" in final and "BETA" in final


async def test_failed_debater_noted_others_continue():
    cfg = {
        "cli_agents": {"a": _debater("ALPHA"), "boom": _boom()},
        "cli_roundtable": {"debaters": ["a", "boom"], "rounds": 1},
    }
    bp = CliRoundtableBlueprint(config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "q"}]))
    assert "ALPHA" in _final(chunks)
    assert "boom did not respond" in _progress(chunks)


async def test_all_debaters_fail():
    cfg = {
        "cli_agents": {"boom": _boom()},
        "cli_roundtable": {"debaters": ["boom"], "rounds": 1},
    }
    bp = CliRoundtableBlueprint(config=cfg)
    final = _final(await _collect(bp.run([{"role": "user", "content": "q"}])))
    assert "no positions" in final.lower()


async def test_no_debaters_configured():
    bp = CliRoundtableBlueprint(config={})
    final = _final(await _collect(bp.run([{"role": "user", "content": "q"}])))
    assert "No debater CLIs are configured" in final
    assert "[Manage CLI](/chat?settings=cli-agents)" in final
    assert "docs/CLI_FUSION.md" not in final


async def test_falls_back_to_fusion_preset():
    cfg = {
        "cli_agents": {"a": _debater("A"), "b": _debater("B"), "m": _moderator(True, "DONE")},
        "cli_fusion": {"presets": {"p": {"panel": ["a", "b"], "judge": "m"}}, "default_preset": "p"},
    }
    bp = CliRoundtableBlueprint(config=cfg)
    final = _final(await _collect(bp.run([{"role": "user", "content": "q"}])))
    assert final == "DONE"

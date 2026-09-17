"""Tests for the cli_map blueprint (decompose → distribute → reduce)."""

from __future__ import annotations

import sys

from swarm.blueprints.cli_map.blueprint_cli_map import CliMapBlueprint

PY = sys.executable


def _worker(name: str) -> dict:
    # Echoes "<name>:<subtask>" so worker assignment is visible in output.
    return {"cmd": [PY, "-c", f"import sys; print('{name}:' + sys.argv[1])", "{prompt}"]}


def _planner(*subtasks: str) -> dict:
    import json
    j = json.dumps({"subtasks": list(subtasks)})
    return {"cmd": [PY, "-c", "import sys; print(sys.argv[2])", "{prompt}", j], "parse": "text"}


def _reducer(text: str = "REDUCED") -> dict:
    return {"cmd": [PY, "-c", f"print({text!r})", "{prompt}"], "parse": "text"}


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


async def test_explicit_items_map_and_reduce():
    cfg = {
        "cli_agents": {"w": _worker("W"), "r": _reducer("COMBINED")},
        "cli_map": {"worker": "w", "reducer": "r"},
    }
    bp = CliMapBlueprint(config=cfg)
    bp.set_params({"items": ["task one", "task two"]})
    chunks = await _collect(bp.run([{"role": "user", "content": "big task"}]))
    assert _final(chunks) == "COMBINED"
    assert "Using 2 explicit subtask" in _progress(chunks)


async def test_planner_decomposes_then_maps_and_reduces():
    cfg = {
        "cli_agents": {"p": _planner("s1", "s2", "s3"), "w": _worker("W"), "r": _reducer("DONE")},
        "cli_map": {"planner": "p", "worker": "w", "reducer": "r"},
    }
    bp = CliMapBlueprint(config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "decompose me"}]))
    assert _final(chunks) == "DONE"
    assert "Planned 3 subtask" in _progress(chunks)


async def test_no_reducer_falls_back_to_labeled_concatenation():
    cfg = {
        "cli_agents": {"w": _worker("W")},
        "cli_map": {"worker": "w"},  # no reducer
    }
    bp = CliMapBlueprint(config=cfg)
    bp.set_params({"items": ["alpha", "beta"]})
    final = _final(await _collect(bp.run([{"role": "user", "content": "t"}])))
    assert "W:alpha" in final and "W:beta" in final  # both subtask results present


async def test_round_robin_distributes_across_workers():
    cfg = {
        "cli_agents": {"a": _worker("A"), "b": _worker("B")},
        "cli_map": {"workers": ["a", "b"]},
    }
    bp = CliMapBlueprint(config=cfg)
    bp.set_params({"items": ["x", "y", "z"]})
    final = _final(await _collect(bp.run([{"role": "user", "content": "t"}])))
    # subtasks x,y,z -> workers a,b,a
    assert "A:x" in final and "B:y" in final and "A:z" in final


async def test_all_workers_fail():
    cfg = {
        "cli_agents": {"boom": {"cmd": [PY, "-c", "import sys; sys.exit(1)", "{prompt}"]}},
        "cli_map": {"worker": "boom"},
    }
    bp = CliMapBlueprint(config=cfg)
    bp.set_params({"items": ["x"]})
    assert "All map workers failed" in _final(await _collect(bp.run([{"role": "user", "content": "t"}])))


async def test_no_workers_configured():
    bp = CliMapBlueprint(config={})
    final = _final(await _collect(bp.run([{"role": "user", "content": "t"}])))
    assert "No worker CLIs are configured" in final
    assert "[Manage CLI](/chat?settings=cli-agents)" in final
    assert "docs/CLI_FUSION.md" not in final


async def test_planner_empty_subtasks():
    cfg = {
        "cli_agents": {"p": _planner(), "w": _worker("W")},
        "cli_map": {"planner": "p", "worker": "w"},
    }
    bp = CliMapBlueprint(config=cfg)
    assert "no subtasks" in _final(await _collect(bp.run([{"role": "user", "content": "t"}]))).lower()

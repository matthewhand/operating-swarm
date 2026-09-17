"""Tests for the cli_planner blueprint (Magentic-One-style ledger)."""

from __future__ import annotations

import sys

from swarm.blueprints.cli_planner.blueprint_cli_planner import CliPlannerBlueprint

PY = sys.executable


def _planner(code: str) -> dict:
    return {"cmd": [PY, "-c", code, "{prompt}"], "parse": "text"}


def _worker(tag: str = "W") -> dict:
    # Echoes "<tag>:<subtask>" so the executed subtask is visible in results.
    return {"cmd": [PY, "-c", f"import sys; print('{tag}:' + sys.argv[1])", "{prompt}"], "parse": "text"}


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


# A planner that, on review, adds one follow-up subtask the first time, then
# concludes once that follow-up's result ("extra-task") shows up as completed.
_REPLANNING_PLANNER = (
    "import sys\n"
    "p = sys.argv[1]\n"
    "if 'PROGRESS REVIEW' in p:\n"
    "    if 'extra-task' in p:\n"
    "        print('{\"done\": true, \"synthesis\": \"FINAL\"}')\n"
    "    else:\n"
    "        print('{\"done\": false, \"new_subtasks\": [\"extra-task\"], \"synthesis\": \"interim\"}')\n"
    "elif 'PLAN THE GOAL' in p:\n"
    "    print('{\"subtasks\": [\"s1\"]}')\n"
    "else:\n"
    "    print('SYNTH')\n"
)


async def test_replans_on_stall_then_concludes():
    cfg = {
        "cli_agents": {"p": _planner(_REPLANNING_PLANNER), "w": _worker("W")},
        "cli_planner": {"planner": "p", "worker": "w", "max_rounds": 5},
    }
    bp = CliPlannerBlueprint(config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "achieve the goal"}]))
    assert _final(chunks) == "FINAL"
    prog = _progress(chunks)
    assert "added subtask" in prog  # the ledger grew in response to progress
    assert "goal met" in prog


async def test_concludes_immediately_with_synthesis():
    code = (
        "import sys\n"
        "p = sys.argv[1]\n"
        "if 'PROGRESS REVIEW' in p:\n"
        "    print('{\"done\": true, \"synthesis\": \"QUICK\"}')\n"
        "elif 'PLAN THE GOAL' in p:\n"
        "    print('{\"subtasks\": [\"only\"]}')\n"
        "else:\n"
        "    print('SYNTH')\n"
    )
    cfg = {
        "cli_agents": {"p": _planner(code), "w": _worker("W")},
        "cli_planner": {"planner": "p", "worker": "w"},
    }
    bp = CliPlannerBlueprint(config=cfg)
    assert _final(await _collect(bp.run([{"role": "user", "content": "g"}]))) == "QUICK"


async def test_synthesis_fallback_calls_planner_synth():
    # done=true but no synthesis text -> blueprint makes a final SYNTH call.
    code = (
        "import sys\n"
        "p = sys.argv[1]\n"
        "if 'PROGRESS REVIEW' in p:\n"
        "    print('{\"done\": true, \"synthesis\": \"\"}')\n"
        "elif 'PLAN THE GOAL' in p:\n"
        "    print('{\"subtasks\": [\"only\"]}')\n"
        "else:\n"
        "    print('FINAL-SYNTH')\n"
    )
    cfg = {
        "cli_agents": {"p": _planner(code), "w": _worker("W")},
        "cli_planner": {"planner": "p", "worker": "w"},
    }
    bp = CliPlannerBlueprint(config=cfg)
    assert _final(await _collect(bp.run([{"role": "user", "content": "g"}]))) == "FINAL-SYNTH"


async def test_no_planner_configured():
    cfg = {"cli_agents": {"w": _worker("W")}}
    bp = CliPlannerBlueprint(config=cfg)
    final = _final(await _collect(bp.run([{"role": "user", "content": "g"}])))
    assert "No planner CLI is configured" in final
    assert "[Manage CLI](/chat?settings=cli-agents)" in final
    assert "docs/CLI_FUSION.md" not in final


async def test_planner_no_subtasks():
    code = (
        "import sys\n"
        "p = sys.argv[1]\n"
        "if 'PLAN THE GOAL' in p:\n"
        "    print('{\"subtasks\": []}')\n"
        "else:\n"
        "    print('{}')\n"
    )
    cfg = {
        "cli_agents": {"p": _planner(code), "w": _worker("W")},
        "cli_planner": {"planner": "p", "worker": "w"},
    }
    bp = CliPlannerBlueprint(config=cfg)
    assert "no subtasks" in _final(await _collect(bp.run([{"role": "user", "content": "g"}]))).lower()


async def test_all_worker_subtasks_fail():
    code = (
        "import sys\n"
        "p = sys.argv[1]\n"
        "if 'PROGRESS REVIEW' in p:\n"
        "    print('{\"done\": false, \"new_subtasks\": []}')\n"
        "elif 'PLAN THE GOAL' in p:\n"
        "    print('{\"subtasks\": [\"s1\"]}')\n"
        "else:\n"
        "    print('X')\n"
    )
    cfg = {
        "cli_agents": {"p": _planner(code), "boom": _boom()},
        "cli_planner": {"planner": "p", "worker": "boom", "max_rounds": 2},
    }
    bp = CliPlannerBlueprint(config=cfg)
    assert "Every worker subtask failed" in _final(await _collect(bp.run([{"role": "user", "content": "g"}])))

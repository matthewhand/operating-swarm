"""cli_recurse — recursive divide-and-conquer with depth/width/node limiters.

Deterministic fake CLIs drive a controlled recursion tree: the decomposer splits
a prompt of N 'x's into two prompts of N-1 'x's until one 'x' remains (atomic),
so recursion depth and leaf count are predictable.
"""

from __future__ import annotations

import sys

from swarm.blueprints.cli_recurse.blueprint_cli_recurse import CliRecurseBlueprint

PY = sys.executable

# Splits "xxx" -> ["xx","xx"] -> ["x","x"] ... until a single 'x' is atomic.
_DECOMPOSER = (
    "import sys, json; p = sys.argv[1]; n = p.count('x'); "
    "print(json.dumps({'atomic': True} if n <= 1 else "
    "{'atomic': False, 'subproblems': ['x'*(n-1), 'x'*(n-1)]}))"
)
_SOLVER = "import sys; print('LEAF:' + sys.argv[1])"
_SYNTH = "print('SYNTHESIZED')"


def _cli(script: str) -> dict:
    return {"cmd": [PY, "-c", script, "{prompt}"], "parse": "text"}


def _cfg(**recurse) -> dict:
    return {
        "cli_agents": {"dec": _cli(_DECOMPOSER), "sol": _cli(_SOLVER), "syn": _cli(_SYNTH)},
        "cli_recurse": {"decomposer": "dec", "solver": "sol", "synthesizer": "syn", **recurse},
    }


async def _run(prompt: str, **params):
    bp = CliRecurseBlueprint(config=_cfg())
    bp.set_params(params)
    return [c async for c in bp.run([{"role": "user", "content": prompt}])]


def _final(chunks):
    text = None
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = msgs[0]["content"]
    return text


def _progress(chunks):
    return "\n".join(
        c["content"] for c in chunks if isinstance(c, dict) and c.get("type") == "fusion_progress"
    )


def _meta(chunks):
    for c in chunks:
        if isinstance(c, dict) and c.get("meta"):
            return c["meta"]
    return None


async def test_atomic_problem_solves_directly():
    chunks = await _run("x")  # n=1 -> atomic
    final = _final(chunks)
    assert final.startswith("LEAF:") and "x" in final  # solver answered it directly
    assert "solving directly (atomic)" in _progress(chunks)
    assert "split into" not in _progress(chunks)


async def test_recurses_and_synthesizes():
    chunks = await _run("xxx")  # depth-2 tree, 4 leaves
    assert _final(chunks) == "SYNTHESIZED"
    prog = _progress(chunks)
    assert "split into 2" in prog
    assert "4 leaf problem(s) solved" in prog
    # synthesizer is the judge in the fingerprint meta
    assert _meta(chunks) == {"backends": ["sol", "syn"], "judge": "syn"}


async def test_depth_limiter_forces_direct_solve():
    chunks = await _run("xxx", max_depth=1)  # children at depth 1 are forced
    assert _final(chunks) == "SYNTHESIZED"
    prog = _progress(chunks)
    assert "solving directly (limiter)" in prog
    assert "2 leaf problem(s) solved" in prog  # only the two depth-1 children


async def test_node_budget_limiter_caps_total_work():
    chunks = await _run("xxx", max_nodes=1)  # budget spent by the root split
    prog = _progress(chunks)
    assert "solving directly (limiter)" in prog
    assert "2 leaf problem(s) solved" in prog


async def test_no_cli_configured():
    bp = CliRecurseBlueprint(config={})
    chunks = [c async for c in bp.run([{"role": "user", "content": "q"}])]
    final = _final(chunks)
    assert "No CLI is configured" in final
    assert "[Manage CLI](/chat?settings=cli-agents)" in final
    assert "docs/CLI_FUSION.md" not in final

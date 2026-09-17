"""Tests for the cli_orchestrator blueprint (granular consensus routing)."""

from __future__ import annotations

import sys

from swarm.blueprints.cli_orchestrator.blueprint_cli_orchestrator import (
    CliOrchestratorBlueprint,
)

PY = sys.executable


def _router(escalate: bool, answer: str = "ROUTER_ANSWER") -> dict:
    j = '{"answer": "%s", "escalate": %s, "reason": "t"}' % (
        answer, "true" if escalate else "false"
    )
    # Echo a fixed JSON decision regardless of the prompt (argv[2] = the json).
    return {"cmd": [PY, "-c", "import sys; print(sys.argv[2])", "{prompt}", j], "parse": "text"}


def _echo(prefix: str) -> dict:
    return {"cmd": [PY, "-c", f"import sys; print('{prefix}:' + sys.argv[1])", "{prompt}"]}


def _judge(answer: str = "CONSENSUS") -> dict:
    j = '{"answer": "%s", "done": true}' % answer
    return {"cmd": [PY, "-c", "import sys; print(sys.argv[2])", "{prompt}", j], "parse": "text"}


def _config(*, escalate: bool, with_panel: bool = True, router_answer: str = "ROUTER_ANSWER") -> dict:
    agents = {"router": _router(escalate, router_answer), "a": _echo("A"), "b": _echo("B"), "judge": _judge()}
    oc: dict = {"router": "router"}
    if with_panel:
        oc["panel"] = ["a", "b"]
        oc["judge"] = "judge"
    return {"cli_agents": agents, "cli_orchestrator": oc}


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


async def test_router_resolves_directly_without_consensus():
    # escalate=false -> returns the router's own answer; panel is NOT consulted.
    bp = CliOrchestratorBlueprint(config=_config(escalate=False))
    chunks = await _collect(bp.run([{"role": "user", "content": "what's 2+2?"}]))
    assert _final(chunks) == "ROUTER_ANSWER"
    assert "no consensus needed" in _progress(chunks).lower()


async def test_router_escalates_to_consensus():
    # escalate=true -> consensus panel runs; judge's answer is returned.
    bp = CliOrchestratorBlueprint(config=_config(escalate=True))
    chunks = await _collect(bp.run([{"role": "user", "content": "is this migration safe?"}]))
    assert _final(chunks) == "CONSENSUS"
    assert "escalating to consensus" in _progress(chunks).lower()


async def test_escalate_without_panel_falls_back_to_router_answer():
    bp = CliOrchestratorBlueprint(config=_config(escalate=True, with_panel=False))
    chunks = await _collect(bp.run([{"role": "user", "content": "q"}]))
    assert _final(chunks) == "ROUTER_ANSWER"


async def test_no_router_configured_reports_cleanly():
    bp = CliOrchestratorBlueprint(config={})
    chunks = await _collect(bp.run([{"role": "user", "content": "q"}]))
    final = _final(chunks)
    assert "No router CLI is configured" in final
    assert "[Manage CLI](/chat?settings=cli-agents)" in final
    assert "docs/CLI_FUSION.md" not in final


async def test_empty_prompt():
    bp = CliOrchestratorBlueprint(config=_config(escalate=False))
    chunks = await _collect(bp.run([]))
    assert "No prompt provided" in _final(chunks)

"""Tests for the persona_council blueprint (diverse-lens consensus)."""

from __future__ import annotations

import sys

from swarm.blueprints.persona_council.blueprint_persona_council import (
    COUNCILS,
    PersonaCouncilBlueprint,
)

PY = sys.executable


def _echo(tag: str) -> dict:
    return {"cmd": [PY, "-c", f"print({tag!r})", "{prompt}"], "parse": "text"}


def _boom() -> dict:
    return {"cmd": [PY, "-c", "import sys; sys.exit(1)", "{prompt}"]}


def _cfg(**pc) -> dict:
    return {
        "cli_agents": {"c": _echo("VIEW"), "j": _echo("SYNTH")},
        "persona_council": {"cli": "c", "judge": "j", **pc},
    }


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


def _meta(chunks):
    for c in chunks:
        if isinstance(c, dict) and c.get("meta"):
            return c["meta"]
    return None


async def test_builtin_ethics_council_runs_and_judges():
    bp = PersonaCouncilBlueprint(config=_cfg())
    chunks = await _collect(bp.run([{"role": "user", "content": "Is it ok to lie?"}]))
    assert _final(chunks) == "SYNTH"  # judge synthesized
    prog = _progress(chunks)
    assert f"Council of {len(COUNCILS['ethics'])} lenses" in prog
    assert "Utilitarian" in prog and "Kantian" in prog  # the lens roster is named
    assert _meta(chunks) == {"backends": ["c"], "judge": "j"}


async def test_named_council_param_selects_roster():
    bp = PersonaCouncilBlueprint(config=_cfg())
    bp.set_params({"council": "science"})
    prog = _progress(await _collect(bp.run([{"role": "user", "content": "why is the sky blue?"}])))
    assert "Physicist" in prog and "Statistician" in prog
    assert "Utilitarian" not in prog


async def test_show_analysis_appends_lens_views():
    bp = PersonaCouncilBlueprint(config=_cfg())
    bp.set_params({"show_analysis": True})
    final = _final(await _collect(bp.run([{"role": "user", "content": "q"}])))
    assert "SYNTH" in final and "VIEW" in final and "Council views" in final


async def test_explicit_personas_roster():
    bp = PersonaCouncilBlueprint(config=_cfg())
    bp.set_params({"personas": [{"name": "Alpha", "lens": "be alpha"}, {"name": "Beta", "lens": "be beta"}]})
    prog = _progress(await _collect(bp.run([{"role": "user", "content": "q"}])))
    assert "Alpha" in prog and "Beta" in prog
    assert "Utilitarian" not in prog  # built-in council not used


async def test_no_judge_returns_labeled_views():
    cfg = {"cli_agents": {"c": _echo("VIEW")}, "persona_council": {"cli": "c", "judge": "boom"}}
    cfg["cli_agents"]["boom"] = _boom()
    bp = PersonaCouncilBlueprint(config=cfg)
    bp.set_params({"council": "decision"})
    final = _final(await _collect(bp.run([{"role": "user", "content": "q"}])))
    assert "VIEW" in final  # judge failed -> the lens views are returned, labeled
    assert "### FirstPrinciples" in final


async def test_no_cli_configured():
    bp = PersonaCouncilBlueprint(config={})
    final = _final(await _collect(bp.run([{"role": "user", "content": "q"}])))
    assert "No CLI backend" in final
    assert "[Manage CLI](/chat?settings=cli-agents)" in final
    assert "docs/CLI_FUSION.md" not in final


async def test_all_lenses_fail():
    cfg = {"cli_agents": {"boom": _boom()}, "persona_council": {"cli": "boom", "judge": "boom"}}
    bp = PersonaCouncilBlueprint(config=cfg)
    assert "Every council lens failed" in _final(await _collect(bp.run([{"role": "user", "content": "q"}])))

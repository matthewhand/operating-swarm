"""Tests for the Hybrid Swarm blueprint (REST reasoning MIXED with CLI agents).

Both halves are deterministic, independently:
  * REST half  -> stubbed via SWARM_TEST_MODE.
  * CLI half   -> driven by fake echo CLIs (python -c '... print(...)'), so no
                  real model/network is touched (same idiom as test_cli_fusion).
"""

from __future__ import annotations

import sys

import pytest

from swarm.blueprints.hybrid_swarm.blueprint_hybrid_swarm import HybridSwarmBlueprint

PY = sys.executable


# --------------------------------------------------------------------------- #
# Fake CLIs + config helpers (mirror tests/blueprints/test_cli_fusion.py)
# --------------------------------------------------------------------------- #

def _echo(name_prefix: str) -> dict:
    return {"cmd": [PY, "-c", f"import sys; print('{name_prefix}:' + sys.argv[1])", "{prompt}"]}


def _boom(code: int = 1) -> dict:
    return {"cmd": [PY, "-c", f"import sys; sys.exit({code})", "{prompt}"]}


def _config(*, grok="grok", panel=("a", "b"), judge=None) -> dict:
    agents = {"grok": _echo("GROK"), "a": _echo("A"), "b": _echo("B")}
    hc: dict = {}
    if grok is not None:
        hc["grok"] = grok
    if panel is not None:
        hc["panel"] = list(panel)
    if judge is not None:
        hc["judge"] = judge
    return {"cli_agents": agents, "hybrid_swarm": hc}


async def _collect(gen):
    return [c async for c in gen]


def _final_content(chunks):
    text = None
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = msgs[0]["content"]
    return text


def _all_progress(chunks):
    return "\n".join(
        c["content"]
        for c in chunks
        if isinstance(c, dict) and c.get("type") == "fusion_progress"
    )


@pytest.fixture(autouse=True)
def _test_mode(monkeypatch):
    # Make the REST half deterministic with no network for every test here.
    monkeypatch.setenv("SWARM_TEST_MODE", "1")


# --------------------------------------------------------------------------- #
# Discovery / metadata contract
# --------------------------------------------------------------------------- #

def test_metadata_name_is_hybrid_swarm():
    assert HybridSwarmBlueprint.metadata["name"] == "hybrid_swarm"


def test_subclasses_blueprint_base():
    from swarm.core.blueprint_base import BlueprintBase

    assert issubclass(HybridSwarmBlueprint, BlueprintBase)


# --------------------------------------------------------------------------- #
# Happy path: REST + grok persona + consensus all run
# --------------------------------------------------------------------------- #

async def test_run_mixes_rest_grok_and_consensus():
    bp = HybridSwarmBlueprint(config=_config())
    bp.set_params({})
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    final = _final_content(chunks)
    assert chunks[-1].get("final") is True
    # REST step ran (stubbed plan present).
    assert "[rest-plan] hi" in final
    # grok persona ran (fake CLI echoed the sub-question, which starts with prompt).
    assert "GROK:hi" in final
    # consensus panel ran (one of the fake panelists' echoes).
    assert ("A:hi" in final) or ("B:hi" in final)


async def test_run_yields_progress_for_each_stage():
    bp = HybridSwarmBlueprint(config=_config())
    chunks = await _collect(bp.run([{"role": "user", "content": "q"}]))
    progress = _all_progress(chunks)
    assert "REST step" in progress
    assert "grok persona" in progress
    assert "consensus" in progress.lower()
    assert "a, b" in progress  # both panelists named


async def test_final_answer_is_non_empty_in_test_mode():
    bp = HybridSwarmBlueprint(config=_config())
    chunks = await _collect(bp.run([{"role": "user", "content": "anything"}]))
    final = _final_content(chunks)
    assert isinstance(final, str) and final.strip()


# --------------------------------------------------------------------------- #
# Empty prompt
# --------------------------------------------------------------------------- #

async def test_empty_prompt_short_circuits():
    bp = HybridSwarmBlueprint(config=_config())
    chunks = await _collect(bp.run([]))
    assert "No prompt provided" in _final_content(chunks)
    assert chunks[-1].get("final") is True


# --------------------------------------------------------------------------- #
# No CLI agents configured: REST half still produces a deterministic answer
# --------------------------------------------------------------------------- #

async def test_no_cli_agents_still_runs_rest_step():
    bp = HybridSwarmBlueprint(config={})
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    final = _final_content(chunks)
    assert "[rest-plan] hi" in final  # REST half is deterministic on its own
    assert "No CLI agents are configured" in final
    assert "[Manage CLI](/chat?settings=cli-agents)" in final
    assert "docs/CLI_FUSION.md" not in final
    assert chunks[-1].get("final") is True


# --------------------------------------------------------------------------- #
# Per-request params override the config block
# --------------------------------------------------------------------------- #

async def test_params_override_grok_and_panel():
    cfg = _config(grok="grok", panel=("a", "b"))
    bp = HybridSwarmBlueprint(config=cfg)
    # Restrict the panel to just "a" and use "b" as the grok persona.
    bp.set_params({"grok": "b", "panel": ["a"]})
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    final = _final_content(chunks)
    assert "B:hi" in final          # grok persona overridden to "b"
    assert "A:hi" in final          # panel narrowed to "a"
    progress = _all_progress(chunks)
    assert "Escalating to consensus over a…" in progress
    assert "grok persona (`b`)" in progress


# --------------------------------------------------------------------------- #
# Resolution falls back to the cli_fusion preset when no hybrid_swarm panel
# --------------------------------------------------------------------------- #

async def test_falls_back_to_cli_fusion_preset():
    cfg = {
        "cli_agents": {"grok": _echo("GROK"), "a": _echo("A"), "b": _echo("B")},
        # No hybrid_swarm block -> grok defaults to first available; panel from preset.
        "cli_fusion": {"presets": {"p": {"panel": ["a", "b"]}}, "default_preset": "p"},
    }
    bp = HybridSwarmBlueprint(config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    final = _final_content(chunks)
    assert "[rest-plan] hi" in final
    assert ("A:hi" in final) or ("B:hi" in final)  # consensus ran off the preset panel


# --------------------------------------------------------------------------- #
# CLI failures never sink the run (sentinels, not exceptions)
# --------------------------------------------------------------------------- #

async def test_grok_failure_degrades_to_sentinel_not_exception():
    cfg = {
        "cli_agents": {"grok": _boom(), "a": _echo("A"), "b": _echo("B")},
        "hybrid_swarm": {"grok": "grok", "panel": ["a", "b"]},
    }
    bp = HybridSwarmBlueprint(config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    final = _final_content(chunks)
    # cli_persona returns "[grok unavailable: …]" rather than raising.
    assert "grok unavailable" in final
    # The consensus panel survivors still answer.
    assert ("A:hi" in final) or ("B:hi" in final)
    assert chunks[-1].get("final") is True


async def test_all_panel_fail_reports_no_consensus():
    cfg = {
        "cli_agents": {"grok": _echo("GROK"), "boom1": _boom(), "boom2": _boom(2)},
        "hybrid_swarm": {"grok": "grok", "panel": ["boom1", "boom2"]},
    }
    bp = HybridSwarmBlueprint(config=cfg)
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    final = _final_content(chunks)
    # consensus_fn returns "(no consensus reached)" when every panelist failed.
    assert "(no consensus reached)" in final
    # grok persona still contributed; REST plan still present.
    assert "GROK:hi" in final
    assert "[rest-plan] hi" in final


# --------------------------------------------------------------------------- #
# Unknown names in config are filtered before registry.get() is called
# --------------------------------------------------------------------------- #

async def test_unknown_panel_names_are_filtered():
    cfg = {
        "cli_agents": {"grok": _echo("GROK"), "a": _echo("A")},
        "hybrid_swarm": {"grok": "grok", "panel": ["a", "ghost-not-configured"]},
    }
    bp = HybridSwarmBlueprint(config=cfg)
    # Must not raise CliAdapterError on the unknown "ghost-not-configured".
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    assert "A:hi" in _final_content(chunks)

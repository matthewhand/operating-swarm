"""Tests for the hybrid_team blueprint (REST coordinator + grok persona + consensus).

Both halves are made deterministic without a live LLM or live CLI:

* REST half -> stubbed by setting ``SWARM_TEST_MODE``.
* CLI half  -> driven by fake echo CLIs (``python -c '... print(...)'``), the same
               idiom as tests/blueprints/test_cli_fusion.py / test_cli_agent.py.
"""

from __future__ import annotations

import sys

import pytest

from swarm.blueprints.hybrid_team.blueprint_hybrid_team import HybridTeamBlueprint

PY = sys.executable


# --------------------------------------------------------------------------- #
# Fake CLIs + config helpers (mirror tests/blueprints/test_cli_fusion.py)
# --------------------------------------------------------------------------- #

def _echo(prefix: str) -> dict:
    return {"cmd": [PY, "-c", f"import sys; print('{prefix}:' + sys.argv[1])", "{prompt}"]}


def _boom(code: int = 1) -> dict:
    return {"cmd": [PY, "-c", f"import sys; sys.exit({code})", "{prompt}"]}


def _config(*, grok="grok", panel=("a", "b"), judge=None) -> dict:
    agents = {"grok": _echo("GROK"), "a": _echo("A"), "b": _echo("B")}
    block: dict = {"grok": grok, "panel": list(panel)}
    if judge is not None:
        block["judge"] = judge
    return {"cli_agents": agents, "hybrid_team": block}


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
    # REST half deterministic: no model / no network / no API key.
    monkeypatch.setenv("SWARM_TEST_MODE", "1")


# --------------------------------------------------------------------------- #
# Discovery / metadata
# --------------------------------------------------------------------------- #

def test_metadata_name_is_hybrid_team():
    assert HybridTeamBlueprint.metadata["name"] == "hybrid_team"


def test_subclasses_blueprint_base():
    from swarm.core.blueprint_base import BlueprintBase

    assert issubclass(HybridTeamBlueprint, BlueprintBase)


# --------------------------------------------------------------------------- #
# REST + CLI mix (the happy path)
# --------------------------------------------------------------------------- #

async def test_run_mixes_rest_grok_and_consensus():
    bp = HybridTeamBlueprint(config=_config())
    bp.set_params({})
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))

    final = _final_content(chunks)
    assert chunks[-1].get("final") is True
    # REST coordinator ran (stubbed under SWARM_TEST_MODE).
    assert "[rest-plan] hi" in final
    # grok persona ran (fake CLI echoed with its prefix).
    assert "GROK:" in final
    # consensus panel ran (one of the fake panelists' echoes).
    assert ("A:" in final) or ("B:" in final)


async def test_progress_names_grok_and_panel():
    bp = HybridTeamBlueprint(config=_config())
    bp.set_params({})
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    progress = _all_progress(chunks)
    assert "REST step" in progress
    assert "grok" in progress
    assert "a, b" in progress  # panel names surfaced on the consensus progress line


async def test_deterministic_across_runs():
    cfg = _config()
    a = _final_content(await _collect(HybridTeamBlueprint(config=cfg).run(
        [{"role": "user", "content": "q"}])))
    b = _final_content(await _collect(HybridTeamBlueprint(config=cfg).run(
        [{"role": "user", "content": "q"}])))
    assert a == b


# --------------------------------------------------------------------------- #
# Per-request param overrides
# --------------------------------------------------------------------------- #

async def test_params_override_grok_and_panel():
    bp = HybridTeamBlueprint(config=_config(grok="grok", panel=("a", "b")))
    bp.set_params({"grok": "a", "panel": ["b"]})
    final = _final_content(await _collect(bp.run([{"role": "user", "content": "hi"}])))
    # grok persona is now adapter "a".
    assert "A:" in final
    # panel collapsed to a single panelist "b".
    assert "B:" in final
    assert "GROK:" not in final


# --------------------------------------------------------------------------- #
# Empty / missing configuration
# --------------------------------------------------------------------------- #

async def test_empty_prompt():
    bp = HybridTeamBlueprint(config=_config())
    chunks = await _collect(bp.run([]))
    assert "No prompt provided" in _final_content(chunks)


async def test_no_cli_agents_still_returns_rest_plan():
    # No cli_agents configured: REST coordinator alone still yields a final answer.
    bp = HybridTeamBlueprint(config={})
    bp.set_params({})
    chunks = await _collect(bp.run([{"role": "user", "content": "solo"}]))
    final = _final_content(chunks)
    assert chunks[-1].get("final") is True
    assert "[rest-plan] solo" in final
    assert "No CLI agents are configured" in final
    assert "[Manage CLI](/chat?settings=cli-agents)" in final
    assert "docs/CLI_FUSION.md" not in final


# --------------------------------------------------------------------------- #
# CLI failures never sink the run (cli_persona / consensus_fn return sentinels)
# --------------------------------------------------------------------------- #

async def test_grok_failure_degrades_gracefully():
    cfg = {
        "cli_agents": {"grok": _boom(), "a": _echo("A"), "b": _echo("B")},
        "hybrid_team": {"grok": "grok", "panel": ["a", "b"]},
    }
    bp = HybridTeamBlueprint(config=cfg)
    bp.set_params({})
    final = _final_content(await _collect(bp.run([{"role": "user", "content": "hi"}])))
    # grok persona never raises: failure surfaces as an "[grok unavailable: …]" note.
    assert "grok unavailable" in final
    # The consensus panel still produced an answer.
    assert ("A:" in final) or ("B:" in final)


def test_resolve_prefers_grok_then_agy_not_claude():
    class _Reg:
        def names(self):
            return ["claude", "agy", "grok"]

        def available(self):
            return ["claude", "agy", "grok"]

    bp = HybridTeamBlueprint(
        config={"cli_agents": {"claude": _echo("C"), "agy": _echo("A"), "grok": _echo("G")}}
    )
    grok, _panel, _judge = bp._resolve({}, _Reg())
    assert grok == "grok"

    no_grok = HybridTeamBlueprint(
        config={"cli_agents": {"claude": _echo("C"), "agy": _echo("A")}}
    )

    class _Agy:
        def names(self):
            return ["claude", "agy"]

        def available(self):
            return ["claude", "agy"]

    grok2, _p, _j = no_grok._resolve({}, _Agy())
    assert grok2 == "agy"


def test_claude_persona_ignored_unless_in_config():
    """Host claude on PATH / registry must not become the orchestrator."""
    bp = HybridTeamBlueprint(config={"cli_agents": {"grok": _echo("GROK")}})

    class _Reg:
        def names(self):
            return ["grok", "claude"]

        def get(self, name):
            raise AssertionError(f"must not fetch {name}")

    assert bp._claude_persona(_Reg()) is None

    bp_explicit = HybridTeamBlueprint(
        config={"cli_agents": {"claude": _echo("C"), "grok": _echo("GROK")}}
    )
    assert bp_explicit._claude_persona(_RegGet()) is not None


class _RegGet:
    def names(self):
        return ["grok", "claude"]

    def get(self, name):
        from swarm.core.cli_adapter import CliAdapter

        return CliAdapter.from_config(name, _echo(name.upper()))


async def test_all_panel_fail_reports_no_consensus():
    cfg = {
        "cli_agents": {"grok": _echo("GROK"), "boom": _boom()},
        "hybrid_team": {"grok": "grok", "panel": ["boom"]},
    }
    bp = HybridTeamBlueprint(config=cfg)
    bp.set_params({})
    final = _final_content(await _collect(bp.run([{"role": "user", "content": "hi"}])))
    # grok still answered; consensus collapsed to the sentinel.
    assert "GROK:" in final
    assert "no consensus reached" in final


async def test_workdir_uses_run_consensus_path(tmp_path, monkeypatch):
    # Passing a workdir takes the run_consensus branch; still deterministic.
    monkeypatch.setenv("SWARM_WORKSPACES_DIR", str(tmp_path))
    bp = HybridTeamBlueprint(config=_config())
    bp.set_params({"workdir": "team-wd"})
    final = _final_content(await _collect(bp.run([{"role": "user", "content": "hi"}])))
    assert "[rest-plan] hi" in final
    assert ("A:" in final) or ("B:" in final)

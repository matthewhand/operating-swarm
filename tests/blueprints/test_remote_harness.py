"""Tests for the remote_harness blueprint grammar and as_tool wiring."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from swarm.blueprints.remote_harness.blueprint_remote_harness import (
    RemoteHarnessBlueprint,
    _render_operate,
)
from swarm.core import remotes as remotes_core
from swarm.core.blueprint_discovery import discover_blueprints
from swarm.core.remotes import HealthResult, OperateResult


async def _collect(gen):
    return [c async for c in gen]


def _final(chunks):
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content"):
            return msgs[0]["content"]
    return None


@pytest.fixture
def bp():
    return RemoteHarnessBlueprint(config={"llm": {}})


async def _ask(bp, content, params=None):
    bp.set_params(params or {})
    return _final(await _collect(bp.run([{"role": "user", "content": content}])))


def test_remote_harness_is_discoverable():
    found = discover_blueprints("src/swarm/blueprints")
    assert "remote_harness" in found


@pytest.mark.asyncio
async def test_health_grammar(bp):
    with patch(
        "swarm.blueprints.remote_harness.blueprint_remote_harness.remotes_core.check_health",
        return_value=HealthResult(remote="hermes", ok=False, state="DOWN", detail="tcp timeout"),
    ) as probe:
        out = await _ask(bp, "health hermes")
    assert "DOWN" in out
    assert "hermes" in out
    probe.assert_called()


@pytest.mark.asyncio
async def test_list_config_without_probing(bp):
    out = await _ask(bp, "list")
    assert "hermes" in out
    assert "omb" in out
    assert "rakazo" in out
    assert "swarm" in out
    assert "10.0.0.36:8642" in out
    assert "127.0.0.1:9" in out


@pytest.mark.asyncio
async def test_send_params(bp):
    with patch(
        "swarm.blueprints.remote_harness.blueprint_remote_harness.remotes_core.operate",
        return_value=OperateResult(remote="hermes", op="send", ok=True, detail="started"),
    ) as op:
        out = await _ask(bp, "", params={"op": "send", "name": "hermes", "prompt": "hi"})
    assert "OK" in out
    op.assert_called_once()


def test_render_operate_not_added_is_natural_sentence(monkeypatch):
    monkeypatch.delenv("HERMES_BASE_URL", raising=False)
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    result = remotes_core.operate(
        "hermes", "send", prompt="hey there", config={"llm": {}, "remotes": {}}
    )
    assert result.ok is False
    out = _render_operate(result)
    assert out.startswith("Hermes is not added as a remote")
    assert "send: FAIL" not in out
    assert "swarm-cli remotes set hermes" in out


@pytest.mark.asyncio
async def test_health_not_added_rendered_natural(bp):
    detail = "Hermes is not added as a remote — the sidebar seat is a catalog placeholder."
    with patch(
        "swarm.blueprints.remote_harness.blueprint_remote_harness.remotes_core.check_health",
        return_value=HealthResult(remote="hermes", ok=False, state="UNKNOWN", detail=detail),
    ) as probe:
        out = await _ask(bp, "health hermes")
    assert out.startswith("Hermes is not added as a remote")
    assert "UNKNOWN —" not in out
    assert "hermes:" not in out
    probe.assert_called()


@pytest.mark.asyncio
async def test_runner_failure_fallback_is_short(bp, monkeypatch):
    """Coordinator LLM failure yields a short honest fallback, not a dump (issue #131)."""
    async def boom(*args, **kwargs):
        raise RuntimeError("coordinator exploded with a very long detail string" * 40)

    monkeypatch.setattr("agents.Runner.run", boom)
    out = await _ask(bp, "tell me something interesting")
    # No bound remote ⇒ just the short honest line — never the full
    # multi-remote health dump or a raw stack dump (DEBUG may append the
    # bounded exception detail via client_safe_error_message).
    assert "unavailable" in out
    assert "hermes:" not in out and "omb:" not in out and "rakazo" not in out
    assert len(out) < 700


@pytest.mark.asyncio
async def test_runner_failure_fallback_bound_shows_only_bound_health(bp, monkeypatch):
    """A bound seat keeps one health line + the honest failure, nothing else."""
    async def boom(*args, **kwargs):
        raise RuntimeError("boom detail " * 60)

    monkeypatch.setattr("agents.Runner.run", boom)
    monkeypatch.setattr(
        "swarm.blueprints.remote_harness.blueprint_remote_harness._health_tool",
        lambda name="": "hermes: DOWN — tcp timeout",
    )
    monkeypatch.setattr(bp, "_parse", lambda messages: ("health", "hermes", "", ""))
    out = await _ask(bp, "tell me something interesting")
    assert out.startswith("hermes: DOWN")
    assert "unavailable" in out
    assert "rakazo" not in out and "swarm:" not in out
    assert len(out) < 700


@pytest.mark.asyncio
async def test_as_tool_specialists_wired(bp):
    agents = bp._build_agents()
    assert agents, "expected coordinator + specialist agents (bare Agent fallback if no LLM)"
    coord = agents["coordinator"]
    names = []
    for tool in getattr(coord, "tools", []) or []:
        names.append(getattr(tool, "name", None) or getattr(tool, "__name__", ""))
    joined = " ".join(str(n) for n in names)
    assert "consult_hermes" in joined
    assert "consult_omb" in joined
    assert "consult_rakazo" in joined


@pytest.mark.asyncio
async def test_as_tool_only_placed_members():
    bp = RemoteHarnessBlueprint(
        config={"llm": {}, "agent_team": {"members": ["hermes"]}}
    )
    agents = bp._build_agents()
    assert agents, "expected coordinator + placed specialist"
    assert "hermes" in agents
    assert "omb" not in agents
    assert "rakazo" not in agents
    assert "swarm" not in agents
    names = []
    for tool in getattr(agents["coordinator"], "tools", []) or []:
        names.append(getattr(tool, "name", None) or getattr(tool, "__name__", ""))
    joined = " ".join(str(n) for n in names)
    assert "consult_hermes" in joined
    assert "consult_omb" not in joined
    assert "consult_rakazo" not in joined
    assert "consult_swarm" not in joined


@pytest.mark.asyncio
async def test_as_tool_swarm_when_placed():
    bp = RemoteHarnessBlueprint(
        config={"llm": {}, "agent_team": {"members": ["swarm"]}}
    )
    agents = bp._build_agents()
    assert agents, "expected coordinator + swarm specialist"
    assert "swarm" in agents
    assert "hermes" not in agents
    names = []
    for tool in getattr(agents["coordinator"], "tools", []) or []:
        names.append(getattr(tool, "name", None) or getattr(tool, "__name__", ""))
    joined = " ".join(str(n) for n in names)
    assert "consult_swarm" in joined

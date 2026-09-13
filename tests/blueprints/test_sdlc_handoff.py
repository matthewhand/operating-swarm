"""REQ-156: sdlc_handoff blueprint wires example graph edges."""

from __future__ import annotations

import pytest

from swarm.blueprints.sdlc_handoff.blueprint_sdlc_handoff import SdlcHandoffBlueprint
from swarm.core.blueprint_discovery import discover_blueprints
from swarm.core.handoff_graph import (
    PIPELINE_GRAPH_ID,
    SKEPTIC_LOOP_GRAPH_ID,
    live_edges,
)


async def _collect(gen):
    return [c async for c in gen]


def _final(chunks):
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content"):
            return msgs[0]["content"]
    return None


async def _ask(bp, content, params=None):
    if params:
        merged = dict(bp._params)
        merged.update(params)
        bp.set_params(merged)
    return _final(await _collect(bp.run([{"role": "user", "content": content}])))


def test_sdlc_handoff_is_discoverable():
    found = discover_blueprints("src/swarm/blueprints")
    assert "sdlc_handoff" in found
    assert "sdlc-handoff" in found
    meta = found["sdlc_handoff"]["metadata"]
    assert "handoff" in (meta.get("description") or "").lower()


def test_pipeline_variant_wires_one_way_edges():
    bp = SdlcHandoffBlueprint(config={"llm": {}, "sdlc_handoff": {"variant": "pipeline"}})
    graph = bp.graph()
    assert graph.id == PIPELINE_GRAPH_ID
    agents = bp._build_agents()
    edges = live_edges(agents)
    assert edges == {("ba", "engineer"), ("engineer", "tester")}
    assert ("ba", "tester") not in edges
    assert graph.outgoing("tester") == ()


def test_skeptic_loop_variant_wires_punt_back():
    bp = SdlcHandoffBlueprint(
        config={"llm": {}, "sdlc_handoff": {"variant": "skeptic_loop"}}
    )
    graph = bp.graph()
    assert graph.id == SKEPTIC_LOOP_GRAPH_ID
    agents = bp._build_agents()
    edges = live_edges(agents)
    assert ("skeptic", "engineer") in edges
    assert ("tester", "skeptic") in edges
    assert ("ba", "tester") not in edges


@pytest.mark.asyncio
async def test_run_prints_pipeline_edges(monkeypatch):
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    bp = SdlcHandoffBlueprint(config={"llm": {}})
    out = await _ask(bp, "graph")
    assert "ba -> engineer" in out
    assert "engineer -> tester" in out
    assert "ba -> tester" not in out
    assert "CLI and remote" in out


@pytest.mark.asyncio
async def test_run_variant_switch_prints_skeptic_edge(monkeypatch):
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    bp = SdlcHandoffBlueprint(config={"llm": {}})
    out = await _ask(bp, "variant skeptic_loop")
    assert "skeptic -> engineer" in out
    assert "circular-skeptic" in out


def _profile_config():
    return {
        "llm": {
            "local": {
                "provider": "openai",
                "model": "auxiliary",
                "base_url": "http://10.0.0.30:8000/v1",
                "api_key": "test-key",
            }
        },
        "settings": {"default_llm_profile": "local"},
    }


class _FakeCompletions:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        class _Msg:
            content = self.content

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]

        return _Resp()


class _FakeClient:
    last_kwargs = None
    completions = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs
        self.chat = type("Chat", (), {"completions": type(self).completions})()


@pytest.mark.asyncio
async def test_ba_chat_calls_saved_profile_not_echo(monkeypatch):
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    fake = _FakeCompletions(content="Acceptance criteria: user can log in.")
    _FakeClient.completions = fake
    monkeypatch.setattr(
        "swarm.blueprints.sdlc_handoff.blueprint_sdlc_handoff.AsyncOpenAI",
        _FakeClient,
    )
    bp = SdlcHandoffBlueprint(config=_profile_config())
    bp.set_params({"target": "ba"})
    user = "Write a user story for login unique-ba-echo-probe"
    out = await _ask(bp, user)
    assert out == "Acceptance criteria: user can log in."
    assert user not in out
    assert "falling back to echo" not in out
    assert fake.kwargs["model"] == "auxiliary"
    assert _FakeClient.last_kwargs["base_url"] == "http://10.0.0.30:8000/v1"
    roles = [m["role"] for m in fake.kwargs["messages"]]
    assert "system" in roles
    assert "user" in roles


@pytest.mark.asyncio
async def test_ba_chat_unreachable_llm_is_honest_error_not_echo(monkeypatch):
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    fake = _FakeCompletions(error=RuntimeError("connection refused"))
    _FakeClient.completions = fake
    monkeypatch.setattr(
        "swarm.blueprints.sdlc_handoff.blueprint_sdlc_handoff.AsyncOpenAI",
        _FakeClient,
    )
    bp = SdlcHandoffBlueprint(config=_profile_config())
    probe = "unique-ba-echo-probe-unreachable"
    out = await _ask(bp, probe)
    assert probe not in out
    assert "falling back to echo" not in out.lower()
    assert "Error: LLM call failed" in out
    assert "connection refused" in out

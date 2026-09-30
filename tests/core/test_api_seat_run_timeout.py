"""Non-agent_router API seats must not cap an LLM turn below the #1264 budget.

``ApiKindBase.run`` and ``ChatbotBlueprint._run_non_interactive`` used to wrap
``Runner.run`` in a 30s / 20s ``asyncio.wait_for``. A slow gateway route (the
``orchestration`` profile reports 300s+) therefore always failed. Both now
resolve their budget through ``swarm.core.agent_run_timeout.agent_run_timeout``.
"""

from __future__ import annotations

import asyncio

import pytest


class _FakeResult:
    final_output = "ok"


async def _fake_runner_run(_agent, _instruction):
    return _FakeResult()


@pytest.fixture
def capture_wait_for(monkeypatch):
    """Record the timeout handed to ``asyncio.wait_for`` and run the awaitable."""
    captured: dict[str, float] = {}

    async def _spy(awaitable, timeout):
        captured["timeout"] = timeout
        return await awaitable

    monkeypatch.setattr(asyncio, "wait_for", _spy)
    return captured


@pytest.fixture(autouse=True)
def _fake_runner(monkeypatch):
    import agents

    monkeypatch.setattr(agents.Runner, "run", staticmethod(_fake_runner_run))


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    monkeypatch.delenv("SWARM_AGENT_LLM_TIMEOUT", raising=False)
    # Never touch the real model resolver / Django config on a bare agent.
    monkeypatch.setattr(
        "swarm.core.blueprint_base.apply_agent_model_defaults",
        lambda agent: agent,
    )


async def _run_api_kind_base(config):
    from swarm.core.kind_bases import ApiKindBase

    class StubApi(ApiKindBase):
        metadata = {"name": "stub", "version": "1.0.0"}

        def create_starting_agent(self, _mcp_servers=None):
            return object()

    bp = StubApi("stub", config=config)
    return [c async for c in bp.run([{"role": "user", "content": "hi"}])]


def _chatbot(config):
    from swarm.blueprints.chatbot.blueprint_chatbot import ChatbotBlueprint

    bp = ChatbotBlueprint("chatbot", config=config)
    bp.create_starting_agent = lambda **_: object()
    return bp


async def test_api_kind_base_uses_configurable_timeout(capture_wait_for, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_LLM_TIMEOUT", "600")
    chunks = await _run_api_kind_base({"settings": {"agent_llm_timeout_s": 300}})
    assert capture_wait_for["timeout"] == 600.0
    assert chunks[-1]["final"] is True


async def test_api_kind_base_uses_config_setting_when_env_absent(capture_wait_for):
    await _run_api_kind_base({"settings": {"agent_llm_timeout_s": 450}})
    assert capture_wait_for["timeout"] == 450.0


async def test_api_kind_base_defaults_lenient(capture_wait_for):
    await _run_api_kind_base({})
    assert capture_wait_for["timeout"] == 600.0


async def test_chatbot_api_seat_uses_configurable_timeout(capture_wait_for, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_LLM_TIMEOUT", "600")
    bp = _chatbot({"settings": {"agent_llm_timeout_s": 120}})
    chunks = [c async for c in bp._run_non_interactive("hi")]
    assert capture_wait_for["timeout"] == 600.0
    assert chunks[-1]["final"] is True


async def test_chatbot_api_seat_defaults_lenient(capture_wait_for):
    bp = _chatbot({})
    chunks = [c async for c in bp._run_non_interactive("hi")]
    assert capture_wait_for["timeout"] == 600.0
    assert chunks[-1]["final"] is True

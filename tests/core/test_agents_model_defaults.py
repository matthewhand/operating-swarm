"""#737: bare openai-agents Agents must not inherit gpt-4o via /responses.

Support-generated blueprints (and persona_swarm) construct ``Agent(...)``
without a model; the SDK then defaults to ``gpt-4o`` on the ``/responses``
API — both rejected by LiteLLM/Ollama/other OpenAI-compatible providers.
"""

import pytest


def test_framework_init_forces_chat_completions_default():
    """Importing the framework pins the SDK's default API to chat_completions."""
    import agents.models._openai_shared as shared

    import swarm.core.blueprint_base  # noqa: F401  (framework init side effect)

    assert shared.get_use_responses_by_default() is False


def test_apply_agent_model_defaults_sets_env_model(monkeypatch):
    from agents import Agent

    from swarm.core.blueprint_base import apply_agent_model_defaults

    monkeypatch.setenv("LITELLM_MODEL", "orchestration-model")
    agent = Agent(name="A", instructions="i")
    assert agent.model is None  # SDK default state before the fix
    apply_agent_model_defaults(agent)
    assert agent.model == "orchestration-model"


def test_apply_agent_model_defaults_uses_chat_route(monkeypatch):
    """Without env override the chat-default route (settings chain) supplies it."""
    from agents import Agent

    from swarm.core.blueprint_base import apply_agent_model_defaults

    monkeypatch.delenv("LITELLM_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM", raising=False)
    monkeypatch.setattr(
        "swarm.core.blueprint_base._resolve_framework_chat_model",
        lambda: "default-chat-model",
    )
    agent = Agent(name="A", instructions="i")
    apply_agent_model_defaults(agent)
    assert agent.model == "default-chat-model"


def test_apply_agent_model_defaults_respects_explicit_model(monkeypatch):
    from agents import Agent

    from swarm.core.blueprint_base import apply_agent_model_defaults

    monkeypatch.setenv("LITELLM_MODEL", "orchestration-model")
    agent = Agent(name="A", instructions="i", model="explicit-model")
    apply_agent_model_defaults(agent)
    assert agent.model == "explicit-model"


@pytest.mark.asyncio
async def test_api_kind_base_applies_defaults_to_starting_agent(monkeypatch):
    """ApiKindBase.run wires the helper before Runner.run (#737)."""
    from swarm.core import kind_bases

    captured = {}

    class FakeAgent:
        name = "Start"
        model = None

    class FakeRunner:
        @staticmethod
        async def run(agent, instruction):
            captured["model"] = agent.model
            captured["instruction"] = instruction

            class R:
                final_output = "pong"

            return R()

    class Bp(kind_bases.ApiKindBase):
        def __init__(self):
            self.blueprint_id = "bare_agents_737"

        def create_starting_agent(self, mcp_servers):
            return FakeAgent()

    monkeypatch.setenv("LITELLM_MODEL", "orchestration-model")
    monkeypatch.setattr("agents.Runner", FakeRunner, raising=False)
    monkeypatch.setattr("swarm.core.kind_bases.Runner", FakeRunner, raising=False)

    bp = Bp()
    chunks = []
    async for chunk in bp.run([{"role": "user", "content": "hi"}]):
        chunks.append(chunk)
    assert chunks and chunks[0]["messages"][0]["content"] == "pong"
    assert captured["model"] == "orchestration-model"

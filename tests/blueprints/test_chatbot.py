"""Tests for the chatbot blueprint (minimal single-agent REST template).

Mirrors the async/_collect/final-content style of test_cli_agent.py and
test_cli_fusion.py. The SWARM_TEST_MODE path is exercised directly so these
tests need no live LLM, API key, or network.
"""

from __future__ import annotations

import pytest

from swarm.blueprints.chatbot.blueprint_chatbot import ChatbotBlueprint


async def _collect(gen):
    return [c async for c in gen]


def _final_content(chunks):
    text = None
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = msgs[0]["content"]
    return text


@pytest.fixture(autouse=True)
def _test_mode(monkeypatch):
    # Deterministic, network-free path for every test in this module.
    monkeypatch.setenv("SWARM_TEST_MODE", "1")


# --------------------------------------------------------------------------- #
# Metadata / discovery
# --------------------------------------------------------------------------- #

def test_metadata_name_is_chatbot():
    assert ChatbotBlueprint.metadata["name"] == "chatbot"


def test_subclasses_blueprint_base():
    from swarm.core.blueprint_base import BlueprintBase

    assert issubclass(ChatbotBlueprint, BlueprintBase)


# --------------------------------------------------------------------------- #
# run() behaviour
# --------------------------------------------------------------------------- #

async def test_echoes_user_message():
    bp = ChatbotBlueprint(blueprint_id="chatbot")
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert _final_content(chunks) == "You said: ping"


async def test_last_chunk_marked_final():
    bp = ChatbotBlueprint(blueprint_id="chatbot")
    chunks = await _collect(bp.run([{"role": "user", "content": "hi"}]))
    assert chunks[-1].get("final") is True


async def test_answer_is_nonempty_string():
    bp = ChatbotBlueprint(blueprint_id="chatbot")
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    final = _final_content(chunks)
    assert isinstance(final, str) and final.strip()


async def test_empty_messages_gives_greeting():
    bp = ChatbotBlueprint(blueprint_id="chatbot")
    chunks = await _collect(bp.run([]))
    final = _final_content(chunks)
    assert final == "Hello! How can I help you?"


async def test_blank_content_gives_greeting():
    bp = ChatbotBlueprint(blueprint_id="chatbot")
    chunks = await _collect(bp.run([{"role": "user", "content": "   "}]))
    assert _final_content(chunks) == "Hello! How can I help you?"


async def test_uses_latest_turn_in_multiturn():
    bp = ChatbotBlueprint(blueprint_id="chatbot")
    chunks = await _collect(
        bp.run(
            [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "ok"},
                {"role": "user", "content": "second"},
            ]
        )
    )
    assert _final_content(chunks) == "You said: second"


async def test_does_not_leak_spinner_text():
    # Guards the regression the API smoke matrix protects against.
    bp = ChatbotBlueprint(blueprint_id="chatbot")
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert not _final_content(chunks).startswith("Generating")


def test_create_starting_agent_uses_resolved_profile(monkeypatch):
    """api_agent maps to chatbot; both must honor default_llm_profile."""
    bp = ChatbotBlueprint(blueprint_id="chatbot")
    bp._resolved_llm_profile = "orchestration"
    seen = {}

    def fake(profile_name):
        seen["profile"] = profile_name
        raise RuntimeError("stop-before-agent")

    monkeypatch.setattr(bp, "_get_model_instance", fake)
    try:
        bp.create_starting_agent([])
    except RuntimeError as exc:
        assert "stop-before-agent" in str(exc)
    assert seen.get("profile") == "orchestration"


def test_get_model_instance_accepts_litellm_provider(monkeypatch):
    bp = ChatbotBlueprint(blueprint_id="chatbot")
    profile = {
        "provider": "litellm",
        "model": "orchestration",
        "base_url": "http://127.0.0.1:8000/v1",
        "api_key": "sk-test",
    }
    monkeypatch.setattr(bp, "get_llm_profile", lambda _name: dict(profile))
    monkeypatch.setattr(
        "swarm.core.config_loader.named_profile_model",
        lambda *_a, **_k: "orchestration",
    )
    captured = {}

    class _Client:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    class _Model:
        def __init__(self, model, openai_client):
            captured["model"] = model
            captured["client"] = openai_client

    monkeypatch.setattr(
        "swarm.blueprints.chatbot.blueprint_chatbot.AsyncOpenAI",
        _Client,
    )
    monkeypatch.setattr(
        "swarm.blueprints.chatbot.blueprint_chatbot.OpenAIChatCompletionsModel",
        _Model,
    )
    inst = bp._get_model_instance("orchestration")
    assert captured["model"] == "orchestration"
    assert isinstance(inst, _Model)

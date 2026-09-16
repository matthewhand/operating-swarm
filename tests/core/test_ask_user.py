"""Issue #221 — ask_user contract: opt-in, sanitize, cap, demo payload."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swarm.core.ask_user import (
    ERROR_CAP,
    ERROR_DISABLED,
    ERROR_INVALID,
    EVENT_TYPE,
    MAX_OUTSTANDING_PER_TURN,
    TOOL_NAME,
    AskUserSession,
    ask_user,
    attach_ask_user_to_agent,
    demo_profile_question,
    elicit_questions_enabled,
    install_ask_user_for_runtime,
    install_ask_user_session,
    normalize_answer,
    normalize_question,
    question_event,
    reset_ask_user_session,
)
from swarm.core.safety import CHANNEL_API, CHANNEL_CLI, CHANNEL_REMOTE


def test_elicit_questions_default_off():
    assert elicit_questions_enabled(None) is False
    assert elicit_questions_enabled({}) is False
    assert elicit_questions_enabled({"elicit_questions": False}) is False
    assert elicit_questions_enabled({"elicit_questions": True}) is True
    assert elicit_questions_enabled({"elicit_questions": "true"}) is True


def test_elicit_questions_cli_and_remote_never_enable():
    params = {"elicit_questions": True}
    assert elicit_questions_enabled(params, channel=CHANNEL_CLI) is False
    assert elicit_questions_enabled(params, channel=CHANNEL_REMOTE) is False
    assert elicit_questions_enabled(params, channel=CHANNEL_API) is True


def test_normalize_question_sanitizes_and_rejects_empty():
    payload = normalize_question(
        ask="  Which profile? \x1b[31m",
        choices=["staging", " staging ", "", "canary"],
        other=" Custom ",
        question_id="deploy-profile",
    )
    assert payload == {
        "id": "deploy-profile",
        "ask": "Which profile?",
        "choices": ["staging", "canary"],
        "other": "Custom",
    }
    assert normalize_question(ask="", choices=["a"]) is None
    assert normalize_question(ask="pick", choices=[]) is None


def test_normalize_question_parses_json_or_csv_choices():
    from_json = normalize_question(ask="pick", choices='["a","b"]')
    assert from_json is not None and from_json["choices"] == ["a", "b"]
    from_csv = normalize_question(ask="pick", choices="a, b, a")
    assert from_csv is not None and from_csv["choices"] == ["a", "b"]


def test_demo_profile_question_is_three_choices_plus_custom():
    demo = demo_profile_question()
    assert demo["ask"] == "Which profile should I deploy?"
    assert demo["choices"] == ["staging", "canary", "prod"]
    assert demo["other"] == "Custom profile"
    event = question_event(demo, agent_id="chatbot")
    assert event["type"] == EVENT_TYPE
    assert event["agent_id"] == "chatbot"
    assert event["id"] == demo["id"]


def test_normalize_answer_strips_tokenizer_junk():
    assert normalize_answer("staging<|endoftext|>") == "staging"
    assert normalize_answer(None) == ""


@pytest.mark.asyncio
async def test_session_cap_blocks_second_outstanding_question():
    calls: list[dict] = []

    async def elicit(question: dict) -> str:
        calls.append(question)
        # Stay outstanding until the first ask finishes.
        session.outstanding = MAX_OUTSTANDING_PER_TURN
        return "staging"

    session = AskUserSession(agent_id="chatbot", elicit_fn=elicit)
    first = await session.ask("Which profile should I deploy?", ["staging", "canary", "prod"])
    assert first == "staging"
    session.outstanding = MAX_OUTSTANDING_PER_TURN
    second = await session.ask("Again?", ["yes", "no"])
    assert second == ERROR_CAP
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_ask_user_tool_uses_installed_session():
    async def elicit(question: dict) -> str:
        assert question["ask"] == "Which profile should I deploy?"
        return "canary"

    session = AskUserSession(agent_id="chatbot", elicit_fn=elicit)
    token = install_ask_user_session(session)
    try:
        assert await ask_user("Which profile should I deploy?", "staging,canary,prod") == "canary"
    finally:
        reset_ask_user_session(token)


@pytest.mark.asyncio
async def test_ask_user_without_session_is_disabled():
    token = install_ask_user_session(None)
    try:
        assert await ask_user("pick?", "a,b") == ERROR_DISABLED
    finally:
        reset_ask_user_session(token)


@pytest.mark.asyncio
async def test_invalid_question_does_not_elicit():
    elicited = []

    async def elicit(question: dict) -> str:
        elicited.append(question)
        return "nope"

    session = AskUserSession(elicit_fn=elicit)
    assert await session.ask("", []) == ERROR_INVALID
    assert elicited == []


def test_install_is_opt_in_and_attaches_tool_name():
    agent = SimpleNamespace(tools=[], name="Chatbot")
    blueprint = SimpleNamespace(agents=[agent], create_starting_agent=lambda: agent)

    assert install_ask_user_for_runtime(blueprint, params={}) == []
    assert agent.tools == []

    attached = install_ask_user_for_runtime(
        blueprint, params={"elicit_questions": True}, channel=CHANNEL_API
    )
    assert TOOL_NAME in attached
    names = [
        str(getattr(tool, "name", None) or getattr(tool, "__name__", ""))
        for tool in agent.tools
    ]
    assert names.count(TOOL_NAME) == 1
    install_ask_user_for_runtime(
        blueprint, params={"elicit_questions": True}, channel=CHANNEL_API
    )
    names = [
        str(getattr(tool, "name", None) or getattr(tool, "__name__", ""))
        for tool in agent.tools
    ]
    assert names.count(TOOL_NAME) == 1


def test_attach_to_bare_agent():
    agent = SimpleNamespace()
    attached = attach_ask_user_to_agent(agent)
    assert TOOL_NAME in attached
    assert isinstance(agent.tools, list)
    assert agent.tools

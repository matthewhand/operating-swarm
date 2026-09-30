"""#1411 — emoji reactions persist and the agent add_reaction tool."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from swarm.core.chat_store import _normalize_messages
from swarm.core.message_reactions import (
    ACTOR_USER,
    ERROR_EMOJI,
    ERROR_INDEX,
    ERROR_NO_SESSION,
    ERROR_NO_TARGET,
    EVENT_TYPE,
    REACTION_EMOJIS,
    RESPOND_TOOL_NAME,
    TOOL_NAME,
    ReactionSession,
    actor_for_agent,
    add_reaction,
    attach_reaction_to_agent,
    emoji_error,
    install_reaction_for_runtime,
    install_reaction_session,
    normalize_reactions,
    public_reactions,
    reaction_only_record,
    reaction_tool_schema,
    reactions_for_theme,
    reset_reaction_session,
    resolve_target_index,
    ensure_reaction,
    normalize_emoji,
    respond_with_reaction,
    toggle_reaction,
)
from swarm.core.safety import CHANNEL_API, CHANNEL_CLI
from swarm.core.thread_load import public_message
from swarm.core.transcript_roles import messages_for_model


def test_toggle_adds_then_removes_user_reaction():
    message = {"role": "user", "content": "hi"}
    first = toggle_reaction(message, "👍", ACTOR_USER)
    assert first == [{"emoji": "👍", "actors": [ACTOR_USER]}]
    assert message["reactions"] == first
    second = toggle_reaction(message, "👍", ACTOR_USER)
    assert second == []
    assert "reactions" not in message


def test_toggle_rejects_unknown_emoji_and_keeps_store():
    message = {"role": "assistant", "content": "ok"}
    assert toggle_reaction(message, "🔥", ACTOR_USER) is None
    assert "reactions" not in message


def test_agent_and_user_share_a_pill():
    message = {"role": "user", "content": "ship it"}
    toggle_reaction(message, "🎉", ACTOR_USER)
    toggle_reaction(message, "🎉", actor_for_agent("jeeves"))
    pub = public_reactions(message["reactions"])
    assert pub == [
        {
            "emoji": "🎉",
            "count": 2,
            "userReacted": True,
            "agentReacted": True,
            "viewerReacted": True,
        }
    ]


def test_normalize_and_public_drop_unknown_emoji():
    raw = [
        {"emoji": "👍", "actors": ["user", "user", "agent:jeeves"]},
        {"emoji": "🔥", "actors": ["user"]},
        "nope",
    ]
    assert normalize_reactions(raw) == [
        {"emoji": "👍", "actors": ["user", "agent:jeeves"]},
    ]


def test_chat_store_and_thread_keep_reactions():
    [row] = _normalize_messages(
        [
            {
                "role": "user",
                "content": "hi",
                "reactions": [{"emoji": "👀", "actors": ["user"]}],
            }
        ]
    )
    assert row["reactions"] == [{"emoji": "👀", "actors": ["user"]}]
    public = public_message(row)
    assert public["reactions"][0]["emoji"] == "👀"
    assert public["reactions"][0]["count"] == 1
    assert public["reactions"][0]["userReacted"] is True


def test_messages_for_model_strip_reactions():
    payload = messages_for_model(
        [
            {
                "role": "user",
                "content": "hi",
                "reactions": [{"emoji": "👍", "actors": ["user"]}],
            }
        ]
    )
    assert payload == [{"role": "user", "content": "hi"}]


def test_resolve_target_defaults_to_last_user():
    messages = [
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
        {"role": "user", "content": "three"},
    ]
    assert resolve_target_index(messages, -1) == 2
    assert resolve_target_index(messages, 0) == 0
    assert resolve_target_index(messages, 9) is None
    assert resolve_target_index([], -1) is None


@pytest.mark.asyncio
async def test_add_reaction_tool_writes_and_emits():
    messages = [
        {"role": "user", "content": "please look"},
        {"role": "assistant", "content": "working"},
    ]
    emitted: list[dict] = []
    persisted = {"n": 0}

    async def persist():
        persisted["n"] += 1

    async def emit(event):
        emitted.append(event)

    session = ReactionSession(
        messages=messages,
        agent_id="jeeves",
        channel=CHANNEL_API,
        persist_fn=persist,
        emit_fn=emit,
    )
    token = install_reaction_session(session)
    try:
        result = json.loads(await add_reaction("👀"))
        assert result == {"ok": True, "action": "added", "emoji": "👀", "index": 0}
        assert messages[0]["reactions"] == [
            {"emoji": "👀", "actors": ["agent:jeeves"]}
        ]
        assert persisted["n"] == 1
        assert emitted[0]["type"] == EVENT_TYPE
        assert emitted[0]["emoji"] == "👀"
        assert emitted[0]["index"] == 0
        assert emitted[0]["reactions"][0]["agentReacted"] is True
        again = json.loads(await add_reaction("👀"))
        assert again["action"] == "added"
        assert messages[0]["reactions"] == [
            {"emoji": "👀", "actors": ["agent:jeeves"]}
        ]
        heart = json.loads(await add_reaction("❤", 0))
        assert heart == {"ok": True, "action": "added", "emoji": "❤️", "index": 0}
    finally:
        reset_reaction_session(token)


@pytest.mark.asyncio
async def test_add_reaction_tool_errors():
    assert await add_reaction("👍") == ERROR_NO_SESSION
    messages = [{"role": "assistant", "content": "only me"}]
    token = install_reaction_session(
        ReactionSession(messages=messages, agent_id="jeeves", channel=CHANNEL_API)
    )
    try:
        assert await add_reaction("🔥") == ERROR_EMOJI
        assert await add_reaction("👍") == ERROR_NO_TARGET
        assert await add_reaction("👍", 4) == ERROR_INDEX
    finally:
        reset_reaction_session(token)


def test_install_reaction_runtime_api_only():
    agent = SimpleNamespace(tools=[], functions=[])
    blueprint = SimpleNamespace(agents={"a": agent}, starting_agent=agent)
    assert install_reaction_for_runtime(blueprint, channel=CHANNEL_CLI) == []
    attached = install_reaction_for_runtime(blueprint, channel=CHANNEL_API)
    assert TOOL_NAME in attached
    names = {getattr(fn, "name", None) or getattr(fn, "__name__", "") for fn in agent.tools}
    assert TOOL_NAME in names or "add_reaction" in names
    assert attach_reaction_to_agent(agent) == []


def test_palette_is_the_eight_slack_style_emoji():
    assert REACTION_EMOJIS == ("👍", "👎", "❤️", "😂", "🎉", "👀", "🚀", "✅")


def test_normalize_emoji_accepts_unqualified_heart():
    assert normalize_emoji("❤") == "❤️"
    assert normalize_emoji("❤️") == "❤️"
    assert normalize_emoji("👍\ufe0f") == "👍"
    assert normalize_emoji("🔥") is None


def test_ensure_reaction_is_idempotent_add():
    message = {"role": "user", "content": "hi"}
    toggle_reaction(message, "👀", ACTOR_USER)
    first = ensure_reaction(message, "❤", "agent:jeeves")
    assert first == [
        {"emoji": "❤️", "actors": ["agent:jeeves"]},
        {"emoji": "👀", "actors": [ACTOR_USER]},
    ]
    second = ensure_reaction(message, "❤️", "agent:jeeves")
    assert second == first
    assert message["reactions"] == first


def test_bubble_themes_define_reaction_sets():
    assert reactions_for_theme("speech") == REACTION_EMOJIS
    assert reactions_for_theme("simple") == ("👍", "👎", "❤️", "😂", "✅")
    assert reactions_for_theme("irc") == ("👍", "👎", "👀", "🎉")
    assert reactions_for_theme("nope") == REACTION_EMOJIS
    speech = reaction_tool_schema("speech")
    irc = reaction_tool_schema("irc")
    assert speech["name"] == RESPOND_TOOL_NAME
    assert speech["parameters"]["properties"]["emoji"]["enum"] == list(REACTION_EMOJIS)
    assert irc["parameters"]["properties"]["emoji"]["enum"] == list(reactions_for_theme("irc"))
    assert "🚀" not in irc["parameters"]["properties"]["emoji"]["enum"]


def test_installed_tool_schema_follows_theme():
    agent = SimpleNamespace(tools=[], functions=[])
    blueprint = SimpleNamespace(agents={"a": agent}, starting_agent=agent)
    install_reaction_for_runtime(blueprint, channel=CHANNEL_API, theme="irc")
    tools = {getattr(fn, "name", ""): fn for fn in agent.tools}
    assert RESPOND_TOOL_NAME in tools
    enum = tools[RESPOND_TOOL_NAME].params_json_schema["properties"]["emoji"]["enum"]
    assert enum == list(reactions_for_theme("irc"))
    assert TOOL_NAME in tools
    assert tools[TOOL_NAME].params_json_schema["properties"]["emoji"]["enum"] == enum


@pytest.mark.asyncio
async def test_respond_with_reaction_happy_path_has_no_text():
    messages = [{"role": "user", "content": "ship it"}]
    session = ReactionSession(
        messages=messages,
        agent_id="jeeves",
        channel=CHANNEL_API,
        bubble_theme="speech",
    )
    token = install_reaction_session(session)
    try:
        result = json.loads(await respond_with_reaction("👍"))
    finally:
        reset_reaction_session(token)
    assert result == {"ok": True, "reaction_only": True, "emoji": "👍", "text": ""}
    assert messages == [{"role": "user", "content": "ship it"}]
    assert session.reaction_only == {"emoji": "👍", "actor": "agent:jeeves"}


@pytest.mark.asyncio
async def test_respond_with_reaction_rejects_emoji_outside_theme():
    assert await respond_with_reaction("👍") == ERROR_NO_SESSION
    messages = [{"role": "user", "content": "hi"}]
    session = ReactionSession(
        messages=messages,
        agent_id="jeeves",
        channel=CHANNEL_API,
        bubble_theme="irc",
    )
    token = install_reaction_session(session)
    try:
        assert await respond_with_reaction("🚀") == emoji_error("irc", RESPOND_TOOL_NAME)
        assert await respond_with_reaction("🔥") == emoji_error("irc", RESPOND_TOOL_NAME)
        assert await add_reaction("🚀") == emoji_error("irc", TOOL_NAME)
    finally:
        reset_reaction_session(token)
    assert session.reaction_only is None
    assert "reactions" not in messages[0]


def test_reaction_only_turn_persists_and_model_sees_the_emoji():
    row = reaction_only_record(emoji="👍", actor="agent:jeeves")
    stored = _normalize_messages(
        [
            {"role": "user", "content": "ship it"},
            row,
            {"role": "user", "content": "again"},
        ]
    )
    assert stored[1]["content"] == ""
    assert stored[1]["reaction_only"] is True
    assert stored[1]["reactions"] == [{"emoji": "👍", "actors": ["agent:jeeves"]}]
    public = public_message(stored[1])
    assert public["reaction_only"] is True
    assert public["content"] == ""
    assert public["reactions"][0]["emoji"] == "👍"
    assert public["reactions"][0]["agentReacted"] is True
    # The bubble stays empty. The model still sees the emoji, so the next
    # user turn is not adjacent to the previous one.
    model = messages_for_model(stored)
    assert model == [
        {"role": "user", "content": "ship it"},
        {"role": "assistant", "content": "👍"},
        {"role": "user", "content": "again"},
    ]
    ghost = public_message(
        {
            "role": "assistant",
            "content": "",
            "reaction_only": True,
            "reactions": [{"emoji": "🔥", "actors": ["agent:jeeves"]}],
        }
    )
    assert "reaction_only" not in ghost
    assert "reactions" not in ghost
    # failure: an unknown emoji does not survive as a reaction-only ghost
    dropped = _normalize_messages(
        [
            {
                "role": "assistant",
                "content": "",
                "reaction_only": True,
                "reactions": [{"emoji": "🔥", "actors": ["agent:jeeves"]}],
            }
        ]
    )
    assert "reaction_only" not in dropped[0]
    assert "reactions" not in dropped[0]


def test_reaction_only_rail_snippet_is_the_emoji(tmp_path):
    """A reaction-only latest turn must not crash the rail catalog.

    ``_latest_visible_turn`` used to return the emoji string. Callers then
    called ``.get`` on it and the whole activity sweep died.
    """
    from swarm.core import chat_store

    turns = [
        {"role": "user", "content": "ship it"},
        reaction_only_record(emoji="👍", actor="agent:jeeves"),
    ]
    assert chat_store._snippet_from_turns(turns) == "👍"
    assert chat_store._snippet_from_turns(
        turns + [{"role": "assistant", "content": "landed"}]
    ) == "landed"

    path = chat_store._active_path("u0", "jeeves", chat_store.store_dir(base_dir=tmp_path))
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    record = chat_store.empty_record(user_key="u0", agent_id="jeeves")
    record["updated_at"] = "2026-09-27T12:00:00+00:00"
    record["messages"] = turns
    chat_store._atomic_write(path, record)
    summary = chat_store.rail_activity_summaries(base_dir=tmp_path, user_key="u0")["jeeves"]
    assert summary["text"] == "👍"


def test_django_extra_round_trips_reaction_only_turn():
    """Django is the restore source of truth, so the flag and actors must survive."""
    from types import SimpleNamespace

    from swarm.core.chat_db import extra_from_turn, turn_from_row

    stored = reaction_only_record(emoji="👍", actor="agent:jeeves")
    extra = extra_from_turn(stored)
    assert extra["reaction_only"] is True
    assert extra["reactions"] == [{"emoji": "👍", "actors": ["agent:jeeves"]}]
    restored = turn_from_row(
        SimpleNamespace(sender="assistant", content="", extra=extra, timestamp=None)
    )
    assert restored["reaction_only"] is True
    assert restored["reactions"][0]["actors"] == ["agent:jeeves"]
    public = public_message(restored)
    assert public["reaction_only"] is True
    assert public["content"] == ""
    assert public["reactions"][0]["emoji"] == "👍"
    assert public["reactions"][0]["agentReacted"] is True
    ghost = extra_from_turn(
        {
            "role": "assistant",
            "content": "",
            "reaction_only": True,
            "reactions": [{"emoji": "🔥", "actors": ["agent:jeeves"]}],
        }
    )
    assert "reaction_only" not in ghost
    assert "reactions" not in ghost
    restored_ghost = turn_from_row(
        SimpleNamespace(
            sender="assistant",
            content="",
            extra={"reaction_only": True},
            timestamp=None,
        )
    )
    assert "reaction_only" not in restored_ghost
    poisoned = turn_from_row(
        SimpleNamespace(
            sender="assistant",
            content="",
            extra={
                "reaction_only": True,
                "reactions": [{"emoji": "🔥", "actors": ["agent:jeeves"]}],
            },
            timestamp=None,
        )
    )
    assert "reaction_only" not in poisoned
    assert "reactions" not in poisoned


def _chat_consumer():
    from unittest.mock import MagicMock

    from swarm.consumers import DjangoChatConsumer

    user = MagicMock()
    user.is_authenticated = True
    user.pk = 1
    consumer = DjangoChatConsumer()
    consumer.scope = {
        "user": user,
        "url_route": {"kwargs": {"conversation_id": "conv-1411"}},
    }
    consumer.user = user
    consumer.messages = [{"role": "user", "content": "ship it"}]
    consumer.ui_events = []
    consumer.conversation_id = "conv-1411"
    return consumer


def _frames(mock_send) -> list[str]:
    return [
        call.kwargs.get("text_data") or (call.args[0] if call.args else "")
        for call in mock_send.await_args_list
    ]


def _json_frames(frames: list[str]) -> list[dict]:
    out = []
    for frame in frames:
        text = str(frame or "").strip()
        if not text.startswith("{"):
            continue
        try:
            out.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return out


@pytest.mark.asyncio
async def test_respond_with_blueprint_completes_reaction_only_turn(monkeypatch):
    """The live turn path persists and emits a reaction-only reply with no text."""
    from unittest.mock import AsyncMock, MagicMock, patch

    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    consumer = _chat_consumer()
    saved: dict = {}

    async def save_conversation(conversation_id, messages):
        saved["id"] = conversation_id
        saved["messages"] = [dict(row) for row in messages]

    consumer.save_conversation = save_conversation

    async def fake_run(_messages, **_kwargs):
        payload = json.loads(await respond_with_reaction("👍"))
        assert payload["text"] == ""
        assert payload["reaction_only"] is True
        yield {"messages": [{"role": "assistant", "content": ""}], "final": True}

    instance = MagicMock()
    instance.run = fake_run
    instance.metadata = {}
    instance.agents = {}

    with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = instance
        with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
            await consumer.respond_with_blueprint(
                "jeeves",
                "message-response-abc",
                params={"bubble_theme": "speech"},
            )

    joined = "\n".join(_frames(mock_send))
    assert "did not return a reply" not in joined
    assert "no usable text" not in joined
    events = [row for row in _json_frames(_frames(mock_send)) if row.get("type") == "reaction_turn"]
    assert len(events) == 1
    assert events[0]["id"] == "message-response-abc"
    assert events[0]["emoji"] == "👍"
    assert events[0]["reaction_only"] is True
    assert events[0]["reactions"][0]["emoji"] == "👍"
    assert events[0]["reactions"][0]["agentReacted"] is True
    turn = consumer.messages[-1]
    assert turn["role"] == "assistant"
    assert turn["content"] == ""
    assert turn["reaction_only"] is True
    assert turn["reactions"] == [{"emoji": "👍", "actors": ["agent:jeeves"]}]
    assert saved["id"] == "conv-1411"
    assert saved["messages"][-1]["reaction_only"] is True
    stored = _normalize_messages(saved["messages"])
    assert stored[-1]["reaction_only"] is True
    assert messages_for_model(stored) == [
        {"role": "user", "content": "ship it"},
        {"role": "assistant", "content": "👍"},
    ]


@pytest.mark.asyncio
async def test_respond_with_blueprint_rejects_off_theme_emoji(monkeypatch):
    """IRC cannot finish a turn with a speech-only emoji, and no ghost is stored."""
    from unittest.mock import AsyncMock, MagicMock, patch

    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    consumer = _chat_consumer()
    saved: dict = {}

    async def save_conversation(conversation_id, messages):
        saved["id"] = conversation_id
        saved["messages"] = list(messages)

    consumer.save_conversation = save_conversation

    async def fake_run(_messages, **_kwargs):
        rejected = await respond_with_reaction("🚀")
        assert rejected.startswith("respond_with_reaction:")
        yield {"messages": [{"role": "assistant", "content": ""}], "final": True}

    instance = MagicMock()
    instance.run = fake_run
    instance.metadata = {}
    instance.agents = {}

    with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = instance
        with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
            await consumer.respond_with_blueprint(
                "jeeves",
                "message-response-irc",
                params={"bubble_theme": "irc"},
            )

    joined = "\n".join(_frames(mock_send))
    assert "no usable text" in joined
    assert not any(row.get("type") == "reaction_turn" for row in _json_frames(_frames(mock_send)))
    assert all(row.get("role") != "assistant" for row in consumer.messages)
    assert saved == {}


@pytest.mark.asyncio
async def test_respond_with_blueprint_text_reply_is_not_reaction_only(monkeypatch):
    """A real text reply stays text when the model also calls the reaction tool."""
    from unittest.mock import AsyncMock, MagicMock, patch

    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    consumer = _chat_consumer()

    async def fake_run(_messages, **_kwargs):
        await respond_with_reaction("👀")
        yield {"messages": [{"role": "assistant", "content": "landed it"}], "final": True}

    instance = MagicMock()
    instance.run = fake_run
    instance.metadata = {}
    instance.agents = {}

    with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = instance
        with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
            with patch.object(consumer, "save_conversation", new_callable=AsyncMock):
                await consumer.respond_with_blueprint(
                    "jeeves",
                    "message-response-text",
                    params={"bubble_theme": "irc"},
                )

    assert not any(row.get("type") == "reaction_turn" for row in _json_frames(_frames(mock_send)))
    turn = consumer.messages[-1]
    assert turn["content"] == "landed it"
    assert "reaction_only" not in turn

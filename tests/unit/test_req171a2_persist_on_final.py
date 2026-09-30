"""REQ-171A-2 / #602 — persist a finished turn before websocket disconnect.

A completed user/assistant pair must be on ``chat_store`` JSON and Django
rows after ``assistant_final`` / blueprint final partial. Disconnect save
must stay an idempotent replace. Status and edit keep their immediate save.

``test_save_*_sync`` helpers that write ORM rows by hand do not count.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

from helpers.py_ast import (
    awaited_call_count,
    await_sites,
    find_function,
    parse_module,
)
from swarm.consumers import DjangoChatConsumer
from swarm.core import chat_store
from swarm.models import ChatMessage

REPO = Path(__file__).resolve().parents[2]
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
# #855 slice 2: the stub responders and persistence methods moved verbatim
# into the swarm/chat mixins; the doctrine now spans both homes.
STUBS_MIXIN = REPO / "src" / "swarm" / "chat" / "stubs_mixin.py"
ADVICE_MIXIN = REPO / "src" / "swarm" / "chat" / "advice_mixin.py"
CONVERSATIONS_MIXIN = REPO / "src" / "swarm" / "chat" / "conversations_mixin.py"
CHAT_PAGE = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CI = REPO / ".github" / "workflows" / "req171a2-persist-on-final.yml"


def _consumer(user, conversation_id, agent="jeeves"):
    consumer = DjangoChatConsumer()
    consumer.scope = {
        "user": user,
        "url_route": {"kwargs": {"conversation_id": conversation_id}},
    }
    consumer.user = user
    consumer.conversation_id = conversation_id
    consumer.messages = []
    consumer.ui_events = []
    consumer.default_blueprint = agent
    consumer.active_agent = agent
    return consumer


@sync_to_async
def _db_contents(conversation_id):
    return list(
        ChatMessage.objects.filter(
            conversation__conversation_id=conversation_id
        ).order_by("timestamp", "pk").values_list("sender", "content")
    )


# Every responder that emits a final assistant message must persist the turn
# before the socket can go away. The list is the doctrine; the *number* of
# persistence points inside each responder is not — see below.
FINAL_RESPONDERS = {
    "stubs_mixin": {
        "respond_with_team_stub": REPO / "src/swarm/chat/stubs_mixin.py",
        "respond_with_roster_run": REPO / "src/swarm/chat/stubs_mixin.py",
        "respond_with_demo": REPO / "src/swarm/chat/stubs_mixin.py",
        "respond_with_bootstrap": REPO / "src/swarm/chat/stubs_mixin.py",
        "respond_with_blueprint": REPO / "src/swarm/chat/stubs_mixin.py",
    },
    "consumers": {
        "respond_with_default_model": CONSUMERS,
        "_emit_omb_followup": CONSUMERS,
        "_emit_herdr_frame": CONSUMERS,
    },
    "advice_mixin": {
        "_run_skeptic_rework_loop": ADVICE_MIXIN,
    },
}


def test_every_final_responder_awaits_persist_completed_turn():
    """Each final-emitting path persists; a comment naming it does not count.

    The old version counted ``"await self._persist_completed_turn()"`` inside
    each method with ``str.count`` and demanded an exact total — ``== 2`` for
    ``respond_with_blueprint``. That is a pin on an accident, not on the rule:
    a third, legitimate persistence point was added for the reaction-only and
    fatal-config paths and the suite went red with no behaviour change. Worse,
    ``str.count`` cannot tell a live call from the same phrase sitting in a
    comment.

    This reads the AST instead, so it survives a reformat, and it asserts the
    rule the count was proxying for: a real ``await`` on the real method.
    """
    for owner, responders in FINAL_RESPONDERS.items():
        for func_name, path in responders.items():
            module = parse_module(path)
            count = awaited_call_count(module, func_name, "self._persist_completed_turn")
            assert count >= 1, (
                f"{owner}.{func_name} emits a final message but never awaits "
                "self._persist_completed_turn(); a disconnect would lose the turn"
            )


def test_persist_completed_turn_is_a_coroutine_not_a_name():
    """The helper itself is a real coroutine on the consumer."""
    module = parse_module(CONSUMERS)
    fn = find_function(module, "_persist_completed_turn")
    assert fn.name == "_persist_completed_turn"
    # It must save both the JSON mirror and the database, not just one.
    assert await_sites(module, "_persist_completed_turn"), (
        "_persist_completed_turn awaits nothing — it persists nothing"
    )


def test_status_edit_and_disconnect_still_save():
    """REQ-46/REQ-49 keep their immediate saves; disconnect stays idempotent.

    Checked as AST call sites in the three homes the logic lives in, so a
    method moving between ``consumers.py`` and the mixins does not break it.
    """
    consumers = parse_module(CONSUMERS)
    conversations = parse_module(CONVERSATIONS_MIXIN)

    assert awaited_call_count(consumers, "disconnect", "self.save_conversation") >= 1, (
        "disconnect() no longer saves the conversation"
    )
    assert awaited_call_count(conversations, "apply_message_edit", "self.save_conversation") >= 1, (
        "the edit path no longer saves immediately"
    )

    # The status frame saves before the socket can close.
    status_save = awaited_call_count(consumers, "receive", "self.save_conversation")
    assert status_save >= 1, "the status frame no longer saves immediately"


def test_no_legacy_port_or_retired_labels_in_the_persistence_path():
    """Negative hygiene, kept because it genuinely is a text property.

    ``:8001`` (the retired LAN port) and the retired ``WAVE`` label vocabulary
    must not reappear in the consumer or the own-diff workflow. These are
    *forbidden-token* checks, which is the one direction a source read can be
    trusted for; the positive direction is asserted by the behavioural tests
    below.
    """
    source = CONSUMERS.read_text(encoding="utf-8")
    ci = CI.read_text(encoding="utf-8")
    assert ":8001" not in source
    assert ":8001" not in ci
    assert "neon" not in ci.lower()
    assert "WAVE" not in source
    assert "WAVE" not in CHAT_PAGE.read_text(encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_blueprint_final_persists_before_disconnect(test_user, monkeypatch):
    """Complete a turn, inspect disk/DB, then disconnect — no duplicate rows."""
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    conv_id = chat_store.conversation_id_for(test_user, "jeeves")
    consumer = _consumer(test_user, conv_id, "jeeves")

    with patch("swarm.consumers.render_to_string", return_value="<div/>"):
        with patch.object(consumer, "send", new_callable=AsyncMock):
            await consumer.receive(
                json.dumps({"message": "persist me", "blueprint": "jeeves"})
            )

    loaded = chat_store.load(chat_store.user_key_for(test_user), "jeeves")
    assert loaded is not None
    contents = [row["content"] for row in loaded["messages"]]
    assert contents[0] == "persist me"
    assert contents[1].startswith("[TEST-MODE]")
    assert [row["role"] for row in loaded["messages"]] == ["user", "assistant"]

    db_rows = await _db_contents(conv_id)
    assert len(db_rows) == 2
    assert db_rows[0] == ("user", "persist me")
    assert db_rows[1][0] == "assistant"
    assert db_rows[1][1].startswith("[TEST-MODE]")

    await consumer.disconnect(1000)
    assert await _db_contents(conv_id) == db_rows
    again = chat_store.load(chat_store.user_key_for(test_user), "jeeves")
    assert [row["content"] for row in again["messages"]] == contents


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_default_model_final_persists_before_disconnect(test_user, monkeypatch):
    """Default-model assistant_final also writes JSON + DB before disconnect."""
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    # Hermeticity: a developer shell often exports a real LiteLLM gateway URL
    # (e.g. LITELLM_BASE_URL=http://10.x.x.x:8000/v1). The default-model path
    # must run against the mocked client, never the LAN gateway.
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("LITELLM_MODEL", raising=False)
    monkeypatch.delenv("SWARM_LLM_FALLBACK_BASE_URL", raising=False)
    conv_id = chat_store.conversation_id_for(test_user, None)
    consumer = _consumer(test_user, conv_id, None)
    consumer.default_blueprint = None
    consumer.active_agent = None

    async def mock_stream():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "final reply"
        yield chunk

    mock_client = MagicMock()
    mock_client.base_url = None
    mock_client.api_key = "test-key"
    mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())
    mock_client.close = AsyncMock()

    with patch("swarm.consumers.render_to_string", return_value="<div/>"):
        with patch("swarm.consumers.AsyncOpenAI", return_value=mock_client):
            with patch.object(consumer, "send", new_callable=AsyncMock):
                await consumer.receive(json.dumps({"message": "hello default"}))

    loaded = chat_store.load(
        chat_store.user_key_for(test_user),
        None,
        conversation_id=conv_id,
    )
    assert loaded is not None, (
        "the default-model path did not persist the completed turn; the mock "
        "stream must be what the consumer actually calls"
    )
    assert [row["content"] for row in loaded["messages"]] == [
        "hello default",
        "final reply",
    ]
    db_rows = await _db_contents(conv_id)
    assert db_rows == [("user", "hello default"), ("assistant", "final reply")]

    await consumer.disconnect(1000)
    assert await _db_contents(conv_id) == db_rows


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_status_frame_still_saves_immediately(test_user):
    """REQ-46 status path keeps its immediate save (no wait for disconnect)."""
    conv_id = chat_store.conversation_id_for(test_user, "cli_agent")
    consumer = _consumer(test_user, conv_id, "cli_agent")

    await consumer.receive(
        json.dumps(
            {
                "type": "status",
                "text": "CLI: antigravity → grok",
                "agent": "cli_agent",
            }
        )
    )

    loaded = chat_store.load(chat_store.user_key_for(test_user), "cli_agent")
    assert loaded is not None
    assert loaded["ui_events"][-1]["content"] == "CLI: antigravity → grok"
    assert all(row["role"] != "status" for row in loaded["messages"])

    await consumer.disconnect(1000)
    again = chat_store.load(chat_store.user_key_for(test_user), "cli_agent")
    assert again["ui_events"][-1]["content"] == "CLI: antigravity → grok"
    assert len(again["ui_events"]) == len(loaded["ui_events"])


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_edit_frame_still_saves_immediately(test_user, monkeypatch):
    """REQ-49 edit path keeps its immediate save (no wait for disconnect)."""
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    conv_id = chat_store.conversation_id_for(test_user, "jeeves")
    consumer = _consumer(test_user, conv_id, "jeeves")

    with patch("swarm.consumers.render_to_string", return_value="<div/>"):
        with patch.object(consumer, "send", new_callable=AsyncMock):
            await consumer.receive(
                json.dumps({"message": "old question", "blueprint": "jeeves"})
            )
            await consumer.receive(
                json.dumps({"edit": {"index": 0, "content": "engineered question"}})
            )

    loaded = chat_store.load(chat_store.user_key_for(test_user), "jeeves")
    assert loaded is not None
    assert loaded["messages"][0]["content"] == "engineered question"
    assert loaded["messages"][0].get("edited") is True
    db_rows = await _db_contents(conv_id)
    assert db_rows[0] == ("user", "engineered question")

    await consumer.disconnect(1000)
    assert await _db_contents(conv_id) == db_rows

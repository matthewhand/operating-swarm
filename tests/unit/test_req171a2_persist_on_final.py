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

from swarm.consumers import DjangoChatConsumer
from swarm.core import chat_store
from swarm.models import ChatMessage

REPO = Path(__file__).resolve().parents[2]
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
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


def test_source_lock_persist_on_final_and_keep_status_edit():
    """Call sites: final-turn persist; status/edit/disconnect still save."""
    src = CONSUMERS.read_text(encoding="utf-8")
    assert "async def _persist_completed_turn(self):" in src
    assert "REQ-171A-2" in src
    after_team = src.split("async def respond_with_team_stub", 1)[1].split(
        "async def _emit_teammate_task_cards", 1
    )[0]
    after_bp = src.split("async def respond_with_blueprint", 1)[1].split(
        "async def _persist_completed_turn", 1
    )[0]
    after_default = src.split("async def respond_with_default_model", 1)[1].split(
        "async def apply_message_edit", 1
    )[0]
    assert after_team.count("await self._persist_completed_turn()") == 1
    assert after_bp.count("await self._persist_completed_turn()") == 2
    assert after_default.count("await self._persist_completed_turn()") == 1

    status_block = src.split('if text_data_json.get("type") == "status":', 1)[1].split(
        'if "edit" in text_data_json:', 1
    )[0]
    assert "await self.save_conversation(conversation_id, self.messages)" in status_block
    edit_block = src.split("async def apply_message_edit", 1)[1].split(
        "async def fetch_conversation", 1
    )[0]
    assert "await self.save_conversation(conversation_id, self.messages)" in edit_block
    disconnect = src.split("async def disconnect", 1)[1].split("async def receive", 1)[0]
    assert "await self.save_conversation(self.conversation_id, self.messages)" in disconnect

    chat = CHAT_PAGE.read_text(encoding="utf-8")
    assert "WAVE" not in chat
    ci = CI.read_text(encoding="utf-8")
    assert "own-diff" in ci
    assert "neon" not in ci.lower()
    assert ":8001" not in src
    assert ":8001" not in ci


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
    assert loaded is not None
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

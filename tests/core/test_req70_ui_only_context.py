"""REQ-70 / #407: status/info are UI-only — never in the LLM payload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from swarm.core.chat_compact import (
    build_model_context,
    compact_backlog,
    context_for_conversation,
    summarize_items,
)
from swarm.core.speaker_identity import apply_speaker_identity
from swarm.core.transcript_roles import context_blob, messages_for_model
from swarm.blueprints.common import cli_fusion_support as support


STATUS_CLI = "CLI: antigravity → grok"
STATUS_MESSAGED = "Messaged 3 Bots"
STATUS_FROM = "Message from Codey"
STATUS_FALLBACK = "Rate limited — retrying with grok"
INFO_CONNECTING = "Connecting…"


def _thread():
    return [
        {"role": "status", "content": STATUS_CLI, "ts": "2026-09-05T12:00:00+00:00"},
        {"role": "info", "content": INFO_CONNECTING, "ts": "2026-09-05T12:00:01+00:00"},
        {"role": "status", "content": STATUS_MESSAGED},
        {"role": "status", "content": STATUS_FROM},
        {"role": "info", "content": STATUS_FALLBACK},
        {"role": "user", "content": "hello there"},
        {"role": "assistant", "content": "hi back", "name": "jeeves"},
        {"role": "tool", "content": "ok", "name": "lookup", "tool_call_id": "c1"},
    ]


def _assert_no_chrome(payload: list[dict]):
    blob = context_blob(payload)
    for chrome in (STATUS_CLI, STATUS_MESSAGED, STATUS_FROM, STATUS_FALLBACK, INFO_CONNECTING):
        assert chrome not in blob
    roles = [m.get("role") for m in payload]
    assert "status" not in roles
    assert "info" not in roles


def test_messages_for_model_keeps_pair_and_tool_drops_chrome():
    payload = messages_for_model(_thread())
    assert [(m["role"], m["content"]) for m in payload] == [
        ("user", "hello there"),
        ("assistant", "hi back"),
        ("tool", "ok"),
    ]
    assert payload[1]["name"] == "jeeves"
    assert payload[2]["tool_call_id"] == "c1"
    _assert_no_chrome(payload)


def test_messages_for_model_drops_prior_history_keeps_system_prompt():
    payload = messages_for_model(
        [
            {"role": "system", "kind": "prior_history", "content": "old thread"},
            {"role": "system", "content": "be terse"},
            {"role": "status", "content": STATUS_CLI},
            {"role": "user", "content": "next"},
        ]
    )
    assert [(m["role"], m["content"]) for m in payload] == [
        ("system", "be terse"),
        ("user", "next"),
    ]
    assert "old thread" not in context_blob(payload)


def test_build_model_context_excludes_status_info():
    payload = build_model_context(_thread(), [])
    assert [(m["role"], m["content"]) for m in payload] == [
        ("user", "hello there"),
        ("assistant", "hi back"),
        ("tool", "ok"),
    ]
    assert payload[1].get("name") == "jeeves"
    _assert_no_chrome(payload)


def test_build_model_context_excludes_prior_history():
    payload = build_model_context(
        [
            {"role": "system", "kind": "prior_history", "content": "old thread"},
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "next"},
        ],
        [],
    )
    assert [(m["role"], m["content"]) for m in payload] == [
        ("system", "be terse"),
        ("user", "next"),
    ]
    assert "old thread" not in context_blob(payload)


def test_context_for_conversation_no_cid_filters_chrome():
    payload = context_for_conversation("", _thread())
    _assert_no_chrome(payload)
    assert any(m["role"] == "user" and m["content"] == "hello there" for m in payload)
    assert any(m["role"] == "assistant" and m["content"] == "hi back" for m in payload)


def test_summarize_items_skips_status_info():
    body = summarize_items(
        [
            {"kind": "message", "role": "status", "content": STATUS_CLI},
            {"kind": "message", "role": "info", "content": INFO_CONNECTING},
            {
                "kind": "message",
                "source_kind": "prior_history",
                "role": "system",
                "content": "old thread",
            },
            {"kind": "message", "role": "user", "content": "alpha question"},
            {"kind": "message", "role": "assistant", "content": "alpha answer"},
        ]
    )
    assert "alpha question" in body
    assert "alpha answer" in body
    assert STATUS_CLI not in body
    assert INFO_CONNECTING not in body
    assert "old thread" not in body
    assert "status" not in body
    assert "Summary of 2 items" in body


@pytest.mark.django_db
def test_compact_backlog_summarises_real_messages_only(stub_compact_llm):
    from django.contrib.auth import get_user_model
    from swarm.core import chat_store

    user = get_user_model().objects.create_user(username="req70-compact", password="pw")
    cid = "conv-req70-compact"
    messages = [
        {"role": "status", "content": STATUS_CLI, "ts": "2026-09-05T01:00:00Z"},
        {"role": "user", "content": "remember this"},
        {"role": "assistant", "content": "ok"},
        {"role": "info", "content": STATUS_FALLBACK},
    ]
    chat_store.save(chat_store.user_key_for(user), "jeeves", messages, conversation_id=cid)
    row, raw = compact_backlog(
        user=user,
        conversation_id=cid,
        agent_id="jeeves",
        messages=messages,
    )
    assert [item["role"] for item in raw] == ["user", "assistant"]
    assert STATUS_CLI not in row.body
    assert STATUS_FALLBACK not in row.body
    assert row.body == "LLM digest of the compacted range."
    sent = stub_compact_llm[-1]["items"]
    assert any(item.get("content") == "remember this" for item in sent)
    assert all(STATUS_CLI not in str(item.get("content") or "") for item in sent)
    context = build_model_context(raw, [row])
    blob = context_blob(context)
    assert STATUS_CLI not in blob
    assert STATUS_FALLBACK not in blob
    assert any(m["role"] == "system" and "[Conversation summary]" in m["content"] for m in context)


@pytest.mark.django_db
def test_thread_post_stamps_status_timestamp():
    import json

    from django.contrib.auth import get_user_model
    from django.test import Client

    get_user_model().objects.create_user(username="req70-ts", password="pw")
    client = Client()
    client.login(username="req70-ts", password="pw")
    resp = client.post(
        "/chat/thread/?agent=jeeves",
        data=json.dumps(
            {
                "message": {
                    "role": "info",
                    "content": STATUS_FALLBACK,
                }
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    rows = resp.json()["messages"]
    assert rows[-1]["role"] == "info"
    assert rows[-1]["content"] == STATUS_FALLBACK
    assert rows[-1]["ts"]

    again = client.get("/chat/thread/?agent=jeeves")
    assert again.status_code == 200
    restored = again.json()["messages"][-1]
    assert restored["role"] == "info"
    assert restored["ts"] == rows[-1]["ts"]


def test_render_prompt_excludes_status_and_keeps_turns():
    prompt = support.render_prompt(
        [
            {"role": "status", "content": STATUS_CLI},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "ok", "name": "echo"},
            {"role": "user", "content": "again"},
        ]
    )
    assert STATUS_CLI not in prompt
    assert "hello" in prompt
    assert "again" in prompt
    assert "ok" in prompt


@pytest.mark.asyncio
async def test_compacted_context_exception_still_strips_chrome():
    from swarm.consumers import _compacted_context

    thread = _thread()
    # The #900 hop seed reads the active agent off the consumer; a stub with
    # no agent identity exercises the seed as a no-op pass-through.
    stub_consumer = type("C", (), {"active_agent": None, "default_blueprint": ""})()
    with patch(
        "swarm.core.chat_compact.context_for_conversation",
        side_effect=RuntimeError("db down"),
    ):
        payload = await _compacted_context(stub_consumer, "conv-x", thread)
    _assert_no_chrome(payload)
    assert any(m["role"] == "user" and m["content"] == "hello there" for m in payload)


@pytest.mark.asyncio
async def test_blueprint_run_payload_has_zero_status_strings(monkeypatch):
    from swarm.consumers import DjangoChatConsumer

    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    consumer = DjangoChatConsumer()
    consumer.conversation_id = "conv-req70"
    consumer.messages = _thread()
    consumer.user = type("U", (), {"is_authenticated": False, "pk": None})()
    seen = {}

    async def fake_run(messages, **kwargs):
        seen["messages"] = messages
        yield {"messages": [{"role": "assistant", "content": "ok"}]}

    instance = MagicMock()
    instance.run = fake_run
    instance.metadata = {}
    instance.agents = None
    # A bare MagicMock auto-creates truthy attributes; declare the context
    # axis explicitly so the server-managed trim does not kick in.
    instance.server_managed_context = False
    instance.capabilities = {}

    async def fake_context(consumer, conversation_id, messages):
        return build_model_context(messages, [])

    with patch("swarm.consumers._compacted_context", side_effect=fake_context):
        with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, "send", new_callable=AsyncMock):
                await consumer.respond_with_blueprint("jeeves", "message-response-req70")

    payload = seen["messages"]
    _assert_no_chrome(payload)
    assert any(m["content"] == "hello there" for m in payload)
    assert any(m["content"] == "hi back" for m in payload)

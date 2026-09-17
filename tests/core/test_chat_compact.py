"""REQ-37 / #672: nested conversation compact / LLM summaries.

Compact replaces model context with an LLM-written digest (not a raw dump).
Raw JSON + ChatMessage rows stay. Nested compact sets parent_summary_id.
No Neon, no secrets.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store
from swarm.core.chat_compact import (
    CompactError,
    build_compact_prompt,
    build_model_context,
    compact_backlog,
    context_for_conversation,
    llm_summarize_items,
    resolve_compact_model,
    summarize_items,
    summary_to_dict,
)
from swarm.models import ChatConversation, ChatMessage, ConversationSummary


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="compact-op", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="compact-op", password="pw")
    return c


def _turns(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in pairs]


def _seed_json(user, agent, messages, conversation_id):
    chat_store.save(
        chat_store.user_key_for(user),
        agent,
        messages,
        conversation_id=conversation_id,
    )


@pytest.mark.django_db
def test_compact_replaces_model_context(user, stub_compact_llm):
    cid = "conv-compact-ctx"
    messages = _turns(
        ("user", "alpha question"),
        ("assistant", "alpha answer"),
        ("user", "beta question"),
        ("assistant", "beta answer"),
    )
    _seed_json(user, "jeeves", messages, cid)
    row, raw = compact_backlog(
        user=user,
        conversation_id=cid,
        agent_id="jeeves",
        messages=messages,
    )
    assert raw == messages
    context = build_model_context(raw, [row])
    assert len(context) == 1
    assert context[0]["role"] == "system"
    assert context[0]["content"].startswith("[Conversation summary]")
    assert not any(m["role"] == "user" for m in context)
    assert not any(m["role"] == "assistant" for m in context)


@pytest.mark.django_db
def test_nested_compact_sets_parent_summary_id(user, stub_compact_llm):
    cid = "conv-compact-nest"
    first = _turns(("user", "one"), ("assistant", "two"))
    _seed_json(user, "codey", first, cid)
    s1, _ = compact_backlog(user=user, conversation_id=cid, agent_id="codey", messages=first)
    assert s1.parent_summary_id is None

    later = first + _turns(("user", "three"), ("assistant", "four"))
    s2, raw = compact_backlog(user=user, conversation_id=cid, agent_id="codey", messages=later)
    assert s2.parent_summary_id == s1.id
    assert s2.span == {"start": 0, "end": 3}
    assert raw == later

    context = context_for_conversation(cid, later)
    assert len(context) == 1
    assert context[0]["role"] == "system"
    assert "[Conversation summary]" in context[0]["content"]
    assert "[nested summary]" in context[0]["content"]
    assert not any(m.get("role") == "user" and m.get("content") == "three" for m in context)


@pytest.mark.django_db
def test_compact_keeps_raw_json_and_chatmessage_rows(user, stub_compact_llm):
    cid = "conv-compact-raw"
    messages = _turns(("user", "keep me"), ("assistant", "still here"))
    _seed_json(user, "stewie", messages, cid)
    compact_backlog(user=user, conversation_id=cid, agent_id="stewie", messages=messages)

    loaded = chat_store.load(chat_store.user_key_for(user), "stewie")
    assert loaded is not None
    assert [m["content"] for m in loaded["messages"]] == ["keep me", "still here"]

    chat = ChatConversation.objects.get(conversation_id=cid)
    assert list(chat.chat_messages.values_list("content", flat=True)) == [
        "keep me",
        "still here",
    ]
    assert chat.summaries.count() == 1


@pytest.mark.django_db
def test_compact_endpoint_and_thread_payload(client, user, stub_compact_llm):
    cid = "conv-compact-api"
    messages = _turns(("user", "remember this"), ("assistant", "ok"))
    _seed_json(user, "jeeves", messages, cid)

    resp = client.post(
        "/chat/compact/",
        data={
            "conversation_id": cid,
            "agent": "jeeves",
            "messages": messages,
        },
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["parent_summary_id"] is None
    assert body["summary"]["span"] == {"start": 0, "end": 1}
    assert body["raw_count"] == 2
    assert body["context"][0]["role"] == "system"
    assert body["summary"]["body"] == "LLM digest of the compacted range."
    assert "remember this" not in body["summary"]["body"]
    assert len(body["context"]) == 1
    assert not any(m.get("role") == "user" for m in body["context"])

    thread = client.get(f"/chat/thread/?agent=jeeves&conversation_id={cid}")
    assert thread.status_code == 200
    payload = thread.json()
    assert payload["messages"][0]["content"] == "remember this"
    assert payload["summaries"][0]["id"] == body["summary"]["id"]
    assert payload["summaries"][0]["parent_summary_id"] is None


@pytest.mark.django_db
def test_compact_empty_rejected(client, user):
    resp = client.post(
        "/chat/compact/",
        data={"conversation_id": "empty-conv", "agent": "jeeves", "messages": []},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "Nothing to compact" in resp.json()["error"]


@pytest.mark.django_db
def test_compact_requires_login():
    resp = Client().post(
        "/chat/compact/",
        data={"conversation_id": "x", "agent": "jeeves"},
        content_type="application/json",
    )
    assert resp.status_code == 302
    assert "login" in resp["Location"]


@pytest.mark.django_db
def test_compact_does_not_delete_existing_chatmessages(user, stub_compact_llm):
    cid = "conv-compact-keep-ids"
    chat = ChatConversation.objects.create(conversation_id=cid, student=user)
    first = ChatMessage.objects.create(conversation=chat, sender="user", content="original")
    ChatMessage.objects.create(conversation=chat, sender="assistant", content="reply")
    compact_backlog(
        user=user,
        conversation_id=cid,
        agent_id="jeeves",
        messages=_turns(("user", "original"), ("assistant", "reply")),
    )
    assert ChatMessage.objects.filter(pk=first.pk).exists()
    assert ChatMessage.objects.filter(conversation=chat).count() == 2


def test_summarize_items_is_extractive_no_secrets():
    body = summarize_items(
        [
            {"kind": "message", "role": "user", "content": "plain question"},
            {"kind": "summary", "body": "earlier digest"},
        ]
    )
    assert "plain question" in body
    assert "[summary] earlier digest" in body
    assert "sk-" not in body
    assert "api_key" not in body


def test_compact_prompt_is_transcript_not_task_continuation():
    prompt = build_compact_prompt(
        [
            {"kind": "message", "role": "user", "content": "hello"},
            {"kind": "summary", "body": "earlier digest"},
        ]
    )
    assert "Do not answer the user" in prompt
    assert "user: hello" in prompt
    assert "[summary]: earlier digest" in prompt
    assert "sk-" not in prompt


@pytest.mark.django_db
def test_second_compact_mixes_summary_and_raw(user, stub_compact_llm):
    cid = "conv-compact-mix"
    first = _turns(("user", "a"), ("assistant", "b"))
    s1, _ = compact_backlog(user=user, conversation_id=cid, agent_id="x", messages=first)
    later = first + _turns(("user", "fresh turn"), ("assistant", "fresh reply"))
    s2, _ = compact_backlog(user=user, conversation_id=cid, agent_id="x", messages=later)
    assert s2.parent_summary_id == s1.id
    assert s2.body == "LLM digest of the compacted range."
    mix = stub_compact_llm[-1]["items"]
    assert any(item.get("kind") == "summary" for item in mix)
    assert any(item.get("content") == "fresh turn" for item in mix)
    assert ConversationSummary.objects.filter(conversation_id=cid).count() == 2


@pytest.mark.django_db
def test_compact_error_on_foreign_conversation(user, db):
    other = get_user_model().objects.create_user(username="other-op", password="pw")
    ChatConversation.objects.create(conversation_id="owned-by-other", student=other)
    with pytest.raises(CompactError) as exc:
        compact_backlog(
            user=user,
            conversation_id="owned-by-other",
            agent_id="jeeves",
            messages=_turns(("user", "nope"), ("assistant", "no")),
        )
    assert exc.value.status == 403


@pytest.mark.django_db
def test_compact_body_is_llm_summary_not_concat(user):
    """#672 success: bubble is summary-shaped; char count ≪ raw dump."""
    cid = "conv-compact-llm-shape"
    long_q = "Please remember this planning thread. " * 40
    long_a = "We decided to ship the demo on Friday and leave two open tasks. " * 40
    messages = _turns(
        ("user", long_q),
        ("assistant", long_a),
        ("user", "Also keep the API names."),
        ("assistant", "Noted the API names."),
    )
    _seed_json(user, "jeeves", messages, cid)
    raw_dump = summarize_items(
        [{"kind": "message", "role": m["role"], "content": m["content"]} for m in messages]
    )
    summary_text = "Users planned a Friday demo and left two open tasks; keep API names."

    def _llm(items, *, agent_id=""):
        assert agent_id == "jeeves"
        assert items
        return summary_text

    row, raw = compact_backlog(
        user=user,
        conversation_id=cid,
        agent_id="jeeves",
        messages=messages,
        summarizer=_llm,
    )
    assert raw == messages
    assert row.body == summary_text
    assert "Summary of" not in row.body
    assert "- user:" not in row.body
    assert long_q not in row.body
    assert len(row.body) < len(raw_dump) // 4
    context = build_model_context(raw, [row])
    assert context[0]["role"] == "system"
    assert summary_text in context[0]["content"]
    assert long_q not in context[0]["content"]


@pytest.mark.django_db
def test_compact_llm_failure_does_not_write_summary(user, client):
    """#672: honest failure — no silent extractive fake-compact."""
    cid = "conv-compact-llm-fail"
    messages = _turns(("user", "alpha question"), ("assistant", "alpha answer"))
    _seed_json(user, "jeeves", messages, cid)

    def _boom(items, *, agent_id=""):
        raise RuntimeError("gateway 502 using sk-secretTESTKEY999")

    with pytest.raises(CompactError) as exc:
        compact_backlog(
            user=user,
            conversation_id=cid,
            agent_id="jeeves",
            messages=messages,
            summarizer=_boom,
        )
    assert exc.value.status == 502
    assert "Compact summary failed" in str(exc.value)
    assert "sk-secretTESTKEY999" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)
    assert ConversationSummary.objects.filter(conversation_id=cid).count() == 0

    from unittest.mock import patch

    with patch(
        "swarm.core.chat_compact.llm_summarize_items",
        side_effect=CompactError("Compact summary failed: model timeout", status=502),
    ):
        resp = client.post(
            "/chat/compact/",
            data={"conversation_id": cid, "agent": "jeeves", "messages": messages},
            content_type="application/json",
        )
    assert resp.status_code == 502
    assert resp.json()["error"] == "Compact summary failed: model timeout"
    assert ConversationSummary.objects.filter(conversation_id=cid).count() == 0


def test_llm_summarize_items_uses_resolved_model(monkeypatch):
    captured: dict[str, object] = {}

    class _Msg:
        content = "Short digest of the thread."

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Resp()

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs

        chat = _Chat()

    monkeypatch.setenv("LITELLM_MODEL", "auxiliary")
    monkeypatch.setattr("swarm.core.chat_compact.resolve_compact_model", lambda agent_id="": "aux-model")
    monkeypatch.setattr("openai.OpenAI", _Client)
    monkeypatch.setattr(
        "swarm.utils.env_utils.openai_client_kwargs",
        lambda: {"api_key": "ollama", "base_url": "http://litellm.local/v1"},
    )

    text = llm_summarize_items(
        [{"kind": "message", "role": "user", "content": "hello there"}],
        agent_id="jeeves",
    )
    assert text == "Short digest of the thread."
    assert captured["model"] == "aux-model"
    assert captured["messages"][0]["role"] == "system"
    assert "Do not invent secrets" in captured["messages"][0]["content"]
    assert "user: hello there" in captured["messages"][1]["content"]
    # Client kwargs may include a key; we never log it from llm_summarize_items.
    assert "sk-" not in text


def test_llm_summarize_empty_response_is_failure(monkeypatch):
    class _Msg:
        content = "   "

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Client:
        def __init__(self, **_kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(**_kwargs):
                    return _Resp()

    monkeypatch.setattr("swarm.core.chat_compact.resolve_compact_model", lambda agent_id="": "m")
    monkeypatch.setattr("openai.OpenAI", _Client)
    monkeypatch.setattr("swarm.utils.env_utils.openai_client_kwargs", lambda: {})
    with pytest.raises(CompactError) as exc:
        llm_summarize_items([{"kind": "message", "role": "user", "content": "x"}])
    assert exc.value.status == 502
    assert "empty summary" in str(exc.value)


def test_resolve_compact_model_prefers_agent_then_env(monkeypatch):
    monkeypatch.setenv("LITELLM_MODEL", "env-model")
    monkeypatch.setattr(
        "swarm.core.llm_task_routing.load_swarm_config",
        lambda: {
            "blueprints": {"jeeves": {"llm_profile": "jeeves-fast"}},
            "llm": {"jeeves-fast": {"model": "jeeves-mini"}},
            "settings": {"default_llm_profile": "default"},
        },
    )
    assert resolve_compact_model("jeeves") == "jeeves-mini"
    monkeypatch.setattr(
        "swarm.core.llm_task_routing.load_swarm_config",
        lambda: {"llm": {}, "settings": {}},
    )
    assert resolve_compact_model("unknown-agent") == "env-model"


def test_resolve_compact_model_missing_is_honest(monkeypatch):
    monkeypatch.delenv("LITELLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("DEFAULT_LLM", raising=False)

    def _boom():
        raise RuntimeError("no config")

    monkeypatch.setattr("swarm.core.llm_task_routing.load_swarm_config", _boom)
    with pytest.raises(CompactError) as exc:
        resolve_compact_model("jeeves")
    assert "No default LLM" in str(exc.value)
    assert exc.value.status == 400


# ------------------------------------------------------------ include_in_context


def _summary_row(cid: str, start: int, end: int, *, include: bool = True, parent=None, user=None):
    ChatConversation.objects.get_or_create(conversation_id=cid, defaults={"student": user})
    return ConversationSummary.objects.create(
        conversation_id=cid,
        span={"start": start, "end": end},
        body=f"summary of {start}..{end}",
        include_in_context=include,
        parent_summary=parent,
    )


@pytest.mark.django_db
def test_excluded_summary_is_omitted_and_span_stays_archived(user):
    """Core contract: unticked summary drops out of context AND its
    summarised raw turns do not silently reappear."""
    cid = "conv-214-exclude"
    messages = _turns(
        ("user", "old question"),
        ("assistant", "old answer"),
        ("user", "new question"),
    )
    row = _summary_row(cid, 0, 1, include=False, user=user)

    context = build_model_context(messages, [row])
    rendered = [str(item.get("content", "")) for item in context]
    assert not any("summary of 0..1" in text for text in rendered)
    assert not any("old answer" in text for text in rendered)
    assert any("new question" in text for text in rendered)


@pytest.mark.django_db
def test_included_summary_keeps_current_behavior(user):
    cid = "conv-214-include"
    messages = _turns(("user", "old question"), ("assistant", "old answer"))
    row = _summary_row(cid, 0, 1, include=True, user=user)
    context = build_model_context(messages, [row])
    joined = "\n".join(str(item.get("content", "")) for item in context)
    assert "summary of 0..1" in joined
    assert "old answer" not in joined


def test_rows_without_flag_default_to_included():
    """Legacy fakes / rows lacking the attribute behave as today."""

    class FakeRow:
        id = 7
        span = {"start": 0, "end": 1}
        body = "legacy"
        parent_summary_id = None

    messages = _turns(("user", "old"), ("assistant", "old reply"))
    context = build_model_context(messages, [FakeRow()])
    joined = "\n".join(str(item.get("content", "")) for item in context)
    assert "legacy" in joined
    assert "old reply" not in joined


@pytest.mark.django_db
def test_excluded_parent_excludes_nested_child(user):
    cid = "conv-214-nested"
    parent = _summary_row(cid, 0, 3, include=False, user=user)
    child = _summary_row(cid, 1, 2, include=True, parent=parent, user=user)
    messages = _turns(("user", "a"), ("assistant", "b"), ("user", "c"), ("user", "later"))
    context = build_model_context(messages, [parent, child])
    joined = "\n".join(str(item.get("content", "")) for item in context)
    assert "summary of 0..3" not in joined
    assert "summary of 1..2" not in joined  # nested inside excluded parent
    assert "later" in joined


@pytest.mark.django_db
def test_summary_to_dict_includes_flag(user):
    row = _summary_row("conv-214-dict", 0, 1, include=False, user=user)
    data = summary_to_dict(row)
    assert data["include_in_context"] is False
    row.include_in_context = True
    assert summary_to_dict(row)["include_in_context"] is True


@pytest.mark.django_db
def test_toggle_endpoint_updates_flag(client, user):
    row = _summary_row("conv-214-toggle", 0, 1, include=True, user=user)
    response = client.post(
        "/chat/summary/toggle-context/",
        json.dumps({"summary_id": row.id, "include_in_context": False}),
        content_type="application/json",
    )
    assert response.status_code == 200
    row.refresh_from_db()
    assert row.include_in_context is False
    assert response.json()["summary"]["include_in_context"] is False


@pytest.mark.django_db
def test_toggle_endpoint_validates(client, user):
    row = _summary_row("conv-214-validate", 0, 1, user=user)
    # non-boolean
    response = client.post(
        "/chat/summary/toggle-context/",
        json.dumps({"summary_id": row.id, "include_in_context": "yes"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    # unknown summary → honest 404
    response = client.post(
        "/chat/summary/toggle-context/",
        json.dumps({"summary_id": 999999, "include_in_context": True}),
        content_type="application/json",
    )
    assert response.status_code == 404
    row.refresh_from_db()
    assert row.include_in_context is True


@pytest.mark.django_db
def test_toggle_endpoint_requires_login():
    from django.test import Client as DjangoClient

    response = DjangoClient().post(
        "/chat/summary/toggle-context/",
        json.dumps({"summary_id": 1, "include_in_context": False}),
        content_type="application/json",
    )
    assert response.status_code in (302, 401, 403)

"""REQ-87: shared auto-compress threshold, unknown-max skip, hover-to-here.

No live paid model. No Neon. No secrets.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from swarm.core import chat_store
from swarm.core.chat_compact import (
    build_model_context,
    compact_backlog,
    ensure_transcript,
    list_summaries,
)
from swarm.core.context_compress_policy import (
    DEFAULT_AUTO_COMPRESS_PCT,
    UNKNOWN_MAX_INFO,
    auto_compact_before_send,
    choose_auto_compact_span,
    estimate_context_tokens,
    load_auto_compress_threshold,
    normalize_auto_compress_pct,
    resolve_model_context_max,
    should_auto_compress,
)
from swarm.core.user_preferences import public_payload
from swarm.models import ConversationSummary
from swarm.models.preferences import UserPreference


def _turns(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"role": role, "content": content} for role, content in pairs]


def _seed_json(user, agent, messages, conversation_id):
    chat_store.save(
        chat_store.user_key_for(user),
        agent,
        messages,
        conversation_id=conversation_id,
    )


def test_normalize_auto_compress_pct_defaults_and_clamps():
    assert normalize_auto_compress_pct(None) == DEFAULT_AUTO_COMPRESS_PCT
    assert normalize_auto_compress_pct("") == 80
    assert normalize_auto_compress_pct("nope") == 80
    assert normalize_auto_compress_pct(0) == 1
    assert normalize_auto_compress_pct(100) == 99
    assert normalize_auto_compress_pct(50) == 50


def test_public_payload_default_threshold_is_80():
    payload = public_payload(principal="user:alice", guest=False, empty=True)
    assert payload["context_auto_compress_pct"] == 80
    assert any(item["key"] == "context_auto_compress_pct" for item in payload["registry"])
    blob = str(payload)
    assert "sk-" not in blob
    assert "api_key" not in blob


def test_resolve_model_context_max_never_guesses_128k():
    assert resolve_model_context_max() is None
    assert resolve_model_context_max(model_id="gpt-4o") is None
    assert resolve_model_context_max(profile={"model": "gpt-4o", "max_tokens": 4096}) is None
    assert (
        resolve_model_context_max(profile={"context_length": 200_000}) == 200_000
    )
    assert (
        resolve_model_context_max(inference_entry={"context_window": 8192}) == 8192
    )


def test_should_auto_compress_requires_known_max():
    assert should_auto_compress(10_000, None, 80) is False
    assert should_auto_compress(79, 100, 80) is False
    assert should_auto_compress(80, 100, 80) is True
    assert should_auto_compress(50, 100, 50) is True


def test_choose_auto_compact_span_keeps_recent_tail():
    assert choose_auto_compact_span(2) is None
    assert choose_auto_compact_span(5) == (0, 2)


@pytest.mark.django_db
def test_default_threshold_persists_as_80():
    user = get_user_model().objects.create_user("compress-default", password="pw")
    assert load_auto_compress_threshold(user) == 80
    UserPreference.objects.create(
        user=user,
        principal="user:compress-default",
        values={"favourites": []},
    )
    assert load_auto_compress_threshold(user) == 80


@pytest.mark.django_db
def test_settings_patch_50_is_read_by_helper():
    user = get_user_model().objects.create_user("compress-fifty", password="pw")
    client = APIClient()
    client.force_login(user)
    resp = client.patch(
        "/v1/preferences/",
        {"context_auto_compress_pct": 50},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["context_auto_compress_pct"] == 50
    assert "sk-" not in str(body)
    assert load_auto_compress_threshold(user) == 50
    assert load_auto_compress_threshold(principal="user:compress-fifty") == 50


@pytest.mark.django_db
def test_unknown_max_skips_auto_manual_compact_still_writes(stub_compact_llm):
    user = get_user_model().objects.create_user("compress-unknown", password="pw")
    cid = "conv-unknown-max"
    messages = _turns(
        ("user", "alpha " * 40),
        ("assistant", "beta " * 40),
        ("user", "gamma " * 40),
        ("assistant", "delta " * 40),
        ("user", "draft question"),
    )
    _seed_json(user, "jeeves", messages, cid)

    result = auto_compact_before_send(
        user=user,
        conversation_id=cid,
        agent_id="jeeves",
        messages=messages,
        model_id="mystery-model",
    )
    assert result.acted is False
    assert result.reason == "unknown_max"
    assert result.info == UNKNOWN_MAX_INFO
    assert result.max_context is None
    assert ConversationSummary.objects.filter(conversation_id=cid).count() == 0

    row, raw = compact_backlog(
        user=user,
        conversation_id=cid,
        agent_id="jeeves",
        messages=messages,
    )
    assert row.body
    assert raw == messages
    assert ConversationSummary.objects.filter(conversation_id=cid).count() == 1


@pytest.mark.django_db
def test_auto_compacts_when_over_threshold_and_max_known(stub_compact_llm):
    user = get_user_model().objects.create_user("compress-auto", password="pw")
    UserPreference.objects.create(
        user=user,
        principal="user:compress-auto",
        values={"context_auto_compress_pct": 50},
    )
    cid = "conv-auto-hit"
    messages = _turns(
        ("user", "old question " * 80),
        ("assistant", "old answer " * 80),
        ("user", "mid question " * 80),
        ("assistant", "mid answer " * 80),
        ("user", "latest draft"),
    )
    _seed_json(user, "jeeves", messages, cid)
    estimated = estimate_context_tokens(messages)
    assert estimated > 10

    result = auto_compact_before_send(
        user=user,
        conversation_id=cid,
        agent_id="jeeves",
        messages=messages,
        inference_entry={"context_length": max(20, estimated)},
    )
    assert result.acted is True
    assert result.max_context == max(20, estimated)
    assert result.threshold_pct == 50
    assert ConversationSummary.objects.filter(conversation_id=cid).count() == 1
    context = result.context
    assert any(
        row.get("role") == "system" and "[Conversation summary]" in str(row.get("content"))
        for row in context
    )
    assert any(row.get("content") == "latest draft" for row in context)


@pytest.mark.django_db
def test_hover_to_here_keeps_later_messages_raw(stub_compact_llm):
    user = get_user_model().objects.create_user("compress-here", password="pw")
    cid = "conv-to-here"
    messages = _turns(
        ("user", "one"),
        ("assistant", "two"),
        ("user", "three"),
        ("assistant", "four"),
        ("user", "five stays raw"),
        ("assistant", "six stays raw"),
    )
    _seed_json(user, "codey", messages, cid)
    chat, _raw = ensure_transcript(user, cid, "codey", messages)
    cutoff = list(chat.chat_messages.all())[3]
    row, raw = compact_backlog(
        user=user,
        conversation_id=cid,
        agent_id="codey",
        messages=messages,
        through_message_id=cutoff.pk,
    )
    assert raw == messages
    assert row.span == {"start": 0, "end": 3}
    context = build_model_context(raw, list_summaries(cid))
    contents = [row.get("content") for row in context]
    assert any("[Conversation summary]" in str(item) for item in contents)
    assert "five stays raw" in contents
    assert "six stays raw" in contents
    assert "one" not in contents
    assert "three" not in contents


@pytest.mark.django_db
def test_compact_endpoint_accepts_through_message_id(stub_compact_llm):
    user = get_user_model().objects.create_user("compress-api", password="pw")
    from django.test import Client

    client = Client()
    client.login(username="compress-api", password="pw")
    cid = "conv-api-through"
    messages = _turns(
        ("user", "keep-summary"),
        ("assistant", "ok"),
        ("user", "after cutoff"),
    )
    _seed_json(user, "jeeves", messages, cid)
    chat, _raw = ensure_transcript(user, cid, "jeeves", messages)
    cutoff = list(chat.chat_messages.all())[1]
    resp = client.post(
        "/chat/compact/",
        data={
            "conversation_id": cid,
            "agent": "jeeves",
            "messages": messages,
            "through_message_id": cutoff.pk,
        },
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["span"] == {"start": 0, "end": 1}
    served = [row.get("content") for row in body["context"]]
    assert "after cutoff" in served
    assert "keep-summary" not in served


@pytest.mark.django_db
def test_auto_compact_skips_cli_and_remote_without_unknown_max_warning():
    user = get_user_model().objects.create_user("compress-skip", password="pw")
    messages = _turns(
        ("user", "turn 1"),
        ("assistant", "turn 2"),
        ("user", "turn 3"),
        ("assistant", "turn 4"),
    )
    # CLI agent:
    cli_res = auto_compact_before_send(
        user=user,
        conversation_id="conv-cli",
        agent_id="cli:grok",
        messages=messages,
    )
    assert cli_res.acted is False
    assert cli_res.reason == "non_api_agent"
    assert cli_res.info is None

    # Remote agent:
    remote_res = auto_compact_before_send(
        user=user,
        conversation_id="conv-remote",
        agent_id="remote:hermes",
        messages=messages,
    )
    assert remote_res.acted is False
    assert remote_res.reason == "non_api_agent"
    assert remote_res.info is None

    from swarm.core.context_cull_policy import prepare_context_before_send

    prep_res = prepare_context_before_send(
        user=user,
        conversation_id="conv-remote-prep",
        agent_id="remote:omb",
        messages=messages,
    )
    assert prep_res.acted is False
    assert prep_res.reason == "non_api_agent"
    assert prep_res.info is None


def _prep_result_for(agent_id: str, messages: list):
    from swarm.core.context_cull_policy import prepare_context_before_send

    return prepare_context_before_send(
        user=None,
        conversation_id=f"conv-{agent_id.replace(':', '-')}",
        agent_id=agent_id,
        messages=messages,
    )


@pytest.mark.django_db
def test_blueprint_seats_keep_compression_per_issue_72_acceptance():
    """#72: CLI/remote manage their own context; API *and* blueprint seats keep compress."""
    messages = _turns(
        ("user", "turn 1"),
        ("assistant", "turn 2"),
    )
    for seat in ("codey", "blueprint:codey"):
        res = _prep_result_for(seat, messages)
        assert res.reason != "non_api_agent", seat


@pytest.mark.django_db
def test_recipe_blueprints_gate_like_their_payload_issue_534():
    """#534: the SPA sends ``blueprint: remote_harness`` (plus
    ``params.remote``) when a remote seat chats, so the send-path gate sees the
    recipe id — which used to classify as ``api`` and let the
    'Auto-compress skipped' notice fire on remote transcripts."""
    messages = _turns(
        ("user", "turn 1"),
        ("assistant", "turn 2"),
    )
    for seat in ("remote_harness", "cli_agent"):
        res = _prep_result_for(seat, messages)
        assert res.acted is False, seat
        assert res.reason == "non_api_agent", seat
        assert res.info is None, seat

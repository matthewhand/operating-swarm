"""#215: per-seat context-window usage (read-only estimate + API payload)."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store
from swarm.core.chat_compact import compact_backlog
from swarm.core.context_usage import (
    CONTEXT_USAGE_TYPE,
    breakdown_from_context,
    estimate_tokens,
    overhead_from_blueprint,
    schema_from_tool,
    usage_snapshot,
)
from swarm.models import ConversationSummary


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="usage-op", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="usage-op", password="pw")
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


def test_estimate_tokens_is_chars_over_four():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2
    assert estimate_tokens({"role": "user", "content": "abcd"}) >= 1


def test_breakdown_splits_summaries_messages_system_and_tools():
    context = [
        {"role": "system", "content": "[Conversation summary]\nolder thread"},
        {"role": "system", "content": "You are a helpful seat."},
        {"role": "user", "content": "hello there"},
        {"role": "assistant", "content": "hi"},
    ]
    tools = [{"name": "search", "parameters": {"type": "object"}}]
    parts = breakdown_from_context(
        context,
        instructions="You are a helpful seat.",
        tool_schemas=tools,
    )
    assert parts["summaries"] > 0
    assert parts["messages"] > 0
    assert parts["system"] > 0
    assert parts["tools"] > 0
    # Instructions already present in a system row are not double-counted.
    assert parts["system"] == estimate_tokens(context[1])


@pytest.mark.django_db
def test_excluded_summary_drops_usage_tokens(user, stub_compact_llm):
    cid = "conv-215-excl"
    messages = _turns(
        ("user", "alpha question " * 20),
        ("assistant", "alpha answer " * 20),
        ("user", "later"),
    )
    _seed_json(user, "jeeves", messages, cid)
    compact_backlog(
        user=user,
        conversation_id=cid,
        agent_id="jeeves",
        messages=messages,
        span_end=1,
    )
    included = usage_snapshot(conversation_id=cid, agent_id="jeeves", turns=messages)
    row = ConversationSummary.objects.get(conversation_id=cid)
    row.include_in_context = False
    row.save(update_fields=["include_in_context"])
    excluded = usage_snapshot(conversation_id=cid, agent_id="jeeves", turns=messages)
    assert included["tokens"] > excluded["tokens"]
    assert excluded["breakdown"]["summaries"] == 0
    assert included["estimate"] is True
    assert included["type"] == CONTEXT_USAGE_TYPE
    assert included["window"] is None
    assert included["pct"] is None


@pytest.mark.django_db
def test_usage_reports_known_window_and_tools_overhead(user):
    cid = "conv-215-window"
    messages = _turns(("user", "hello"), ("assistant", "hi"))
    payload = usage_snapshot(
        conversation_id=cid,
        agent_id="jeeves",
        turns=messages,
        profile={"context_window": 8192},
        instructions="Be brief.",
        tool_schemas=[{"name": "lookup", "description": "Look things up."}],
    )
    assert payload["window"] == 8192
    assert payload["pct"] is not None
    assert payload["breakdown"]["tools"] > 0
    assert payload["breakdown"]["system"] > 0
    assert payload["tokens"] == sum(payload["breakdown"].values())


@pytest.mark.django_db
def test_usage_endpoint_returns_payload(client, user):
    cid = "conv-215-api"
    messages = _turns(("user", "alpha question"), ("assistant", "alpha answer"))
    _seed_json(user, "jeeves", messages, cid)
    resp = client.get(f"/chat/context-usage/?agent=jeeves&conversation_id={cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == CONTEXT_USAGE_TYPE
    assert body["conversation_id"] == cid
    assert body["agent_id"] == "jeeves"
    assert body["estimate"] is True
    assert "messages" in body["breakdown"]
    assert "summaries" in body["breakdown"]
    assert "system" in body["breakdown"]
    assert "tools" in body["breakdown"]
    assert body["tokens"] == sum(body["breakdown"].values())
    assert "window" in body


@pytest.mark.django_db
def test_usage_endpoint_requires_login():
    resp = Client().get("/chat/context-usage/?agent=jeeves&conversation_id=x")
    assert resp.status_code in (302, 401, 403)


@pytest.mark.django_db
def test_usage_endpoint_requires_conversation_id(client):
    resp = client.get("/chat/context-usage/?agent=jeeves")
    assert resp.status_code == 400


@pytest.mark.django_db
def test_compact_and_toggle_include_usage_payload(client, user, stub_compact_llm):
    cid = "conv-215-events"
    messages = _turns(
        ("user", "alpha question"),
        ("assistant", "alpha answer"),
        ("user", "beta question"),
    )
    _seed_json(user, "jeeves", messages, cid)
    compact = client.post(
        "/chat/compact/",
        json.dumps(
            {
                "agent": "jeeves",
                "conversation_id": cid,
                "messages": messages,
                "span_end": 1,
            }
        ),
        content_type="application/json",
    )
    assert compact.status_code == 200
    compact_body = compact.json()
    assert compact_body["usage"]["type"] == CONTEXT_USAGE_TYPE
    assert compact_body["usage"]["breakdown"]["summaries"] > 0
    summary_id = compact_body["summary"]["id"]

    toggled = client.post(
        "/chat/summary/toggle-context/",
        json.dumps({"summary_id": summary_id, "include_in_context": False}),
        content_type="application/json",
    )
    assert toggled.status_code == 200
    toggle_body = toggled.json()
    assert toggle_body["usage"]["type"] == CONTEXT_USAGE_TYPE
    assert toggle_body["usage"]["tokens"] < compact_body["usage"]["tokens"]
    assert toggle_body["usage"]["breakdown"]["summaries"] == 0


class _DummyTool:
    name = "lookup"
    description = "Look things up."
    params_json_schema = {"type": "object", "properties": {"q": {"type": "string"}}}


class _DummyAgent:
    instructions = "Be brief."
    tools = [_DummyTool()]


class _DummyBlueprint:
    agents = {"seat": _DummyAgent()}
    metadata = {"instructions": "Seat instructions."}


def test_schema_from_tool_is_read_only():
    schema = schema_from_tool(_DummyTool())
    assert schema["name"] == "lookup"
    assert schema["parameters"]["type"] == "object"
    assert schema_from_tool({"name": "search"}) == {"name": "search"}
    assert schema_from_tool(None) is None


def test_overhead_from_blueprint_counts_instructions_and_tools():
    instructions, schemas = overhead_from_blueprint(_DummyBlueprint())
    assert "Be brief." in instructions
    assert "Seat instructions." in instructions
    assert any(row.get("name") == "lookup" for row in schemas)


@pytest.mark.django_db
def test_usage_snapshot_includes_live_blueprint_overhead():
    payload = usage_snapshot(
        conversation_id="conv-215-bp",
        agent_id="jeeves",
        turns=_turns(("user", "hello"), ("assistant", "hi")),
        profile={"context_window": 4096},
        blueprint=_DummyBlueprint(),
    )
    assert payload["window"] == 4096
    assert payload["breakdown"]["tools"] > 0
    assert payload["breakdown"]["system"] > 0
    assert payload["tokens"] == sum(payload["breakdown"].values())
    assert json.dumps(payload)


@pytest.mark.django_db
def test_usage_endpoint_survives_catalog_errors(client, user, monkeypatch):
    cid = "conv-215-catalog"
    messages = _turns(("user", "alpha"), ("assistant", "beta"))
    _seed_json(user, "jeeves", messages, cid)

    def boom():
        raise RuntimeError("catalog down")

    monkeypatch.setattr("swarm.views.utils.get_available_blueprints_sync", boom)
    resp = client.get(f"/chat/context-usage/?agent=jeeves&conversation_id={cid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == CONTEXT_USAGE_TYPE
    assert body["tokens"] == sum(body["breakdown"].values())

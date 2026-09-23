"""Settings-only chat persistence + retention (REQ-14)."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store
from swarm.models import ChatConversation, ChatMessage


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="chat-op", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="chat-op", password="pw")
    return c


def _seed_thread(user, agent="jeeves", content="hello", ts=None):
    user_row = {"role": "user", "content": content}
    if ts:
        user_row["ts"] = ts
    chat_store.save(
        chat_store.user_key_for(user),
        agent,
        [user_row, {"role": "assistant", "content": "ok"}],
        conversation_id=chat_store.conversation_id_for(user, agent),
    )


@pytest.mark.django_db
def test_settings_shows_chat_counts_and_disk(client, user):
    _seed_thread(user)
    html = client.get("/settings/").content.decode()
    assert "Chat persistence" in html
    assert "Chats" in html
    assert "Disk used" in html
    assert "SWARM_CHAT_MAX_AGE_DAYS" in html
    assert "jeeves" in html
    assert 'data-action="chat-archive-all"' in html
    assert 'data-action="chat-empty-trash"' in html
    assert "Move to trash" in html
    # Must stay off the Chat chrome contract.
    assert "onclick=" not in html


@pytest.mark.django_db
def test_settings_unauthenticated_redirects():
    resp = Client().get("/settings/")
    assert resp.status_code == 302
    assert "login" in resp["Location"]


@pytest.mark.django_db
def test_chat_thread_restores_json(client, user):
    _seed_thread(user, "codey", "remember this")
    resp = client.get("/chat/thread/?agent=codey")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_id"] == "codey"
    assert body["conversation_id"] == chat_store.conversation_id_for(user, "codey")
    assert body["messages"][0]["content"] == "remember this"
    assert body["messages"][1]["role"] == "assistant"


@pytest.mark.django_db
def test_chat_thread_passes_through_stored_ts(client, user):
    _seed_thread(user, "codey", "stamped", ts="2026-09-02T21:21:00+00:00")
    resp = client.get("/chat/thread/?agent=codey")
    assert resp.status_code == 200
    assert resp.json()["messages"][0]["ts"] == "2026-09-02T21:21:00+00:00"


@pytest.mark.django_db
def test_chat_thread_backfills_from_django_db(client, user):
    cid = chat_store.conversation_id_for(user, "hybrid_team")
    chat = ChatConversation.objects.create(conversation_id=cid, student=user)
    ChatMessage.objects.create(conversation=chat, sender="user", content="from-db")
    resp = client.get("/chat/thread/?agent=hybrid_team")
    assert resp.status_code == 200
    assert resp.json()["messages"][0]["content"] == "from-db"
    loaded = chat_store.load(chat_store.user_key_for(user), "hybrid_team")
    assert loaded is not None
    assert loaded["messages"][0]["content"] == "from-db"


@pytest.mark.django_db
def test_chat_thread_isolates_two_agents_after_switch(client, user):
    """REQ-14 #319: GET /chat/thread/?agent= returns that agent's messages only."""
    _seed_thread(user, "codey", "prior question A")
    _seed_thread(user, "stewie", "prior question B")

    codey = client.get("/chat/thread/?agent=codey")
    stewie = client.get("/chat/thread/?agent=stewie")
    assert codey.status_code == 200
    assert stewie.status_code == 200
    assert codey.json()["agent_id"] == "codey"
    assert stewie.json()["agent_id"] == "stewie"
    assert codey.json()["messages"][0]["content"] == "prior question A"
    assert stewie.json()["messages"][0]["content"] == "prior question B"
    assert codey.json()["conversation_id"] != stewie.json()["conversation_id"]
    assert all(row["content"] != "prior question B" for row in codey.json()["messages"])
    assert all(row["content"] != "prior question A" for row in stewie.json()["messages"])


@pytest.mark.django_db
def test_chat_thread_isolates_two_sessions_and_summaries(client, user):
    """REQ-105: switching sessions does not leak transcript or compact state."""
    from swarm.core.agent_sessions import create_empty_session
    from swarm.core.chat_compact import compact_backlog

    first = create_empty_session(user, "codey", title="Alpha")
    second = create_empty_session(user, "codey", title="Beta")
    chat_store.save(
        chat_store.user_key_for(user),
        "codey",
        [{"role": "user", "content": "alpha only"}, {"role": "assistant", "content": "ok-a"}],
        conversation_id=first.conversation_id,
        session_id=first.conversation_id,
    )
    compact_backlog(
        user=user,
        conversation_id=first.conversation_id,
        agent_id="codey",
        messages=[
            {"role": "user", "content": "alpha only"},
            {"role": "assistant", "content": "ok-a"},
        ],
        summarizer=lambda items, **_kwargs: "LLM digest of the compacted range.",
    )
    alpha = client.get(
        f"/chat/thread/?agent=codey&conversation_id={first.conversation_id}"
    )
    beta = client.get(
        f"/chat/thread/?agent=codey&conversation_id={second.conversation_id}"
    )
    assert alpha.status_code == 200
    assert beta.status_code == 200
    assert alpha.json()["conversation_id"] == first.conversation_id
    assert beta.json()["conversation_id"] == second.conversation_id
    assert alpha.json()["messages"][0]["content"] == "alpha only"
    assert beta.json()["messages"] == []
    assert alpha.json()["summaries"]
    assert beta.json()["summaries"] == []
    assert all(row["content"] != "alpha only" for row in beta.json()["messages"])


@pytest.mark.django_db
def test_chat_thread_missing_selected_session_does_not_swap(client, user, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    chat_store.save(
        chat_store.user_key_for(user),
        "codey",
        [{"role": "user", "content": "older session"}, {"role": "assistant", "content": "old"}],
        conversation_id=chat_store.conversation_id_for(user, "codey"),
    )
    gone = client.get("/chat/thread/?agent=codey&conversation_id=sess-gone")
    assert gone.status_code == 200
    payload = gone.json()
    assert payload["conversation_id"] == "sess-gone"
    assert payload["session_missing"] is True
    assert payload["messages"] == []
    assert all(row.get("content") != "older session" for row in payload["messages"])


@pytest.mark.django_db
def test_chat_thread_requires_login():
    resp = Client().get("/chat/thread/?agent=jeeves")
    assert resp.status_code == 302


@pytest.mark.django_db
def test_chat_thread_get_marks_api_editable(client, user):
    _seed_thread(user, "jeeves", "hello")
    resp = client.get("/chat/thread/?agent=jeeves")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "api"
    assert body["editable"] is True


@pytest.mark.django_db
def test_patch_api_message_persists_and_marks_edited(client, user):
    _seed_thread(user, "jeeves", "hello")
    resp = client.patch(
        "/chat/thread/?agent=jeeves",
        data=json.dumps({"index": 0, "content": "engineered context"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["messages"][0]["content"] == "engineered context"
    assert body["messages"][0]["edited"] is True
    assert body["messages"][1]["content"] == "ok"
    loaded = chat_store.load(chat_store.user_key_for(user), "jeeves")
    assert loaded["messages"][0]["content"] == "engineered context"
    assert loaded["messages"][0]["edited"] is True

    again = client.get("/chat/thread/?agent=jeeves")
    assert again.json()["messages"][0]["content"] == "engineered context"


@pytest.mark.django_db
def test_patch_cli_and_remote_threads_are_forbidden(client, user):
    # REQ-808: CLI edits restart the provider session (200 + session_reset);
    # remote threads stay read-only (REQ-49).
    _seed_thread(user, "cli-grok", "cli-owned")
    _seed_thread(user, "remote-acp", "remote-owned")
    cli = client.patch(
        "/chat/thread/?agent=cli:grok",
        data=json.dumps({"index": 0, "content": "nope"}),
        content_type="application/json",
    )
    assert cli.status_code == 200
    assert cli.json()["session_reset"] is True
    cli_get = client.get("/chat/thread/?agent=cli:grok")
    assert cli_get.status_code == 200
    assert cli_get.json()["kind"] == "cli"
    assert cli_get.json()["editable"] is True
    assert (
        chat_store.load(chat_store.user_key_for(user), "cli-grok")["messages"][0]["content"]
        == "nope"
    )
    remote = client.patch(
        "/chat/thread/?agent=remote:acp",
        data=json.dumps({"index": 0, "content": "nope"}),
        content_type="application/json",
    )
    assert remote.status_code == 403
    remote_get = client.get("/chat/thread/?agent=remote:acp")
    assert remote_get.json()["kind"] == "remote"
    assert remote_get.json()["editable"] is False
    # CLI edit applied (REQ-808); remote thread stays untouched.
    assert chat_store.load(chat_store.user_key_for(user), "cli-grok")["messages"][0]["content"] == "nope"
    assert chat_store.load(chat_store.user_key_for(user), "remote-acp")["messages"][0]["content"] == "remote-owned"


@pytest.mark.django_db
def test_patch_rejects_bad_index_and_unauthenticated():
    assert Client().patch(
        "/chat/thread/?agent=jeeves",
        data=json.dumps({"index": 0, "content": "x"}),
        content_type="application/json",
    ).status_code == 302


@pytest.mark.django_db
def test_patch_index_out_of_range(client, user):
    _seed_thread(user, "jeeves")
    resp = client.patch(
        "/chat/thread/?agent=jeeves",
        data=json.dumps({"index": 9, "content": "x"}),
        content_type="application/json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_archive_one_and_restore(client, user):
    _seed_thread(user, "jeeves")
    resp = client.post("/settings/chats/action/", {"action": "archive", "agent_id": "jeeves"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert chat_store.load(chat_store.user_key_for(user), "jeeves") is None

    resp = client.post("/settings/chats/action/", {"action": "restore", "agent_id": "jeeves"})
    assert resp.status_code == 200
    loaded = chat_store.load(chat_store.user_key_for(user), "jeeves")
    assert loaded is not None
    assert loaded["messages"][0]["content"] == "hello"


@pytest.mark.django_db
def test_archive_all_and_empty_trash(client, user):
    _seed_thread(user, "a")
    _seed_thread(user, "b")
    resp = client.post("/settings/chats/action/", {"action": "archive_all"})
    assert resp.status_code == 200
    assert sorted(resp.json()["archived"]) == ["a", "b"]
    stats = chat_store.stats(chat_store.user_key_for(user))
    assert stats["active_count"] == 0
    assert stats["trash_count"] == 2

    resp = client.post("/settings/chats/action/", {"action": "empty_trash"})
    assert resp.status_code == 200
    assert resp.json()["removed"] == 2
    assert chat_store.stats(chat_store.user_key_for(user))["trash_count"] == 0


@pytest.mark.django_db
def test_unknown_action_rejected(client):
    resp = client.post("/settings/chats/action/", {"action": "explode"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_retention_scoped_to_current_user(client, user, db):
    other = get_user_model().objects.create_user(username="other", password="pw")
    _seed_thread(other, "other-user-thread", "private-other-transcript")
    _seed_thread(user, "mine-thread", "visible-own-transcript")
    html = client.get("/settings/").content.decode()
    assert "mine-thread" in html
    assert "other-user-thread" not in html
    client.post("/settings/chats/action/", {"action": "archive_all"})
    assert chat_store.load(chat_store.user_key_for(other), "other-user-thread") is not None
    assert chat_store.load(chat_store.user_key_for(user), "mine-thread") is None


@pytest.mark.django_db
def test_consumer_save_writes_json(user):
    from swarm.consumers import DjangoChatConsumer

    consumer = DjangoChatConsumer()
    consumer.user = user
    consumer.active_agent = "jeeves"
    save_sync = next(c for c in DjangoChatConsumer.__mro__ if "save_conversation" in c.__dict__).__dict__["save_conversation"].func
    save_sync(
        consumer,
        chat_store.conversation_id_for(user, "jeeves"),
        [{"role": "user", "content": "via-ws"}, {"role": "assistant", "content": "ack"}],
    )
    loaded = chat_store.load(chat_store.user_key_for(user), "jeeves")
    assert loaded is not None
    assert loaded["messages"][0]["content"] == "via-ws"


@pytest.mark.django_db
def test_settings_chat_group_lists_env_vars(client):
    html = client.get("/settings/").content.decode()
    assert "SWARM_CHAT_DIR" in html
    start = html.find("id=\"swarm-settings-data\"")
    assert start != -1
    payload = html[html.find(">", start) + 1 : html.find("</script>", start)]
    data = json.loads(payload)
    assert "chat_persistence" in data
    assert "SWARM_CHAT_MAX_AGE_DAYS" in data["chat_persistence"]["settings"]


@pytest.mark.django_db
def test_chat_thread_post_appends_status_message(client, user):
    _seed_thread(user, "codey", "prior turn")
    resp = client.post(
        "/chat/thread/?agent=codey",
        data=json.dumps({"message": {"role": "status", "content": "CLI: antigravity → grok"}}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["messages"]) == 3
    assert body["messages"][-1]["role"] == "status"
    assert body["messages"][-1]["content"] == "CLI: antigravity → grok"

    loaded = chat_store.load(chat_store.user_key_for(user), "codey")
    assert loaded is not None
    assert loaded["ui_events"][-1]["content"] == "CLI: antigravity → grok"
    assert all(row["role"] != "status" for row in loaded["messages"])


@pytest.mark.django_db
def test_chat_thread_post_requires_valid_message(client, user):
    resp = client.post(
        "/chat/thread/?agent=codey",
        data=json.dumps({"message": {}}),
        content_type="application/json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_chat_thread_passes_through_fatal_config_error(client, user):
    chat_store.save(
        chat_store.user_key_for(user),
        "cli_agent",
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "No CLI agents are configured.",
                "fatal_config_error": True,
            },
        ],
        conversation_id=chat_store.conversation_id_for(user, "cli_agent"),
    )
    resp = client.get("/chat/thread/?agent=cli_agent")
    assert resp.status_code == 200
    assistant = next(row for row in resp.json()["messages"] if row["role"] == "assistant")
    assert assistant["fatal_config_error"] is True


@pytest.mark.django_db
def test_chat_thread_clear_wipes_poisoned_history(client, user):
    _seed_thread(user, "cli_agent", "poisoned")
    resp = client.post(
        "/chat/thread/?agent=cli_agent",
        data=json.dumps({"action": "clear"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["messages"] == []
    loaded = chat_store.load(chat_store.user_key_for(user), "cli_agent")
    assert loaded is not None
    assert loaded["messages"] == []
    assert loaded.get("ui_events") == []


"""REQ-105: Django-backed sessions scoped to one agent."""

from django.contrib.auth import get_user_model

from swarm.core import chat_store
from swarm.core.agent_sessions import (
    DEFAULT_TITLE,
    NEW_TITLE,
    create_empty_session,
    ensure_default_session,
    list_agent_sessions,
    persist_allocated_session,
    title_and_snippet,
)
from swarm.core.chat_compact import compact_backlog
from swarm.models import ConversationSummary


def _user(db, name="sess-op"):
    return get_user_model().objects.create_user(username=name, password="pw")


def test_title_and_snippet_ignore_status_lines():
    title, snippet = title_and_snippet(
        [
            {"role": "status", "content": "Connecting…"},
            {"role": "user", "content": "first question about bees"},
            {"role": "assistant", "content": "bees make honey"},
        ]
    )
    assert title.startswith("first question")
    assert snippet == "bees make honey"


def test_default_session_migrates_existing_transcript(db, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    user = _user(db)
    cid = chat_store.conversation_id_for(user, "codey")
    chat_store.save(
        chat_store.user_key_for(user),
        "codey",
        [{"role": "user", "content": "remember this"}, {"role": "assistant", "content": "ok"}],
        conversation_id=cid,
    )
    row = ensure_default_session(user, "codey")
    assert row.conversation_id == cid
    assert row.agent_id == "codey"
    assert row.title == "remember this"
    assert row.snippet == "ok"
    listed = list_agent_sessions(user, "codey")
    assert [item.conversation_id for item in listed] == [cid]


def test_create_n_sessions_lists_only_that_agent(db, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    user = _user(db)
    ensure_default_session(user, "codey")
    a = create_empty_session(user, "codey", title="Notes")
    b = create_empty_session(user, "codey", title="Later")
    other = create_empty_session(user, "stewie", title="Other")
    ids = {row.conversation_id for row in list_agent_sessions(user, "codey")}
    assert a.conversation_id in ids
    assert b.conversation_id in ids
    assert other.conversation_id not in ids
    assert all(row.agent_id == "codey" for row in list_agent_sessions(user, "codey"))
    empty = create_empty_session(user, "codey")
    assert empty.title == NEW_TITLE
    assert empty.snippet == ""


def test_scale_out_allocate_appears_in_picker(db, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    user = _user(db, "scale-op")
    persist_allocated_session(user, "worker", "task-1-worker-alpha", empty=True)
    persist_allocated_session(user, "worker", "task-1-worker-beta", empty=True)
    ids = {row.conversation_id for row in list_agent_sessions(user, "worker")}
    assert "task-1-worker-alpha" in ids
    assert "task-1-worker-beta" in ids


def test_compact_does_not_leak_across_sessions(db, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    user = _user(db, "compact-sess")
    first = create_empty_session(user, "jeeves", title="Alpha")
    second = create_empty_session(user, "jeeves", title="Beta")
    messages = [
        {"role": "user", "content": "alpha question"},
        {"role": "assistant", "content": "alpha answer"},
    ]
    compact_backlog(
        user=user,
        conversation_id=first.conversation_id,
        agent_id="jeeves",
        messages=messages,
        summarizer=lambda items, **_kwargs: "LLM digest of the compacted range.",
    )
    assert ConversationSummary.objects.filter(conversation_id=first.conversation_id).exists()
    assert not ConversationSummary.objects.filter(conversation_id=second.conversation_id).exists()
    assert DEFAULT_TITLE or first.title


# ---- #731: session retitling via tiny/auxiliary override chain ----

def test_schedule_session_retitle_skips_non_default_titles(db, monkeypatch):
    """Sessions already carrying a curated title are never retitled."""
    from swarm.core import agent_sessions
    from swarm.models import ChatConversation

    chat = ChatConversation.objects.create(
        student=_user(db, "retitle-owner-a"),
        conversation_id="agt-jeeves-731a",
        title="Quarterly planning",
        agent_id="jeeves",
    )
    scheduled = []
    monkeypatch.setattr(agent_sessions, "_schedule_background_task", lambda fn: scheduled.append(fn))

    agent_sessions.schedule_session_retitle(chat)
    assert scheduled == []  # curated title → no work scheduled


def test_schedule_session_retitle_schedules_for_default_titles(db, monkeypatch):
    from swarm.core import agent_sessions
    from swarm.models import ChatConversation

    owner = _user(db, "retitle-owner-b")
    for title in ("", "Session 1", "New session"):
        chat = ChatConversation.objects.create(
            student=owner,
            conversation_id=f"agt-jeeves-731-{abs(hash(title)) % 99999}",
            title=title,
            agent_id="jeeves",
        )
        scheduled = []
        monkeypatch.setattr(agent_sessions, "_schedule_background_task", lambda fn: scheduled.append(fn))
        agent_sessions.schedule_session_retitle(chat)
        assert len(scheduled) == 1, f"title={title!r} should schedule a retitle"


def test_perform_session_retitle_uses_tiny_chain_and_persists(db, monkeypatch):
    """The retitle pass generates via the tiny chain and writes a clipped title."""
    from swarm.core import agent_sessions
    from swarm.models import ChatConversation

    chat = ChatConversation.objects.create(
        student=_user(db, "retitle-owner-c"),
        conversation_id="agt-jeeves-731c",
        title="",
        agent_id="jeeves",
    )

    captured = {}
    def fake_generate_session_title(messages):
        captured["messages"] = messages
        return "Philosophers Chat Plan"

    monkeypatch.setattr(
        "swarm.core.llm_assist.generate_session_title", fake_generate_session_title
    )

    agent_sessions.perform_session_retitle(
        chat.conversation_id,
        messages=[{"role": "user", "content": "lets plan the philosophers chat"}],
    )

    chat.refresh_from_db()
    assert chat.title == "Philosophers Chat Plan"
    assert captured["messages"][0]["role"] == "user"


def test_schedule_session_retitle_treats_raw_truncation_as_uncurated(db, monkeypatch):
    """touch_session stamps the first-line truncation — that is still raw."""
    from swarm.core import agent_sessions
    from swarm.models import ChatConversation

    messages = [{"role": "user", "content": "hey help me debug the flask app startup"}]
    raw_title, _ = agent_sessions.title_and_snippet(messages)

    chat = ChatConversation.objects.create(
        student=_user(db, "retitle-owner-d"),
        conversation_id="agt-jeeves-731d",
        title=raw_title,  # what touch_session just stamped
        agent_id="jeeves",
    )
    scheduled = []
    monkeypatch.setattr(agent_sessions, "_schedule_background_task", lambda fn: scheduled.append(fn))
    agent_sessions.schedule_session_retitle(chat, messages=messages)
    assert len(scheduled) == 1, "raw truncation title must still be retitled"

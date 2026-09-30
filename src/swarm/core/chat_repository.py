"""Canonical chat writes (#1440).

Product code inserts and retains ``ChatMessage`` / ``ChatConversation``
rows here. Each new composer message is one ``ChatMessage`` via
``sync_transcript`` (tail insert, in-place edit). ``replace_thread``
remains the full-snapshot write used by hops and compact. The JSON
``chat_store`` file is rewritten only as a derived cache
(``mirror_db=False``), so a send does not create a second record.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _owned(user):
    from swarm.models import ChatConversation

    if user is None:
        return ChatConversation.objects.none()
    return ChatConversation.objects.filter(student=user)


def thread_is_trashed(user, conversation_id: str) -> bool:
    """True when the canonical row is soft- or hard-deleted.

    ``purged_at`` (#1721) counts: a thread the user emptied from the trash is
    gone for good, and every write path funnels through this check, so one
    predicate is what makes "permanent" mean anything.
    """
    cid = (conversation_id or "").strip()
    if not cid or user is None:
        return False
    chat = _owned(user).filter(conversation_id=cid).first()
    if chat is None:
        return False
    from swarm.core.chat_db import is_retired

    return is_retired(chat)


def _cache_turns(chat) -> list[dict[str, Any]]:
    from swarm.core.chat_db import turn_from_row

    return [turn_from_row(row) for row in chat.chat_messages.all()]


def _write_cache(
    user,
    agent_id: str,
    chat,
    *,
    turns: list[dict[str, Any]] | None = None,
    ui_events: list[dict[str, Any]] | None = None,
    session_id: str = "",
    cli_sessions: dict[str, Any] | None = None,
    cli_hop: Any = ...,
    active_cli: str | None = None,
    base_dir: Path | None = None,
) -> None:
    """Refresh the JSON export from the canonical rows. Never mirrors back.

    ``user is None`` is a genuine early return: ``user_key_for(None)`` raises
    and there is no owner to file the export under. An EMPTY ``agent_id`` is
    *not* an error. The default-model seat has no blueprint, and
    ``chat_store.normalize_agent_id("")`` maps it to ``_default`` — a real,
    addressable seat. Treating "" as "nothing to write" meant the default-model
    thread was never exported to JSON, so every file-only reader (archive,
    retention/prune, the export endpoint, the one-way import) reported an empty
    thread while the Django rows were correct. ``load_or_django`` masked it by
    falling back to the DB; the file-only paths did not. #1712.
    """
    from swarm.core import chat_store

    if user is None:
        return
    try:
        user_key = chat_store.user_key_for(user)
    except Exception:
        logger.debug("chat cache user key skipped", exc_info=True)
        return
    events = ui_events
    if events is None:
        raw_events = getattr(chat, "ui_events", None)
        events = list(raw_events) if isinstance(raw_events, list) else []
    body = turns if turns is not None else _cache_turns(chat)
    try:
        chat_store.save(
            user_key,
            agent_id,
            body,
            conversation_id=getattr(chat, "conversation_id", "") or "",
            session_id=session_id,
            ui_events=events,
            cli_sessions=cli_sessions,
            cli_hop=cli_hop,
            active_cli=active_cli,
            base_dir=base_dir,
            mirror_db=False,
        )
    except Exception:
        logger.debug("chat cache refresh skipped for %s", agent_id, exc_info=True)


def replace_thread(
    user,
    conversation_id: str,
    turns: list[dict[str, Any]] | None,
    *,
    agent_id: str = "",
    ui_events: list[dict[str, Any]] | None = None,
    cli_sessions: dict[str, Any] | None = None,
    cli_hop: Any = ...,
    active_cli: str | None = None,
    session_id: str = "",
    cache: bool = True,
):
    """Replace one thread's canonical rows, then refresh the JSON cache.

    ``cache=False`` is the DB-only mirror (#901). The JSON file stays empty
    so a later hop can still read the database snapshot.
    """
    from swarm.core.chat_db import replace_db_thread

    if thread_is_trashed(user, conversation_id):
        return None
    try:
        chat = replace_db_thread(
            user,
            conversation_id,
            turns,
            agent_id=agent_id,
            ui_events=ui_events,
        )
    except PermissionError:
        return None
    if cache:
        _write_cache(
            user,
            agent_id,
            chat,
            turns=list(turns or []),
            ui_events=ui_events,
            session_id=session_id,
            cli_sessions=cli_sessions,
            cli_hop=cli_hop,
            active_cli=active_cli,
        )
    return chat


def sync_transcript(
    user,
    conversation_id: str,
    turns: list[dict[str, Any]] | None,
    *,
    agent_id: str = "",
    ui_events: list[dict[str, Any]] | None = None,
    refresh: bool = True,
    session_id: str = "",
    base_dir: Path | None = None,
    truncate: bool = False,
) -> int:
    """Insert only new tail rows and update rows whose content changed.

    Returns the number of ``ChatMessage`` rows inserted. Existing primary
    keys stay put. This is the composer / disconnect write — not a
    delete-all plus bulk insert.

    ``truncate`` is the *only* way canonical rows are ever deleted here, and
    it means "the user asked for this thread to be shorter", not "the caller
    happens to hold a shorter list". It is set by exactly one caller,
    :func:`clear_thread`.

    #1722: this used to delete the tail whenever ``turns`` was shorter than
    what the database held, which made "short list" indistinguishable from
    "delete". Every writer that is behind — a websocket socket hydrated before
    a concurrent append, a ``chat_store`` cache file left behind by a failed
    write, a second worker process with its own memory — then destroyed live
    rows. Under DB-is-canonical a short list is *stale*, not authoritative,
    so the rows it does not mention survive and the ones it does mention are
    still updated in place.
    """
    from django.db import transaction

    from swarm.core.agent_sessions import get_or_create_session
    from swarm.core.chat_db import extra_from_turn, timestamp_for_turn
    from swarm.core.transcript_roles import is_ui_only_role
    from swarm.models import ChatConversation, ChatMessage

    cid = (conversation_id or "").strip()
    if not cid:
        raise ValueError("conversation_id is required")
    if thread_is_trashed(user, cid):
        return 0
    model_turns = [
        item
        for item in (turns or [])
        if isinstance(item, dict) and not is_ui_only_role(item.get("role"))
    ]
    inserted = 0
    with transaction.atomic():
        chat = get_or_create_session(user, cid, agent_id=agent_id)
        chat = ChatConversation.objects.select_for_update().get(pk=chat.pk)
        existing = list(chat.chat_messages.select_for_update().order_by("timestamp", "id"))
        if existing and all(_row_seq(row) is not None for row in existing):
            existing.sort(key=_row_seq)
        for index, turn in enumerate(model_turns):
            payload_extra = extra_from_turn(turn)
            sender = turn.get("role") or "user"
            content = turn.get("content") or ""
            if index < len(existing):
                row = existing[index]
                if (
                    row.sender != sender
                    or row.content != content
                    or (row.extra or {}) != payload_extra
                ):
                    row.sender = sender
                    row.content = content
                    row.extra = payload_extra
                    row.timestamp = timestamp_for_turn(turn)
                    row.save(update_fields=["sender", "content", "extra", "timestamp"])
                continue
            ChatMessage.objects.create(
                conversation=chat,
                sender=sender,
                content=content,
                timestamp=timestamp_for_turn(turn),
                extra=payload_extra,
            )
            inserted += 1
        if truncate and len(existing) > len(model_turns):
            tail_ids = [row.id for row in existing[len(model_turns) :]]
            ChatMessage.objects.filter(id__in=tail_ids).delete()
        if ui_events is not None:
            chat.ui_events = [event for event in ui_events if isinstance(event, dict)]
            chat.save(update_fields=["ui_events", "updated_at"])
        elif inserted:
            chat.save(update_fields=["updated_at"])
    if refresh:
        refresh_cache(
            user,
            agent_id,
            cid,
            list(turns or []),
            ui_events,
            session_id=session_id,
            base_dir=base_dir,
        )
    return inserted


def append_message(user, agent_id: str, conversation_id: str, turn: dict[str, Any]):
    """Insert exactly one ``ChatMessage``. The JSON file is cache-only."""
    from swarm.core.agent_sessions import get_or_create_session
    from swarm.core.chat_db import extra_from_turn, timestamp_for_turn
    from swarm.models import ChatMessage

    cid = (conversation_id or "").strip()
    if not cid:
        raise ValueError("conversation_id is required")
    if thread_is_trashed(user, cid):
        return None
    item = dict(turn or {})
    chat = get_or_create_session(user, cid, agent_id=agent_id or "")
    created = ChatMessage.objects.bulk_create(
        [
            ChatMessage(
                conversation=chat,
                sender=item.get("role") or "user",
                content=item.get("content") or "",
                timestamp=timestamp_for_turn(item),
                extra=extra_from_turn(item),
            )
        ]
    )
    row = created[0]
    chat.save(update_fields=["updated_at"])
    _write_cache(
        user,
        agent_id,
        chat,
        session_id=_session_id_for(user, agent_id, cid),
    )
    return row


def append_ui_event(user, agent_id: str, conversation_id: str, event: dict[str, Any]):
    from swarm.core.agent_sessions import get_or_create_session

    cid = (conversation_id or "").strip()
    if not cid:
        raise ValueError("conversation_id is required")
    if thread_is_trashed(user, cid):
        return None
    chat = get_or_create_session(user, cid, agent_id=agent_id or "")
    events = list(chat.ui_events or []) if isinstance(chat.ui_events, list) else []
    if isinstance(event, dict):
        events.append(event)
    chat.ui_events = events
    chat.save(update_fields=["ui_events", "updated_at"])
    _write_cache(
        user,
        agent_id,
        chat,
        session_id=_session_id_for(user, agent_id, cid),
    )
    return chat


def insert_turns(chat, turns: list[dict[str, Any]] | None) -> int:
    """Append canonical rows without deleting the ones already stored."""
    from swarm.core.chat_db import extra_from_turn, is_retired, timestamp_for_turn
    from swarm.core.transcript_roles import is_ui_only_role
    from swarm.models import ChatMessage

    if is_retired(chat):
        return 0
    rows: list[ChatMessage] = []
    for item in turns or []:
        if not isinstance(item, dict) or is_ui_only_role(item.get("role")):
            continue
        rows.append(
            ChatMessage(
                conversation=chat,
                sender=item.get("role") or "user",
                content=item.get("content") or "",
                timestamp=timestamp_for_turn(item),
                extra=extra_from_turn(item),
            )
        )
    if not rows:
        return 0
    ChatMessage.objects.bulk_create(rows)
    return len(rows)


def clear_thread(
    user,
    conversation_id: str,
    *,
    agent_id: str = "",
    base_dir: Path | None = None,
) -> None:
    """Drop every canonical row and write an empty JSON cache.

    ``agent_id=""`` is the default-model seat, so the empty cache it writes is
    ``_default.json`` — otherwise clearing the default thread left a stale
    export behind that a later ``load`` would return as live. #1712.

    This is the one caller that means "shorter" as *intent*, so it is the one
    caller that passes ``truncate=True`` (#1722).
    """
    from swarm.core import chat_store

    cid = (conversation_id or "").strip()
    if thread_is_trashed(user, cid):
        return
    sync_transcript(
        user,
        cid,
        [],
        agent_id=agent_id,
        ui_events=[],
        refresh=False,
        truncate=True,
    )
    if user is None:
        return
    session_id = _session_id_for(user, agent_id, cid)
    chat_store.save(
        chat_store.user_key_for(user),
        agent_id,
        [],
        conversation_id=cid,
        session_id=session_id,
        ui_events=[],
        cli_sessions={},
        cli_hop=None,
        active_cli="",
        base_dir=base_dir,
        mirror_db=False,
    )


def refresh_cache(
    user,
    agent_id: str,
    conversation_id: str,
    turns: list[dict[str, Any]] | None,
    ui_events: list[dict[str, Any]] | None,
    *,
    session_id: str = "",
    base_dir: Path | None = None,
) -> None:
    """Write the JSON cache from turns that were already stored in Django.

    An empty ``agent_id`` is the default-model seat, not a skip: the store
    normalises it to ``_default`` (#1712).
    """
    from swarm.core import chat_store

    if user is None:
        return
    sid = session_id or _session_id_for(user, agent_id, conversation_id)
    chat_store.save(
        chat_store.user_key_for(user),
        agent_id,
        list(turns or []),
        conversation_id=conversation_id,
        session_id=sid,
        ui_events=ui_events,
        base_dir=base_dir,
        mirror_db=False,
    )


def _unwritten_suffix(
    owner,
    conversation_id: str,
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """The tail of ``turns`` the database does not already hold.

    Longest common prefix on ``(role, content)``. A JSON cache is a
    *derived* view, so a cache writer may only ever contribute turns the
    canonical store has not seen; it may not rewrite the ones it has.
    """
    from swarm.core.chat_db import load_db_thread

    loaded = load_db_thread(owner, conversation_id)
    stored = list(loaded[0]) if loaded else []
    matched = 0
    for row, incoming in zip(stored, turns):
        if (row.get("role") or "user") != (incoming.get("role") or "user"):
            break
        if (row.get("content") or "") != (incoming.get("content") or ""):
            break
        matched += 1
    return list(turns[matched:])


def _ui_event_key(item: Any) -> tuple[str, Any]:
    """Stable identity for one UI event, so a union can skip what it has."""
    if isinstance(item, dict):
        seq = item.get("seq")
        if isinstance(seq, int) and not isinstance(seq, bool):
            return ("seq", seq)
        return ("raw", json.dumps(item, sort_keys=True, default=str))
    return ("raw", str(item))


def _extend_ui_events(chat, events: list[dict[str, Any]] | None) -> int:
    """Add cache-origin UI events the column does not already hold. Never removes.

    ``ChatConversation.ui_events`` is a column, so it is canonical for the
    side-channel chrome. A JSON-origin write may extend it (a mailbox hop
    notice the cache saw and the column has not) but may not shrink it: a short
    cache file must never be able to delete chrome.
    """
    if not events:
        return 0
    stored = list(chat.ui_events or []) if isinstance(chat.ui_events, list) else []
    seen = {_ui_event_key(item) for item in stored}
    added = [
        item
        for item in events
        if isinstance(item, dict) and _ui_event_key(item) not in seen
    ]
    if not added:
        return 0
    chat.ui_events = stored + added
    chat.save(update_fields=["ui_events", "updated_at"])
    return len(added)


def persist_from_cache_record(
    user_key: str,
    agent_id: str,
    record: dict[str, Any] | None,
    *,
    base_dir: Path | None = None,
) -> bool:
    """Append-only database write from a ``chat_store`` record. False when
    the key is not a user.

    Every ``chat_store.save(..., mirror_db=True)`` call site lands here, so
    this is the one funnel that decides what a JSON file is allowed to do to
    the canonical rows. #1722 made that decision "reconcile by index", which
    is the same thing as "the cache is authoritative": a writer that was
    behind, or that was writing about a different conversation, overwrote or
    deleted live rows.

    It is now **append-only**:

    * a retired thread (trashed / purged, #1721) gets no write at all;
    * turns the database already holds are never rewritten or removed;
    * only the genuinely new tail is inserted.

    The JSON file is then rewritten so it can never be shorter than the
    canonical rows, and the record's thread metadata (``cli_sessions`` /
    ``cli_hop`` / ``active_cli``) is carried across, since that is the part of
    the record the database does not model.
    """
    from swarm.core import chat_store
    from swarm.core.agent_sessions import get_or_create_session
    from swarm.core.chat_db import user_from_key

    if not isinstance(record, dict):
        return False
    owner = user_from_key(user_key)
    if owner is None:
        return False
    cid = str(record.get("conversation_id") or "").strip()
    if not cid:
        cid = chat_store.conversation_id_for(owner, agent_id)
    if not cid:
        return False
    if thread_is_trashed(owner, cid):
        return True
    session_id = str(record.get("session_id") or "")
    incoming = list(record.get("messages") or [])
    events = [item for item in (record.get("ui_events") or []) if isinstance(item, dict)]
    chat = get_or_create_session(owner, cid, agent_id=agent_id)
    suffix = _unwritten_suffix(owner, cid, incoming)
    if suffix:
        written = insert_turns(chat, suffix)
        if written:
            chat.save(update_fields=["updated_at"])
    # Not even an EMPTY incoming list truncates. "The cache says this thread is
    # empty" and "the user cleared this thread" are different claims, and a
    # ``chat_store.save(..., messages=[])`` call cannot tell them apart — the
    # two real callers of that shape (``create_empty_session`` and
    # ``_persist_empty_task_record``) both write freshly minted ids where it is
    # a no-op anyway. Clearing is :func:`clear_thread`'s job, on the canonical
    # store, with ``truncate=True``. Anything else would leave "a JSON file that
    # happens to be empty" able to destroy live rows.
    _extend_ui_events(chat, events)
    # Export the caller's own turn dicts so per-turn metadata it supplied
    # (``ts`` from the client, a title, an attachment list) survives the round
    # trip, EXCEPT when that list is shorter than the canonical rows — which is
    # exactly the stale-cache case. Publishing a cache shorter than the
    # database is what leaves a permanently truncating file on disk for the
    # next writer to read back, so that case is repaired from the rows.
    canonical = _cache_turns(chat)
    export = list(incoming) if len(incoming) >= len(canonical) else canonical
    sessions = record.get("cli_sessions")
    chat_store.save(
        user_key,
        agent_id,
        export,
        conversation_id=cid,
        session_id=session_id or _session_id_for(owner, agent_id, cid),
        cli_sessions=sessions if isinstance(sessions, dict) else None,
        ui_events=list(record.get("ui_events") or []),
        cli_hop=record.get("cli_hop"),
        active_cli=str(record.get("active_cli") or ""),
        base_dir=base_dir,
        mirror_db=False,
    )
    return True


def _forget_memory_cache(user, *conversation_ids: str) -> None:
    """Drop a thread from the process-local websocket cache.

    ``archive_agent`` / ``empty_trash`` touch the database and the filesystem
    only, so a live socket in this process kept being served the full
    transcript out of ``IN_MEMORY_CONVERSATIONS`` after the user had deleted
    it. Retirement is a privacy promise; the memory cache has to honour it
    too (#1722). Best-effort: the module is importable without Django's
    consumer stack.
    """
    try:
        from swarm.consumers import IN_MEMORY_CONVERSATIONS, IN_MEMORY_UI_EVENTS
        from swarm.consumers import _conversation_cache_key
    except Exception:
        logger.debug("ws memory cache unavailable for purge", exc_info=True)
        return
    for cid in conversation_ids:
        if not cid or user is None:
            continue
        try:
            key = _conversation_cache_key(user, cid)
        except Exception:
            continue
        IN_MEMORY_CONVERSATIONS.pop(key, None)
        IN_MEMORY_UI_EVENTS.pop(key, None)


def archive_agent(user, agent_id: str, *, base_dir: Path | None = None) -> bool:
    """Trash the agent's canonical threads. JSON archive follows as a cache move.

    The cache move covers **every** file this seat owns, not just
    ``<agent>.json``. ``archive_all`` already did (it walks
    ``list_active``), and the single-agent path leaving ``<agent>__<cid>.json``
    behind in ``active/`` is what let a session thread survive its own
    archive and be re-imported later (#1721). One rule, both entry points.
    """
    from swarm.core import chat_store

    agent = (agent_id or "").strip()
    rows = [row for row in _owned(user).filter(agent_id=agent) if row.trashed_at is None]
    if not rows:
        try:
            moved = chat_store.archive(chat_store.user_key_for(user), agent, base_dir=base_dir)
        except Exception:
            logger.debug("chat cache archive skipped for %s", agent, exc_info=True)
            return False
        return moved is not None
    stamp = _now()
    for row in rows:
        row.trashed_at = stamp
        row.save(update_fields=["trashed_at", "updated_at"])
    _forget_memory_cache(user, *(row.conversation_id for row in rows))
    try:
        chat_store.archive(chat_store.user_key_for(user), agent, base_dir=base_dir)
    except Exception:
        logger.debug("chat cache archive skipped for %s", agent, exc_info=True)
    return True


def archive_all(user, *, base_dir: Path | None = None) -> list[str]:
    from swarm.core import chat_store

    agents: list[str] = []
    seen: set[str] = set()
    for row in _owned(user):
        agent = (row.agent_id or "").strip()
        if not agent or agent in seen or row.trashed_at is not None or row.purged_at is not None:
            continue
        if archive_agent(user, agent, base_dir=base_dir):
            agents.append(agent)
            seen.add(agent)
    try:
        # Cache files the DB did not know about still leave the active dir.
        for agent in chat_store.archive_all(chat_store.user_key_for(user), base_dir=base_dir):
            if agent not in seen:
                agents.append(agent)
                seen.add(agent)
    except Exception:
        logger.debug("chat cache archive_all skipped", exc_info=True)
    return agents


def restore_agent(user, agent_id: str, *, base_dir: Path | None = None) -> bool:
    from swarm.core import chat_store
    from swarm.core.chat_db import load_db_thread

    agent = (agent_id or "").strip()
    rows = [
        row
        for row in _owned(user).filter(agent_id=agent)
        if row.trashed_at is not None and row.purged_at is None
    ]
    json_restored = False
    try:
        json_restored = (
            chat_store.restore(chat_store.user_key_for(user), agent, base_dir=base_dir) is not None
        )
    except Exception:
        logger.debug("chat cache restore skipped for %s", agent, exc_info=True)
    if not rows and not json_restored:
        return False
    for row in rows:
        row.trashed_at = None
        row.save(update_fields=["trashed_at", "updated_at"])
    if rows:
        primary = rows[0]
        try:
            loaded = load_db_thread(user, primary.conversation_id)
            turns = list(loaded[0]) if loaded else []
            events = list(loaded[1]) if loaded else []
            refresh_cache(
                user,
                agent,
                primary.conversation_id,
                turns,
                events,
                base_dir=base_dir,
            )
        except Exception:
            logger.debug("restore cache rebuild skipped for %s", agent, exc_info=True)
    return True


def empty_trash(user, *, base_dir: Path | None = None) -> int:
    """Permanently delete every trashed thread (#1721).

    The row is **retired, not dropped**. ``ChatConversation.purged_at`` is the
    tombstone: a missing row is indistinguishable from a thread that never
    existed, and the one-way ``chat_store`` JSON import is gated on "the DB
    thread is empty" — so deleting the row and leaving the cache file on disk
    is precisely the combination that resurrected permanently deleted content
    and re-wrote it into the database. Keeping a content-free row means every
    read and write path can refuse the id forever, including one that runs in
    another process or against a cache file written after this call.

    The content really is gone: every ``ChatMessage`` row is deleted, the
    title/snippet/cli binding/UI chrome are cleared, the active cache files
    for these conversations are unlinked, and the in-process websocket cache
    is dropped.
    """
    from swarm.core import chat_store
    from swarm.models import ChatMessage

    removed = 0
    stamp = _now()
    purged: list[tuple[str, str]] = []
    for row in list(_owned(user)):
        if row.trashed_at is None or row.purged_at is not None:
            continue
        agent = (row.agent_id or "").strip()
        ChatMessage.objects.filter(conversation=row).delete()
        row.purged_at = stamp
        row.trashed_at = stamp
        row.title = ""
        row.snippet = ""
        row.labels = []
        row.cli_session_id = ""
        row.context_meta = {}
        row.ui_events = []
        row.save(
            update_fields=[
                "purged_at",
                "trashed_at",
                "title",
                "snippet",
                "labels",
                "cli_session_id",
                "context_meta",
                "ui_events",
                "updated_at",
            ]
        )
        purged.append((agent, row.conversation_id))
        removed += 1
    _forget_memory_cache(user, *(cid for _agent, cid in purged))
    # The cache file for a purged conversation is the resurrection fuel. Delete
    # it here as well as at archive time: a file written by a racing process
    # between the archive and this call would otherwise be all that is left.
    for agent, cid in purged:
        try:
            chat_store.purge_conversation(
                chat_store.user_key_for(user),
                agent,
                cid,
                base_dir=base_dir,
            )
        except Exception:
            logger.debug("chat cache purge skipped for %s/%s", agent, cid, exc_info=True)
    try:
        json_removed = chat_store.empty_trash(chat_store.user_key_for(user), base_dir=base_dir)
    except Exception:
        logger.debug("chat cache empty_trash skipped", exc_info=True)
        json_removed = 0
    return removed or int(json_removed or 0)


def prune_expired(
    user, *, max_age_days: int | None = None, now: datetime | None = None, base_dir: Path | None = None
) -> list[str]:
    from swarm.core import chat_store
    from swarm.core.chat_store import get_max_age_days

    age = int(max_age_days) if max_age_days is not None else get_max_age_days()
    if age <= 0:
        return []
    clock = now or _now()
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    cutoff = clock - timedelta(days=age)
    archived: list[str] = []
    seen: set[str] = set()
    # Trash only the stale rows. archive_agent would also hide a fresh
    # sibling conversation that shares the agent id (on-mode sessions).
    for row in list(_owned(user)):
        if row.trashed_at is not None or row.purged_at is not None:
            continue
        updated = row.updated_at
        if updated is None:
            continue
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if updated > cutoff:
            continue
        row.trashed_at = clock
        row.save(update_fields=["trashed_at", "updated_at"])
        agent = (row.agent_id or "").strip()
        label = agent or row.conversation_id
        if label not in seen:
            archived.append(label)
            seen.add(label)
        if not agent:
            continue
        if _owned(user).filter(
            agent_id=agent, trashed_at__isnull=True, purged_at__isnull=True
        ).exists():
            continue
        try:
            chat_store.archive(chat_store.user_key_for(user), agent, base_dir=base_dir)
        except Exception:
            logger.debug("chat cache archive skipped for %s", agent, exc_info=True)
    return archived


def stats_for(user, *, base_dir: Path | None = None) -> dict[str, Any]:
    from swarm.core.chat_store import (
        ENV_CHAT_DIR,
        ENV_CHAT_MAX_AGE_DAYS,
        format_bytes,
        get_max_age_days,
        store_dir,
    )

    active: list[dict[str, Any]] = []
    trash: list[dict[str, Any]] = []
    total_bytes = 0
    for row in _owned(user).order_by("-updated_at"):
        messages = list(row.chat_messages.all())
        nbytes = sum(len(message.content or "") for message in messages)
        total_bytes += nbytes
        updated = row.updated_at
        item = {
            "agent_id": row.agent_id or row.conversation_id,
            "filename": row.conversation_id,
            "updated_at": updated.isoformat() if updated is not None else "",
            "message_count": len(messages),
            "bytes": nbytes,
        }
        if row.trashed_at is not None or row.purged_at is not None:
            trash.append(item)
        else:
            active.append(item)
    age = get_max_age_days()
    return {
        "store_dir": str(store_dir(base_dir=base_dir)),
        "format": "db",
        "canonical": "django:ChatMessage",
        "active_count": len(active),
        "trash_count": len(trash),
        "bytes_used": total_bytes,
        "bytes_label": format_bytes(total_bytes),
        "active_bytes_label": format_bytes(sum(row["bytes"] for row in active)),
        "trash_bytes_label": format_bytes(sum(row["bytes"] for row in trash)),
        "max_age_days": age,
        "auto_archive_enabled": age > 0,
        "chats": active,
        "trash": trash,
        "env_dir": ENV_CHAT_DIR,
        "env_max_age": ENV_CHAT_MAX_AGE_DAYS,
    }


def _session_id_for(user, agent_id: str, conversation_id: str) -> str:
    """The ``chat_store`` stem that holds this conversation's transcript.

    Delegates to :func:`chat_store.session_stem_for_conversation`, which is
    also what ``cli_sessions.thread_session_id`` uses. The rule used to be
    written down twice, in two modules, and the two copies had already
    drifted: this one only predicted, that one also honoured a layout
    already on disk. A cache writer that predicted a *different* file than
    the one the transcript was in wrote one conversation's turns into
    another's rows (#1722), so there is now exactly one copy.
    """
    from swarm.core import chat_store

    if not agent_id or not conversation_id:
        return ""
    return chat_store.session_stem_for_conversation(
        chat_store.user_key_for(user), agent_id, conversation_id
    )


def _row_seq(row) -> int | None:
    extra = getattr(row, "extra", None)
    if not isinstance(extra, dict):
        return None
    seq = extra.get("seq")
    if isinstance(seq, int) and not isinstance(seq, bool):
        return seq
    return None


class ChatRepository:
    """Object wrapper around the module functions."""

    append_message = staticmethod(append_message)
    append_ui_event = staticmethod(append_ui_event)
    replace_thread = staticmethod(replace_thread)
    sync_transcript = staticmethod(sync_transcript)
    insert_turns = staticmethod(insert_turns)
    clear_thread = staticmethod(clear_thread)
    persist_from_cache_record = staticmethod(persist_from_cache_record)
    archive_agent = staticmethod(archive_agent)
    archive_all = staticmethod(archive_all)
    restore_agent = staticmethod(restore_agent)
    empty_trash = staticmethod(empty_trash)
    prune_expired = staticmethod(prune_expired)
    stats_for = staticmethod(stats_for)

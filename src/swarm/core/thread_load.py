"""Shared transcript load for HTTP ``GET /chat/thread/`` and WS reconnect.

Load order (Django is the source of truth — #1440):

1. Django ``ChatMessage`` / ``ChatConversation.ui_events`` for the
   conversation id (keeps ``ts`` / ``edited`` / ``seq`` in ``extra``).
2. Per-agent / session JSON on disk (``chat_store.load``) only when Django
   has no turns and no events.
3. One-way upgrade write: if Django was empty and JSON had turns, migrate
   those turns into Django. Load never writes JSON from Django (no loop).

``GET /chat/thread/`` and ``DjangoChatConsumer.fetch_conversation`` both use
this order so reload and reconnect return the same turns, including ``ts``
and ``edited``. In-memory WS cache and on-mode mint (REQ-171C-4) run
*before* this helper and are not a second source of truth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from swarm.core import chat_store
from swarm.core.chat_db import (
    load_db_thread,
    mirror_json_record_to_django,
)
from swarm.core.transcript_roles import carried_summary_from_row

logger = logging.getLogger(__name__)


@dataclass
class ThreadLoad:
    """Result of the shared Django-first / JSON-migrate load."""

    record: dict[str, Any] | None
    turns: list[dict[str, Any]]
    events: list[dict[str, Any]]
    db_id: str
    from_json: bool
    # #1319: newest-first paging — ``has_more`` is True when older turns were
    # sliced off, ``next_cursor`` is the ``before`` value that fetches them.
    has_more: bool = False
    next_cursor: str = ""


def _seq_of(row: Any, fallback: int) -> int:
    """Numeric ``seq`` on a stored row, or the list index when unstamped."""
    if isinstance(row, dict):
        value = row.get("seq")
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return fallback


def paginate_thread(
    turns: list[dict[str, Any]] | None,
    events: list[dict[str, Any]] | None,
    *,
    limit: int | None = None,
    before: str | int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool, str]:
    """Slice one contiguous newest-first page of turns + UI events (#1319).

    Newest-page-first hydration: the newest ``limit`` turns are returned,
    ``has_more`` flags older turns, and ``next_cursor`` is the exclusive
    ``before`` bound (oldest ``seq`` on the page) that fetches the next
    older page. UI events are windowed to the same ``seq`` range so a page
    reconstructs without gaps or duplicates; compacted spans that reference
    raw turn offsets therefore stay contiguous across page boundaries.

    With ``limit=None`` and ``before=None`` the full transcript is returned
    unchanged (backward compatible).
    """
    all_turns = list(turns or [])
    all_events = list(events or [])
    before_seq: int | None = None
    if before is not None:
        try:
            before_seq = int(before)
        except (TypeError, ValueError):
            before_seq = None
    page_limit: int | None = None
    if limit is not None:
        try:
            parsed = int(limit)
        except (TypeError, ValueError):
            parsed = 0
        page_limit = parsed if parsed > 0 else None

    if page_limit is None and before_seq is None:
        return all_turns, all_events, False, ""

    turn_seqs = [_seq_of(row, idx) for idx, row in enumerate(all_turns)]
    if before_seq is None:
        end = len(all_turns)
    else:
        end = 0
        for seq in turn_seqs:
            if seq < before_seq:
                end += 1
            else:
                break
    start = max(0, end - page_limit) if page_limit is not None else 0
    page_turns = all_turns[start:end]
    has_more = start > 0
    next_cursor = str(turn_seqs[start]) if has_more else ""

    # Events share the same seq space. Window by half-open [lo, hi): include
    # events at/after this page's oldest turn, below the exclusive cursor.
    # On the oldest page keep events that precede the very first turn too.
    lo: int | None = None if start == 0 else turn_seqs[start]
    hi = before_seq
    page_events: list[dict[str, Any]] = []
    for idx, event in enumerate(all_events):
        seq = _seq_of(event, idx)
        if hi is not None and seq >= hi:
            continue
        if lo is not None and seq < lo:
            continue
        page_events.append(event)
    return page_turns, page_events, has_more, next_cursor


def public_message(item: Any) -> dict[str, Any]:
    """Project one stored row for HTTP / WS (keep ``ts`` and ``edited``)."""
    if not isinstance(item, dict):
        return {"role": "user", "content": ""}
    row: dict[str, Any] = {
        "role": item.get("role", "user"),
        "content": item.get("content", ""),
    }
    ts = item.get("ts") or item.get("timestamp")
    if isinstance(ts, str) and ts:
        row["ts"] = ts
    if item.get("edited"):
        row["edited"] = True
    kind = item.get("kind")
    if isinstance(kind, str) and kind:
        row["kind"] = kind
    from_cid = item.get("from_conversation_id")
    if isinstance(from_cid, str) and from_cid:
        row["from_conversation_id"] = from_cid
    seq = item.get("seq")
    if isinstance(seq, int) and not isinstance(seq, bool):
        row["seq"] = seq
    if item.get("fatal_config_error") is True:
        row["fatal_config_error"] = True
    name = item.get("name")
    if isinstance(name, str) and name.strip():
        row["name"] = name.strip()
    target = item.get("config_target")
    if isinstance(target, dict):
        section = target.get("section")
        if isinstance(section, str) and section.strip():
            row["config_target"] = {"section": section.strip()}
    from swarm.core.message_reactions import public_reactions

    reactions = public_reactions(item.get("reactions"))
    if reactions:
        row["reactions"] = reactions
    # #1722: the HTTP / WS projection is the third whitelist on this key, and
    # it was the one the websocket send actually went through. Attachment ids
    # are opaque strings the client already owns; they are echoed back, never
    # resolved, so this is not an authorisation surface.
    attachments = item.get("attachments")
    if isinstance(attachments, list):
        ids = [str(aid).strip() for aid in attachments if isinstance(aid, (str, int))]
        ids = [aid for aid in ids if aid][:64]
        if ids:
            row["attachments"] = ids
    # Flag without a palette emoji reloads as an empty bubble.
    if item.get("reaction_only") is True and reactions:
        row["reaction_only"] = True
    # #1694: the carried summary reaches the browser through here. This is the
    # projection the HTTP thread endpoint and the websocket send both go
    # through, and it is the last fixed-key rebuild before the client — a
    # summary that survives to Django but not through here is still invisible
    # after a reload. Shares its normalizer with ``chat_store`` deliberately:
    # the two whitelists must agree on the shape or one silently drops it.
    if "carried_summary" in item:
        carried = carried_summary_from_row(item.get("carried_summary"))
        if carried is not None:
            row["carried_summary"] = carried
    return row


def public_messages(messages: Any) -> list[dict[str, Any]]:
    return [public_message(item) for item in messages or []]


def messages_from_db(user, conversation_id: str) -> list[dict[str, Any]]:
    """Django SoT rows. ``ts`` / ``edited`` / ``seq`` live in ``extra`` (#1440)."""
    loaded = load_db_thread(user, conversation_id)
    if loaded is None:
        return []
    turns, _events = loaded
    return turns


def load_thread(
    user,
    agent_id: str,
    *,
    requested_cid: str = "",
    session_id: str = "",
    default_cid: str = "",
    fresh_task: bool = False,
    backfill_json: bool = True,
    limit: int | None = None,
    before: str | int | None = None,
) -> ThreadLoad:
    """Load one agent thread: Django first, then one-way JSON migrate.

    ``fresh_task`` (on-mode) looks up DB rows only for ``requested_cid`` so
    a new task cannot inherit the reused default conversation.

    ``limit`` / ``before`` page the transcript newest-first (#1319). Django
    and the JSON cache always hold the *full* transcript; only the returned
    ``turns`` / ``events`` slice is bounded.

    ``backfill_json`` is accepted and ignored: #1440 forbids Django → JSON
    writes on load (no JSON↔SQL loop).
    """
    from swarm.core.transcript_roles import split_store

    user_key = chat_store.user_key_for(user)
    record = chat_store.load(
        user_key,
        agent_id,
        conversation_id=requested_cid,
        session_id=session_id,
    )
    db_id = requested_cid or (record or {}).get("conversation_id") or default_cid
    lookup_id = requested_cid if fresh_task else db_id

    from swarm.core.chat_repository import thread_is_trashed

    if thread_is_trashed(user, lookup_id):
        page_turns, page_events, has_more, next_cursor = paginate_thread(
            [], [], limit=limit, before=before
        )
        return ThreadLoad(
            record=None,
            turns=page_turns,
            events=page_events,
            db_id=db_id,
            from_json=False,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    loaded_db = load_db_thread(user, lookup_id)
    if loaded_db is not None and (loaded_db[0] or loaded_db[1]):
        turns, events = split_store(loaded_db[0], loaded_db[1], stamp_seq=False)
        page_turns, page_events, has_more, next_cursor = paginate_thread(
            turns, events, limit=limit, before=before
        )
        return ThreadLoad(
            record=record,
            turns=page_turns,
            events=page_events,
            db_id=db_id,
            from_json=False,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    if record is not None:
        turns, events = split_store(
            record.get("messages") or [],
            record.get("ui_events") or [],
        )
        if turns or events:
            try:
                mirror_json_record_to_django(
                    user_key,
                    agent_id,
                    {**record, "conversation_id": db_id or record.get("conversation_id") or ""},
                    user=user,
                )
            except Exception:
                logger.exception("Failed to migrate chat JSON into Django for %s/%s", user_key, agent_id)
        page_turns, page_events, has_more, next_cursor = paginate_thread(
            turns, events, limit=limit, before=before
        )
        return ThreadLoad(
            record=record,
            turns=page_turns,
            events=page_events,
            db_id=db_id,
            from_json=True,
            has_more=has_more,
            next_cursor=next_cursor,
        )

    page_turns, page_events, has_more, next_cursor = paginate_thread(
        [], [], limit=limit, before=before
    )
    return ThreadLoad(
        record=None,
        turns=page_turns,
        events=page_events,
        db_id=db_id,
        from_json=False,
        has_more=has_more,
        next_cursor=next_cursor,
    )

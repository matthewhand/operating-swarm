"""Shared transcript load for HTTP ``GET /chat/thread/`` and WS reconnect.

Load order (JSON is the source of truth):

1. Per-agent / session JSON on disk (``chat_store.load``).
2. Django ``ChatMessage`` rows for the conversation id, only when the JSON
   file is missing.
3. Optional upgrade write: if JSON was missing and DB had turns, mirror
   those turns onto disk (no session id).

``GET /chat/thread/`` and ``DjangoChatConsumer.fetch_conversation`` both use
this order so reload and reconnect return the same turns, including ``ts``
and ``edited`` whenever JSON has them. In-memory WS cache and on-mode mint
(REQ-171C-4) run *before* this helper and are not a second source of truth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from swarm.core import chat_store
from swarm.models import ChatConversation

logger = logging.getLogger(__name__)


@dataclass
class ThreadLoad:
    """Result of the shared JSON-first / DB-backfill load."""

    record: dict[str, Any] | None
    turns: list[dict[str, Any]]
    events: list[dict[str, Any]]
    db_id: str
    from_json: bool


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
    return row


def public_messages(messages: Any) -> list[dict[str, Any]]:
    return [public_message(item) for item in messages or []]


def messages_from_db(user, conversation_id: str) -> list[dict[str, Any]]:
    """Django mirror rows. ``ts`` comes from ``ChatMessage.timestamp``."""
    if not conversation_id:
        return []
    try:
        chat = ChatConversation.objects.get(
            conversation_id=conversation_id,
            student=user,
        )
    except ChatConversation.DoesNotExist:
        return []
    out: list[dict[str, Any]] = []
    for row in chat.chat_messages.all():
        item: dict[str, Any] = {"role": row.sender, "content": row.content}
        ts = row.timestamp.isoformat() if getattr(row, "timestamp", None) else ""
        if ts:
            item["ts"] = ts
        out.append(item)
    return out


def load_thread(
    user,
    agent_id: str,
    *,
    requested_cid: str = "",
    session_id: str = "",
    default_cid: str = "",
    fresh_task: bool = False,
    backfill_json: bool = True,
) -> ThreadLoad:
    """Load one agent thread: JSON first, then Django backfill.

    ``fresh_task`` (on-mode) looks up DB rows only for ``requested_cid`` so
    a new task cannot inherit the reused default conversation.
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
    if record is not None:
        turns, events = split_store(
            record.get("messages") or [],
            record.get("ui_events") or [],
        )
        return ThreadLoad(
            record=record,
            turns=turns,
            events=events,
            db_id=db_id,
            from_json=True,
        )

    lookup_id = requested_cid if fresh_task else db_id
    db_messages = messages_from_db(user, lookup_id)
    turns, events = split_store(db_messages, [])
    if backfill_json and turns and not session_id:
        try:
            chat_store.save(
                user_key,
                agent_id,
                turns,
                conversation_id=db_id,
                ui_events=events,
            )
        except OSError:
            logger.exception("Failed to backfill chat JSON for %s/%s", user_key, agent_id)
    return ThreadLoad(
        record=None,
        turns=turns,
        events=events,
        db_id=db_id,
        from_json=False,
    )

"""Conversation directory: list + handoff by conversation id (Issue #1681).

OpenRig can hand off between *known* teammate/room ids (``SendToAgent``). There
was no way to enumerate conversations or to post into an arbitrary id the user
names, so an operator could not relocate work without re-pasting context.

**This is a projection over the canonical store, not a second registry.**
Every function here reads and writes ``ChatConversation`` / ``ChatMessage``
through :mod:`swarm.core.chat_repository`. Nothing is kept in a process-global
list, a JSON file, or a side table, and no conversation is ever "created" by
listing. The ``agent_router`` blueprint keeps its own in-memory
``_conversations`` list for its own routing UI; that is a parallel model and it
is deliberately not reused here, because the issue is explicit that a second
chat registry must not be created.

Vocabulary, derived rather than stored:

``id``
    ``ChatConversation.conversation_id`` — the exact id the user types.
``type``
    ``"room"`` when the conversation's seat is a multi-member rig (a team
    roster), ``"dm"`` otherwise. Open Swarm has no separate room entity: a
    room *is* a team roster, and a conversation against a roster seat is a
    room conversation. Everything else is a direct thread with one seat.
``members``
    The seat ids that can see and post in the conversation. Always includes the
    conversation's own seat; for a room, the roster's members.

AuthZ is ownership, not role: a caller sees and may post only into
conversations they own (``ChatConversation.student``). An id that does not
exist and an id owned by somebody else are both reported as "not found", so the
API cannot be used to probe for the existence of another tenant's threads.
"""

from __future__ import annotations

import logging
from typing import Any

from swarm.core.chat_store import normalize_agent_id

logger = logging.getLogger(__name__)

TYPE_DM = "dm"
TYPE_ROOM = "room"

# Bounded so a long-lived install cannot make the directory endpoint an
# unbounded table scan. The SPA page is "recent conversations", not an export.
DEFAULT_LIMIT = 200
MAX_LIMIT = 500


class ConversationNotFound(LookupError):
    """The id is unknown, or belongs to another owner.

    One error for both cases on purpose: distinguishing them would turn this
    endpoint into a cross-tenant existence oracle. The string value is the
    offending id, so a caller can say *which* id was refused without the server
    disclosing whether somebody else owns it.
    """


def _roster_members() -> dict[str, list[str]]:
    """``{seat_id: [member seat ids]}`` for every team roster on this install.

    Best-effort: a missing or unreadable roster store degrades every
    conversation to a ``dm`` with its own seat, which is honest rather than
    wrong. It never fabricates membership.
    """
    try:
        from swarm.core.team_rosters import iter_normalized_rosters

        rosters = iter_normalized_rosters()
    except Exception:
        logger.debug("team rosters unavailable for the conversation directory", exc_info=True)
        return {}
    out: dict[str, list[str]] = {}
    for rid, roster in rosters.items():
        members: list[str] = []
        for member in roster.get("members") or []:
            mid = str(member.get("id") or "").strip()
            if mid and mid not in members:
                members.append(mid)
        if not members:
            continue
        out[rid] = members
        # A roster also names the blueprint that serves it; a conversation
        # against that seat is the same room.
        blueprint_id = str(roster.get("blueprint_id") or "").strip()
        if blueprint_id:
            out.setdefault(blueprint_id, members)
    return out


def conversation_summary(row, *, rooms: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """Public projection of one ``ChatConversation`` row.

    ``rooms`` is injectable so tests do not have to touch the roster store.
    ``message_count`` is taken from a ``message_count`` annotation when the
    caller supplied one, so a directory listing is two queries rather than one
    per row.
    """
    if rooms is None:
        rooms = _roster_members()
    agent = str(getattr(row, "agent_id", "") or "").strip()
    members = list(rooms.get(agent) or [])
    if agent and agent not in members:
        members.insert(0, agent)
    kind = TYPE_ROOM if len(members) > 1 else TYPE_DM
    annotated = getattr(row, "message_count", None)
    if annotated is None:
        annotated = row.chat_messages.count() if hasattr(row, "chat_messages") else 0
    return {
        "id": getattr(row, "conversation_id", "") or "",
        "conversation_id": getattr(row, "conversation_id", "") or "",
        "title": getattr(row, "title", "") or "",
        "snippet": getattr(row, "snippet", "") or "",
        "type": kind,
        "agent_id": agent,
        "members": members,
        "labels": list(getattr(row, "labels", None) or []),
        "message_count": int(annotated or 0),
    }


def list_conversations(
    user,
    *,
    agent_id: str = "",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Conversations the caller may see, newest activity first.

    Purged rows are excluded: they are ``empty_trash`` tombstones (#1721), not
    conversations. Soft-deleted threads are excluded too — a trashed thread is
    not something to hand work into.
    """
    from django.db.models import Count

    from swarm.core.chat_repository import _owned

    if user is None or not getattr(user, "is_authenticated", False):
        return []
    qs = _owned(user).filter(purged_at__isnull=True, trashed_at__isnull=True)
    if agent_id:
        qs = qs.filter(agent_id=normalize_agent_id(agent_id))
    qs = qs.annotate(message_count=Count("chat_messages")).order_by("-updated_at", "-created_at")
    # Slice last: Django refuses to reorder a query that has been sliced.
    bound = DEFAULT_LIMIT if limit is None else max(0, int(limit))
    if bound:
        qs = qs[: min(bound, MAX_LIMIT)]
    rooms = _roster_members()
    return [conversation_summary(row, rooms=rooms) for row in qs]


def resolve_conversation(user, conversation_id: str):
    """The caller's own conversation row, or :class:`ConversationNotFound`.

    Ownership is the whole check. There is no "admin sees everything" branch:
    an operator reaching another tenant's thread through this API would be the
    cross-tenant leak the issue forbids.
    """
    from swarm.core.chat_repository import _owned
    from swarm.core.chat_db import is_retired

    cid = str(conversation_id or "").strip()
    if not cid or user is None or not getattr(user, "is_authenticated", False):
        raise ConversationNotFound(cid or "")
    row = _owned(user).filter(conversation_id=cid).first()
    if row is None or is_retired(row):
        raise ConversationNotFound(cid)
    return row


def post_to_conversation(
    user,
    conversation_id: str,
    turn: dict[str, Any],
    *,
    from_conversation_id: str = "",
    kind: str = "",
) -> dict[str, Any]:
    """Append one turn to a named conversation and return the summary.

    The write is :func:`chat_repository.append_message` — one
    ``ChatMessage`` row, then the derived JSON cache. Nothing here re-derives
    the transcript from disk, which is the class of bug #1721 / #1722 were
    about, and nothing here can resurrect or truncate a thread.
    """
    from swarm.core.chat_repository import append_message

    row = resolve_conversation(user, conversation_id)
    item = dict(turn or {})
    item.setdefault("role", "user")
    if from_conversation_id:
        item.setdefault("from_conversation_id", str(from_conversation_id).strip())
    if kind:
        item.setdefault("kind", str(kind).strip()[:64])
    written = append_message(
        user,
        str(getattr(row, "agent_id", "") or ""),
        row.conversation_id,
        item,
    )
    if written is None:
        # Retired between the resolve and the write, or the thread went to
        # trash under us. Say so rather than reporting a success.
        raise ConversationNotFound(str(conversation_id))
    row.refresh_from_db()
    return conversation_summary(row)


def move_topic(
    user,
    conversation_id: str,
    summary: str,
    *,
    source_conversation_id: str = "",
) -> dict[str, Any]:
    """Park a workstream in a room with a short status summary.

    One attributed turn, exactly as a handoff is: "here is where this came from
    and here is the state". It is deliberately not a title change and not a
    transcript move — the source conversation keeps its history, and the target
    gains a pointer plus a summary, which is the only shape that stays honest
    about what actually happened.
    """
    text = str(summary or "").strip()
    if not text:
        raise ValueError("summary is required")
    row = resolve_conversation(user, conversation_id)
    source = str(source_conversation_id or "").strip()
    if source and source != row.conversation_id:
        # The source must be one the caller can see, or the summary becomes a
        # probe for ids they do not own.
        resolve_conversation(user, source)
    body = f"Moved from {source}:\n{text}" if source else text
    return post_to_conversation(
        user,
        row.conversation_id,
        {"role": "user", "content": body, "kind": "handoff"},
        from_conversation_id=source,
    )

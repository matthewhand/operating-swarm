"""Django helpers for canonical chat rows (#1440).

``ChatRepository`` is the write path. These helpers load and replace rows.
``chat_store`` JSON is a derived cache/export, not a second message store.
Attachment bytes stay on disk. Load never writes JSON from Django.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

_TURN_EXTRA_KEYS = (
    "ts",
    "edited",
    "seq",
    "kind",
    "from_conversation_id",
    "fatal_config_error",
    "name",
    "reactions",
    "reaction_only",
    "config_target",
    # #1722: ``attachments`` is a list of ChatAttachment ids carried on the
    # turn. It was missing from this allowlist *and* from
    # ``chat_store._normalize_messages``, so the websocket's
    # ``attachments=[aid]`` was dropped twice on the way to disk and the
    # message -> attachment link did not survive a restart. The bytes were
    # always safe on disk; only the link was lost.
    "attachments",
)


def is_retired(chat) -> bool:
    """True when this conversation must never be read or written again.

    Two states, one predicate, so no caller can honour one and forget the
    other:

    * ``trashed_at`` — soft delete; ``restore_agent`` can bring it back.
    * ``purged_at``  — hard delete (``empty_trash``, #1721). The id is
      retired forever. This has to be a durable row, not an absence: an
      absent row is exactly what the one-way JSON import reads as
      "never existed", which resurrected permanently deleted content.
    """
    if chat is None:
        return False
    return (
        getattr(chat, "trashed_at", None) is not None
        or getattr(chat, "purged_at", None) is not None
    )


def user_from_key(user_key: str):
    """Resolve ``u<pk>`` to a Django user. Unknown keys (webhook, tests) miss."""
    text = (user_key or "").strip()
    if len(text) < 2 or text[0] not in "uU" or not text[1:].isdigit():
        return None
    try:
        from django.contrib.auth import get_user_model

        return get_user_model().objects.filter(pk=int(text[1:])).first()
    except Exception:
        return None


def extra_from_turn(item: dict[str, Any] | None) -> dict[str, Any]:
    """Project persistable restore metadata off one turn."""
    if not isinstance(item, dict):
        return {}
    extra: dict[str, Any] = {}
    ts = item.get("ts") or item.get("timestamp")
    if isinstance(ts, str) and ts.strip():
        extra["ts"] = ts.strip()
    if item.get("edited") is True:
        extra["edited"] = True
    seq = item.get("seq")
    if isinstance(seq, int) and not isinstance(seq, bool):
        extra["seq"] = seq
    kind = item.get("kind")
    if isinstance(kind, str) and kind:
        extra["kind"] = kind
    from_cid = item.get("from_conversation_id")
    if isinstance(from_cid, str) and from_cid:
        extra["from_conversation_id"] = from_cid
    if item.get("fatal_config_error") is True:
        extra["fatal_config_error"] = True
    name = item.get("name")
    if isinstance(name, str) and name.strip():
        extra["name"] = name.strip()
    target = item.get("config_target")
    if isinstance(target, dict):
        section = target.get("section")
        if isinstance(section, str) and section.strip():
            extra["config_target"] = {"section": section.strip()}
    # #1411: Django wins on reload. Without these keys a reaction-only
    # turn comes back as an empty assistant bubble. The flag is written only
    # when a palette emoji survived, so an off-palette reaction cannot be
    # persisted as a reaction-only shell that reloads with no pill.
    from swarm.core.message_reactions import normalize_reactions

    reactions = normalize_reactions(item.get("reactions"))
    if reactions:
        extra["reactions"] = reactions
    if item.get("reaction_only") is True and reactions:
        extra["reaction_only"] = True
    # #1722: the WRITE-side allowlist. ``_TURN_EXTRA_KEYS`` above is the read
    # side and ``chat_store._normalize_messages`` is the cache side; a key has
    # to be carried by all three or it silently vanishes. ``attachments`` was
    # missing from all of them, so an uploaded file's link to its message did
    # not survive a restart (the bytes were never at risk — those stay on
    # disk). Ids are echoed back verbatim; nothing here resolves them, so this
    # is not an authorisation surface.
    attachments = item.get("attachments")
    if isinstance(attachments, list):
        ids = [str(aid).strip() for aid in attachments if isinstance(aid, (str, int))]
        ids = [aid for aid in ids if aid][:64]
        if ids:
            extra["attachments"] = ids
    return extra


def timestamp_for_turn(item: dict[str, Any] | None, *, fallback: datetime | None = None) -> datetime:
    """Prefer the stored ``ts`` so replace-all keeps chronological order."""
    if isinstance(item, dict):
        raw = item.get("ts") or item.get("timestamp")
        if isinstance(raw, str) and raw.strip():
            parsed = parse_datetime(raw.strip())
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
    return fallback or datetime.now(timezone.utc)


def turn_from_row(row) -> dict[str, Any]:
    """Rebuild one public/store turn from a ``ChatMessage`` row."""
    item: dict[str, Any] = {
        "role": getattr(row, "sender", None) or "user",
        "content": getattr(row, "content", None) or "",
    }
    extra = getattr(row, "extra", None)
    if isinstance(extra, dict):
        for key in _TURN_EXTRA_KEYS:
            if key not in extra:
                continue
            value = extra[key]
            if value in (None, "", False) and key != "seq":
                continue
            item[key] = value
    if "ts" not in item:
        ts = getattr(row, "timestamp", None)
        if ts is not None:
            try:
                item["ts"] = ts.isoformat()
            except Exception:
                pass
    from swarm.core.message_reactions import normalize_reactions

    reactions = normalize_reactions(item.get("reactions"))
    if reactions:
        item["reactions"] = reactions
    else:
        item.pop("reactions", None)
    if item.get("reaction_only") is True and not reactions:
        item.pop("reaction_only", None)
    return item


def load_db_thread(
    user,
    conversation_id: str,
    *,
    strict: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Load turns + ui_events from Django. ``None`` when the conversation is missing.

    ``strict`` re-raises database errors so a metadata save can refuse to
    publish an empty snapshot (#1440).
    """
    cid = (conversation_id or "").strip()
    if not cid or user is None:
        return None
    try:
        from swarm.models import ChatConversation

        chat = ChatConversation.objects.filter(conversation_id=cid).first()
    except Exception:
        if strict:
            raise
        logger.debug("chat_db load missed %s", cid, exc_info=True)
        return None
    if chat is None:
        return None
    owner_id = getattr(chat, "student_id", None)
    user_id = getattr(user, "pk", None)
    if owner_id is not None and user_id is not None and owner_id != user_id:
        return None
    if getattr(chat, "trashed_at", None) is not None or getattr(chat, "purged_at", None) is not None:
        return None
    turns = [turn_from_row(row) for row in chat.chat_messages.order_by("timestamp", "id")]
    if turns and all(_seq_value(item) is not None for item in turns):
        turns.sort(key=_seq_value)
    events = list(chat.ui_events or []) if isinstance(chat.ui_events, list) else []
    return turns, events


def conversation_is_trashed(user, conversation_id: str) -> bool:
    """True when the canonical row is in trash, or hard-deleted (#1721).

    Missing rows are not trashed — but a *purged* row is, and that is the
    whole point of the tombstone: the id exists precisely so this returns
    True and no write path treats the thread as new.
    """
    cid = (conversation_id or "").strip()
    if not cid or user is None:
        return False
    try:
        from swarm.models import ChatConversation

        chat = ChatConversation.objects.filter(conversation_id=cid).first()
    except Exception:
        logger.debug("chat_db trash check missed %s", cid, exc_info=True)
        return False
    if chat is None:
        return False
    owner_id = getattr(chat, "student_id", None)
    user_id = getattr(user, "pk", None)
    if owner_id is not None and user_id is not None and owner_id != user_id:
        return False
    return is_retired(chat)


def _seq_value(item: dict[str, Any]) -> int | None:
    seq = item.get("seq")
    if isinstance(seq, int) and not isinstance(seq, bool):
        return seq
    return None


def replace_db_thread(
    user,
    conversation_id: str,
    turns: list[dict[str, Any]] | None,
    *,
    agent_id: str = "",
    ui_events: list[dict[str, Any]] | None = None,
):
    """Idempotent Django replace of one thread (SoT write).

    Delete and insert run in one transaction so a failed insert cannot
    leave the thread empty. The conversation row is locked for the
    duration so two ``replace_db_thread`` callers cannot interleave
    delete and insert.

    ``get_or_create`` stays outside that block. A concurrent insert's
    ``IntegrityError`` aborts the surrounding PostgreSQL transaction,
    and Django cannot recover the row from inside it.
    """
    from django.db import transaction

    from swarm.core.agent_sessions import get_or_create_session
    from swarm.core.transcript_roles import is_ui_only_role
    from swarm.models import ChatConversation, ChatMessage

    cid = (conversation_id or "").strip()
    if not cid:
        raise ValueError("conversation_id is required")
    chat = get_or_create_session(user, cid, agent_id=agent_id)
    with transaction.atomic():
        chat = ChatConversation.objects.select_for_update().get(pk=chat.pk)
        if is_retired(chat):
            return chat
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
        ChatMessage.objects.filter(conversation=chat).delete()
        if rows:
            ChatMessage.objects.bulk_create(rows)
        if ui_events is not None:
            chat.ui_events = [event for event in ui_events if isinstance(event, dict)]
            chat.save(update_fields=["ui_events", "updated_at"])
    return chat


def mirror_json_record_to_django(
    user_key: str,
    agent_id: str,
    record: dict[str, Any] | None,
    *,
    user=None,
) -> bool:
    """One-way JSON record → Django, **into an empty thread only**.

    This is the import half of "Django is canonical, ``chat_store`` JSON is a
    derived cache". ``replace_db_thread`` is a full delete-and-reinsert, so
    calling it on a thread that already has canonical rows turns a cache file
    into a write-back source: whoever wrote the file last wins, and a stale,
    short, or foreign-process file silently destroys live content (#1722).

    The guard is the contract the docstring above already claimed, now
    enforced in one place instead of only at the ``thread_load`` call site:

    * a retired thread (trashed or purged, #1721) is never imported into;
    * a thread that already has any turn or UI event is never imported into.

    Both are checked under the row lock, in the same transaction as the
    replace, so a concurrent canonical write cannot slip between the check and
    the delete-and-reinsert.

    That makes the import genuinely one-way and idempotent: it can populate a
    thread the database has never seen, and it can do that any number of
    times, but it can never shrink or overwrite one. Best-effort; never
    raises to the JSON path.
    """
    if not isinstance(record, dict):
        return False
    owner = user if user is not None else user_from_key(user_key)
    if owner is None:
        return False
    cid = str(record.get("conversation_id") or "").strip()
    if not cid:
        try:
            from swarm.core.chat_store import conversation_id_for

            cid = conversation_id_for(owner, agent_id)
        except Exception:
            cid = ""
    if not cid:
        return False
    if conversation_is_trashed(owner, cid):
        logger.debug("chat_db import refused: %s is retired", cid)
        return False
    # The emptiness check and the replace run in ONE transaction, holding the
    # row lock across both. Checking first and replacing second would leave a
    # window in which a concurrent canonical write commits, and
    # ``replace_db_thread`` then deletes it — a TOCTOU race that only opens
    # under load, which is the hardest kind to reproduce and the worst kind to
    # ship. ``get_or_create`` stays outside the block (see
    # ``replace_db_thread``): a concurrent insert's ``IntegrityError`` aborts the
    # surrounding transaction and Django cannot recover from inside it.
    from django.db import transaction

    from swarm.core.agent_sessions import get_or_create_session
    from swarm.models import ChatConversation

    chat = get_or_create_session(owner, cid, agent_id=agent_id)
    try:
        with transaction.atomic():
            chat = ChatConversation.objects.select_for_update().get(pk=chat.pk)
            if is_retired(chat):
                logger.debug("chat_db import refused: %s retired under lock", cid)
                return False
            if chat.chat_messages.exists() or (
                isinstance(chat.ui_events, list) and chat.ui_events
            ):
                logger.debug(
                    "chat_db import refused: %s already has canonical rows (#1722)",
                    cid,
                )
                return False
            replace_db_thread(
                owner,
                cid,
                list(record.get("messages") or []),
                agent_id=agent_id or str(record.get("agent_id") or ""),
                ui_events=list(record.get("ui_events") or []),
            )
        return True
    except PermissionError:
        logger.info("chat_db mirror refused %s for %s", cid, user_key)
        return False
    except Exception:
        logger.debug("chat_db mirror failed %s/%s", user_key, agent_id, exc_info=True)
        return False


def django_transcript_record(
    user_key: str,
    agent_id: str,
    *,
    conversation_id: str = "",
    session_id: str = "",
) -> dict[str, Any] | None:
    """Django transcript shaped like a chat_store record, or None.

    Used when the JSON file is missing. File-only :func:`chat_store.load`
    stays the retention/archive signal — this helper is for mutators that
    would otherwise append onto an empty snapshot and replace the SoT.
    """
    owner = user_from_key(user_key)
    if owner is None:
        return None
    cid = (conversation_id or "").strip() or (session_id or "").strip()
    if not cid:
        try:
            from swarm.core.chat_store import conversation_id_for

            cid = conversation_id_for(owner, agent_id)
        except Exception:
            return None
    loaded = load_db_thread(owner, cid, strict=True)
    if not loaded or not (loaded[0] or loaded[1]):
        return None
    turns, events = loaded
    return {
        "agent_id": agent_id,
        "user_key": user_key,
        "conversation_id": cid,
        "session_id": (session_id or "").strip(),
        "messages": turns,
        "ui_events": events,
        "cli_sessions": {},
        "cli_hop": None,
        "active_cli": "",
    }

"""REQ-105: Django-backed chat sessions scoped to one agent.

Django ``ChatConversation`` is the source of truth for API (and for our
index/binding of CLI sessions). Provider browse/import stays in #468.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from django.utils.dateparse import parse_datetime

from swarm.core.chat_store import (
    conversation_id_for,
    list_sessions as list_disk_sessions,
    load as load_disk,
    normalize_agent_id,
    save as save_disk,
    user_key_for,
)
from swarm.core.cli_sessions import sanitize_cli_session_id
from swarm.models import ChatConversation, ChatMessage

logger = logging.getLogger("swarm.agent_sessions")

TITLE_MAX = 80
SNIPPET_MAX = 160
DEFAULT_TITLE = "Session 1"
NEW_TITLE = "New session"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _clip(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _iso(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if getattr(value, "tzinfo", None) is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_ms(value: str | None) -> int:
    text = (value or "").strip()
    if not text:
        return 0
    parsed = parse_datetime(text)
    if parsed is None:
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _user_or_none(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "pk", None) is None:
        return None
    return user


def _safe_labels(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        text = str(item).strip()[:64]
        if text and text not in out:
            out.append(text)
        if len(out) >= 8:
            break
    return out


def infer_agent_id(conversation_id: str) -> str:
    """Best-effort agent id from a deterministic conversation PK."""
    text = (conversation_id or "").strip()
    if text.startswith("agt-"):
        parts = text.split("-", 2)
        return normalize_agent_id(parts[2]) if len(parts) == 3 else ""
    if text.startswith("task-"):
        rest = text[5:]
        if rest and rest[0].isdigit():
            parts = rest.split("-", 1)
            if len(parts) == 2:
                return normalize_agent_id(parts[1].rsplit("-", 1)[0])
        return normalize_agent_id(rest.rsplit("-", 1)[0])
    if text.startswith("sess-"):
        rest = text[5:]
        if rest and rest[0].isdigit():
            parts = rest.split("-", 1)
            if len(parts) == 2:
                return normalize_agent_id(parts[1].rsplit("-", 1)[0])
        return normalize_agent_id(rest.rsplit("-", 1)[0])
    return ""


def title_and_snippet(messages: list[dict[str, Any]] | None) -> tuple[str, str]:
    """First user line → title; last user/assistant line → snippet."""
    title = ""
    snippet = ""
    for item in messages or []:
        role = str(item.get("role") or item.get("sender") or "")
        content = str(item.get("content") or item.get("text") or "")
        if role in {"status", "system", "info"}:
            continue
        if not content.strip():
            continue
        snippet = _clip(content, SNIPPET_MAX)
        if not title and role == "user":
            title = _clip(content, TITLE_MAX)
    return title, snippet


def _schedule_background_task(fn) -> None:
    """Run ``fn`` on a daemon thread — retitling must never block a chat turn."""
    threading.Thread(target=fn, daemon=True, name="swarm-session-retitle").start()


def _needs_generated_title(row: ChatConversation, messages: list[dict[str, Any]] | None = None) -> bool:
    """Only sessions still carrying a placeholder/raw title qualify.

    "Raw" includes the first-line truncation ``touch_session`` stamps — a
    session whose title is exactly the clipped opener has not been curated
    by anyone yet. Anything else (user rename, prior LLM pass) is respected.
    """
    title = (row.title or "").strip()
    if not title or title in {DEFAULT_TITLE, NEW_TITLE}:
        return True
    if messages:
        raw_title, _ = title_and_snippet(messages)
        if raw_title and title == raw_title:
            return True
    return False


def schedule_session_retitle(row: ChatConversation, messages: list[dict[str, Any]] | None = None) -> None:
    """#731: queue a background semantic retitle when the title is still raw.

    Called after a session receives its first turns; ``messages`` is the turn
    snapshot already in hand (avoids racing the transcript write). Curated
    titles (anything the user or an earlier pass set) are never touched.
    """
    try:
        if not _needs_generated_title(row, messages=messages):
            return
        conversation_id = row.conversation_id
        snapshot = list(messages or [])

        def _job() -> None:
            try:
                perform_session_retitle(conversation_id, messages=snapshot)
            except Exception:
                logger.exception("Background session retitle failed for %s", conversation_id)

        _schedule_background_task(_job)
    except Exception:
        logger.exception("Scheduling session retitle failed for %s", getattr(row, "conversation_id", "?"))


def perform_session_retitle(
    conversation_id: str,
    messages: list[dict[str, Any]] | None = None,
) -> None:
    """#731: generate title via the tiny/auxiliary override chain and persist.

    Resolution order (mirrors #858/#859): ``tiny`` task override, then
    ``auxiliary``, then the API default — ``generate_session_title`` already
    encapsulates the tiny chain with deterministic fallback under pytest.
    Writes back only if the title is still un-curated at completion time.
    """
    from swarm.core.llm_assist import generate_session_title

    row = ChatConversation.objects.filter(conversation_id=conversation_id).first()
    if row is None or not _needs_generated_title(row, messages=messages):
        return

    if messages is None:
        messages = [
            {"role": msg.sender, "content": msg.content}
            for msg in row.chat_messages.all()
            if msg.content
        ]
    else:
        messages = [
            {"role": str(m.get("role") or m.get("sender") or ""), "content": str(m.get("content") or m.get("text") or "")}
            for m in messages
        ]
    messages = [m for m in messages if m["content"].strip() and m["role"] not in {"status", "system", "info"}]
    if not messages:
        return

    title = generate_session_title(messages).strip()
    if not title:
        return
    # Clip to the same bound the truncation path uses so UIs stay consistent.
    title = title[:TITLE_MAX]

    # A curated title may land while the pass was in flight — re-check
    # (without the snapshot; a deliberate rename would differ from raw).
    fresh = ChatConversation.objects.filter(conversation_id=conversation_id).first()
    if fresh is None or not _needs_generated_title(fresh):
        return
    fresh.title = title
    fresh.save(update_fields=["title", "updated_at"])


def mint_user_session_id(user, agent_id: str) -> str:
    """Filesystem-safe conversation id for a user-created empty session."""
    agent = normalize_agent_id(agent_id)
    suffix = uuid.uuid4().hex[:12]
    pk = getattr(user, "pk", None)
    if pk is None:
        pk = getattr(user, "id", None)
    prefix = f"sess-{pk}-" if pk is not None else "sess-"
    return f"{prefix}{agent}-{suffix}"[:128]


def _messages_for_row(row: ChatConversation) -> list[dict[str, str]]:
    return [
        {"role": msg.sender, "content": msg.content}
        for msg in row.chat_messages.all()
    ]


def touch_session(
    row: ChatConversation,
    messages: list[dict[str, Any]] | None = None,
    *,
    agent_id: str = "",
    cli_session_id: str | None = None,
    labels: list[str] | None = None,
) -> ChatConversation:
    """Stamp title/snippet/agent and bump ``updated_at``."""
    fields: list[str] = ["updated_at"]
    if agent_id:
        agent = normalize_agent_id(agent_id)
        if row.agent_id != agent:
            row.agent_id = agent
            fields.append("agent_id")
    if messages is not None:
        title, snippet = title_and_snippet(messages)
        if title and (not row.title or row.title in {DEFAULT_TITLE, NEW_TITLE}):
            row.title = title
            fields.append("title")
        if snippet != row.snippet:
            row.snippet = snippet
            fields.append("snippet")
    if cli_session_id is not None:
        sid = sanitize_cli_session_id(cli_session_id) or ""
        if row.cli_session_id != sid:
            row.cli_session_id = sid
            fields.append("cli_session_id")
    if labels is not None:
        cleaned = _safe_labels(labels)
        if list(row.labels or []) != cleaned:
            row.labels = cleaned
            fields.append("labels")
    row.save(update_fields=fields)
    return row


def get_or_create_session(
    user,
    conversation_id: str,
    *,
    agent_id: str = "",
    title: str = "",
    student=None,
) -> ChatConversation:
    owner = student if student is not None else _user_or_none(user)
    agent = normalize_agent_id(agent_id) if agent_id else infer_agent_id(conversation_id)
    row, created = ChatConversation.objects.get_or_create(
        conversation_id=conversation_id,
        defaults={
            "student": owner,
            "agent_id": agent,
            "title": title or DEFAULT_TITLE,
        },
    )
    if created:
        return row
    if owner is not None and row.student_id is not None and row.student_id != owner.pk:
        raise PermissionError("conversation belongs to another user")
    changed: list[str] = []
    if owner is not None and row.student_id is None:
        row.student = owner
        changed.append("student")
    if agent and not row.agent_id:
        row.agent_id = agent
        changed.append("agent_id")
    if title and not row.title:
        row.title = title
        changed.append("title")
    if changed:
        row.save(update_fields=changed)
    return row


def ensure_default_session(user, agent_id: str) -> ChatConversation:
    """Today's single conversation becomes Session 1 (no extra rows)."""
    agent = normalize_agent_id(agent_id)
    owner = _user_or_none(user)
    fallback_cid = conversation_id_for(user, agent)
    record = None
    if owner is not None:
        try:
            record = load_disk(user_key_for(owner), agent)
        except Exception:
            record = None
    disk_cid = str((record or {}).get("conversation_id") or "").strip()
    cid = disk_cid or fallback_cid
    row = get_or_create_session(user, cid, agent_id=agent, title=DEFAULT_TITLE, student=owner)
    if row.title and row.snippet:
        return row
    messages: list[dict[str, Any]] = list((record or {}).get("messages") or [])
    cli = (record or {}).get("cli_sessions") or {}
    if isinstance(cli, dict) and cli:
        first = next(iter(cli.values()), "")
        if first and not row.cli_session_id:
            touch_session(row, cli_session_id=str(first), agent_id=agent)
    if not messages:
        messages = _messages_for_row(row)
    if messages:
        touch_session(row, messages, agent_id=agent)
    elif not row.title:
        row.title = DEFAULT_TITLE
        row.save(update_fields=["title"])
    return row


def create_empty_session(
    user,
    agent_id: str,
    *,
    title: str = NEW_TITLE,
    labels: list[str] | None = None,
    conversation_id: str | None = None,
) -> ChatConversation:
    """Mint an empty Django session and select-ready conversation id."""
    agent = normalize_agent_id(agent_id)
    owner = _user_or_none(user)
    cid = (conversation_id or "").strip() or mint_user_session_id(user, agent)
    row = get_or_create_session(user, cid, agent_id=agent, title=title or NEW_TITLE, student=owner)
    if labels:
        touch_session(row, labels=labels, agent_id=agent)
    if owner is not None:
        try:
            save_disk(
                user_key_for(owner),
                agent,
                [],
                conversation_id=cid,
                session_id=cid,
            )
        except OSError:
            pass
    return row


def import_disk_sessions(user, agent_id: str) -> list[ChatConversation]:
    """Promote scale-out / disk threads into Django rows (same picker)."""
    owner = _user_or_none(user)
    if owner is None:
        return []
    agent = normalize_agent_id(agent_id)
    imported: list[ChatConversation] = []
    try:
        disk_rows = list_disk_sessions(user_key_for(owner), agent)
    except Exception:
        return imported
    for item in disk_rows:
        cid = str(item.get("conversation_id") or item.get("session_id") or "").strip()
        if not cid:
            continue
        row = get_or_create_session(user, cid, agent_id=agent, student=owner)
        record = load_disk(
            user_key_for(owner),
            agent,
            conversation_id=cid,
            session_id=str(item.get("session_id") or ""),
        )
        messages = list((record or {}).get("messages") or [])
        cli = (record or {}).get("cli_sessions") or {}
        bound = ""
        if isinstance(cli, dict) and cli:
            bound = str(next(iter(cli.values()), "") or "")
        touch_session(row, messages or None, agent_id=agent, cli_session_id=bound or None)
        imported.append(row)
    return imported


def list_agent_sessions(user, agent_id: str, *, include_default: bool = True) -> list[ChatConversation]:
    """This agent's Django sessions, newest activity first."""
    agent = normalize_agent_id(agent_id)
    owner = _user_or_none(user)
    if include_default:
        ensure_default_session(user, agent)
        import_disk_sessions(user, agent)
    qs = ChatConversation.objects.filter(agent_id=agent)
    if owner is not None:
        qs = qs.filter(student=owner)
    else:
        qs = qs.filter(student__isnull=True)
    return list(qs.order_by("-updated_at", "-created_at"))


def session_to_dict(row: ChatConversation, *, active_ids: list[str] | None = None) -> dict[str, Any]:
    running = bool(active_ids) and row.conversation_id in set(active_ids or [])
    return {
        "id": row.conversation_id,
        "conversation_id": row.conversation_id,
        "agent_id": row.agent_id,
        "title": row.title or DEFAULT_TITLE,
        "snippet": row.snippet or "",
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at or row.created_at),
        "labels": _safe_labels(row.labels),
        "cli_session_id": row.cli_session_id or None,
        "status": "running" if running else "finished",
        "started_at": _iso(row.created_at),
        "updated_at_ms": _parse_iso_ms(_iso(row.updated_at or row.created_at)),
        "started_at_ms": _parse_iso_ms(_iso(row.created_at)),
        "empty": not bool(row.snippet),
    }


def persist_allocated_session(
    user,
    agent_id: str,
    conversation_id: str,
    *,
    empty: bool = False,
    title: str = "",
) -> ChatConversation:
    """Ensure a scale-out / allocate POST has a Django row in the picker."""
    agent = normalize_agent_id(agent_id)
    owner = _user_or_none(user)
    row = get_or_create_session(
        user,
        conversation_id,
        agent_id=agent,
        title=title or (NEW_TITLE if empty else DEFAULT_TITLE),
        student=owner,
    )
    if empty and not row.snippet and row.title == DEFAULT_TITLE:
        row.title = title or NEW_TITLE
        row.save(update_fields=["title"])
    return row

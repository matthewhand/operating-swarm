"""File-backed persistence for per-agent SPA chat threads.

Each logged-in user gets one JSON file per agent (blueprint id, or
``_default`` when the server-default model is selected). Retention lives
on the Settings page only: archive moves a file to ``trash/``; auto-age
does the same after ``SWARM_CHAT_MAX_AGE_DAYS`` (default 90). Trash is
never hard-deleted automatically.

Layout (under :func:`store_dir`)::

    active/<user_key>/<agent_id>.json
    trash/<user_key>/<agent_id>__<UTC stamp>.json

This JSON file is a derived cache/export. Django
``ChatConversation`` / ``ChatMessage`` is canonical (#1440), written
through ``ChatRepository`` (one ``ChatMessage`` per new message).
Attachment bytes stay on disk.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swarm.core.paths import get_user_data_dir_for_swarm

logger = logging.getLogger(__name__)

SCHEMA = 2
DEFAULT_AGENT_ID = "_default"
ENV_CHAT_DIR = "SWARM_CHAT_DIR"
ENV_CHAT_MAX_AGE_DAYS = "SWARM_CHAT_MAX_AGE_DAYS"
DEFAULT_MAX_AGE_DAYS = 90

# #1318: webhook / routine sessions are written under an installation-global
# key. The operator chat reads under ``u<pk>``; these helpers surface the
# webhook turns there — a live mirror on write, plus a read-only fallback for
# sessions recorded before the mirror existed.
GITHUB_WEBHOOK_USER_KEY = "github-webhook"
_WEBHOOK_CID_PREFIXES = ("conv-github-",)
# Filled by a sync lookup. Routine replies persist inside ``asyncio.run``,
# where the Django ORM raises SynchronousOnlyOperation; the mirror reuses
# this instead of querying again.
_cached_operator_key: str = ""

# User keys and agent ids must stay inside the store dir.
_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_TRASH_STAMP_RE = re.compile(r"^(.+)__(\d{8}T\d{6}Z)$")


def store_dir(*, base_dir: Path | None = None) -> Path:
    """Root of the chat JSON store.

    ``SWARM_CHAT_DIR`` wins; otherwise ``<SWARM_USER_DATA_DIR or the user data dir>/chats``.
    """
    if base_dir is not None:
        return Path(base_dir)
    env = (os.environ.get(ENV_CHAT_DIR) or "").strip()
    if env:
        return Path(env)
    return get_user_data_dir_for_swarm() / "chats"


def user_key_for(user) -> str:
    """Stable filesystem-safe key for a Django user (pk, not username)."""
    pk = getattr(user, "pk", None)
    if pk is None:
        pk = getattr(user, "id", None)
    return f"u{int(pk)}"


def normalize_agent_id(raw: str | None) -> str:
    """Map a blueprint id (or empty/default) to a safe agent file stem."""
    text = (raw or "").strip()
    if not text:
        return DEFAULT_AGENT_ID
    if _ID_RE.match(text):
        return text
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")[:128]
    return slug if slug and _ID_RE.match(slug) else DEFAULT_AGENT_ID


def conversation_id_for(user, agent_id: str) -> str:
    """Deterministic websocket / Django PK for ``(user, agent)``."""
    pk = getattr(user, "pk", None)
    if pk is None:
        pk = getattr(user, "id", None)
    return f"agt-{pk}-{normalize_agent_id(agent_id)}"


def default_conversation_id_for_key(user_key: str, agent_id: str) -> str:
    """``conversation_id_for`` for a filesystem owner key instead of a user.

    The owner key is ``u<pk>``, so the owner's *default* thread id is derivable
    from the same pair. A key that is not a user key (webhook, ``_api``) has
    no default thread, so every conversation there counts as its own and this
    returns "".
    """
    text = str(user_key or "").strip()
    if len(text) < 2 or text[0] not in "uU" or not text[1:].isdigit():
        return ""
    return f"agt-{int(text[1:])}-{normalize_agent_id(agent_id)}"


def session_stem_for_conversation(
    user_key: str,
    agent_id: str,
    conversation_id: str = "",
    *,
    base_dir: Path | None = None,
) -> str:
    """The one rule for "which file holds this conversation's transcript".

    ``chat_store`` files a conversation that is not the owner's default one
    (and *any* conversation while the agent is in new-chat-per-task mode) under
    ``<agent>__<conversation_id>.json``; the default conversation lives in
    ``<agent>.json``. A CLI session id, a hop stamp, a composer turn, and a
    retention sweep all have to name the same file, or one conversation's
    turns land in another's rows (#1690, #1722).

    A record that already carries this conversation id wins, so a layout that
    is already on disk is never second-guessed. Only then is the layout
    predicted, which is what a first turn of a conversation has to do.

    This is the single source of that rule. It used to be written down twice —
    here-adjacent in ``chat_repository._session_id_for`` and in
    ``cli_sessions.thread_session_id`` — and the copies had drifted, which is
    how a metadata write ended up reading the agent's default file and saving
    it under the caller's conversation id.
    """
    cid = str(conversation_id or "").strip()
    if not cid:
        return ""
    try:
        for row in list_sessions(user_key, agent_id, base_dir=base_dir):
            if str(row.get("conversation_id") or "") == cid:
                return str(row.get("session_id") or "")
    except Exception:
        logger.debug("chat_store stem lookup missed for %s/%s", user_key, agent_id, exc_info=True)
    try:
        from swarm.core.agent_settings import is_new_chat_per_task

        on_mode = bool(is_new_chat_per_task(agent_id))
    except Exception:
        on_mode = False
    if on_mode or cid != default_conversation_id_for_key(user_key, agent_id):
        return cid
    return ""


def get_max_age_days(*, override: int | None = None) -> int:
    """Days of inactivity before an active thread is moved to trash.

    ``0`` disables auto-archive. Unset / invalid env → ``DEFAULT_MAX_AGE_DAYS`` (90).
    """
    if override is not None:
        return max(0, int(override))
    raw = (os.environ.get(ENV_CHAT_MAX_AGE_DAYS) or "").strip()
    if not raw:
        return DEFAULT_MAX_AGE_DAYS
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_MAX_AGE_DAYS


def format_bytes(n: int) -> str:
    """Human-readable byte count for the Settings page."""
    value = float(max(0, int(n)))
    for unit, step in (("B", 1024.0), ("KB", 1024.0), ("MB", 1024.0), ("GB", 1024.0)):
        if value < step or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= step
    return f"{int(n)} B"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None = None) -> str:
    stamp = dt or _utc_now()
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _safe_id(value: str | None) -> str | None:
    text = (value or "").strip()
    return text if _ID_RE.match(text) else None


def _session_stem(agent_id: str, session_id: str = "") -> str | None:
    """Filesystem stem for one thread.

    Reuse mode (no session_id) stays ``<agent>.json``. Concurrent on-mode
    tasks (REQ-65) write ``<agent>__<session>.json`` so two running chats
    do not clobber each other.
    """
    agent = _safe_id(normalize_agent_id(agent_id))
    if agent is None:
        return None
    sid = _safe_id((session_id or "").strip())
    if not sid:
        return agent
    combined = f"{agent}__{sid}"
    if _ID_RE.match(combined):
        return combined
    trimmed = combined[:128]
    return trimmed if _ID_RE.match(trimmed) else None


def _active_path(
    user_key: str,
    agent_id: str,
    base: Path,
    *,
    session_id: str = "",
) -> Path | None:
    uk = _safe_id(user_key)
    stem = _session_stem(agent_id, session_id)
    if uk is None or stem is None:
        return None
    return base / "active" / uk / f"{stem}.json"


def _trash_dir(user_key: str, base: Path) -> Path | None:
    uk = _safe_id(user_key)
    if uk is None:
        return None
    return base / "trash" / uk


def _atomic_write(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, default=str)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _normalize_messages(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("sender") or "user"
        content = item.get("content")
        if content is None:
            content = item.get("text") or ""
        if not isinstance(content, str):
            content = str(content)
        role_raw = str(role)
        if role_raw == "assistant":
            role_s = "assistant"
        elif role_raw in ("status", "info"):
            role_s = role_raw
        elif role_raw in ("system", "tool"):
            role_s = role_raw
        else:
            role_s = "user"
        msg: dict[str, Any] = {"role": role_s, "content": content}
        ts = item.get("ts") or item.get("timestamp") or item.get("created_at")
        if isinstance(ts, str) and ts:
            msg["ts"] = ts
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            msg["name"] = name.strip()
        if item.get("edited") is True or item.get("edited") == "true":
            msg["edited"] = True
        kind = item.get("kind")
        if isinstance(kind, str) and kind.strip():
            msg["kind"] = kind.strip()[:64]
        from_cid = item.get("from_conversation_id")
        if isinstance(from_cid, str) and from_cid.strip():
            msg["from_conversation_id"] = from_cid.strip()[:128]
        seq = item.get("seq")
        if isinstance(seq, int) and not isinstance(seq, bool):
            msg["seq"] = seq
        if item.get("fatal_config_error") is True:
            msg["fatal_config_error"] = True
            # #499: the classified Settings section survives rehydrate so the
            # recovery banner can deep-link to the fix, not just reshuffle.
            target = item.get("config_target")
            if isinstance(target, dict) and isinstance(target.get("section"), str):
                msg["config_target"] = {"section": target["section"]}
        # #1722: ``attachments`` is a list of ChatAttachment ids carried on the
        # turn. This function is a whitelist *rebuild* — anything not copied
        # here does not exist in the file — so the websocket's
        # ``attachments=[aid]`` was dropped on its way to disk here, and again
        # by ``chat_db._TURN_EXTRA_KEYS`` on its way into Django. Bytes stayed
        # on disk the whole time; only the message -> attachment link was
        # lost, so an uploaded file stopped appearing on its message after a
        # restart.
        attachments = item.get("attachments")
        if isinstance(attachments, list):
            ids = [str(aid).strip() for aid in attachments if isinstance(aid, (str, int))]
            ids = [aid for aid in ids if aid][:64]
            if ids:
                msg["attachments"] = ids
        from swarm.core.message_reactions import normalize_reactions

        reactions = normalize_reactions(item.get("reactions"))
        if reactions:
            msg["reactions"] = reactions
        # An invalid emoji must not leave a reaction-only shell with no pill.
        if item.get("reaction_only") is True and reactions:
            msg["reaction_only"] = True
        # #1694: the body of a session hop's carried summary. Reached only on
        # the ``context_carried`` ui event — a summary is a boundary marker, not
        # a turn. Redacted again here, not just in ``build_injection_payload``:
        # this is a second durable copy, so an unredacted blob reaching it must
        # not become a secret at rest.
        if "carried_summary" in item:
            from swarm.core.cli_session_hop import redact_injection_text
            from swarm.core.transcript_roles import carried_summary_from_row

            raw_carried = item.get("carried_summary")
            if isinstance(raw_carried, dict) and isinstance(raw_carried.get("text"), str):
                raw_carried = {**raw_carried, "text": redact_injection_text(raw_carried["text"])}
            carried = carried_summary_from_row(raw_carried)
            if carried is not None:
                msg["carried_summary"] = carried
        out.append(msg)
    return out


def _normalize_events(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = _normalize_messages([item])
        if not row:
            continue
        event = row[0]
        if "kind" not in event:
            content = str(event.get("content") or "")
            role = str(event.get("role") or "status")
            if content.startswith("Messaged ") or content.startswith("Message from "):
                event["kind"] = "hop"
            elif role in ("status", "info"):
                event["kind"] = role
            else:
                event["kind"] = "status"
        if event.get("role") not in ("status", "info"):
            event["role"] = "status"
        out.append(event)
    return out


def _split_record(messages: Any, ui_events: Any = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from swarm.core.transcript_roles import split_store

    return split_store(
        _normalize_messages(messages),
        _normalize_events(ui_events),
        stamp_seq=True,
    )


def empty_record(
    *,
    user_key: str,
    agent_id: str,
    conversation_id: str = "",
) -> dict[str, Any]:
    now = _iso()
    return {
        "schema": SCHEMA,
        "agent_id": normalize_agent_id(agent_id),
        "user_key": user_key,
        "conversation_id": conversation_id,
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "ui_events": [],
        "cli_sessions": {},
        "cli_hop": None,
        "active_cli": "",
    }


def save(
    user_key: str,
    agent_id: str,
    messages: list[dict[str, Any]] | None = None,
    *,
    conversation_id: str = "",
    session_id: str = "",
    cli_sessions: dict[str, Any] | None = None,
    ui_events: list[dict[str, Any]] | None = None,
    cli_hop: Any = ...,
    active_cli: str | None = None,
    base_dir: Path | None = None,
    mirror_db: bool = True,
) -> Path | None:
    """Write (or replace) the active thread. Returns the path, or None if ids are unsafe.

    ``messages`` is the model-turn list. Status/info/hop chrome is stored in
    ``ui_events``. Mixed schema-1 lists are split on write.
    ``cli_hop`` / ``active_cli`` default to preserving the existing record
    (``cli_hop=None`` clears a pending quota hop).
    """
    agent = normalize_agent_id(agent_id)
    uk = _safe_id(user_key)
    if uk is None:
        return None
    base = store_dir(base_dir=base_dir)
    path = _active_path(uk, agent, base, session_id=session_id)
    if path is None:
        return None
    existing = _read_json(path) if path.is_file() else None
    # messages=None means "keep the current transcript". A missing file must
    # not become an empty snapshot that write-through then deletes the
    # Django SoT (#1440).
    if existing is None and messages is None:
        try:
            from swarm.core.chat_db import django_transcript_record

            hydrated = django_transcript_record(
                uk,
                agent,
                conversation_id=conversation_id,
                session_id=session_id,
            )
        except Exception:
            # A failed read is not an empty thread. Publishing that snapshot
            # would write-through and delete the Django SoT (#1440).
            logger.debug(
                "chat_store refused metadata save; Django hydrate failed for %s/%s",
                uk,
                agent,
                exc_info=True,
            )
            return None
        if hydrated:
            existing = hydrated
    created = (existing or {}).get("created_at") or _iso()
    sessions = (
        normalize_cli_sessions(cli_sessions)
        if cli_sessions is not None
        else normalize_cli_sessions((existing or {}).get("cli_sessions"))
    )
    if cli_hop is ...:
        hop = (existing or {}).get("cli_hop")
    else:
        hop = cli_hop
    try:
        from swarm.core.cli_session_hop import normalize_cli_hop

        hop = normalize_cli_hop(hop)
    except Exception:
        hop = hop if isinstance(hop, dict) else None
    if active_cli is None:
        previous_cli = str((existing or {}).get("active_cli") or "")
    else:
        previous_cli = str(active_cli or "")
    previous_cli = normalize_agent_id(previous_cli) if previous_cli else ""
    if messages is not None:
        if ui_events is not None:
            incoming_events = ui_events
        else:
            from swarm.core.transcript_roles import is_chrome_message

            if any(is_chrome_message(item) for item in messages):
                incoming_events = []
            else:
                incoming_events = (existing or {}).get("ui_events") or []
        turns, events = _split_record(messages, incoming_events)
    else:
        prior_turns, prior_events = _split_record(
            (existing or {}).get("messages"),
            (existing or {}).get("ui_events"),
        )
        if ui_events is not None:
            turns, events = prior_turns, _normalize_events(ui_events)
            _, events = _split_record(turns, events)
        else:
            turns, events = prior_turns, prior_events
    record = {
        "schema": SCHEMA,
        "agent_id": agent,
        "user_key": uk,
        "conversation_id": conversation_id or (existing or {}).get("conversation_id") or "",
        "session_id": session_id or (existing or {}).get("session_id") or "",
        "created_at": created,
        "updated_at": _iso(),
        "messages": turns,
        "ui_events": events,
        "cli_sessions": sessions,
        "cli_hop": hop,
        "active_cli": previous_cli,
    }
    # #1440: Django is written first, one row per new message. The file
    # below is the cache. Compact passes mirror_db=False so existing
    # ChatMessage primary keys are left to the compactor.
    if mirror_db and messages is not None:
        try:
            from swarm.core.chat_repository import persist_from_cache_record

            if persist_from_cache_record(uk, agent, record, base_dir=base_dir):
                if uk == GITHUB_WEBHOOK_USER_KEY:
                    _mirror_webhook_session(agent, record, base_dir=base_dir)
                return path
        except Exception:
            logger.debug(
                "chat repository persist skipped for %s/%s", uk, agent, exc_info=True
            )
    _atomic_write(path, record)
    if uk == GITHUB_WEBHOOK_USER_KEY:
        _mirror_webhook_session(agent, record, base_dir=base_dir)
    # Fallback when persist_from_cache_record could not own the write
    # (webhook key, missing user). Compact/exports pass mirror_db=False.
    #
    # ``messages is not None`` is load-bearing, and it is the whole fix for
    # the metadata-write-back variant of #1722. ``messages=None`` means "keep
    # whatever the file already holds" — a metadata-only write (mark the
    # active CLI, stamp a hop, store a CLI session id). There is no new
    # transcript in it, and the file it just wrote is derived from the
    # canonical rows, so mirroring it back is a pure round trip through
    # ``replace_db_thread``'s delete-and-reinsert. That turned every
    # ``_mark_active_cli`` into "rebuild the canonical rows from the JSON
    # file", and a stale file (a failed write, a second worker, a file
    # written moments before a concurrent append) silently truncated live
    # content: DB ``['q1','a1','q2']`` → ``['q1','a1']``.
    if mirror_db and messages is not None:
        _mirror_record_to_django(uk, agent, record)
    return path


def _load_record(
    user_key: str,
    agent_id: str,
    *,
    conversation_id: str = "",
    session_id: str = "",
    base_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Read the active thread record for one owner key (no webhook fallback).

    ``session_id`` selects a concurrent on-mode file (REQ-65). ``conversation_id``
    without a session id scans that agent's files for a matching id.
    """
    agent = normalize_agent_id(agent_id)
    base = store_dir(base_dir=base_dir)
    if session_id:
        path = _active_path(user_key, agent, base, session_id=session_id)
        if path is None or not path.is_file():
            return None
        record = _read_json(path)
        if record is None:
            return None
        turns, events = _split_record(record.get("messages"), record.get("ui_events"))
        record["schema"] = SCHEMA
        record["messages"] = turns
        record["ui_events"] = events
        record["cli_sessions"] = normalize_cli_sessions(record.get("cli_sessions"))
        record["cli_hop"] = record.get("cli_hop")
        record["active_cli"] = str(record.get("active_cli") or "")
        return record
    wanted = (conversation_id or "").strip()
    if wanted:
        for row in list_sessions(user_key, agent, base_dir=base_dir):
            if row.get("conversation_id") != wanted:
                continue
            sid = row.get("session_id") or ""
            if sid:
                found = _load_record(user_key, agent, session_id=sid, base_dir=base_dir)
                if found is not None:
                    return found
            path = _active_path(user_key, agent, base)
            if path is None or not path.is_file():
                return None
            record = _read_json(path)
            if record is None:
                return None
            if (record.get("conversation_id") or "") != wanted:
                return None
            record["messages"] = _normalize_messages(record.get("messages"))
            record["cli_sessions"] = normalize_cli_sessions(record.get("cli_sessions"))
            record["cli_hop"] = record.get("cli_hop")
            record["active_cli"] = str(record.get("active_cli") or "")
            return record
        return None
    path = _active_path(user_key, agent, base)
    if path is None or not path.is_file():
        return None
    record = _read_json(path)
    if record is None:
        return None
    turns, events = _split_record(record.get("messages"), record.get("ui_events"))
    record["schema"] = SCHEMA
    record["messages"] = turns
    record["ui_events"] = events
    record["cli_sessions"] = normalize_cli_sessions(record.get("cli_sessions"))
    record["cli_hop"] = record.get("cli_hop")
    record["active_cli"] = str(record.get("active_cli") or "")
    return record


def _mirror_webhook_session(
    agent_id: str,
    record: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> None:
    """Duplicate a webhook session under the operator key (#1318). Never raises.

    The routines dispatcher still writes under ``github-webhook``; mirroring
    the same record under the operator's ``u<pk>`` store makes the fired
    routine visible in the operator's bot chat without changing the webhook
    write path. Skipped when no operator is resolvable.
    """
    conversation_id = str(record.get("conversation_id") or "").strip()
    session_id = str(record.get("session_id") or "").strip()
    if not is_webhook_conversation(conversation_id, session_id):
        return
    operator_key = primary_operator_user_key()
    if not operator_key or operator_key == GITHUB_WEBHOOK_USER_KEY:
        return
    try:
        save(
            operator_key,
            agent_id,
            [dict(item) for item in record.get("messages") or []],
            conversation_id=conversation_id,
            session_id=session_id,
            cli_sessions=record.get("cli_sessions"),
            ui_events=[dict(item) for item in record.get("ui_events") or []],
            cli_hop=record.get("cli_hop"),
            active_cli=str(record.get("active_cli") or ""),
            base_dir=base_dir,
        )
    except Exception:
        logger.exception(
            "Could not mirror webhook session %s to operator store", conversation_id
        )


def is_webhook_conversation(conversation_id: str | None, session_id: str | None = None) -> bool:
    """True when an id belongs to the GitHub webhook / routine session family."""
    for raw in (conversation_id, session_id):
        text = (raw or "").strip()
        if text.startswith(_WEBHOOK_CID_PREFIXES):
            return True
    return False


def _in_running_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _mirror_record_to_django(
    user_key: str, agent_id: str, record: dict[str, Any]
) -> None:
    """Write one JSON record through to Django. Never raises.

    A routine reply calls ``save`` on the event-loop thread. The ORM raises
    ``SynchronousOnlyOperation`` there, and swallowing that left Django on
    the spawn prompt while the JSON cache held the reply. Chat hydration
    reads Django (#1440), so the write runs on a worker thread.

    Skip the hop when this thread already holds an atomic block. The worker
    would wait on that same database lock.
    """

    def _run() -> None:
        from django.db import close_old_connections

        close_old_connections()
        try:
            from swarm.core.chat_db import mirror_json_record_to_django

            mirror_json_record_to_django(user_key, agent_id, record)
        finally:
            close_old_connections()

    try:
        if _in_running_loop():
            from django.db import connection

            if connection.in_atomic_block:
                logger.debug(
                    "chat_store Django write-through skipped for %s/%s inside an atomic block",
                    user_key,
                    agent_id,
                )
                return
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(_run).result()
            return
        from swarm.core.chat_db import mirror_json_record_to_django

        mirror_json_record_to_django(user_key, agent_id, record)
    except Exception:
        logger.debug(
            "chat_store Django write-through skipped for %s/%s",
            user_key,
            agent_id,
            exc_info=True,
        )


def reset_operator_key_cache() -> None:
    """Drop the cached operator key (tests)."""
    global _cached_operator_key
    _cached_operator_key = ""


def primary_operator_user_key() -> str:
    """Chat-store key (``u<pk>``) of the primary installation operator.

    Mirrors :func:`swarm.core.user_preferences.primary_operator_principal` but
    in the filesystem key namespace. Empty when no superuser is resolvable
    (headless / no-DB) or the DB is unavailable.

    Inside a running event loop the last sync lookup is reused. Querying
    there raises ``SynchronousOnlyOperation`` and used to skip the mirror,
    so a routine reply stayed on the webhook key while the operator file
    kept the older prompt.
    """
    global _cached_operator_key
    if _in_running_loop():
        return _cached_operator_key
    try:
        from django.contrib.auth import get_user_model

        operator = (
            get_user_model()
            .objects.filter(is_superuser=True, is_active=True)
            .order_by("pk")
            .first()
        )
    except Exception:
        logger.debug("Primary operator lookup failed", exc_info=True)
        return _cached_operator_key
    key = user_key_for(operator) if operator is not None else ""
    _cached_operator_key = key
    return key


def _record_freshness(record: dict[str, Any] | None) -> tuple[str, int]:
    """Sort key: later ``updated_at``, then longer transcript."""
    if not isinstance(record, dict):
        return ("", -1)
    messages = record.get("messages") if isinstance(record.get("messages"), list) else []
    events = record.get("ui_events") if isinstance(record.get("ui_events"), list) else []
    return (str(record.get("updated_at") or ""), len(messages) + len(events))


def _webhook_read_allowed(user_key: str) -> bool:
    """Scope the webhook read-through to the operator (or a headless install)."""
    operator_key = primary_operator_user_key()
    if operator_key:
        return user_key == operator_key
    # No operator row to scope to: the webhook store is installation-global
    # and a headless install has a single reader, so allow the fallback.
    return True


def _webhook_read_through(
    user_key: str,
    agent_id: str,
    *,
    conversation_id: str = "",
    session_id: str = "",
    base_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Read-only fallback to the webhook store for ``conv-github-*`` ids (#1318).

    Lets the operator chat hydrate routine sessions recorded before the
    operator mirror (or when the operator row is unavailable) without
    duplicating or migrating the file.
    """
    if user_key == GITHUB_WEBHOOK_USER_KEY:
        return None
    if not is_webhook_conversation(conversation_id, session_id):
        return None
    if not _webhook_read_allowed(user_key):
        return None
    return _load_record(
        GITHUB_WEBHOOK_USER_KEY,
        agent_id,
        conversation_id=conversation_id,
        session_id=session_id,
        base_dir=base_dir,
    )


def load_or_django(
    user_key: str,
    agent_id: str,
    *,
    conversation_id: str = "",
    session_id: str = "",
    base_dir: Path | None = None,
) -> dict[str, Any] | None:
    """File record if present, otherwise the Django transcript.

    :func:`load` stays file-only so archive/trash still looks empty.
    Append paths (mailbox, lifecycle audit, CLI metadata) use this so a
    Django-only thread is not replaced by the one new line.
    """
    record = load(
        user_key,
        agent_id,
        conversation_id=conversation_id,
        session_id=session_id,
        base_dir=base_dir,
    )
    if record is not None:
        return record
    try:
        from swarm.core.chat_db import django_transcript_record

        return django_transcript_record(
            user_key,
            agent_id,
            conversation_id=conversation_id,
            session_id=session_id,
        )
    except Exception:
        logger.debug("chat_store Django hydrate skipped for %s/%s", user_key, agent_id, exc_info=True)
        return None


def load(
    user_key: str,
    agent_id: str,
    *,
    conversation_id: str = "",
    session_id: str = "",
    base_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Return the active thread record, or None if missing / unsafe ids.

    ``session_id`` selects a concurrent on-mode file (REQ-65). ``conversation_id``
    without a session id scans that agent's files for a matching id. A
    ``conv-github-*`` id missing under the owner key falls back to the
    installation webhook store read-only (#1318). A stale owner copy yields
    to a newer webhook record and is refreshed in place.
    """
    record = _load_record(
        user_key,
        agent_id,
        conversation_id=conversation_id,
        session_id=session_id,
        base_dir=base_dir,
    )
    fallback = _webhook_read_through(
        user_key,
        agent_id,
        conversation_id=conversation_id,
        session_id=session_id,
        base_dir=base_dir,
    )
    if (
        record is not None
        and fallback is not None
        and _record_freshness(fallback) > _record_freshness(record)
    ):
        _mirror_webhook_session(agent_id, fallback, base_dir=base_dir)
        return fallback
    if record is not None:
        return record
    return fallback


def list_sessions(
    user_key: str,
    agent_id: str,
    *,
    base_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """All active files for one agent (reuse file + concurrent task files)."""
    uk = _safe_id(user_key)
    agent = normalize_agent_id(agent_id)
    if uk is None:
        return []
    root = store_dir(base_dir=base_dir) / "active" / uk
    if not root.is_dir():
        return []
    prefix = f"{agent}__"
    items: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        stem = path.stem
        session = ""
        if stem == agent:
            session = ""
        elif stem.startswith(prefix):
            session = stem[len(prefix) :]
        else:
            continue
        record = _read_json(path) or {}
        turns, events = _split_record(record.get("messages"), record.get("ui_events"))
        items.append(
            {
                "agent_id": agent,
                "session_id": session or record.get("session_id") or "",
                "conversation_id": record.get("conversation_id") or "",
                "updated_at": record.get("updated_at") or "",
                "created_at": record.get("created_at") or "",
                "message_count": len(turns) + len(events),
                "bytes": _file_size(path),
            }
        )
    items.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
    return items


def rail_activity_index(
    *,
    base_dir: Path | None = None,
    user_key: str = "u0",
) -> dict[str, str]:
    """Newest ``updated_at`` per seat id across every persisted thread (#601).

    One directory listing serves the whole rail: keys are the thread ids the
    store already uses (``team:<id>``, ``remote:<id>``, bare agent ids),
    values are the ISO-8601 ``updated_at`` each ``save()`` stamps. Sessions
    of one seat (``<id>__<sid>`` files) collapse into the newest. Honest
    absence — a seat with no persisted thread is simply not in the map;
    callers must not fabricate "now".
    """
    uk = _safe_id(user_key)
    if uk is None:
        return {}
    root = store_dir(base_dir=base_dir) / "active" / uk
    if not root.is_dir():
        return {}
    newest: dict[str, tuple[float, str]] = {}
    for path in root.glob("*.json"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        seat = path.stem.split("__", 1)[0]
        record = _read_json(path) or {}
        updated = record.get("updated_at")
        if not (isinstance(updated, str) and updated.strip()):
            continue
        instant = _parse_iso(updated)
        rank = instant.timestamp() if instant is not None else mtime
        current = newest.get(seat)
        if current is None or rank >= current[0]:
            newest[seat] = (rank, updated)
    return {seat: updated for seat, (_rank, updated) in newest.items()}


# #844: rail snippets are one short line — bounded at write time so the
# catalog payload cannot balloon with long transcripts.
SNIPPET_MAX_CHARS = 160


def _reaction_only_emoji(turn: dict[str, Any]) -> str:
    """Emoji that stands in for an empty reaction-only turn (#1411)."""
    if turn.get("reaction_only") is not True:
        return ""
    reactions = turn.get("reactions") or []
    if not isinstance(reactions, list):
        return ""
    for row in reactions:
        if not isinstance(row, dict):
            continue
        emoji = str(row.get("emoji") or "").strip()
        if emoji:
            return emoji
    return ""


def _visible_turn_text(turn: dict[str, Any]) -> str:
    """Snippet text for one turn. A reaction-only reply is its emoji."""
    emoji = _reaction_only_emoji(turn)
    if emoji:
        return emoji
    return str(turn.get("content") or "").strip()


def _latest_visible_turn(turns: Any) -> dict[str, Any] | None:
    """Newest human-visible turn. Chrome never wins the rail snippet (#844)."""
    if not isinstance(turns, list):
        return None
    try:
        from swarm.core.transcript_roles import is_chrome_message

        candidates = [t for t in reversed(turns) if not is_chrome_message(t)]
    except Exception:
        candidates = [t for t in reversed(turns) if isinstance(t, dict)]
    for turn in candidates:
        if not isinstance(turn, dict):
            continue
        if _visible_turn_text(turn):
            return turn
    return None


def _flatten_snippet(text: str) -> str:
    flattened = " ".join((text or "").split())
    if len(flattened) > SNIPPET_MAX_CHARS:
        return flattened[: SNIPPET_MAX_CHARS - 1].rstrip() + "…"
    return flattened


def _snippet_from_turns(turns: Any) -> str:
    """Newest human-visible turn text, flattened and capped (#844).

    Chrome (status/system chatter) never becomes the snippet: the rail row
    should read like the conversation, not like telemetry.
    """
    turn = _latest_visible_turn(turns)
    if not isinstance(turn, dict):
        return ""
    return _flatten_snippet(_visible_turn_text(turn))


def _preview_class_for_turn(turn: dict[str, Any] | None) -> str:
    """#1441: error vs reply for the turn that became the rail snippet."""
    if turn is None:
        return ""
    from swarm.core.cli_session_error import classify_output_preview

    return classify_output_preview(str(turn.get("content") or ""), meta=turn)


def stamp_rail_activity(payload: dict[str, Any], summary: dict[str, Any] | None) -> None:
    """Copy a rail activity summary onto a catalog row.

    ``last_message_class`` is set only for error previews so ordinary rows
    stay unchanged.
    """
    if not summary:
        return
    payload["last_message_at"] = summary.get("at") or ""
    text = summary.get("text") or ""
    if text:
        payload["last_message"] = text
    if summary.get("preview_class") == "error":
        payload["last_message_class"] = "error"


def rail_activity_summaries(
    *,
    base_dir: Path | None = None,
    user_key: str = "u0",
) -> dict[str, dict[str, str]]:
    """Newest instant **and** snippet per seat across persisted threads (#844).

    Same sweep as :func:`rail_activity_index` but each value carries the
    newest human-visible turn text alongside the ISO instant:
    ``{seat: {"at": iso, "text": snippet}}``. Seats with only chrome turns
    still surface (the instant is real) with an empty snippet. Feeds the
    catalog's ``last_message_at`` / ``last_message`` so every rail row can
    hydrate its activity line on first paint, whatever the agent kind.
    """
    uk = _safe_id(user_key)
    if uk is None:
        return {}
    root = store_dir(base_dir=base_dir) / "active" / uk
    if not root.is_dir():
        return {}
    newest: dict[str, tuple[float, str, str, str]] = {}
    for path in root.glob("*.json"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        seat = path.stem.split("__", 1)[0]
        record = _read_json(path) or {}
        updated = record.get("updated_at")
        if not (isinstance(updated, str) and updated.strip()):
            continue
        instant = _parse_iso(updated)
        rank = instant.timestamp() if instant is not None else mtime
        turn = _latest_visible_turn(record.get("messages"))
        snippet = _flatten_snippet(_visible_turn_text(turn)) if isinstance(turn, dict) else ""
        preview_class = _preview_class_for_turn(turn) if snippet else ""
        current = newest.get(seat)
        if current is None or rank >= current[0]:
            newest[seat] = (rank, updated, snippet, preview_class)
    return {
        seat: {"at": updated, "text": text, "preview_class": preview_class}
        for seat, (_r, updated, text, preview_class) in newest.items()
    }


def normalize_cli_sessions(raw: Any) -> dict[str, str]:
    """``{cli_name: session_id}`` with unsafe keys/values dropped (no secrets)."""
    from swarm.core.cli_sessions import sanitize_cli_session_id

    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        cli = normalize_agent_id(str(key))
        sid = sanitize_cli_session_id(value)
        if cli and sid:
            out[cli] = sid
    return out


def _agent_stem_files(user_key: str, agent_id: str, base: Path) -> list[Path]:
    """Every active file this seat owns: ``<agent>.json`` and ``<agent>__*.json``."""
    uk = _safe_id(user_key)
    agent = normalize_agent_id(agent_id)
    if uk is None or agent is None:
        return []
    root = base / "active" / uk
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.glob("*.json")
        if path.stem == agent or path.stem.startswith(f"{agent}__")
    )


def archive(
    user_key: str,
    agent_id: str,
    *,
    base_dir: Path | None = None,
) -> Path | None:
    """Move the seat's active thread(s) to trash. Returns the first trash path,
    or None if nothing moved.

    Every file the seat owns moves, not just ``<agent>.json``. A per-conversation
    thread lives in ``<agent>__<conversation_id>.json``, and leaving those in
    ``active/`` meant an archived session could still be read back — and, once
    the trash was emptied, re-imported into the database (#1721).
    """
    agent = normalize_agent_id(agent_id)
    base = store_dir(base_dir=base_dir)
    trash = _trash_dir(user_key, base)
    sources = _agent_stem_files(user_key, agent, base)
    if trash is None or not sources:
        return None
    trash.mkdir(parents=True, exist_ok=True)
    first: Path | None = None
    for src in sources:
        dest = trash / f"{src.stem}__{_utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
        # Collision (same-second archive): add a counter suffix.
        if dest.exists():
            for idx in range(2, 50):
                candidate = trash / f"{src.stem}__{_utc_now().strftime('%Y%m%dT%H%M%SZ')}-{idx}.json"
                if not candidate.exists():
                    dest = candidate
                    break
        try:
            shutil.move(str(src), str(dest))
        except OSError:
            logger.debug("chat_store archive move failed for %s", src, exc_info=True)
            continue
        if first is None:
            first = dest
    return first


def purge_conversation(
    user_key: str,
    agent_id: str,
    conversation_id: str,
    *,
    base_dir: Path | None = None,
) -> int:
    """Hard-delete the active cache file(s) that hold one conversation.

    #1721: the database tombstone (``ChatConversation.purged_at``) is what makes
    the deletion durable — a cache file alone must never be able to bring the
    thread back. Deleting the file too is belt-and-braces for the ordinary
    case and is what stops the bytes from sitting on disk after the user asked
    for them to be gone.

    Matches by predicted stem *and* by the ``conversation_id`` the record
    itself claims, so a file written under a layout the prediction did not
    guess is still removed. Returns the number of files unlinked.
    """
    base = store_dir(base_dir=base_dir)
    agent = normalize_agent_id(agent_id)
    candidates: set[Path] = set()
    stem = session_stem_for_conversation(
        user_key, agent, conversation_id, base_dir=base_dir
    )
    uk = _safe_id(user_key)
    for candidate_stem in {stem, str(conversation_id or "").strip()}:
        if uk is None or not candidate_stem:
            continue
        path = _active_path(uk, agent, base, session_id=candidate_stem)
        if path is not None:
            candidates.add(path)
    if uk is not None:
        for path in _agent_stem_files(user_key, agent, base):
            record = _read_json(path) or {}
            if str(record.get("conversation_id") or "").strip() == str(conversation_id or "").strip():
                candidates.add(path)
    removed = 0
    for path in sorted(candidates):
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.debug("chat_store purge unlink failed for %s", path, exc_info=True)
    return removed


def archive_all(user_key: str, *, base_dir: Path | None = None) -> list[str]:
    """Move every active thread for ``user_key`` to trash. Returns archived agent ids."""
    archived: list[str] = []
    for summary in list_active(user_key, base_dir=base_dir):
        if archive(user_key, summary["agent_id"], base_dir=base_dir) is not None:
            archived.append(summary["agent_id"])
    return archived


def restore(
    user_key: str,
    agent_id: str,
    *,
    base_dir: Path | None = None,
) -> Path | None:
    """Restore the newest trash copy for ``agent_id``.

    If an active file already exists it is archived first (conservative).
    """
    agent = normalize_agent_id(agent_id)
    base = store_dir(base_dir=base_dir)
    trash = _trash_dir(user_key, base)
    if trash is None or not trash.is_dir():
        return None
    candidates = sorted(
        (
            path
            for path in trash.iterdir()
            if path.is_file() and path.suffix == ".json" and _trash_agent(path.stem) == agent
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
    active = _active_path(user_key, agent, base)
    if active is not None and active.is_file():
        archive(user_key, agent, base_dir=base)
    dest = _active_path(user_key, agent, base)
    if dest is None:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(candidates[0]), str(dest))
    return dest


def empty_trash(user_key: str, *, base_dir: Path | None = None) -> int:
    """Hard-delete trash files for ``user_key``. Returns the number removed."""
    trash = _trash_dir(user_key, store_dir(base_dir=base_dir))
    if trash is None or not trash.is_dir():
        return 0
    removed = 0
    for path in list(trash.iterdir()):
        if not path.is_file():
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _trash_agent(stem: str) -> str | None:
    match = _TRASH_STAMP_RE.match(stem)
    if match:
        return match.group(1)
    # Counter suffix: agent__stamp-2
    if "__" in stem:
        return stem.rsplit("__", 1)[0]
    return None


def _file_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def list_active(user_key: str, *, base_dir: Path | None = None) -> list[dict[str, Any]]:
    """Summaries of active threads for one user, newest updated first."""
    uk = _safe_id(user_key)
    if uk is None:
        return []
    root = store_dir(base_dir=base_dir) / "active" / uk
    if not root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        agent = path.stem
        if not _ID_RE.match(agent):
            continue
        record = _read_json(path) or {}
        turns, events = _split_record(record.get("messages"), record.get("ui_events"))
        items.append(
            {
                "agent_id": agent,
                "conversation_id": record.get("conversation_id") or "",
                "updated_at": record.get("updated_at") or "",
                "created_at": record.get("created_at") or "",
                "message_count": len(turns) + len(events),
                "bytes": _file_size(path),
            }
        )
    items.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
    return items


def list_trash(user_key: str, *, base_dir: Path | None = None) -> list[dict[str, Any]]:
    """Summaries of trashed copies for one user, newest first."""
    trash = _trash_dir(user_key, store_dir(base_dir=base_dir))
    if trash is None or not trash.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in trash.glob("*.json"):
        agent = _trash_agent(path.stem)
        if not agent or not _ID_RE.match(agent):
            continue
        record = _read_json(path) or {}
        turns, events = _split_record(record.get("messages"), record.get("ui_events"))
        items.append(
            {
                "agent_id": agent,
                "filename": path.name,
                "updated_at": record.get("updated_at") or "",
                "message_count": len(turns) + len(events),
                "bytes": _file_size(path),
            }
        )
    items.sort(key=lambda row: row.get("filename") or "", reverse=True)
    return items


def disk_usage(user_key: str, *, base_dir: Path | None = None) -> dict[str, int]:
    """Byte totals for one user's active + trash files."""
    active = sum(row["bytes"] for row in list_active(user_key, base_dir=base_dir))
    trash = sum(row["bytes"] for row in list_trash(user_key, base_dir=base_dir))
    return {"active_bytes": active, "trash_bytes": trash, "total_bytes": active + trash}


def stats(user_key: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    """Settings-page payload: counts, disk, paths, retention, per-chat lists."""
    base = store_dir(base_dir=base_dir)
    usage = disk_usage(user_key, base_dir=base)
    age = get_max_age_days()
    return {
        "store_dir": str(base),
        "format": "json",
        "active_count": len(list_active(user_key, base_dir=base)),
        "trash_count": len(list_trash(user_key, base_dir=base)),
        "bytes_used": usage["total_bytes"],
        "bytes_label": format_bytes(usage["total_bytes"]),
        "active_bytes_label": format_bytes(usage["active_bytes"]),
        "trash_bytes_label": format_bytes(usage["trash_bytes"]),
        "max_age_days": age,
        "auto_archive_enabled": age > 0,
        "chats": list_active(user_key, base_dir=base),
        "trash": list_trash(user_key, base_dir=base),
        "env_dir": ENV_CHAT_DIR,
        "env_max_age": ENV_CHAT_MAX_AGE_DAYS,
    }


def prune_expired(
    user_key: str,
    *,
    max_age_days: int | None = None,
    base_dir: Path | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Move stale active threads to trash. Never hard-deletes.

    Age is ``updated_at`` (ISO) falling back to file mtime. ``max_age_days``
    ``<= 0`` is a no-op. Returns archived agent ids.
    """
    age = int(max_age_days) if max_age_days is not None else get_max_age_days()
    if age <= 0:
        return []
    clock = now or _utc_now()
    cutoff = clock.timestamp() - (age * 86400)
    archived: list[str] = []
    for row in list_active(user_key, base_dir=base_dir):
        parsed = _parse_iso(row.get("updated_at"))
        if parsed is not None:
            ts = parsed.timestamp()
        else:
            path = _active_path(user_key, row["agent_id"], store_dir(base_dir=base_dir))
            if path is None:
                continue
            try:
                ts = path.stat().st_mtime
            except OSError:
                continue
        if ts > cutoff:
            continue
        if archive(user_key, row["agent_id"], base_dir=base_dir) is not None:
            archived.append(row["agent_id"])
    return archived

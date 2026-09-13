"""CLI session ids — owned by the CLI, tracked next to the chat thread.

API / Django conversation ids are Swarm-owned. Remote harnesses keep the
remote's session. This module stores only the **CLI's** session id so the
next send can pass ``--resume`` / ``--session`` / ``exec resume`` and the
CLI restores its own context.

Ids are persisted on the per-agent chat JSON record (``cli_sessions``),
keyed by CLI name. Nothing here stores secrets, API keys, or env dumps.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from swarm.core import chat_store
from swarm.core.cli_adapter import CliResult

SESSION_TOKEN = "{session_id}"

# Id-shaped tokens only. Reject assignments, whitespace, and common secret prefixes.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SECRET_PREFIX = re.compile(
    r"^(?i:sk-|gsk_|xai-|AIza|ghp_|github_pat_|xox[baprs]-|Bearer )"
)

# Default JSON paths tried after any per-CLI list (Claude often uses session_id
# even when parse is json:.result).
DEFAULT_SESSION_ID_PATHS = (
    ".session_id",
    ".sessionId",
    ".thread_id",
    ".conversation_id",
    ".session.id",
    ".session",
)

_RESUME_FAILURE_NEEDLES = (
    "no conversation",
    "conversation found",
    "session not found",
    "unknown session",
    "invalid session",
    "expired session",
    "cannot resume",
    "failed to resume",
    "no such session",
    "unable to resume",
    "resume failed",
)


def sanitize_cli_session_id(raw: Any) -> str | None:
    """Return a storeable CLI session id, or None if it looks unsafe / secret.

    Rejects leading ``-`` (``--help``) and leading ``.`` (``.``, ``..``) so
    an id cannot become a flag or a path hop. Mid-id dashes stay valid for
    UUIDs.
    """
    if raw is None:
        return None
    if isinstance(raw, (bool, dict, list)):
        return None
    text = str(raw).strip()
    if not text or len(text) > 128:
        return None
    if text.startswith("-") or text.startswith("."):
        return None
    if any(ch in text for ch in ("=", " ", "\n", "\t", "/", "\\")):
        return None
    if _SECRET_PREFIX.match(text):
        return None
    if not _SESSION_ID_RE.match(text):
        return None
    return text


def _iter_json_blobs(stdout: str):
    text = (stdout or "").strip()
    if not text:
        return
    try:
        yield json.loads(text)
        return
    except json.JSONDecodeError:
        pass
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def extract_session_id(stdout: str, paths: list[str] | None = None) -> str | None:
    """Best-effort session id from JSON or JSONL stdout. Last match wins."""
    from swarm.core.cli_adapter import _extract_json_path

    ordered: list[str] = []
    for path in list(paths or []) + list(DEFAULT_SESSION_ID_PATHS):
        if path and path not in ordered:
            ordered.append(path)
    found: str | None = None
    for blob in _iter_json_blobs(stdout):
        items = blob if isinstance(blob, list) else [blob]
        for item in items:
            if not isinstance(item, dict):
                continue
            for path in ordered:
                try:
                    value = _extract_json_path(item, path)
                except (KeyError, IndexError, TypeError, ValueError):
                    continue
                sid = sanitize_cli_session_id(value)
                if sid:
                    found = sid
    return found


def is_resume_failure(result: CliResult) -> bool:
    """True when a resumed CLI run looks like a missing/expired session."""
    if result.ok:
        return False
    blob = f"{result.error or ''} {result.stderr or ''} {result.text or ''}".lower()
    return any(needle in blob for needle in _RESUME_FAILURE_NEEDLES)


def resolve_thread(
    params: dict[str, Any] | None, *, default_agent: str
) -> tuple[str, str] | None:
    """``(user_key, agent_id)`` for the chat thread, or None if unknown.

    Prefer the websocket identity (``user_key`` + ``agent``). API callers can
    pass ``conversation_id`` / ``thread`` and we persist under ``_api``.
    """
    params = params or {}
    user_key = str(params.get("user_key") or "").strip()
    agent = str(
        params.get("agent") or params.get("agent_id") or default_agent or ""
    ).strip()
    conversation_id = str(
        params.get("conversation_id") or params.get("thread") or ""
    ).strip()
    if user_key and agent:
        return user_key, chat_store.normalize_agent_id(agent)
    if conversation_id:
        return "_api", chat_store.normalize_agent_id(conversation_id)
    return None


def get_cli_session(
    user_key: str,
    agent_id: str,
    cli_name: str,
    *,
    conversation_id: str = "",
    session_id: str = "",
    base_dir: Path | None = None,
) -> str | None:
    """Stored CLI session id for this chat thread + CLI, or None."""
    record = chat_store.load(
        user_key,
        agent_id,
        conversation_id=conversation_id,
        session_id=session_id,
        base_dir=base_dir,
    )
    if not record:
        return None
    sessions = chat_store.normalize_cli_sessions(record.get("cli_sessions"))
    return sessions.get(chat_store.normalize_agent_id(cli_name))


def put_cli_session(
    user_key: str,
    agent_id: str,
    cli_name: str,
    session_id: str | None,
    *,
    conversation_id: str = "",
    base_dir: Path | None = None,
) -> str | None:
    """Write or clear one CLI session id on the thread. Returns the stored id."""
    sid = sanitize_cli_session_id(session_id)
    record = chat_store.load(user_key, agent_id, base_dir=base_dir)
    messages = (record or {}).get("messages") or []
    sessions = chat_store.normalize_cli_sessions((record or {}).get("cli_sessions"))
    key = chat_store.normalize_agent_id(cli_name)
    if sid:
        sessions[key] = sid
    else:
        sessions.pop(key, None)
    chat_store.save(
        user_key,
        agent_id,
        messages,
        conversation_id=conversation_id
        or (record or {}).get("conversation_id")
        or "",
        cli_sessions=sessions,
        base_dir=base_dir,
    )
    return sid


def clear_cli_session(
    user_key: str,
    agent_id: str,
    cli_name: str,
    *,
    conversation_id: str = "",
    base_dir: Path | None = None,
) -> None:
    put_cli_session(
        user_key,
        agent_id,
        cli_name,
        None,
        conversation_id=conversation_id,
        base_dir=base_dir,
    )


def session_notice_text(cli_name: str, *, resumed: bool) -> str:
    """Honest user-facing line. Never claims restore unless we actually resumed."""
    if resumed:
        return f"Resumed {cli_name} session."
    return f"Started a new {cli_name} session."

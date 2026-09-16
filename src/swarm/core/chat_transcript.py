"""Shared CLI transcript ordering — session notices sit before the reply.

REQ-92: a new-session status line is context for the assistant turn that
follows. Live stream and persist/hydrate must keep that order. Resume must
not invent a spurious ``Started a new …`` line.
"""

from __future__ import annotations

import re
from typing import Any

_NEW_SESSION_RE = re.compile(
    r"^Started a new \S+ session(?: on \S+)?\.?$", re.IGNORECASE
)
_RESUME_SESSION_RE = re.compile(
    r"^Resumed \S+ session(?: on \S+)?\.?$", re.IGNORECASE
)


def is_cli_session_notice(text: str | None) -> bool:
    """True for the honest CLI session lines (new or resumed)."""
    blob = (text or "").strip()
    return bool(_NEW_SESSION_RE.match(blob) or _RESUME_SESSION_RE.match(blob))


def is_new_cli_session_notice(text: str | None) -> bool:
    return bool(_NEW_SESSION_RE.match((text or "").strip()))


def _status_text(row: dict[str, Any]) -> str:
    return str(row.get("content") or row.get("text") or "").strip()


def _last_user_index(messages: list[dict[str, Any]]) -> int:
    last = -1
    for index, row in enumerate(messages):
        if (row.get("role") or "") == "user":
            last = index
    return last


def transcript_already_has_notice(messages: list[dict[str, Any]], text: str) -> bool:
    """True when this turn already recorded the same status line."""
    needle = (text or "").strip()
    if not needle:
        return False
    last_user = _last_user_index(messages)
    for row in messages[last_user + 1 :]:
        if (row.get("role") or "") == "status" and _status_text(row) == needle:
            return True
    return False


def insert_status_before_turn_assistant(
    messages: list[dict[str, Any]],
    status_row: dict[str, Any],
) -> list[dict[str, Any]]:
    """Insert ``status_row`` immediately before this turn's assistant content.

    Dropdown / other status lines still append. Duplicate CLI session notices
    for the same turn are ignored so a pre-emitted new-session line is not
    repeated when the blueprint yields the same chunk.
    """
    text = _status_text(status_row)
    if not is_cli_session_notice(text):
        return [*messages, status_row]
    if transcript_already_has_notice(messages, text):
        return list(messages)
    last_user = _last_user_index(messages)
    assistant_idx = next(
        (
            index
            for index, row in enumerate(messages)
            if index > last_user and (row.get("role") or "") == "assistant"
        ),
        None,
    )
    if assistant_idx is None:
        return [*messages, status_row]
    return [*messages[:assistant_idx], status_row, *messages[assistant_idx:]]


def new_cli_session_notice_if_needed(
    *,
    blueprint_id: str | None,
    params: dict[str, Any] | None = None,
    user_key: str | None = None,
) -> str | None:
    """Return ``Started a new {cli} session.`` only when this turn cannot resume.

    Returns None when the agent is not a CLI, or when a stored CLI session id
    exists (resume / same-session — do not print a spurious new-session line).
    """
    from swarm.core import chat_store
    from swarm.core.agent_settings import is_new_chat_per_task
    from swarm.core.cli_catalog import cli_from_rail_id
    from swarm.core.cli_sessions import get_cli_session, session_notice_text

    params = params or {}
    cli_name = None
    raw_cli = params.get("cli")
    if isinstance(raw_cli, str) and raw_cli.strip():
        cli_name = raw_cli.strip()
    if not cli_name:
        cli_name = cli_from_rail_id(blueprint_id)
    if not cli_name:
        return None

    agent = str(
        params.get("agent") or params.get("agent_id") or blueprint_id or ""
    ).strip()
    agent_id = chat_store.normalize_agent_id(agent) if agent else ""
    host = None
    raw_remote = params.get("cli_remote") or params.get("remote")
    if raw_remote:
        from swarm.core.cli_remote import remote_endpoint_label, resolve_cli_remote

        host = remote_endpoint_label(resolve_cli_remote(cli_name, params=params))
    if agent_id and is_new_chat_per_task(agent_id):
        return session_notice_text(cli_name, resumed=False, host=host)
    if is_new_chat_per_task(cli_name):
        return session_notice_text(cli_name, resumed=False, host=host)
    if not user_key or not agent_id:
        # Without a thread we cannot prove resume; stay quiet (no spurious line).
        return None
    stored = get_cli_session(user_key, agent_id, cli_name)
    if stored:
        return None
    return session_notice_text(cli_name, resumed=False, host=host)

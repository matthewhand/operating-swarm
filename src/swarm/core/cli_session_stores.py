"""Provider-owned session stores (ids + display metadata only).

Used when a CLI has no official non-interactive list argv but still owns
sessions on disk. Open Swarm does **not** invent a parallel session DB —
we only enumerate the CLI's own files. Never open secret-shaped payloads
(agy conversation sqlite is protobuf; we use filename stem + mtime only).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swarm.core.cli_catalog import (
    AGY_CONVERSATIONS_STORE,
    QWEN_SESSIONS_STORE,
)
from swarm.core.cli_sessions import sanitize_cli_session_id

logger = logging.getLogger(__name__)


def list_store_sessions(kind: str, store_dir: str | Path | None) -> list[dict[str, Any]]:
    """Enumerate one provider store. Unknown kind → empty (no fake rows)."""
    if kind == AGY_CONVERSATIONS_STORE:
        return list_agy_conversations(store_dir)
    if kind == QWEN_SESSIONS_STORE:
        return list_qwen_sessions(store_dir)
    logger.warning("Unknown CLI session store %r — not listing", kind)
    return []


def list_agy_conversations(store_dir: str | Path | None) -> list[dict[str, Any]]:
    """List agy conversation ids from ``<dir>/<uuid>.db`` stems.

    The stem is the id passed to ``agy --conversation``. Display metadata is
    the id plus file mtime. The sqlite is never opened.
    """
    if not store_dir:
        return []
    root = Path(store_dir)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        logger.warning("Could not read agy conversations dir %s", root)
        return []
    for path in entries:
        if not path.is_file() or path.suffix != ".db":
            continue
        sid = sanitize_cli_session_id(path.stem)
        if not sid:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        updated = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        rows.append(
            {
                "id": sid,
                "title": sid,
                "snippet": "",
                "updated_at": updated,
                "source": "provider",
            }
        )
    rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return rows


_QWEN_FIRST_USER_SCAN_LINES = 40


def _qwen_first_user_text(path: Path) -> str:
    """First real user prompt in a qwen JSONL, or "" (metadata only, cheap scan)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for index, line in enumerate(handle):
                if index >= _QWEN_FIRST_USER_SCAN_LINES:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    blob = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(blob, dict) or blob.get("type") != "user":
                    continue
                message = blob.get("message") or {}
                for part in (message.get("parts") or []):
                    text = part.get("text") if isinstance(part, dict) else None
                    if isinstance(text, str) and text.strip():
                        return text.strip()
    except OSError:
        return ""
    return ""


_QWEN_TRANSCRIPT_MAX_TURNS = 200
_QWEN_TRANSCRIPT_MAX_CHARS = 60000


def _qwen_session_file(store_dir: str | Path | None, session_id: str) -> Path | None:
    sid = sanitize_cli_session_id(session_id)
    if not sid or not store_dir:
        return None
    root = Path(store_dir).expanduser()
    try:
        matches = list(root.glob(f"*/chats/{sid}.jsonl"))
    except OSError:
        return None
    return matches[0] if matches else None


def read_qwen_transcript(
    store_dir: str | Path | None,
    session_id: str,
    *,
    max_turns: int = _QWEN_TRANSCRIPT_MAX_TURNS,
    max_chars: int = _QWEN_TRANSCRIPT_MAX_CHARS,
) -> dict[str, Any] | None:
    """Provider transcript for a qwen session: turns + real cwd/branch.

    Turns are ``{role, content}`` (user/model text only — thought parts,
    tool calls/results, and system chrome are skipped). Bounded scan so a
    huge JSONL cannot blow up the select path. Returns ``None`` when the
    session file is missing or unreadable (caller proceeds without import).
    """
    path = _qwen_session_file(store_dir, session_id)
    if path is None:
        return None
    turns: list[dict[str, str]] = []
    chars = 0
    cwd: str | None = None
    branch: str | None = None
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            if len(turns) >= max_turns or chars >= max_chars:
                break
            line = line.strip()
            if not line:
                continue
            try:
                blob = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(blob, dict):
                continue
            if cwd is None and isinstance(blob.get("cwd"), str) and blob["cwd"].strip():
                cwd = blob["cwd"].strip()
            if branch is None and isinstance(blob.get("gitBranch"), str) and blob["gitBranch"].strip():
                branch = blob["gitBranch"].strip()
            kind = blob.get("type")
            message = blob.get("message")
            if not isinstance(message, dict):
                continue
            parts = message.get("parts")
            if not isinstance(parts, list):
                continue
            if kind == "user":
                role = "user"
            elif kind == "assistant" and message.get("role") == "model":
                role = "assistant"
            else:
                continue
            texts = [
                str(part.get("text")).strip()
                for part in parts
                if isinstance(part, dict)
                and isinstance(part.get("text"), str)
                and part.get("text").strip()
                and not part.get("thought")
            ]
            content = "\n".join(texts).strip()
            if not content:
                continue
            turns.append({"role": role, "content": content})
            chars += len(content)
    if not turns and cwd is None and branch is None:
        return None
    return {"turns": turns, "cwd": cwd, "git_branch": branch}


def read_provider_transcript(
    cli_name: str,
    session_id: str | None,
    store_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """Best-effort provider transcript for one CLI session (qwen only for now)."""
    if not session_id:
        return None
    name = str(cli_name or "").strip().lower()
    if name != "qwen":
        return None
    if store_dir is None:
        from swarm.core import cli_catalog
        try:
            store_dir = cli_catalog.list_sessions_store_dir(name, None)
        except Exception:
            return None
    try:
        return read_qwen_transcript(store_dir, session_id)
    except Exception:
        logger.exception("Could not read qwen transcript for %s", session_id)
        return None


def list_qwen_sessions(store_dir: str | Path | None) -> list[dict[str, Any]]:
    """List qwen session ids from ``<dir>/<escaped-cwd>/chats/<uuid>.jsonl``.

    Display metadata (id + mtime + first user text + owning project folder)
    comes from the filesystem and a bounded first-lines scan — the JSONL body
    is never fully parsed. ``folder`` is the escaped project dir qwen created
    from the session's cwd (non-alphanumerics → ``-``).
    """
    if not store_dir:
        return []
    root = Path(store_dir)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    try:
        chats_dirs = list(root.glob("*/chats"))
    except OSError:
        logger.warning("Could not read qwen projects dir %s", root)
        return []
    for chats in chats_dirs:
        try:
            files = list(chats.glob("*.jsonl"))
        except OSError:
            continue
        for path in files:
            sid = sanitize_cli_session_id(path.stem)
            if not sid:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            updated = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            title = _qwen_first_user_text(path)
            rows.append(
                {
                    "id": sid,
                    "title": title or sid,
                    "snippet": "",
                    "updated_at": updated,
                    "source": "provider",
                    "folder": chats.parent.name,
                }
            )
    rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return rows

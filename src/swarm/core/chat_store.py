"""File-backed persistence for per-agent SPA chat threads.

Each logged-in user gets one JSON file per agent (blueprint id, or
``_default`` when the server-default model is selected). Retention lives
on the Settings page only: archive moves a file to ``trash/``; auto-age
does the same after ``SWARM_CHAT_MAX_AGE_DAYS`` (default 90). Trash is
never hard-deleted automatically.

Layout (under :func:`store_dir`)::

    active/<user_key>/<agent_id>.json
    trash/<user_key>/<agent_id>__<UTC stamp>.json

This is the on-disk source of truth for restore + Settings stats. The
Django ``ChatConversation`` / ``ChatMessage`` tables remain a mirror used
by the websocket consumer.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swarm.core.paths import get_user_data_dir_for_swarm

SCHEMA = 2
DEFAULT_AGENT_ID = "_default"
ENV_CHAT_DIR = "SWARM_CHAT_DIR"
ENV_CHAT_MAX_AGE_DAYS = "SWARM_CHAT_MAX_AGE_DAYS"
DEFAULT_MAX_AGE_DAYS = 90

# User keys and agent ids must stay inside the store dir.
_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_TRASH_STAMP_RE = re.compile(r"^(.+)__(\d{8}T\d{6}Z)$")


def store_dir(*, base_dir: Path | None = None) -> Path:
    """Root of the chat JSON store.

    ``SWARM_CHAT_DIR`` wins; otherwise ``<SWARM_USER_DATA_DIR or platformdirs>/chats``.
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
    _atomic_write(path, record)
    return path


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
                found = load(user_key, agent, session_id=sid, base_dir=base_dir)
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


def archive(
    user_key: str,
    agent_id: str,
    *,
    base_dir: Path | None = None,
) -> Path | None:
    """Move the active thread to trash. Returns the trash path, or None if nothing moved."""
    agent = normalize_agent_id(agent_id)
    base = store_dir(base_dir=base_dir)
    src = _active_path(user_key, agent, base)
    trash = _trash_dir(user_key, base)
    if src is None or trash is None or not src.is_file():
        return None
    trash.mkdir(parents=True, exist_ok=True)
    dest = trash / f"{agent}__{_utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
    # Collision (same-second archive): add a counter suffix.
    if dest.exists():
        for idx in range(2, 50):
            candidate = trash / f"{agent}__{_utc_now().strftime('%Y%m%dT%H%M%SZ')}-{idx}.json"
            if not candidate.exists():
                dest = candidate
                break
    shutil.move(str(src), str(dest))
    return dest


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

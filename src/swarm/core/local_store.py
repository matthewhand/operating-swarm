"""Local store facts for the Settings System section (REQ-56).

Read-only helpers: file size, a home-relative (non-secret) path, and
conversation / message counts. Returned strings never name the framework,
the file engine, or an ORM. Missing or empty store → 0 / ``not created yet``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

NOT_CREATED = "not created yet"
ON_THIS_MACHINE = "on this machine"


def format_size(n: int) -> str:
    """Human-readable byte count for the Settings System section (e.g. 12.4 MB)."""
    value = float(max(0, int(n)))
    for unit, step in (("B", 1024.0), ("KB", 1024.0), ("MB", 1024.0), ("GB", 1024.0)):
        if value < step or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= step
    return f"{int(n)} B"


def looks_like_connection_string(value: str | None) -> bool:
    """True when ``value`` looks like a DSN or credential-bearing locator."""
    text = (value or "").strip().lower()
    if not text:
        return False
    if "://" in text:
        return True
    if "password=" in text or "pwd=" in text:
        return True
    if text.startswith(("postgres", "mysql", "mongodb", "cockroach")):
        return True
    return False


def home_relative_path(path: Path | str) -> str:
    """Home-relative display path (``~/…``) or the resolved path as-is."""
    raw = Path(str(path)).expanduser()
    try:
        resolved = raw.resolve()
    except OSError:
        resolved = raw
    try:
        home = Path.home().resolve()
    except OSError:
        home = Path.home()
    try:
        relative = resolved.relative_to(home)
        return f"~/{relative.as_posix()}"
    except ValueError:
        return resolved.as_posix() if hasattr(resolved, "as_posix") else str(resolved)


def safe_display_path(value: Path | str | None, *, created: bool) -> str:
    """Path shown in Settings: home-relative, never a connection string."""
    if value is None:
        return ON_THIS_MACHINE if created else NOT_CREATED
    text = str(value).strip()
    if not text or looks_like_connection_string(text):
        return ON_THIS_MACHINE if created else NOT_CREATED
    display = home_relative_path(text)
    if looks_like_connection_string(display):
        return ON_THIS_MACHINE if created else NOT_CREATED
    return display


def file_size_facts(path: Path | None) -> dict[str, Any]:
    """Size + created flag for a local file. Missing/unreadable → not created."""
    if path is None:
        return {"created": False, "size_bytes": 0, "size_label": NOT_CREATED}
    try:
        if not path.is_file():
            return {"created": False, "size_bytes": 0, "size_label": NOT_CREATED}
        size = int(path.stat().st_size)
    except OSError:
        return {"created": False, "size_bytes": 0, "size_label": NOT_CREATED}
    if size <= 0:
        return {"created": False, "size_bytes": 0, "size_label": NOT_CREATED}
    return {"created": True, "size_bytes": size, "size_label": format_size(size)}


def _configured_file_path() -> Path | None:
    """Filesystem path of the local store, or None when it is not a local file."""
    name: Any = None
    engine = ""
    try:
        from django.db import connection

        name = connection.settings_dict.get("NAME")
        engine = str(connection.settings_dict.get("ENGINE") or "")
    except Exception:
        try:
            from django.conf import settings

            db = (getattr(settings, "DATABASES", {}) or {}).get("default", {}) or {}
            name = db.get("NAME")
            engine = str(db.get("ENGINE") or "")
        except Exception:
            return None

    if name is None:
        return None
    text = str(name).strip()
    if (
        not text
        or text == ":memory:"
        # SQLite URI names (e.g. pytest's ``file:memorydb_default?mode=memory``)
        # are not filesystem paths. Treating one as a path hid the live counts
        # and surfaced a bogus resolved path, so no ``file:`` URI counts as a
        # local file here.
        or text.startswith("file:")
        or looks_like_connection_string(text)
    ):
        return None
    engine_l = engine.lower()
    looks_like_file = (
        "sqlite" in engine_l
        or "/" in text
        or "\\" in text
        or text.endswith((".db", ".sqlite", ".sqlite3"))
    )
    if not looks_like_file:
        return None
    try:
        return Path(text).expanduser()
    except (TypeError, ValueError):
        return None


def _counts(*, allow: bool) -> tuple[int, int]:
    if not allow:
        return (0, 0)
    try:
        from swarm.models import ChatConversation, ChatMessage

        return (
            int(ChatConversation.objects.count()),
            int(ChatMessage.objects.count()),
        )
    except Exception:
        return (0, 0)


def local_store_facts(
    *,
    path: Path | str | None = None,
    conversation_count: int | None = None,
    message_count: int | None = None,
    discover: bool = True,
) -> dict[str, Any]:
    """Settings System payload. Never raises; never returns a connection string.

    ``path`` is the store file when known. ``discover=True`` (default) reads the
    live local-store location when ``path`` is omitted. Pass ``discover=False``
    with ``path=None`` to skip discovery (unit tests).
    """
    try:
        raw_path: Path | None
        if path is not None:
            if looks_like_connection_string(str(path)):
                raw_path = None
            else:
                raw_path = Path(str(path)).expanduser()
        elif discover:
            raw_path = _configured_file_path()
        else:
            raw_path = None

        size = file_size_facts(raw_path)
        created = bool(size["created"])
        # Count only when a local file exists, or when this is not a file store
        # (already-running process — do not create a missing file by querying).
        can_count = created or raw_path is None
        conv = conversation_count
        msgs = message_count
        if conv is None or msgs is None:
            found_conv, found_msgs = _counts(allow=can_count)
            if conv is None:
                conv = found_conv
            if msgs is None:
                msgs = found_msgs

        return {
            "path": safe_display_path(raw_path, created=created),
            "size_bytes": int(size["size_bytes"]),
            "size_label": str(size["size_label"]),
            "created": created,
            "conversation_count": int(max(0, conv or 0)),
            "message_count": int(max(0, msgs or 0)),
        }
    except Exception:
        return {
            "path": NOT_CREATED,
            "size_bytes": 0,
            "size_label": NOT_CREATED,
            "created": False,
            "conversation_count": 0,
            "message_count": 0,
        }

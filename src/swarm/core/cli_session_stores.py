"""Provider-owned session stores (ids + display metadata + transcript readers).

Used when a CLI has no official non-interactive list argv but still owns
sessions on disk. Open Swarm does **not** invent a parallel session DB —
we only enumerate / read the CLI's own files.

Transcript import (#139): ``read_provider_transcript`` dispatches through a
pluggable reader map so WebUI select can hydrate agy / grok / opencode / qwen.
Agy conversation sqlite stores protobuf blobs; the agy reader extracts
user/assistant printable text heuristically and never treats the DB as a
swarm SoT. Never open secret-shaped payloads.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from swarm.core.cli_catalog import (
    AGY_CONVERSATIONS_STORE,
    QWEN_SESSIONS_STORE,
)
from swarm.core.cli_sessions import sanitize_cli_session_id

logger = logging.getLogger(__name__)

TranscriptReader = Callable[..., dict[str, Any] | None]

DEFAULT_GROK_SESSIONS_DIR = "~/.grok/sessions"
DEFAULT_OPENCODE_SHARE_DIR = "~/.local/share/opencode"
DEFAULT_AGY_CONVERSATIONS_DIR = "~/.gemini/antigravity-cli/conversations"
DEFAULT_QWEN_PROJECTS_DIR = "~/.qwen/projects"

_TRANSCRIPT_MAX_TURNS = 200
_TRANSCRIPT_MAX_CHARS = 60000


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
    the id plus file mtime. Listing never opens the sqlite; the transcript
    reader may open it read-only for hydrate.
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


_QWEN_TRANSCRIPT_MAX_TURNS = _TRANSCRIPT_MAX_TURNS
_QWEN_TRANSCRIPT_MAX_CHARS = _TRANSCRIPT_MAX_CHARS


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


# --- grok ------------------------------------------------------------------

def _grok_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip() and item.get("type", "text") == "text":
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _grok_session_file(store_dir: str | Path | None, session_id: str) -> Path | None:
    sid = sanitize_cli_session_id(session_id)
    if not sid or not store_dir:
        return None
    root = Path(store_dir).expanduser()
    if not root.is_dir():
        return None
    try:
        matches = list(root.glob(f"*/{sid}/chat_history.jsonl"))
    except OSError:
        return None
    if matches:
        return matches[0]
    # Nested worktree / subagent layouts: */*/<sid>/chat_history.jsonl
    try:
        deep = list(root.glob(f"*/*/{sid}/chat_history.jsonl"))
    except OSError:
        return None
    return deep[0] if deep else None


def read_grok_transcript(
    store_dir: str | Path | None,
    session_id: str,
    *,
    max_turns: int = _TRANSCRIPT_MAX_TURNS,
    max_chars: int = _TRANSCRIPT_MAX_CHARS,
) -> dict[str, Any] | None:
    """Read ``~/.grok/sessions/<cwd-enc>/<sid>/chat_history.jsonl`` turns."""
    path = _grok_session_file(store_dir, session_id)
    if path is None:
        return None
    turns: list[dict[str, str]] = []
    chars = 0
    cwd: str | None = None
    # Parent of sid dir is URL-encoded cwd (%2Fhome%2F...)
    try:
        encoded = path.parent.parent.name
        decoded = unquote(encoded)
        if decoded.startswith("/") and "\x00" not in decoded:
            cwd = decoded
    except Exception:
        cwd = None
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
            # Skip synthetic chrome / system reminders.
            if blob.get("synthetic_reason"):
                continue
            kind = str(blob.get("type") or "").lower()
            if kind == "user":
                role = "user"
            elif kind == "assistant":
                role = "assistant"
            else:
                continue
            content = _grok_content_text(blob.get("content"))
            if not content:
                continue
            turns.append({"role": role, "content": content})
            chars += len(content)
    if not turns and cwd is None:
        return None
    return {"turns": turns, "cwd": cwd, "git_branch": None}


# --- opencode --------------------------------------------------------------

def _opencode_db_path(store_dir: str | Path | None) -> Path | None:
    if not store_dir:
        return None
    root = Path(store_dir).expanduser()
    db = root / "opencode.db"
    return db if db.is_file() else None


def _opencode_part_text(pdata: dict[str, Any]) -> str:
    if pdata.get("type") != "text":
        return ""
    if pdata.get("synthetic") is True:
        return ""
    text = pdata.get("text")
    return text.strip() if isinstance(text, str) else ""


def _read_opencode_db_transcript(
    db_path: Path,
    session_id: str,
    *,
    max_turns: int,
    max_chars: int,
) -> dict[str, Any] | None:
    sid = sanitize_cli_session_id(session_id)
    if not sid:
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        cwd: str | None = None
        try:
            row = con.execute(
                "SELECT directory FROM session WHERE id = ? LIMIT 1", (sid,)
            ).fetchone()
            if row and isinstance(row[0], str) and row[0].strip():
                cwd = row[0].strip()
        except sqlite3.Error:
            pass
        try:
            messages = con.execute(
                "SELECT id, data, time_created FROM message "
                "WHERE session_id = ? ORDER BY time_created ASC",
                (sid,),
            ).fetchall()
        except sqlite3.Error:
            return None
        turns: list[dict[str, str]] = []
        chars = 0
        for mid, data, _tc in messages:
            if len(turns) >= max_turns or chars >= max_chars:
                break
            try:
                meta = json.loads(data) if data else {}
            except json.JSONDecodeError:
                meta = {}
            if not isinstance(meta, dict):
                continue
            role = str(meta.get("role") or "").lower()
            if role not in ("user", "assistant"):
                continue
            if cwd is None:
                path_meta = meta.get("path")
                if isinstance(path_meta, dict):
                    for key in ("cwd", "root"):
                        raw = path_meta.get(key)
                        if isinstance(raw, str) and raw.strip():
                            cwd = raw.strip()
                            break
            texts: list[str] = []
            try:
                parts = con.execute(
                    "SELECT data FROM part WHERE message_id = ? "
                    "ORDER BY time_created ASC",
                    (mid,),
                ).fetchall()
            except sqlite3.Error:
                parts = []
            for (pdata_raw,) in parts:
                try:
                    pdata = json.loads(pdata_raw) if pdata_raw else {}
                except json.JSONDecodeError:
                    continue
                if not isinstance(pdata, dict):
                    continue
                chunk = _opencode_part_text(pdata)
                if chunk:
                    texts.append(chunk)
            content = "\n".join(texts).strip()
            if not content:
                continue
            turns.append({"role": role, "content": content})
            chars += len(content)
        if not turns and cwd is None:
            return None
        return {"turns": turns, "cwd": cwd, "git_branch": None}
    finally:
        con.close()


def _read_opencode_fs_transcript(
    store_dir: Path,
    session_id: str,
    *,
    max_turns: int,
    max_chars: int,
) -> dict[str, Any] | None:
    sid = sanitize_cli_session_id(session_id)
    if not sid:
        return None
    msg_dir = store_dir / "storage" / "message" / sid
    if not msg_dir.is_dir():
        return None
    cwd: str | None = None
    # session metadata may live under storage/session/<project>/<sid>
    try:
        for meta_path in store_dir.glob(f"storage/session/*/{sid}"):
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(meta, dict):
                    raw = meta.get("directory")
                    if isinstance(raw, str) and raw.strip():
                        cwd = raw.strip()
                        break
    except OSError:
        pass
    files = sorted(msg_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    # Prefer time.created inside JSON when present.
    loaded: list[tuple[int, dict[str, Any], Path]] = []
    for path in files:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(blob, dict):
            continue
        created = 0
        t = blob.get("time")
        if isinstance(t, dict) and isinstance(t.get("created"), (int, float)):
            created = int(t["created"])
        loaded.append((created, blob, path))
    loaded.sort(key=lambda row: row[0])
    turns: list[dict[str, str]] = []
    chars = 0
    part_root = store_dir / "storage" / "part"
    for _created, blob, _path in loaded:
        if len(turns) >= max_turns or chars >= max_chars:
            break
        role = str(blob.get("role") or "").lower()
        if role not in ("user", "assistant"):
            continue
        mid = str(blob.get("id") or "")
        texts: list[str] = []
        if mid:
            pdir = part_root / mid
            if pdir.is_dir():
                part_files = sorted(pdir.glob("*.json"))
                part_loaded: list[tuple[int, dict[str, Any]]] = []
                for pf in part_files:
                    try:
                        pdata = json.loads(pf.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if not isinstance(pdata, dict):
                        continue
                    pc = 0
                    pt = pdata.get("time")
                    if isinstance(pt, dict) and isinstance(pt.get("start"), (int, float)):
                        pc = int(pt["start"])
                    part_loaded.append((pc, pdata))
                part_loaded.sort(key=lambda row: row[0])
                for _pc, pdata in part_loaded:
                    chunk = _opencode_part_text(pdata)
                    if chunk:
                        texts.append(chunk)
        content = "\n".join(texts).strip()
        if not content:
            continue
        turns.append({"role": role, "content": content})
        chars += len(content)
    if not turns and cwd is None:
        return None
    return {"turns": turns, "cwd": cwd, "git_branch": None}


def read_opencode_transcript(
    store_dir: str | Path | None,
    session_id: str,
    *,
    max_turns: int = _TRANSCRIPT_MAX_TURNS,
    max_chars: int = _TRANSCRIPT_MAX_CHARS,
) -> dict[str, Any] | None:
    """Read opencode turns from ``opencode.db`` (preferred) or storage/ JSON."""
    if not store_dir:
        return None
    root = Path(store_dir).expanduser()
    db = _opencode_db_path(root)
    if db is not None:
        got = _read_opencode_db_transcript(
            db, session_id, max_turns=max_turns, max_chars=max_chars
        )
        if got is not None:
            return got
    return _read_opencode_fs_transcript(
        root, session_id, max_turns=max_turns, max_chars=max_chars
    )


# --- agy (protobuf-in-sqlite heuristic) ------------------------------------

# Observed step_type values in antigravity-cli conversation DBs.
_AGY_STEP_USER = 14
_AGY_STEP_ASSISTANT_FINAL = 132
_AGY_PRINTABLE_RE = re.compile(rb"[\x09\x0a\x0d\x20-\x7e]{16,}")


def _agy_printable_strings(blob: bytes | None) -> list[str]:
    if not blob:
        return []
    out: list[str] = []
    for match in _AGY_PRINTABLE_RE.finditer(blob):
        text = match.group().decode("utf-8", errors="replace").strip()
        if text:
            out.append(text)
    return out


def _agy_is_noise(text: str) -> bool:
    if not text or len(text) < 8:
        return True
    if text.startswith(("command(", "file:///", "http://", "https://", "$", "b$", "I/home")):
        return True
    if text.startswith(("{", "[")) and ("toolAction" in text or "AbsolutePath" in text):
        return True
    if "conversation_transcript" in text or text.endswith("/skills"):
        return True
    if re.fullmatch(r"[0-9a-fA-F-]{36}", text.strip("\"$")):
        return True
    if text.startswith("IThe stream was interrupted"):
        return True
    if re.fullmatch(r"-?\d{10,}", text):
        return True
    return False


def _agy_longest_repeated_chunk(text: str) -> str | None:
    """If agy embeds the same prompt twice in one printable run, peel it out."""
    n = len(text)
    best = None
    for size in range(min(n // 2, 4000), 19, -1):
        for i in range(0, n - 2 * size + 1):
            chunk = text[i : i + size]
            if _agy_is_noise(chunk):
                continue
            if text.find(chunk, i + size) != -1:
                return chunk
    return best


def _agy_user_text(strings: list[str]) -> str | None:
    cands = [s for s in strings if not _agy_is_noise(s) and len(s) >= 20]
    if not cands:
        return None
    # Prefer a chunk that appears twice (common agy protobuf shape).
    for s in sorted(cands, key=len, reverse=True):
        repeated = _agy_longest_repeated_chunk(s)
        if repeated:
            return repeated.strip() or None
    # Otherwise longest clean candidate.
    best = max(cands, key=len)
    return best.strip() or None


def _agy_assistant_text(strings: list[str]) -> str | None:
    for s in strings:
        # Final notify payload: {"Message":"..."}
        if '"Message"' in s or s.lstrip().startswith("{"):
            try:
                # May have leading junk before JSON object.
                start = s.find("{")
                end = s.rfind("}")
                if start >= 0 and end > start:
                    blob = json.loads(s[start : end + 1])
                    if isinstance(blob, dict):
                        msg = blob.get("Message") or blob.get("message")
                        if isinstance(msg, str) and msg.strip() and not _agy_is_noise(msg):
                            return msg.strip()
            except json.JSONDecodeError:
                pass
    cands = [s for s in strings if not _agy_is_noise(s) and len(s) >= 20]
    if not cands:
        return None
    best = max(cands, key=len)
    # Strip leading quote/markdown quote noise from notify formatting.
    best = best.lstrip("> ").strip()
    return best or None


def _agy_cwd_from_meta(con: sqlite3.Connection) -> str | None:
    try:
        row = con.execute(
            "SELECT data FROM trajectory_metadata_blob WHERE id = ? LIMIT 1",
            ("main",),
        ).fetchone()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    blob = row[0] if isinstance(row[0], (bytes, bytearray)) else bytes(str(row[0]), "utf-8")
    # Prefer explicit file:///home/... markers inside protobuf blobs.
    for match in re.finditer(rb"file://(/[A-Za-z0-9._/-]+)", blob):
        path = match.group(1).decode("utf-8", errors="replace")
        if path.startswith("/") and len(path) >= 2:
            return path
    return None
    if not row or not row[0]:
        return None
    blob = row[0] if isinstance(row[0], (bytes, bytearray)) else bytes(str(row[0]), "utf-8")
    # Prefer explicit file:///home/... markers inside protobuf blobs.
    for match in re.finditer(rb"file://(/[A-Za-z0-9._/-]+)", blob):
        path = match.group(1).decode("utf-8", errors="replace")
        if path.startswith("/") and "\x00" not in path:
            return path
    for s in _agy_printable_strings(blob):
        idx = s.find("file://")
        if idx < 0:
            continue
        path = s[idx + len("file://") :]
        if path.startswith("//"):
            path = path[1:]
        path = path.split()[0].strip("\"'")
        if path.startswith("/") and "\x00" not in path:
            return path
    return None
    if not row or not row[0]:
        return None
    for s in _agy_printable_strings(row[0]):
        if s.startswith("file:///"):
            path = s[len("file://") :]
            # file:///home/... → /home/...
            if path.startswith("//"):
                path = path[1:]
            if path.startswith("/") and "\x00" not in path:
                return path
    return None


def read_agy_transcript(
    store_dir: str | Path | None,
    session_id: str,
    *,
    max_turns: int = _TRANSCRIPT_MAX_TURNS,
    max_chars: int = _TRANSCRIPT_MAX_CHARS,
) -> dict[str, Any] | None:
    """Best-effort turns from agy ``<uuid>.db`` protobuf step payloads.

    Opens the sqlite read-only. Extracts printable user (step_type 14) and
    final assistant (step_type 132) text. Tool/thought chrome is skipped.
    """
    sid = sanitize_cli_session_id(session_id)
    if not sid or not store_dir:
        return None
    path = Path(store_dir).expanduser() / f"{sid}.db"
    if not path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        cwd = _agy_cwd_from_meta(con)
        try:
            rows = con.execute(
                "SELECT step_type, step_payload FROM steps ORDER BY idx ASC"
            ).fetchall()
        except sqlite3.Error:
            return None
        turns: list[dict[str, str]] = []
        chars = 0
        for step_type, payload in rows:
            if len(turns) >= max_turns or chars >= max_chars:
                break
            strings = _agy_printable_strings(payload)
            if step_type == _AGY_STEP_USER:
                text = _agy_user_text(strings)
                role = "user"
            elif step_type == _AGY_STEP_ASSISTANT_FINAL:
                text = _agy_assistant_text(strings)
                role = "assistant"
            else:
                continue
            if not text:
                continue
            # Deduplicate consecutive identical user prompts (agy stores twice).
            if turns and turns[-1]["role"] == role and turns[-1]["content"] == text:
                continue
            turns.append({"role": role, "content": text})
            chars += len(text)
        if not turns and cwd is None:
            return None
        return {"turns": turns, "cwd": cwd, "git_branch": None}
    finally:
        con.close()


# --- registry / dispatch ---------------------------------------------------

def _default_provider_store_dir(cli_name: str) -> str | Path | None:
    """Resolve on-disk store root for transcript readers (not list_argv gated)."""
    name = str(cli_name or "").strip().lower()
    env_map = {
        "agy": "SWARM_AGY_CONVERSATIONS_DIR",
        "qwen": "SWARM_QWEN_PROJECTS_DIR",
        "grok": "SWARM_GROK_SESSIONS_DIR",
        "opencode": "SWARM_OPENCODE_SHARE_DIR",
    }
    env_key = env_map.get(name)
    if env_key:
        env = os.environ.get(env_key, "").strip()
        if env:
            return os.path.expanduser(env)
    # Prefer catalog helper when it knows a store dir (agy / qwen).
    try:
        from swarm.core import cli_catalog

        catalog_dir = cli_catalog.list_sessions_store_dir(name, None)
        if catalog_dir:
            return catalog_dir
    except Exception:
        pass
    defaults = {
        "agy": DEFAULT_AGY_CONVERSATIONS_DIR,
        "qwen": DEFAULT_QWEN_PROJECTS_DIR,
        "grok": DEFAULT_GROK_SESSIONS_DIR,
        "opencode": DEFAULT_OPENCODE_SHARE_DIR,
    }
    raw = defaults.get(name)
    return os.path.expanduser(raw) if raw else None


PROVIDER_TRANSCRIPT_READERS: dict[str, TranscriptReader] = {
    "qwen": read_qwen_transcript,
    "agy": read_agy_transcript,
    "grok": read_grok_transcript,
    "opencode": read_opencode_transcript,
}


def read_provider_transcript(
    cli_name: str,
    session_id: str | None,
    store_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    """Best-effort provider transcript via the pluggable reader registry.

    Unknown CLIs (pi / kilo / …) return ``None`` — select proceeds without
    import (honest empty / unsupported). Registered readers return
    ``{turns, cwd, git_branch}`` or ``None`` when the native file is missing.
    """
    if not session_id:
        return None
    name = str(cli_name or "").strip().lower()
    reader = PROVIDER_TRANSCRIPT_READERS.get(name)
    if reader is None:
        return None
    if store_dir is None:
        store_dir = _default_provider_store_dir(name)
    try:
        return reader(store_dir, session_id)
    except Exception:
        logger.exception("Could not read %s transcript for %s", name, session_id)
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

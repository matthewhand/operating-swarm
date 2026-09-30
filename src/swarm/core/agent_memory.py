"""Per-agent memory store (#1390).

File-backed JSON so the memories API, pack export, and pack import share
one source of truth. Kinds ``profile`` and ``log`` travel in a template
pack; ``episode`` and ``note`` stay local and are ignored on pack.

Create rejects credential-shaped strings. Export/import run the scrubber
so packs never carry secrets, PII, or private links.

Layout::

    <user-config>/agent_memories.json

    {
      "schema": 1,
      "agents": {
        "<agent_id>": [
          {
            "id": "...",
            "kind": "profile",
            "title": "...",
            "body": "...",
            "created_at": "..."
          }
        ]
      }
    }

The routine Memories tool (#1404) stores its durable context in one
markdown document next to that store::

    <user-config>/routine_memories/<scope>/<filename>   (MEMORIES.md)

It is not a third memory store: same module, same config root, same
credential gate (``reject_credentials``), and every read/write goes
through ``FilesystemToolset`` — the one allow-listed path mechanism
``fs_introspect`` and the chat filesystem tools already use. See
:func:`run_memories_document_op`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from swarm.core.chat_store import normalize_agent_id
from swarm.core.filesystem_toolset import (
    READONLY,
    READWRITE,
    FilesystemError,
    FilesystemToolset,
)
from swarm.core.memory_scrubber import (
    reject_credentials,
    scrub_for_pack,
)
from swarm.core.paths import (
    ensure_swarm_directories_exist,
    get_user_config_dir_for_swarm,
)

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_MEMORIES_PATH = "SWARM_AGENT_MEMORIES_PATH"
STORE_NAME = "agent_memories.json"

KIND_PROFILE = "profile"
KIND_LOG = "log"
KIND_EPISODE = "episode"
KIND_NOTE = "note"

PACK_KINDS = frozenset({KIND_PROFILE, KIND_LOG})
LOCAL_KINDS = frozenset({KIND_EPISODE, KIND_NOTE})
ALL_KINDS = PACK_KINDS | LOCAL_KINDS

TIER_PACK = "pack"
TIER_LOCAL = "local"

PACK_OBJECT = "agent_memory_pack"
MAX_TITLE = 200
MAX_BODY = 16_384

_KIND_ALIASES = {
    "profile": KIND_PROFILE,
    "persona": KIND_PROFILE,
    "identity": KIND_PROFILE,
    "log": KIND_LOG,
    "journal": KIND_LOG,
    "episode": KIND_EPISODE,
    "episodic": KIND_EPISODE,
    "note": KIND_NOTE,
    "scratch": KIND_NOTE,
}

_TIER_ALIASES = {
    "pack": TIER_PACK,
    "shareable": TIER_PACK,
    "template": TIER_PACK,
    "export": TIER_PACK,
    "local": TIER_LOCAL,
    "private": TIER_LOCAL,
}

_cache: dict[str, Any] | None = None
_cache_stamp: tuple[int, int] | None = None
_LOCK_TIMEOUT_SECONDS = 10


def memories_path() -> Path:
    """Path of the agent-memories JSON file."""
    env = (os.environ.get(ENV_MEMORIES_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / STORE_NAME


def reset_memories_cache() -> None:
    """Drop the in-process cache (tests)."""
    global _cache, _cache_stamp
    _cache = None
    _cache_stamp = None


def kind_tier(kind: str) -> str:
    return TIER_PACK if kind in PACK_KINDS else TIER_LOCAL


def normalize_kind(value: Any, *, default: str | None = None) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        if default in ALL_KINDS:
            return default
        raise ValueError("kind is required (profile, log, episode, or note).")
    mapped = _KIND_ALIASES.get(text)
    if mapped:
        return mapped
    raise ValueError("kind must be profile, log, episode, or note.")


def normalize_tier(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        return None
    mapped = _TIER_ALIASES.get(text)
    if mapped:
        return mapped
    if text in ALL_KINDS or text in _KIND_ALIASES:
        return None
    raise ValueError("tier must be pack or local.")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "agents": {}}


def _file_stamp(path: Path) -> tuple[int, int] | None:
    try:
        if not path.is_file():
            return None
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def _publish(store: dict[str, Any], stamp: tuple[int, int] | None) -> dict[str, Any]:
    global _cache, _cache_stamp
    _cache = store
    _cache_stamp = stamp
    return store


def _remember(store: dict[str, Any], path: Path) -> dict[str, Any]:
    """Publish *store* after this process replaced the file."""
    return _publish(store, _file_stamp(path))


def _load_store() -> dict[str, Any]:
    """Read the JSON file. An unreadable file is an error, not an empty store."""
    path = memories_path()
    if not path.is_file():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read agent memories at %s (%s)", path, exc)
        raise OSError("Could not read agent memories.") from exc
    if not isinstance(data, dict):
        raise OSError("Could not read agent memories.")
    agents = data.get("agents", {})
    if not isinstance(agents, dict):
        raise OSError("Could not read agent memories.")
    return {"schema": SCHEMA, "agents": dict(agents)}


def _read_store() -> dict[str, Any]:
    path = memories_path()
    stamp = _file_stamp(path)
    if _cache is not None and _cache_stamp == stamp:
        return _cache
    store = _load_store()
    if _file_stamp(path) != stamp:
        # The file changed while we were reading. Don't pin these bytes
        # under either stamp: the pre-read stamp is already stale, and the
        # post-read stamp belongs to bytes we did not load.
        return store
    return _publish(store, stamp)


def _write_store(store: dict[str, Any]) -> None:
    path = memories_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "agents": store.get("agents") or {}}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _remember(payload, path)


def _mutate_store(mutator):
    """Reload from disk under a file lock, then persist if *mutator* dirties it.

    The in-process cache is not the source of truth for writes. Another
    worker can hold a stale cache; applying that cache would drop rows.
    """
    path = memories_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(f"{path}.lock", timeout=_LOCK_TIMEOUT_SECONDS)
    try:
        with lock:
            store = _load_store()
            result, dirty = mutator(store)
            if dirty:
                _write_store(store)
            else:
                _remember(store, path)
            return result
    except Timeout as exc:
        raise OSError("Could not lock agent memories.") from exc


def public_memory(raw: dict[str, Any] | None = None, *, agent_id: str = "") -> dict[str, Any]:
    incoming = raw if isinstance(raw, dict) else {}
    kind = normalize_kind(incoming.get("kind"), default=KIND_PROFILE)
    title = reject_credentials(str(incoming.get("title") or "").strip(), "title")[:MAX_TITLE]
    body = incoming.get("body")
    if body is None:
        body = incoming.get("content") or incoming.get("text") or ""
    body = reject_credentials(str(body), "body")
    if len(body) > MAX_BODY:
        raise ValueError(f"body must be at most {MAX_BODY} characters.")
    if not title and not body.strip():
        raise ValueError("title or body is required.")
    created = str(incoming.get("created_at") or "").strip() or _now_iso()
    return {
        "id": str(incoming.get("id") or "").strip() or _new_id(),
        "agent_id": normalize_agent_id(agent_id or incoming.get("agent_id")),
        "kind": kind,
        "tier": kind_tier(kind),
        "title": title,
        "body": body,
        "created_at": created,
    }


def _stored_row(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": memory["id"],
        "kind": memory["kind"],
        "title": memory["title"],
        "body": memory["body"],
        "created_at": memory["created_at"],
    }


def _parse_filter_tokens(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        parts = [str(item).strip() for item in raw]
    else:
        parts = [part.strip() for part in str(raw).split(",")]
    return [part for part in parts if part]


def _kinds_for_tokens(tokens: list[str]) -> set[str]:
    wanted: set[str] = set()
    for token in tokens:
        lowered = token.lower().replace("-", "_")
        mapped_tier = _TIER_ALIASES.get(lowered)
        if mapped_tier == TIER_PACK:
            wanted.update(PACK_KINDS)
            continue
        if mapped_tier == TIER_LOCAL:
            wanted.update(LOCAL_KINDS)
            continue
        wanted.add(normalize_kind(token))
    return wanted


def resolve_kind_filter(*, kind: Any = None, tier: Any = None) -> frozenset[str] | None:
    """Return the kinds a list/export should include, or None for all.

    ``kind`` and ``tier`` intersect. An empty intersection is an empty set,
    not "all kinds".
    """
    kind_tokens = _parse_filter_tokens(kind)
    tier_tokens = _parse_filter_tokens(tier)
    if not kind_tokens and not tier_tokens:
        return None
    kind_set = _kinds_for_tokens(kind_tokens) if kind_tokens else None
    tier_set = _kinds_for_tokens(tier_tokens) if tier_tokens else None
    if kind_set is not None and tier_set is not None:
        return frozenset(kind_set & tier_set)
    chosen = kind_set if kind_set is not None else tier_set
    return frozenset(chosen or ())


def list_memories(
    agent_id: str,
    *,
    kind: Any = None,
    tier: Any = None,
) -> list[dict[str, Any]]:
    agent = normalize_agent_id(agent_id)
    allowed = resolve_kind_filter(kind=kind, tier=tier)
    rows: list[dict[str, Any]] = []
    for item in _read_store()["agents"].get(agent) or []:
        if not isinstance(item, dict):
            continue
        try:
            memory = public_memory(item, agent_id=agent)
        except ValueError:
            continue
        if allowed is not None and memory["kind"] not in allowed:
            continue
        rows.append(memory)
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return rows


def get_memory(agent_id: str, memory_id: str) -> dict[str, Any] | None:
    needle = str(memory_id or "").strip()
    if not needle:
        return None
    for row in list_memories(agent_id):
        if row["id"] == needle:
            return row
    return None


def _append_rows(
    store: dict[str, Any],
    agent: str,
    memories: list[dict[str, Any]],
) -> None:
    agents = dict(store.get("agents") or {})
    rows = [item for item in (agents.get(agent) or []) if isinstance(item, dict)]
    rows.extend(_stored_row(memory) for memory in memories)
    agents[agent] = rows
    store["agents"] = agents


def create_memory(agent_id: str, incoming: dict[str, Any] | None) -> dict[str, Any]:
    agent = normalize_agent_id(agent_id)
    payload = dict(incoming) if isinstance(incoming, dict) else {}
    payload.pop("id", None)
    payload.pop("created_at", None)
    memory = public_memory(payload, agent_id=agent)

    def mutator(store: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        _append_rows(store, agent, [memory])
        return memory, True

    return _mutate_store(mutator)


def delete_memory(agent_id: str, memory_id: str) -> bool:
    agent = normalize_agent_id(agent_id)
    needle = str(memory_id or "").strip()
    if not needle:
        return False

    def mutator(store: dict[str, Any]) -> tuple[bool, bool]:
        agents = dict(store.get("agents") or {})
        rows = [item for item in (agents.get(agent) or []) if isinstance(item, dict)]
        kept = [item for item in rows if str(item.get("id") or "") != needle]
        if len(kept) == len(rows):
            return False, False
        if kept:
            agents[agent] = kept
        else:
            agents.pop(agent, None)
        store["agents"] = agents
        return True, True

    return _mutate_store(mutator)


def _pack_row(memory: dict[str, Any]) -> dict[str, Any] | None:
    if memory.get("kind") not in PACK_KINDS:
        return None
    title = scrub_for_pack(str(memory.get("title") or ""))
    body = scrub_for_pack(str(memory.get("body") or ""))
    if not title and not body:
        return None
    return {"kind": memory["kind"], "title": title, "body": body}


def export_pack_fragment(agent_id: str) -> dict[str, Any]:
    """Shareable template fragment: profile + log only, scrubbed."""
    memories = []
    for row in list_memories(agent_id, tier=TIER_PACK):
        packed = _pack_row(row)
        if packed:
            memories.append(packed)
    return {
        "object": PACK_OBJECT,
        "schema": SCHEMA,
        "memories": memories,
    }


def _coerce_pack_rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        items = raw.get("memories")
        if items is None:
            items = raw.get("items") or raw.get("data")
        if items is None and raw.get("kind"):
            items = [raw]
    else:
        items = raw
    if not isinstance(items, list):
        raise ValueError("pack fragment must include a memories list.")
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _prepare_pack_row(item: dict[str, Any]) -> dict[str, Any] | None:
    """One importable profile/log row, or None when the row must be ignored."""
    raw_kind = item.get("kind")
    if raw_kind is None or not str(raw_kind).strip():
        return None
    try:
        kind = normalize_kind(raw_kind)
    except ValueError:
        return None
    if kind not in PACK_KINDS:
        return None
    title = scrub_for_pack(str(item.get("title") or ""))
    body = item.get("body")
    if body is None:
        body = item.get("content") or item.get("text") or ""
    body = scrub_for_pack(str(body))
    if not title and not body:
        return None
    return {"kind": kind, "title": title, "body": body}


def import_pack_fragment(
    agent_id: str,
    raw: Any,
) -> list[dict[str, Any]]:
    """Write scrubbed pack memories onto *agent_id* in one store update.

    Episode, note, and rows with no kind are ignored. A missing kind does
    not default to profile.
    """
    agent = normalize_agent_id(agent_id)
    prepared: list[dict[str, Any]] = []
    for item in _coerce_pack_rows(raw):
        row = _prepare_pack_row(item)
        if row:
            prepared.append(row)
    if not prepared:
        return []
    memories = [public_memory(row, agent_id=agent) for row in prepared]

    def mutator(store: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        _append_rows(store, agent, memories)
        return memories, True

    return _mutate_store(mutator)


def _stored_row_is_pack(item: dict[str, Any]) -> bool:
    try:
        kind = normalize_kind(item.get("kind"))
    except ValueError:
        return False
    return kind in PACK_KINDS


def replace_pack_fragment(
    agent_id: str,
    raw: Any,
) -> list[dict[str, Any]]:
    """Replace pack-tier rows in one locked write. Episode and note rows stay.

    ``public_memory`` runs before the store is opened, so a rejected body
    cannot delete the previous pack rows. The disk file is the source of
    truth: a stale in-process cache is not the list of ids to delete.
    """
    agent = normalize_agent_id(agent_id)
    prepared: list[dict[str, Any]] = []
    for item in _coerce_pack_rows(raw):
        row = _prepare_pack_row(item)
        if row:
            prepared.append(row)
    memories = [public_memory(row, agent_id=agent) for row in prepared]

    def mutator(store: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        agents = dict(store.get("agents") or {})
        rows = [item for item in (agents.get(agent) or []) if isinstance(item, dict)]
        kept = [item for item in rows if not _stored_row_is_pack(item)]
        if not memories and len(kept) == len(rows):
            return [], False
        kept.extend(_stored_row(memory) for memory in memories)
        if kept:
            agents[agent] = kept
        else:
            agents.pop(agent, None)
        store["agents"] = agents
        return memories, True

    return _mutate_store(mutator)


# --- routine memories document (#1404) ----------------------------------
#
# The Memories tool in the routine builder points at ONE markdown file that
# carries durable context between runs. Two rules keep it boring:
#
# 1. Only the *filename* is operator/model configuration, and it must be a
#    bare name. The directory is derived from a validated scope segment, so
#    no caller can spell a path.
# 2. Every read, write, stat, and delete goes through ``FilesystemToolset``
#    (the allow-list the fs_introspect blueprint and the chat filesystem
#    tools already use). That resolves symlinks, so a link pointing out of
#    the memories root is refused instead of followed.

MEMORIES_DOC_DIRNAME = "routine_memories"
DEFAULT_MEMORIES_FILENAME = "MEMORIES.md"
DEFAULT_MEMORIES_SCOPE = "routine"
MEMORIES_DOC_OPS: tuple[str, ...] = ("create", "read", "update", "delete")
# Same ceiling as a memory body: the document is injected into the run prompt,
# so it has to stay inside one context window.
MAX_MEMORIES_CONTENT = MAX_BODY

# One shape for every path segment this module accepts: a bare name. No
# separator, no leading dot (so ``..``, ``.`` and ``.env`` cannot be spelled),
# no drive letter, no ``~``, no control characters.
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

ERROR_MEMORIES_DENIED = "memories path is not allowed"
ERROR_MEMORIES_MISSING = "memories file not found"
ERROR_MEMORIES_EXISTS = "memories file already exists"
ERROR_MEMORIES_NOT_A_FILE = "memories path is not a file"
ERROR_MEMORIES_UNWRITABLE = "could not write memories file"
ERROR_MEMORIES_UNDELETABLE = "could not delete memories file"

# ``FilesystemToolset.read`` marks a capped read with this suffix.
_TRUNCATION_SUFFIX = "\n…[truncated]"


def _path_segment(raw: Any, field: str) -> str:
    """Validate one bare path segment or raise ``ValueError``.

    Rejects, in order: empty, ``.``/``..``/dotfiles, any path separator,
    absolute paths and ``~`` expansion, then anything outside
    ``[A-Za-z0-9][A-Za-z0-9._-]*``. The message names the field only — never
    the rejected value, which came from a model or an API caller.
    """
    text = str(raw if raw is not None else "").strip()
    if not text:
        raise ValueError(f"{field} is required.")
    if any(sep and sep in text for sep in (os.sep, os.altsep, "/", "\\")):
        raise ValueError(f"{field} must be a bare filename with no path separator.")
    if text.startswith("."):
        raise ValueError(f"{field} must not be '.' or a dotfile name.")
    if os.path.isabs(text) or text.startswith("~"):
        raise ValueError(f"{field} must be a bare filename, not a path.")
    if not _PATH_SEGMENT_RE.match(text):
        raise ValueError(
            f"{field} must start with a letter or digit and use only "
            "letters, digits, dot, hyphen, or underscore (max 128)."
        )
    return text


def normalize_memories_filename(raw: Any = None) -> str:
    """Validated memories filename. Missing (``None``) → ``MEMORIES.md``.

    An explicitly empty or blank name is an error, not a silent default: a
    builder that drops the filename must say so.
    """
    if raw is None:
        return DEFAULT_MEMORIES_FILENAME
    return _path_segment(raw, "memories filename")


def normalize_memories_scope(raw: Any = None) -> str:
    """Validated directory segment the document lives in. Blank → default."""
    if raw is None or not str(raw).strip():
        return DEFAULT_MEMORIES_SCOPE
    return _path_segment(raw, "memories scope")


def memories_document_root() -> Path:
    """The only directory the memories tool may touch.

    Deliberately narrower than ``FilesystemToolset.default_roots()`` (the whole
    config root): a memory document must not be able to reach
    ``swarm_config.json`` or a ``.env`` sitting next to it.
    """
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / MEMORIES_DOC_DIRNAME


def memories_document_dir(scope: Any = None) -> Path:
    return memories_document_root() / normalize_memories_scope(scope)


def memories_document_path(filename: Any = None, *, scope: Any = None) -> Path:
    return memories_document_dir(scope) / normalize_memories_filename(filename)


def _memories_toolset(*, write: bool = False) -> FilesystemToolset:
    """``FilesystemToolset`` scoped to the memories root. Least privilege."""
    return FilesystemToolset(
        permission=READWRITE if write else READONLY,
        allowed_paths=[str(memories_document_root())],
    )


def _document_state(path: Path) -> str:
    """``file`` | ``missing`` | ``denied`` | ``other`` — resolved *through*
    the toolset, so a symlink escape reads as ``denied`` and is never followed.

    No exception detail crosses this boundary: ``PathNotAllowed`` names the
    allow-listed roots and this payload goes back to a model.
    """
    try:
        info = _memories_toolset().stat(str(path))
    except FilesystemError:
        # PathNotAllowed / SensitivePathDenied / PermissionDenied.
        return "denied"
    except (FileNotFoundError, NotADirectoryError):
        return "missing"
    except OSError:
        return "missing"
    return "file" if info.get("type") == "file" else "other"


def _doc_result(
    operation: str,
    filename: str,
    *,
    ok: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    return {"ok": ok, "operation": operation, "filename": filename, **extra}


def _state_error(
    operation: str,
    filename: str,
    state: str,
    *,
    exists: bool = False,
) -> dict[str, Any]:
    if exists:
        # ``create`` over a live document. Not an error about the path.
        error = ERROR_MEMORIES_EXISTS
    elif state == "denied":
        error = ERROR_MEMORIES_DENIED
    elif state == "missing":
        error = ERROR_MEMORIES_MISSING
    else:
        error = ERROR_MEMORIES_NOT_A_FILE
    return _doc_result(operation, filename, ok=False, error=error)


def read_memories_document(
    *,
    filename: Any = None,
    scope: Any = None,
) -> dict[str, Any]:
    """Read the memories document. A missing file is a result, not an exception."""
    name = normalize_memories_filename(filename)
    path = memories_document_path(name, scope=scope)
    state = _document_state(path)
    if state != "file":
        return _state_error("read", name, state)
    try:
        text = _memories_toolset().read(str(path))
    except FilesystemError:
        return _state_error("read", name, "denied")
    except OSError:
        return _state_error("read", name, "missing")
    truncated = text.endswith(_TRUNCATION_SUFFIX)
    if truncated:
        text = text[: -len(_TRUNCATION_SUFFIX)]
    return _doc_result(
        "read",
        name,
        path=str(path),
        content=text,
        chars=len(text),
        truncated=truncated,
    )


def write_memories_document(
    *,
    content: Any = "",
    filename: Any = None,
    scope: Any = None,
    create_only: bool = False,
) -> dict[str, Any]:
    """Write the memories document (``create`` refuses to clobber).

    Content goes through the same credential gate as ``create_memory``: a
    memory blob holding a token is refused, not silently redacted, because a
    redacted memory is a lie the next run would act on.
    """
    name = normalize_memories_filename(filename)
    operation = "create" if create_only else "update"
    body = reject_credentials(str(content if content is not None else ""), "memories content")
    if len(body) > MAX_MEMORIES_CONTENT:
        raise ValueError(f"memories content must be at most {MAX_MEMORIES_CONTENT} characters.")
    path = memories_document_path(name, scope=scope)
    state = _document_state(path)
    if state == "denied":
        return _state_error(operation, name, "denied")
    if create_only and state == "file":
        return _state_error(operation, name, state, exists=True)
    if not create_only and state != "file":
        return _state_error(operation, name, state)
    try:
        info = _memories_toolset(write=True).write(str(path), body)
    except FilesystemError:
        return _state_error(operation, name, "denied")
    except OSError:
        logger.warning("Could not write routine memories document %s", name)
        return _doc_result(operation, name, ok=False, error=ERROR_MEMORIES_UNWRITABLE)
    return _doc_result(
        operation,
        name,
        path=info.get("path") or str(path),
        chars=len(body),
        bytes=info.get("bytes", len(body.encode("utf-8", "replace"))),
    )


def delete_memories_document(
    *,
    filename: Any = None,
    scope: Any = None,
) -> dict[str, Any]:
    """Delete the memories document.

    ``FilesystemToolset`` has no delete op, so the unlink is guarded by two of
    its public calls: ``stat`` proves the *resolved* file and the *resolved*
    parent directory both sit inside the memories root. ``os.unlink`` never
    follows the final symlink, so at worst it removes a link — never a file
    outside the root.
    """
    name = normalize_memories_filename(filename)
    path = memories_document_path(name, scope=scope)
    state = _document_state(path)
    if state != "file":
        return _state_error("delete", name, state)
    try:
        _memories_toolset().stat(str(path.parent))
    except (FilesystemError, OSError):
        return _state_error("delete", name, "denied")
    try:
        os.unlink(path)
    except OSError:
        logger.warning("Could not delete routine memories document %s", name)
        return _doc_result("delete", name, ok=False, error=ERROR_MEMORIES_UNDELETABLE)
    return _doc_result("delete", name, path=str(path), deleted=True)


def run_memories_document_op(
    operation: Any,
    *,
    content: Any = "",
    filename: Any = None,
    scope: Any = None,
) -> dict[str, Any]:
    """Dispatch one Memories operation. Never raises for caller input.

    A bad filename, an out-of-root path, or a missing file comes back as
    ``{"ok": False, "error": ...}`` so a tool call gets an answer it can act
    on instead of a traceback.
    """
    op = str(operation or "").strip().lower().replace("-", "_")[:32]
    try:
        name = normalize_memories_filename(filename)
    except ValueError as exc:
        return _doc_result(
            op or "memories",
            str(filename if filename is not None else "")[:64],
            ok=False,
            error=str(exc),
        )
    if op not in MEMORIES_DOC_OPS:
        return _doc_result(
            op or "memories",
            name,
            ok=False,
            error="operation must be create, read, update, or delete.",
        )
    try:
        if op == "read":
            return read_memories_document(filename=name, scope=scope)
        if op == "delete":
            return delete_memories_document(filename=name, scope=scope)
        return write_memories_document(
            content=content,
            filename=name,
            scope=scope,
            create_only=op == "create",
        )
    except ValueError as exc:
        # Credential-shaped or oversized content. The message names the field,
        # never the body.
        logger.info("Memories tool refused %s: %s", op, exc)
        return _doc_result(op, name, ok=False, error=str(exc))
    except OSError:
        logger.warning("Memories tool %s failed on %s", op, name)
        return _doc_result(op, name, ok=False, error=ERROR_MEMORIES_UNWRITABLE)

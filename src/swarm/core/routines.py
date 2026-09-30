"""Per-agent Routines store (REQ-80 / #432, REQ-884 / #285, #222).

File-backed JSON so the computer-icon pane, Test run, GitHub events,
time-based schedules, and mailbox triggers share one source of truth.
Instruction is the runtime prompt, not UI chrome. ``model`` is an optional
seat/profile id (existing OS model field). ``active`` is the armed flag —
Inactive drafts persist without firing. Test run is a dry-run preview of
trigger match + prompt; it never sends messages or merges PRs. No live
GitHub HTTP, no Neon. Schema 2 is backward-compatible with schema 1 files.

Trigger kinds: ``github_pr_merged``, ``github_event``, ``interval``,
``cron``, ``one_shot``, ``mailbox_message``.

Schedules tick inside the Django process (see ``schedule_engine``). No
distributed claims. No secrets in the store.

Concurrency (#1666): the store is a shared file, so every read-modify-write
goes through :func:`_mutate_store` — reload from disk under a ``FileLock``,
mutate, write — and the in-process cache is never the base of a write. Two
sidecars live next to it, each with its own sibling lock file: ``.lock``
(the store lock) and ``agent_routines.webhook_deliveries.json`` (#1667, the
GitHub delivery dedupe record).

Layout::

    <user-config>/agent_routines.json
    <user-config>/agent_routines.json.lock
    <user-config>/agent_routines.json.webhook_deliveries.json

    {
      "schema": 2,
      "agents": {
        "<agent_id>": [
          {
            "id": "...",
            "slug": "...",
            "name": "...",
            "description": "...",
            "instruction": "...",
            "active": true,
            "enabled": true,
            "model": "",
            "next_run": "...",
            "tools": ["open_pull_request"],
            "tools_explicit": false,
            "trigger": {
              "kind": "interval",
              "seconds": 3600
            },
            "history": [
              {
                "id": "...",
                "ran_at": "...",
                "status": "success",
                "source": "run_now",
                "duration_ms": 12,
                "token_cost": 0
              }
            ]
          }
        ]
      }
    }
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
import weakref
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import (
    ensure_swarm_directories_exist,
    get_user_config_dir_for_swarm,
)
from swarm.core.routine_tools import (
    TOOL_OPEN_PULL_REQUEST,
    open_pr_context_from_github_event,
    public_routine_tools,
    reset_open_pr_runner,
    reset_plugin_runtime_applier,
    run_open_pr_if_enabled,
)
from swarm.core.schedule_triggers import (
    ROUTINE_TRIGGER_KINDS,
    TIME_TRIGGER_KINDS,
    TRIGGER_CRON,
    TRIGGER_INTERVAL,
    TRIGGER_MAILBOX_MESSAGE,
    TRIGGER_ONE_SHOT,
    compute_next_run,
    is_due,
    mailbox_event_matches,
    parse_dt,
    public_history_extras,
    public_time_trigger,
    reject_secrets,
    time_trigger_summary,
    to_iso,
    utcnow,
)

logger = logging.getLogger(__name__)

SCHEMA = 2
ENV_ROUTINES_PATH = "SWARM_AGENT_ROUTINES_PATH"
ENV_GITHUB_WEBHOOK_SECRET = "GITHUB_WEBHOOK_SECRET"
TRIGGER_GITHUB_PR_MERGED = "github_pr_merged"
TRIGGER_GITHUB_EVENT = "github_event"
EVENT_MERGED = "merged"
ACTOR_ANYONE = "anyone"
SOURCE_TEST_RUN = "test_run"
SOURCE_RUN_NOW = "run_now"
SOURCE_GITHUB_PR_MERGED = "github_pr_merged"
SOURCE_GITHUB_WEBHOOK = "github_webhook"
SOURCE_MAILBOX_MESSAGE = "mailbox_message"
SOURCE_SCHEDULE = "schedule"
HISTORY_STATUS_SUCCESS = "success"
HISTORY_STATUS_ERROR = "error"
DRY_RUN_SIDE_EFFECTS = "none"
DRY_RUN_NOTE = (
    "Dry-run preview. No messages sent, no PRs merged, instruction not executed."
)
GITHUB_WEBHOOK_USER_KEY = "github-webhook"
GITHUB_EVENT_TYPES = frozenset(
    {
        "issues.opened",
        "issues.assigned",
        "issue_comment.created",
        "pull_request.opened",
        "pull_request.review_requested",
        "push",
    }
)
GITHUB_OBJECT_ISSUE = "issue"
GITHUB_OBJECT_PULL_REQUEST = "pull_request"
GITHUB_OBJECT_KINDS = frozenset({GITHUB_OBJECT_ISSUE, GITHUB_OBJECT_PULL_REQUEST})

_OWNER_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
# Pack fill-ins (#1394): {{owner_repo}} is a slot, not a live GitHub repo.
FILL_IN_TOKEN_RE = re.compile(r"^\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}$")
FILL_IN_SCAN_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
OWNER_REPO_FILL_IN = "{{owner_repo}}"


def fill_in_token(value: Any) -> str | None:
    """Return a canonical ``{{key}}`` token, or None if *value* is not one."""
    match = FILL_IN_TOKEN_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    return "{{" + match.group(1) + "}}"


_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def normalize_slug(value: Any) -> str:
    """Pack slug: lowercase, underscores kept, other runs become hyphens."""
    text = str(value or "").strip().lower()
    text = _SLUG_RE.sub("-", text).strip("-")
    return text[:80]


def routine_fill_in_keys(routine: dict[str, Any] | None) -> list[str]:
    """Ordered ``{{key}}`` names still present on a routine."""
    row = routine if isinstance(routine, dict) else {}
    found: list[str] = []

    def _add(text: Any) -> None:
        for match in FILL_IN_SCAN_RE.finditer(str(text or "")):
            key = match.group(1)
            if key not in found:
                found.append(key)

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                _walk(child)
        elif isinstance(value, list):
            for item in value:
                _walk(item)
        else:
            _add(value)

    _add(row.get("name"))
    _add(row.get("instruction"))
    _add(row.get("description"))
    _walk(row.get("trigger"))
    return found


def assert_fill_ins_allow_enable(routine: dict[str, Any]) -> None:
    """Refuse to arm a routine that still has ``{{fill_in}}`` slots (#1394)."""
    if not routine.get("active"):
        return
    keys = routine_fill_in_keys(routine)
    if keys:
        listed = ", ".join(keys)
        raise ValueError(
            f"Cannot enable while fill-ins remain: {listed}. "
            "Supply fill-ins, then PATCH active or enabled true."
        )


_FILL_IN_FIELD_KEYS = {
    "owner_repo": "owner_repo",
    "repository": "owner_repo",
    "repo": "owner_repo",
    "channel": "channel",
    "channel_id": "channel",
    "channelId": "channel",
}


def _attach_channel(trigger: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Keep an optional channel id on trigger metadata (no secrets)."""
    raw = incoming.get("channel")
    if raw is None or not str(raw).strip():
        raw = incoming.get("channel_id", incoming.get("channelId"))
    if raw is None or not str(raw).strip():
        return trigger
    text = reject_secrets(str(raw).strip(), "channel")
    token = fill_in_token(text)
    if token:
        text = token
    return {**trigger, "channel": text}


def _coerce_flag(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off", ""):
            return False
    raise ValueError(f"{field} must be a boolean.")

_cache: dict[str, Any] | None = None
_cache_stamp: tuple[int, int] | None = None
_fired_prompts: list[dict[str, str]] = []
InstructionRunner = Callable[[str, str, str], None]
_instruction_runner: InstructionRunner | None = None
# #1666: the store is a shared JSON file, and two writers routinely touch it at
# once — a tick-driven fire and an operator PATCH/"Run now" in the same second.
# Both read-modify-write the same rows, so the writer that finishes second
# publishes a snapshot that never saw the first writer's edit and the edit is
# lost. The lost field is usually a ``status``/``last_run``, so it reads as
# "the run never happened" rather than as corruption.
#
# ``_settlement_lock`` (seat-budget accounting) does NOT cover this: it is a
# ``threading.RLock``, so it serialises only inside one process, and it only
# wraps ``append_history``/``settle_routine_tokens`` — the operator PATCH path
# never took it. Every read-modify-write therefore goes through
# :func:`_mutate_store` instead, which holds the store's file lock across the
# read *and* the write and reloads from disk rather than trusting the cache.
#
# The same shape as ``agent_memory`` (sibling ``.lock``, ``Timeout`` surfaced as
# ``OSError``), with one instance per path instead of one per call so a nested
# write re-enters its own lock instead of deadlocking on it.
#
# Lock order is always ``_settlement_lock`` then the store file lock, and a
# mutator never calls back into a public writer, so the two cannot deadlock.
_LOCK_TIMEOUT_SECONDS = 10
# Guards the lock-instance table below, not the store itself.
_store_guard = threading.RLock()
# Weak so a test that repoints SWARM_AGENT_ROUTINES_PATH does not accumulate
# lock objects; the caller's own reference keeps a held lock alive.
_store_locks: weakref.WeakValueDictionary[str, FileLock] = weakref.WeakValueDictionary()


def routines_path() -> Path:
    """Path of the agent-routines JSON file."""
    env = (os.environ.get(ENV_ROUTINES_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "agent_routines.json"


def routines_lock_path(path: Path | None = None) -> Path:
    """Sibling ``.lock`` file for the routines store (the ``agent_memory`` shape)."""
    return Path(f"{path or routines_path()}.lock")


def _file_lock_for(path: Path) -> FileLock:
    """One ``FileLock`` per path, shared by every writer in this process.

    One instance per path (not one per call) because ``FileLock`` counts
    re-entry per thread: a nested write that built a second instance for the
    same file would block on a lock the same thread already holds. Callers hold
    the returned reference for the duration of the ``with`` block, so a live
    lock is never collected. The timeout is passed per acquire, not baked into
    the instance, so it stays a module-level knob.
    """
    key = str(path)
    with _store_guard:
        lock = _store_locks.get(key)
        if lock is None:
            lock = FileLock(str(routines_lock_path(path)))
            _store_locks[key] = lock
        return lock


@contextlib.contextmanager
def _locked_file(path: Path, *, busy: str):
    """Hold *path*'s sibling lock, serialising across threads *and* processes.

    A lock that cannot be taken inside ``_LOCK_TIMEOUT_SECONDS`` raises
    ``OSError`` so a contended write fails loudly instead of clobbering rows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = _file_lock_for(path)
    try:
        lock.acquire(timeout=_LOCK_TIMEOUT_SECONDS)
    except Timeout as exc:
        raise OSError(busy) from exc
    try:
        yield
    finally:
        lock.release()


def reset_routines_cache() -> None:
    """Drop the in-process cache, fired-prompt log, and live-job state (tests)."""
    global _cache, _cache_stamp
    _cache = None
    _cache_stamp = None
    _fired_prompts.clear()
    _live_job_log.clear()
    _live_job_threads.clear()
    with _settlement_lock:
        _settlements.clear()
        _pending_usage.clear()
    reset_open_pr_runner()
    reset_plugin_runtime_applier()


def set_instruction_runner(runner: InstructionRunner | None) -> None:
    """Install a hook used when a routine fires (Test run or merge)."""
    global _instruction_runner
    _instruction_runner = runner


def fired_prompts() -> list[dict[str, str]]:
    """Prompts recorded as this agent's instruction (no live LLM)."""
    return list(_fired_prompts)


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "agents": {}}


def _file_stamp(path: Path) -> tuple[int, int] | None:
    """``(mtime_ns, size)`` of *path*, or None when it does not exist."""
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size)


def _publish(store: dict[str, Any], path: Path) -> dict[str, Any]:
    """Cache *store* only while the file still carries the stamp we read."""
    global _cache, _cache_stamp
    _cache = store
    _cache_stamp = _file_stamp(path)
    return store


def _load_store() -> dict[str, Any]:
    """Read the store from disk. An unreadable file is an error, not an empty one.

    A read-modify-write must never publish an empty store over rows it failed
    to load — that is how a transient read error deletes every routine — so this
    raises. :func:`_read_store` keeps the lenient read for listings.
    """
    path = routines_path()
    if not path.is_file():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read agent routines at %s (%s)", path, exc)
        raise OSError("Could not read agent routines.") from exc
    if not isinstance(data, dict):
        raise OSError("Could not read agent routines.")
    agents = data.get("agents")
    return {
        "schema": SCHEMA,
        "agents": dict(agents) if isinstance(agents, dict) else {},
    }


def _read_store() -> dict[str, Any]:
    """Read the store for listing, reusing the cache only while it is current.

    The stamp is what makes another process's write visible. A cached store
    whose file changed underneath it is stale, and a stale read is how a lost
    update presents as "the run never happened".
    """
    path = routines_path()
    stamp = _file_stamp(path)
    if _cache is not None and _cache_stamp == stamp:
        return _cache
    try:
        store = _load_store()
    except OSError:
        logger.warning("Could not read agent routines at %s", path, exc_info=True)
        return _publish(_empty_store(), path)
    return _publish(store, path)


def _mutate_store(mutator):
    """Reload from disk under the store lock, then persist if *mutator* dirties it.

    The in-process cache is not the source of truth for a write: another process
    can hold rows this one has never seen, and writing a cache-derived snapshot
    drops them. A read-only mutator returns ``(result, False)`` and the freshly
    loaded store is still published to the cache.

    A mutator must not call back into a public writer (that would re-enter the
    lock) and must not raise away a dirty store.
    """
    with _locked_file(routines_path(), busy="Could not lock agent routines."):
        store = _load_store()
        result, dirty = mutator(store)
        if dirty:
            _write_store(store)
        else:
            _publish(store, routines_path())
        return result


def _write_store(store: dict[str, Any]) -> None:
    path = routines_path()
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
    _publish(payload, path)


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_owner_repo(value: Any, *, allow_fill_in: bool = False) -> str:
    """Accept ``owner/repo`` or ``{owner, repo}``. Empty string if unset.

    ``allow_fill_in`` keeps the pack slot ``{{owner_repo}}`` on a stored
    trigger. Inbound events leave it off: a placeholder is not a repository.
    """
    if isinstance(value, dict):
        owner = str(value.get("owner") or "").strip().strip("/")
        repo = str(value.get("repo") or "").strip().strip("/")
        text = f"{owner}/{repo}" if owner and repo else ""
    else:
        text = str(value or "").strip().strip("/")
    if not text:
        return ""
    token = fill_in_token(text)
    if token:
        if allow_fill_in and token == OWNER_REPO_FILL_IN:
            return token
        raise ValueError("Repository must be owner/repo (GitHub only).")
    if not _OWNER_REPO_RE.match(text):
        raise ValueError("Repository must be owner/repo (GitHub only).")
    return text


def owner_repo_is_fill_in(value: Any) -> bool:
    """True when *value* is a pack slot rather than a GitHub repository."""
    return fill_in_token(value) is not None


def normalize_actor(value: Any) -> str:
    text = str(value or "").strip() or ACTOR_ANYONE
    if text.lower() == ACTOR_ANYONE:
        return ACTOR_ANYONE
    if "/" in text or text.startswith("ghp_") or text.startswith("github_pat_"):
        raise ValueError("Actor must be a GitHub login or Anyone.")
    return text


def _stripped(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _owner_login(value: Any) -> str:
    """GitHub login, or ``owner.name`` when ``login`` is blank.

    Surrounding slashes are not part of a login. A slash-only ``login``
    is blank, so ``owner.name`` still applies.
    """
    if isinstance(value, dict):
        login = _stripped(value.get("login")).strip("/")
        if login:
            return login
        return _stripped(value.get("name")).strip("/")
    return _stripped(value).strip("/")


def _bare_repo_text(value: Any) -> str:
    """Strip whitespace and surrounding slashes. Non-strings are unnamed."""
    return _stripped(value).strip("/")


def _unwrap_repo_dict(value: dict[str, Any]) -> Any:
    """GitHub repository object or ``{owner, repo}`` → a normalize input.

    ``""`` means this object did not name a repository, so the caller can
    try the next alias instead of treating the dict as a present value.
    A ``full_name`` or ``name`` that already contains ``/`` is that repo.
    A slash-less ``full_name`` does not hide ``name`` or ``owner`` + ``name``.
    A slash-only ``repo`` is unnamed, so ``name`` still applies. A bare
    name is returned as text so an outer owner can complete the pair.
    The object's own owner completes a slash-less ``full_name`` when
    ``name`` is absent, and that owner wins over the trigger owner.
    """
    full = _bare_repo_text(value.get("full_name"))
    if "/" in full:
        return full
    owner = _owner_login(value.get("owner"))
    repo_text = _bare_repo_text(value.get("repo"))
    if not repo_text:
        repo_text = _bare_repo_text(value.get("name"))
    if "/" in repo_text:
        return repo_text
    if owner and repo_text:
        return {"owner": owner, "repo": repo_text}
    if repo_text:
        return repo_text
    if owner and full:
        return {"owner": owner, "repo": full}
    if full:
        return full
    return ""


def _coerce_owner_repo(incoming: dict[str, Any]) -> Any:
    """Pick a repository from ``owner_repo``, ``repository``, or ``repo``.

    Blank strings are unset, so a whitespace ``owner_repo`` does not hide a
    ``repository`` / ``repo`` alias (and the pack path must not replace that
    alias with ``{{owner_repo}}``). A GitHub repository object counts via
    ``full_name`` or ``owner.login`` + ``name``. ``owner`` plus a bare
    ``repo`` or ``repository`` name (no slash) is that same pair. A name
    that already contains a slash is the qualified repo, not ``owner/name``.
    Surrounding slashes are ignored on the owner and the repo
    (``/acme/`` + ``/widgets/``). A repository object's own owner wins
    over the trigger owner when that object names the repo.
    """
    owner = _owner_login(incoming.get("owner"))
    bare = ""
    slot = ""

    for key in ("owner_repo", "repository", "repo"):
        if key not in incoming:
            continue
        raw = incoming.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if isinstance(raw, str):
            text = _bare_repo_text(raw)
            found = fill_in_token(text)
            # The owner_repo field is the stored value: a token or a typed
            # fragment wins over later aliases. repository/repo tokens do not.
            if found and key == "owner_repo":
                return found
            if found:
                slot = slot or found
                continue
            if "/" in text:
                return text
            if text and key == "owner_repo":
                return text
            if text and not bare:
                bare = text
            continue
        if not isinstance(raw, dict):
            continue
        cooked = _unwrap_repo_dict(raw)
        if isinstance(cooked, dict):
            pair_owner = _stripped(cooked.get("owner"))
            pair_repo = _bare_repo_text(cooked.get("repo"))
            if pair_owner and pair_repo and "/" not in pair_repo:
                return {"owner": pair_owner, "repo": pair_repo}
            if "/" in pair_repo:
                return pair_repo
            continue
        text = _bare_repo_text(cooked) if isinstance(cooked, str) else ""
        found = fill_in_token(text)
        if found:
            slot = slot or found
            continue
        if text and "/" in text:
            return text
        if text and not bare:
            bare = text

    if owner and bare:
        return {"owner": owner, "repo": bare}
    if bare:
        return bare
    if slot:
        return slot
    return ""


def _normalize_object_kind(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"pr", "pullrequest", "pull_request"}:
        return GITHUB_OBJECT_PULL_REQUEST
    if text in {"issue", "issues"}:
        return GITHUB_OBJECT_ISSUE
    if not text:
        return ""
    raise ValueError("filters.object_kind must be issue or pull_request.")


def public_github_event_filters(raw: Any) -> dict[str, Any]:
    """Normalize optional github_event filters (labels, branch, actor, object_kind)."""
    incoming = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    if "labels" in incoming:
        labels = incoming.get("labels")
        if isinstance(labels, str):
            labels = [labels]
        if not isinstance(labels, list):
            raise ValueError("filters.labels must be a list of strings.")
        cleaned = [str(item or "").strip() for item in labels]
        cleaned = [item for item in cleaned if item]
        if cleaned:
            out["labels"] = cleaned
    branch = incoming.get("branch")
    if branch is not None and str(branch).strip():
        out["branch"] = str(branch).strip()
    excluded = incoming.get("exclude_authors")
    if excluded is not None:  # #862 loop prevention
        if isinstance(excluded, str):
            excluded = [excluded]
        if not isinstance(excluded, list):
            raise ValueError("filters.exclude_authors must be a list of logins.")
        cleaned_excluded = [str(item or "").strip() for item in excluded]
        cleaned_excluded = [item for item in cleaned_excluded if item]
        if cleaned_excluded:
            out["exclude_authors"] = cleaned_excluded
    actor = incoming.get("actor")
    if actor is not None and str(actor).strip():
        normalized_actor = normalize_actor(actor)
        if normalized_actor != ACTOR_ANYONE:
            out["actor"] = normalized_actor
    object_kind = _normalize_object_kind(incoming.get("object_kind") or incoming.get("target"))
    if object_kind:
        if object_kind not in GITHUB_OBJECT_KINDS:
            raise ValueError("filters.object_kind must be issue or pull_request.")
        out["object_kind"] = object_kind
    return out


def public_trigger(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = raw if isinstance(raw, dict) else {}
    kind = str(incoming.get("kind") or TRIGGER_GITHUB_PR_MERGED).strip()
    if kind in {TRIGGER_INTERVAL, TRIGGER_CRON, TRIGGER_ONE_SHOT, TRIGGER_MAILBOX_MESSAGE}:
        return _attach_channel(
            public_time_trigger(incoming, allowed=ROUTINE_TRIGGER_KINDS),
            incoming,
        )
    if kind == TRIGGER_GITHUB_EVENT:
        event_type = str(incoming.get("event_type") or incoming.get("event") or "").strip()
        if event_type not in GITHUB_EVENT_TYPES:
            allowed = ", ".join(sorted(GITHUB_EVENT_TYPES))
            raise ValueError(f"github_event event_type must be one of: {allowed}.")
        owner_repo = normalize_owner_repo(_coerce_owner_repo(incoming), allow_fill_in=True)
        if not owner_repo:
            raise ValueError("github_event trigger requires owner/repo.")
        filters_in = incoming.get("filters") if isinstance(incoming.get("filters"), dict) else {}
        merged_filters = dict(filters_in)
        if incoming.get("actor") and "actor" not in merged_filters:
            merged_filters["actor"] = incoming.get("actor")
        if (incoming.get("object_kind") or incoming.get("target")) and "object_kind" not in merged_filters:
            merged_filters["object_kind"] = incoming.get("object_kind") or incoming.get("target")
        return _attach_channel(
            {
                "kind": TRIGGER_GITHUB_EVENT,
                "event_type": event_type,
                "owner_repo": owner_repo,
                "filters": public_github_event_filters(merged_filters),
            },
            incoming,
        )
    if kind != TRIGGER_GITHUB_PR_MERGED:
        raise ValueError(
            "Supported trigger kinds: github_pr_merged, github_event, interval, cron, one_shot, mailbox_message."
        )
    event = str(incoming.get("event") or EVENT_MERGED).strip().lower()
    if event != EVENT_MERGED:
        raise ValueError("GitHub PR-merged trigger event must be merged.")
    return _attach_channel(
        {
            "kind": TRIGGER_GITHUB_PR_MERGED,
            "owner_repo": normalize_owner_repo(_coerce_owner_repo(incoming), allow_fill_in=True),
            "event": EVENT_MERGED,
            "actor": normalize_actor(incoming.get("actor")),
        },
        incoming,
    )


def public_history_row(raw: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    ran_at = str(raw.get("ran_at") or "").strip()
    if not ran_at:
        return None
    status = str(raw.get("status") or HISTORY_STATUS_SUCCESS).strip() or HISTORY_STATUS_SUCCESS
    source = str(raw.get("source") or SOURCE_TEST_RUN).strip() or SOURCE_TEST_RUN
    row_id = str(raw.get("id") or "").strip() or _new_id()
    row: dict[str, Any] = {
        "id": row_id,
        "ran_at": ran_at,
        "status": status,
        "source": source,
    }
    event = reject_secrets(str(raw.get("event") or "").strip(), "event")
    if event:
        row["event"] = event
    conversation_id = reject_secrets(str(raw.get("conversation_id") or "").strip(), "conversation_id")
    if conversation_id:
        row["conversation_id"] = conversation_id
    summary = reject_secrets(str(raw.get("summary") or "").strip(), "summary")
    if summary:
        row["summary"] = summary
    row.update(public_history_extras(raw))
    return row


def _last_run_dt(history: list[dict[str, Any]]) -> datetime | None:
    if not history:
        return None
    return parse_dt(history[0].get("ran_at"))


def public_routine(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = raw if isinstance(raw, dict) else {}
    history: list[dict[str, Any]] = []
    for item in incoming.get("history") or []:
        row = public_history_row(item if isinstance(item, dict) else None)
        if row:
            history.append(row)
    history.sort(key=lambda row: row["ran_at"], reverse=True)
    name = reject_secrets(str(incoming.get("name") or "").strip() or "New routine", "name")
    instruction = incoming.get("instruction")
    if instruction is None:
        instruction = ""
    else:
        instruction = reject_secrets(str(instruction), "instruction")
    description = reject_secrets(str(incoming.get("description") or "").strip(), "description")
    raw_slug = str(incoming.get("slug") or incoming.get("key") or "").strip()
    if raw_slug:
        raw_slug = reject_secrets(raw_slug, "slug")
    slug = normalize_slug(raw_slug)
    if "active" in incoming:
        active = bool(incoming.get("active"))
    elif "enabled" in incoming:
        active = bool(incoming.get("enabled"))
    else:
        active = True
    trigger = public_trigger(incoming.get("trigger") if isinstance(incoming.get("trigger"), dict) else None)
    tools, tools_explicit = public_routine_tools(incoming, trigger)
    # #1404: imported here rather than at module scope — routine_tools pulls in
    # the plugin catalog, and this module is imported by that catalog's own
    # consumers. `routine_memories_block` returns None when the tool is not
    # attached, which is how removing the tool clears the stored document.
    from swarm.core.routine_tools import routine_memories_block

    memories_block = routine_memories_block(incoming, tools)
    next_run = str(incoming.get("next_run") or "").strip() or None
    if not next_run:
        nxt = compute_next_run(trigger, last_run=_last_run_dt(history))
        next_run = to_iso(nxt) if nxt else None
    model = reject_secrets(str(incoming.get("model") or "").strip(), "model")
    fill_in_keys = routine_fill_in_keys(
        {
            "name": name,
            "instruction": instruction,
            "description": description,
            "trigger": trigger,
        }
    )
    return {
        "id": str(incoming.get("id") or "").strip() or _new_id(),
        "slug": slug,
        "name": name,
        "description": description,
        "instruction": instruction,
        "job": instruction,
        "active": active,
        "enabled": active,
        "pending_fill": bool(fill_in_keys),
        "fill_in_keys": fill_in_keys,
        "model": model,
        "trigger": trigger,
        "tools": tools,
        "tools_explicit": tools_explicit,
        "memories": memories_block,
        "history": history,
        "next_run": next_run,
    }


def trigger_summary(trigger: dict[str, Any] | None) -> str:
    """When-to-run subtitle for the Routines list."""
    data = public_trigger(trigger if isinstance(trigger, dict) else None)
    kind = str(data.get("kind") or "")
    if kind in {TRIGGER_INTERVAL, TRIGGER_CRON, TRIGGER_ONE_SHOT, TRIGGER_MAILBOX_MESSAGE}:
        return time_trigger_summary(data)
    repo = data.get("owner_repo") or "a GitHub repo"
    if kind == TRIGGER_GITHUB_EVENT:
        event_type = str(data.get("event_type") or TRIGGER_GITHUB_EVENT)
        filters = data.get("filters") if isinstance(data.get("filters"), dict) else {}
        extras: list[str] = []
        labels = filters.get("labels") if isinstance(filters.get("labels"), list) else []
        if labels:
            extras.append("labels: " + ", ".join(str(item) for item in labels))
        if filters.get("branch"):
            extras.append("branch: " + str(filters["branch"]))
        if filters.get("object_kind"):
            extras.append("on " + str(filters["object_kind"]))
        if filters.get("actor") and str(filters.get("actor")).strip().lower() != ACTOR_ANYONE:
            extras.append("from " + str(filters["actor"]))
        suffix = f" ({'; '.join(extras)})" if extras else ""
        return f"When {event_type} in {repo}{suffix}…"
    return f"When a PR merges in {repo}…"


def list_routines(agent_id: str) -> list[dict[str, Any]]:
    agent = normalize_agent_id(agent_id)
    store = _read_store()
    rows = store["agents"].get(agent) or []
    out: list[dict[str, Any]] = []
    for item in rows:
        if isinstance(item, dict):
            out.append(public_routine(item))
    return out


def list_all_routines() -> list[dict[str, Any]]:
    store = _read_store()
    agents = store.get("agents") or {}
    out: list[dict[str, Any]] = []
    for agent_id, rows in agents.items():
        if isinstance(rows, list):
            for item in rows:
                if isinstance(item, dict):
                    routine = public_routine(item)
                    routine["agent_id"] = agent_id
                    out.append(routine)
    return out


def get_routine(agent_id: str, routine_id: str) -> dict[str, Any] | None:
    wanted = str(routine_id or "").strip()
    if not wanted:
        return None
    for row in list_routines(agent_id):
        if row["id"] == wanted:
            return row
    return None


def _agent_rows(store: dict[str, Any], agent: str) -> list[dict[str, Any]]:
    """Public routine rows for *agent* as *store* currently holds them.

    Call this from inside a :func:`_mutate_store` mutator so the rows a write is
    based on are the rows on disk, not whatever this process last cached.
    """
    rows = (store.get("agents") or {}).get(agent) or []
    return [public_routine(item) for item in rows if isinstance(item, dict)]


def _set_agent_rows(
    store: dict[str, Any], agent: str, rows: list[dict[str, Any]]
) -> None:
    """Replace one agent's rows inside an open mutator (no read, no write)."""
    agents = dict(store.get("agents") or {})
    agents[agent] = list(rows)
    store["agents"] = agents


def _persist_agent(agent_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace one agent's whole row list in one locked write.

    Blunt on purpose: it takes the caller's row list as the agent's entire set,
    so it must not be used to change one field. Tests use it to force a store
    state (an armed legacy row, a forced ``next_run``) that the validated
    writers deliberately refuse to produce.
    """
    agent = normalize_agent_id(agent_id)
    public_rows = [public_routine(row) for row in rows]

    def mutator(store: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        _set_agent_rows(store, agent, public_rows)
        return public_rows, True

    return _mutate_store(mutator)


def _replace_row(
    rows: list[dict[str, Any]], target: dict[str, Any]
) -> list[dict[str, Any]]:
    """*rows* with *target* swapped in for the row carrying its id."""
    return [target if row.get("id") == target.get("id") else row for row in rows]


class DuplicateRoutineError(Exception):
    """Raised when an agent already has an identical routine (#1316).

    Carries the conflicting routine so the API/UI can point the caller at the
    existing row instead of minting a silent twin.
    """

    def __init__(self, existing: dict[str, Any] | None = None) -> None:
        self.existing = existing if isinstance(existing, dict) else None
        existing_id = str((self.existing or {}).get("id") or "").strip()
        suffix = f" (id: {existing_id})" if existing_id else ""
        super().__init__(
            "A routine with the same name, instruction, and trigger already exists"
            f"{suffix}. Send allow_duplicate: true to create another."
        )

    @property
    def existing_id(self) -> str:
        return str((self.existing or {}).get("id") or "").strip()


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_fingerprint_text(value: Any) -> str:
    """Collapse whitespace and case so cosmetic edits count as duplicates."""
    text = "" if value is None else str(value)
    return _WHITESPACE_RE.sub(" ", text).strip().casefold()


def _routine_fingerprint(row: dict[str, Any] | None) -> str:
    """Deterministic fingerprint of ``{normalized name, instruction, trigger}``.

    Deliberately excludes ``id``, ``history``, ``active`` and ``next_run`` so
    that re-creating the same logical routine is detected (#1316).
    """
    incoming = row if isinstance(row, dict) else {}
    raw_trigger = incoming.get("trigger") if isinstance(incoming.get("trigger"), dict) else None
    try:
        trigger = public_trigger(raw_trigger)
    except ValueError:
        trigger = raw_trigger or {}
    canonical = {
        "name": _normalize_fingerprint_text(incoming.get("name")),
        "instruction": _normalize_fingerprint_text(incoming.get("instruction")),
        "trigger": trigger,
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _allow_duplicate(value: Any) -> bool:
    """Truthy check for the explicit ``allow_duplicate`` opt-in."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


def _active_for_create(incoming: dict[str, Any]) -> bool:
    has_active = "active" in incoming
    has_enabled = "enabled" in incoming
    if has_active and has_enabled:
        active = _coerce_flag(incoming.get("active"), field="active")
        enabled = _coerce_flag(incoming.get("enabled"), field="enabled")
        if active != enabled:
            raise ValueError("active and enabled must agree.")
        return active
    if has_enabled and not has_active:
        return _coerce_flag(incoming.get("enabled"), field="enabled")
    return bool(incoming.get("active", True))


def create_routine(agent_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = payload if isinstance(payload, dict) else {}
    create_row: dict[str, Any] = {
        "id": _new_id(),
        "slug": incoming.get("slug") if "slug" in incoming else incoming.get("key") or "",
        "name": incoming.get("name") or "New routine",
        "description": incoming.get("description") or "",
        "instruction": incoming.get("instruction") or "",
        "active": _active_for_create(incoming),
        "model": incoming.get("model") or "",
        "trigger": incoming.get("trigger"),
        "history": [],
    }
    if "tools" in incoming:
        create_row["tools"] = incoming.get("tools")
        create_row["tools_explicit"] = True
    routine = public_routine(create_row)
    assert_fill_ins_allow_enable(routine)
    agent = normalize_agent_id(agent_id)

    def mutator(store: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        rows = _agent_rows(store, agent)
        if not _allow_duplicate(incoming.get("allow_duplicate")):
            fingerprint = _routine_fingerprint(routine)
            for existing in rows:
                if _routine_fingerprint(existing) == fingerprint:
                    logger.info(
                        "Blocked duplicate routine for %s (existing id %s)",
                        agent,
                        existing.get("id"),
                    )
                    raise DuplicateRoutineError(existing)
        _set_agent_rows(store, agent, [*rows, routine])
        return routine, True

    _mutate_store(mutator)
    return routine


def _apply_routine_patch(current: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Apply a validated PATCH onto the stored row (mutates *current* in place)."""
    unknown = [
        key
        for key in incoming
        if key not in {
            "name",
            "instruction",
            "description",
            "slug",
            "key",
            "active",
            "enabled",
            "model",
            "trigger",
            "next_run",
            "tools",
            # #1404: without this field the PATCH silently dropped the
            # document, so the affordance existed but could never be saved.
            "memories",
        }
    ]
    if unknown:
        raise ValueError(f"Unknown routine field(s): {', '.join(sorted(unknown))}.")
    if "name" in incoming:
        current["name"] = str(incoming.get("name") or "").strip() or current["name"]
    if "description" in incoming:
        current["description"] = "" if incoming.get("description") is None else str(incoming.get("description"))
    if "slug" in incoming or "key" in incoming:
        raw_slug = incoming.get("slug") if "slug" in incoming else incoming.get("key")
        current["slug"] = "" if raw_slug is None else str(raw_slug)
        current.pop("key", None)
    if "instruction" in incoming:
        current["instruction"] = "" if incoming.get("instruction") is None else str(incoming.get("instruction"))
    if "active" in incoming or "enabled" in incoming:
        active_value = _coerce_flag(incoming.get("active"), field="active") if "active" in incoming else None
        enabled_value = _coerce_flag(incoming.get("enabled"), field="enabled") if "enabled" in incoming else None
        if active_value is not None and enabled_value is not None and active_value != enabled_value:
            raise ValueError("active and enabled must agree.")
        current["active"] = active_value if active_value is not None else enabled_value
        current["enabled"] = current["active"]
    if "model" in incoming:
        current["model"] = reject_secrets(str(incoming.get("model") or "").strip(), "model")
    if "trigger" in incoming:
        current["trigger"] = public_trigger(incoming.get("trigger") if isinstance(incoming.get("trigger"), dict) else None)
        current["next_run"] = None
        if not current.get("tools_explicit"):
            # Unset tools follow the new trigger (issue → default-on Open PR).
            current.pop("tools", None)
            current["tools_explicit"] = False
    if "tools" in incoming:
        current["tools"] = incoming.get("tools")
        current["tools_explicit"] = True
    if "next_run" in incoming:
        # #531 / REQ-896: the field was whitelisted but silently dropped, so an
        # operator/API-supplied next_run (e.g. forcing a schedule due, or
        # deferring one) never took effect. Apply it after the trigger branch
        # so an explicit value wins over the trigger-change reset.
        raw_next = incoming.get("next_run")
        if raw_next is None or not str(raw_next).strip():
            current["next_run"] = None
        else:
            parsed = parse_dt(raw_next)
            if parsed is None:
                raise ValueError("next_run must be an ISO datetime or null.")
            current["next_run"] = to_iso(parsed)
    assert_fill_ins_allow_enable(current)


def _patch_routine(agent_id: str, routine_id: str, build_patch) -> dict[str, Any]:
    """Read, validate, and persist one routine PATCH as a single locked update.

    *build_patch* receives the row as it is stored **inside** the store lock, so
    a patch computed from a value another writer just changed is applied to the
    new value rather than to a stale copy.
    """
    agent = normalize_agent_id(agent_id)
    wanted = str(routine_id or "").strip()

    def mutator(store: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        rows = _agent_rows(store, agent)
        current = next((row for row in rows if row.get("id") == wanted), None)
        if current is None:
            raise KeyError(f"Routine '{routine_id}' not found.")
        incoming = build_patch(current)
        _apply_routine_patch(current, incoming if isinstance(incoming, dict) else {})
        _set_agent_rows(store, agent, _replace_row(rows, current))
        return current, True

    written = _mutate_store(mutator)
    return get_routine(agent_id, routine_id) or written


def update_routine(agent_id: str, routine_id: str, patch: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = patch if isinstance(patch, dict) else {}
    return _patch_routine(agent_id, routine_id, lambda _current: incoming)


def apply_routine_fill_ins(
    agent_id: str,
    routine_id: str,
    mapping: dict[str, Any] | None,
) -> dict[str, Any]:
    """Replace leftover ``{{key}}`` slots without enabling the row (#1394)."""
    raw = mapping if isinstance(mapping, dict) else {}
    cleaned: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        text_value = reject_secrets(
            str(value if value is not None else "").strip(),
            f"fill_ins.{name}",
        )
        if text_value:
            cleaned[name] = text_value

    def fill_value(value: Any, field_name: str) -> Any:
        if isinstance(value, dict):
            return {
                child_key: fill_value(child, str(child_key))
                for child_key, child in value.items()
            }
        if isinstance(value, list):
            return [fill_value(item, field_name) for item in value]
        if not isinstance(value, str):
            return value
        token = fill_in_token(value)
        if token == "{{FILL_IN}}":
            alias = _FILL_IN_FIELD_KEYS.get(field_name, field_name or "FILL_IN")
            if cleaned.get(alias):
                return cleaned[alias]
            if cleaned.get(field_name):
                return cleaned[field_name]
            if cleaned.get("FILL_IN"):
                return cleaned["FILL_IN"]
            return value

        def _replace(match: re.Match[str]) -> str:
            key_name = match.group(1)
            if key_name == "FILL_IN":
                alias = _FILL_IN_FIELD_KEYS.get(field_name, "FILL_IN")
                if cleaned.get(alias):
                    return cleaned[alias]
                return match.group(0)
            if cleaned.get(key_name):
                return cleaned[key_name]
            return match.group(0)

        return FILL_IN_SCAN_RE.sub(_replace, value)

    # The row is read inside the store lock so a fill-in is substituted into
    # the text on disk, not into a copy another writer may have replaced (#1666).
    return _patch_routine(
        agent_id,
        routine_id,
        lambda current: {
            "name": fill_value(current.get("name"), "name"),
            "description": fill_value(current.get("description"), "description"),
            "instruction": fill_value(current.get("instruction"), "instruction"),
            "trigger": fill_value(current.get("trigger") or {}, ""),
        },
    )


def enable_routine(agent_id: str, routine_id: str) -> dict[str, Any]:
    """Turn a routine on after required fill-ins are supplied (#1394)."""
    return update_routine(agent_id, routine_id, {"active": True})


def delete_routine(agent_id: str, routine_id: str) -> bool:
    agent = normalize_agent_id(agent_id)
    wanted = str(routine_id or "").strip()

    def mutator(store: dict[str, Any]) -> tuple[bool, bool]:
        rows = _agent_rows(store, agent)
        kept = [row for row in rows if row.get("id") != wanted]
        if len(kept) == len(rows):
            return False, False
        _set_agent_rows(store, agent, kept)
        return True, True

    return _mutate_store(mutator)


def _default_instruction_runner(agent_id: str, instruction: str, source: str) -> None:
    """Record the instruction as this agent's prompt. No live LLM."""
    _fired_prompts.append(
        {
            "agent_id": normalize_agent_id(agent_id),
            "instruction": instruction,
            "source": source,
        }
    )


def run_instruction(agent_id: str, instruction: str, source: str) -> None:
    """Run the stored Instruction once as that agent's prompt."""
    runner = _instruction_runner or _default_instruction_runner
    runner(normalize_agent_id(agent_id), instruction, source)


# --- #862: live background runner -------------------------------------------------

_live_instruction_runner: Callable[[str, str, str], None] | None = None
_live_job_log: dict[str, list[dict[str, Any]]] = {}
_live_job_threads: list[threading.Thread] = []

from swarm.core.routine_jobs import run_routine_agent_job  # noqa: E402  (re-export)


def set_live_instruction_runner(runner: Callable[[str, str, str], None] | None) -> None:
    """Install/replace the live (LLM-executing) instruction runner.

    ``None`` restores the recording-only default so tests and offline
    operation stay hermetic.
    """
    global _live_instruction_runner
    _live_instruction_runner = runner


def record_live_job_status(
    agent_id: str,
    status: str,
    *,
    duration_ms: int | None = None,
    detail: str = "",
) -> None:
    """Append a live-job outcome for the agent (bounded in-memory log)."""
    log = _live_job_log.setdefault(normalize_agent_id(agent_id), [])
    log.append(
        {
            "status": status,
            "duration_ms": duration_ms,
            "detail": detail,
        }
    )
    del log[:-50]


def live_job_status(agent_id: str) -> list[dict[str, Any]]:
    """Recent live-job outcomes for the agent, oldest first."""
    return list(_live_job_log.get(normalize_agent_id(agent_id)) or [])


def reset_live_jobs() -> None:
    """Clear the live-job log and thread handles (test isolation)."""
    _live_job_log.clear()
    _live_job_threads.clear()


def wait_for_live_jobs(timeout: float | None = None) -> None:
    """Join any outstanding background live jobs (tests; keeps teardown safe)."""
    for thread in list(_live_job_threads):
        thread.join(timeout=timeout)
    _live_job_threads.clear()


def load_github_event_thread(agent_id: str, conversation_id: str) -> dict[str, Any] | None:
    """Load the webhook conversation record for an agent (review surface)."""
    from swarm.core.chat_store import load as load_chat

    return load_chat(
        GITHUB_WEBHOOK_USER_KEY,
        normalize_agent_id(agent_id),
        conversation_id=conversation_id,
    )


def live_dispatch_enabled() -> bool:
    """Whether webhook runs dispatch live agent turns.

    An injected runner (``set_live_instruction_runner``) always dispatches;
    otherwise the environment must opt in via ``SWARM_ROUTINES_LIVE`` so
    tests and offline installs stay hermetic.
    """
    if _live_instruction_runner is not None:
        return True
    return os.environ.get("SWARM_ROUTINES_LIVE", "").strip().lower() in ("1", "true", "yes", "on")


def _routine_max_turns(routine: dict[str, Any]) -> int:
    try:
        value = int(routine.get("max_turns") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value >= 1 else 3


def _dispatch_live_job(
    agent_id: str,
    conversation_id: str,
    prompt: str,
    routine: dict[str, Any],
    *,
    github_event: dict[str, Any] | None = None,
) -> None:
    """Fire-and-forget the live agent turn for this webhook run. Never raises."""
    agent_id = normalize_agent_id(agent_id)
    tools = list(routine.get("tools") or [])
    if _live_instruction_runner is not None:
        try:
            _live_instruction_runner(agent_id, prompt, SOURCE_GITHUB_WEBHOOK)
        except Exception:
            logger.exception("Injected live instruction runner failed for %s", agent_id)
        try:
            run_open_pr_if_enabled(
                tools,
                reply="",
                **open_pr_context_from_github_event(github_event),
            )
        except Exception:
            logger.exception("Open PR hook failed for injected runner on %s", agent_id)
        return
    thread = threading.Thread(
        target=_run_live_job_in_thread,
        args=(
            agent_id,
            prompt,
            conversation_id,
            _routine_max_turns(routine),
            tools,
            open_pr_context_from_github_event(github_event),
        ),
        kwargs={"routine_id": str(routine.get("id") or ""), "model": _routine_model(routine)},
        daemon=True,
        name=f"routine-live-{agent_id}",
    )
    _live_job_threads.append(thread)
    thread.start()


def _run_live_job_in_thread(
    agent_id: str,
    prompt: str,
    conversation_id: str,
    max_turns: int,
    tools: list[str] | None = None,
    open_pr_context: dict[str, Any] | None = None,
    *,
    routine_id: str = "",
    model: str = "",
    # #1404: the operator-editable memories document, handed to the job so the
    # brief is injected and the runtime attached. None when not configured.
    memories: dict[str, Any] | None = None,
) -> None:
    try:
        asyncio.run(
            run_routine_agent_job(
                agent_id,
                prompt,
                conversation_id=conversation_id,
                max_turns=max_turns,
                tools=tools,
                open_pr_context=open_pr_context,
                routine_id=routine_id,
                model=model,
                memories=memories,
            )
        )
    except Exception:
        logger.exception("Live routine job failed for %s (%s)", agent_id, conversation_id)


def append_history(
    agent_id: str,
    routine_id: str,
    *,
    source: str,
    status: str = HISTORY_STATUS_SUCCESS,
    event: str = "",
    conversation_id: str = "",
    summary: str = "",
    duration_ms: int | None = None,
    token_cost: int | None = None,
    artifact: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    """Prepend one run row to a routine's history and persist the store.

    The whole read-modify-write is held under ``_settlement_lock`` (a live job
    thread settles a run's tokens on the same store — see the seat-budget
    accounting block) **and** under the store's file lock, so a tick-driven fire
    cannot lose its run row to a concurrent operator PATCH, in this process or
    another (#1666). The settlement lock is the outer one: the file lock is
    never taken on its own here.
    """
    agent = normalize_agent_id(agent_id)
    wanted = str(routine_id or "").strip()

    def mutator(store: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        rows = _agent_rows(store, agent)
        routine = next((item for item in rows if item.get("id") == wanted), None)
        if routine is None:
            raise KeyError(f"Routine '{routine_id}' not found.")
        row = _history_row(
            agent,
            source=source,
            status=status,
            event=event,
            conversation_id=conversation_id,
            summary=summary,
            duration_ms=duration_ms,
            token_cost=token_cost,
            artifact=artifact,
            error=error,
        )
        history = [row, *list(routine.get("history") or [])]
        history.sort(key=lambda item: str(item.get("ran_at") or ""), reverse=True)
        routine["history"] = history
        _reschedule_after_run(routine, row, source=source)
        _set_agent_rows(store, agent, _replace_row(rows, routine))
        return routine, True

    with _settlement_lock:
        written = _mutate_store(mutator)
    return get_routine(agent_id, routine_id) or written


def _history_row(
    agent: str,
    *,
    source: str,
    status: str = HISTORY_STATUS_SUCCESS,
    event: str = "",
    conversation_id: str = "",
    summary: str = "",
    duration_ms: int | None = None,
    token_cost: int | None = None,
    artifact: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    """One stored run row. Blank fields are omitted, never stored as blanks."""
    row: dict[str, Any] = {
        "id": _new_id(),
        "ran_at": _now_iso(),
        "status": str(status or "").strip() or HISTORY_STATUS_SUCCESS,
        "source": source,
    }
    if str(event or "").strip():
        row["event"] = str(event).strip()
    if str(conversation_id or "").strip():
        row["conversation_id"] = str(conversation_id).strip()
        if artifact is None:
            artifact = {
                "kind": "chat",
                "url": f"/chat?agent={agent}&conversation={conversation_id}",
                "label": "Chat log",
            }
    if str(summary or "").strip():
        row["summary"] = str(summary).strip()
    if duration_ms is not None:
        row["duration_ms"] = max(0, int(duration_ms))
    if token_cost is not None:
        row["token_cost"] = max(0, int(token_cost))
    if artifact:
        row["artifact"] = artifact
    if str(error or "").strip():
        row["error"] = str(error).strip()
    return row


def _reschedule_after_run(
    routine: dict[str, Any], row: dict[str, Any], *, source: str
) -> None:
    """Move ``next_run`` on from the run that just happened.

    A spent ``one_shot`` disarms itself for a schedule-driven or operator run.
    """
    trigger = routine.get("trigger") if isinstance(routine.get("trigger"), dict) else {}
    if str(trigger.get("kind") or "") not in TIME_TRIGGER_KINDS:
        return
    nxt = compute_next_run(trigger, last_run=parse_dt(row["ran_at"]))
    routine["next_run"] = to_iso(nxt) if nxt else None
    if str(trigger.get("kind") or "") == TRIGGER_ONE_SHOT and source in {
        SOURCE_SCHEDULE,
        SOURCE_RUN_NOW,
    }:
        routine["active"] = False
        routine["next_run"] = None


def _blocked_routine(
    agent_id: str,
    routine_id: str,
    *,
    source: str,
    event: str,
    conversation_id: str,
    message: str,
) -> dict[str, Any]:
    """Record a fire that did not run the instruction."""
    return append_history(
        agent_id,
        routine_id,
        source=source,
        status=HISTORY_STATUS_ERROR,
        event=event,
        conversation_id=conversation_id,
        summary=message,
        duration_ms=0,
        token_cost=0,
        error=message,
    )


# --- seat-budget accounting -------------------------------------------------------
#
# A routine run is charged against the seat (agent) budget in the operator
# plane. The amount is derived from text the run actually handled — never
# invented — and is always a non-negative integer token count:
#
#   basis=declared         the caller stated the cost (test/import paths).
#   basis=prompt_estimate  no turn reported usage, so the instruction text
#                          actually handed to the agent was counted. This is
#                          the floor cost of the run, not a provider bill.
#   basis=measured         a live turn ran: its prompt + completion text was
#                          counted. This replaces the prompt estimate.
#
# ``token_cost`` is a tokenizer count (tiktoken, word-count fallback) — the
# same estimator ``chat_views.usage_counts`` reports for a chat turn — not a
# provider invoice. No backend in this tree surfaces provider-reported usage,
# so no better number exists today; see TOKEN_COST_NOTE.

TOKEN_BASIS_DECLARED = "declared"
TOKEN_BASIS_PROMPT_ESTIMATE = "prompt_estimate"
TOKEN_BASIS_MEASURED = "measured"
TOKEN_COST_NOTE = (
    "token_cost is a tiktoken estimate of the run's prompt + completion text, "
    "not a provider-reported bill. basis=measured means a live turn's usage was "
    "counted; basis=prompt_estimate means no turn reported usage and the "
    "instruction handed to the agent was counted instead."
)
_MAX_TOKEN_SETTLEMENTS = 200
_MAX_PENDING_USAGE = 200
_settlement_lock = threading.RLock()
_settlements: dict[str, dict[str, Any]] = {}
_pending_usage: dict[str, dict[str, Any]] = {}


def clamp_tokens(value: Any) -> int:
    """Coerce reported usage to a non-negative integer token count.

    Missing, non-numeric, NaN/inf, and negative usage all clamp to 0, so a
    bad report can never debit — or credit — a seat budget.
    """
    if value is None:
        return 0
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return count if count > 0 else 0


def _routine_model(routine: dict[str, Any] | None) -> str:
    return str((routine or {}).get("model") or "").strip()


def estimate_instruction_tokens(instruction: Any, model: Any = "") -> int:
    """Tokenizer count for the instruction text a run hands to the agent.

    The floor cost of a run: the text is measured, the count is an estimate.
    Never raises — a tokenizer failure degrades to 0 (no debit), not a crash.
    """
    text = str(instruction or "")
    if not text.strip():
        return 0
    resolved = str(model or "").strip() or "gpt-4"
    try:
        from swarm.utils.context_utils import get_token_count

        return clamp_tokens(get_token_count(text, resolved))
    except Exception:
        logger.warning("Token estimate unavailable; charging 0", exc_info=True)
        return 0


def measure_turn_tokens(messages: Any, reply: Any = "", model: Any = "") -> int:
    """Tokenizer count for one executed turn: every message sent + the reply.

    Integer, clamped at zero, never raises. Callers pass the messages they
    actually sent and the text they actually got back.
    """
    total = 0
    resolved = str(model or "").strip() or "gpt-4"
    try:
        from swarm.utils.context_utils import get_token_count

        for message in messages if isinstance(messages, list) else []:
            total += clamp_tokens(get_token_count(message, resolved))
        total += clamp_tokens(get_token_count(reply if reply is not None else "", resolved))
    except Exception:
        logger.warning("Turn token measurement failed; charging 0", exc_info=True)
        return 0
    return total


def _debit_seat_tokens(agent_id: str, tokens: int) -> tuple[int, bool, str]:
    """Debit ``tokens`` against the seat budget. Returns (charged, refused, reason).

    A seat with no budget is unlimited: nothing is debited, nothing is
    refused. A refused debit is operator-plane hard-stop policy — the seat is
    marked stopped and the overrun is left for the caller to surface. Any
    other failure is reported as a refusal too: accounting must never fail a
    run that already happened.
    """
    if tokens <= 0:
        return 0, False, ""
    from swarm.core.operator_plane import BudgetHardStop, charge_budget

    try:
        budget = charge_budget(scope="seat", scope_id=agent_id, tokens=tokens)
    except BudgetHardStop as exc:
        return 0, True, str(exc)
    except Exception as exc:
        logger.exception("Seat budget debit failed for %s", agent_id)
        return 0, True, f"seat budget debit failed: {exc}"
    if budget is None:
        return 0, False, ""
    return clamp_tokens(tokens), False, ""


def _record_settlement(
    row_id: str,
    *,
    tokens: Any,
    charged: Any,
    basis: str,
    conversation_id: str = "",
    refused: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    """Remember what a run was charged, so a later report charges the delta."""
    row = {
        "row_id": row_id,
        "conversation_id": str(conversation_id or ""),
        "tokens": clamp_tokens(tokens),
        "charged": clamp_tokens(charged),
        "basis": str(basis or TOKEN_BASIS_PROMPT_ESTIMATE),
        "refused": bool(refused),
        "reason": str(reason or ""),
    }
    _settlements[row_id] = row
    if len(_settlements) > _MAX_TOKEN_SETTLEMENTS:
        for stale in list(_settlements)[: len(_settlements) - _MAX_TOKEN_SETTLEMENTS]:
            _settlements.pop(stale, None)
    return row


def _target_history_row(
    routine: dict[str, Any],
    *,
    conversation_id: str = "",
    history_id: str = "",
) -> dict[str, Any] | None:
    """Newest history row for a run: exact row id, then conversation, then newest."""
    history = [row for row in (routine.get("history") or []) if isinstance(row, dict)]
    if history_id:
        for row in history:
            if str(row.get("id") or "") == history_id:
                return row
    if conversation_id:
        for row in history:
            if str(row.get("conversation_id") or "") == conversation_id:
                return row
    return history[0] if history else None


def _stamp_row_tokens(
    store: dict[str, Any],
    agent: str,
    routine_id: str,
    row: dict[str, Any],
    tokens: int,
) -> bool:
    """Write a run's usage onto its history row inside an open mutator.

    Returns True when the row was found and the store is dirty.
    """
    for candidate in (store.get("agents") or {}).get(agent) or []:
        if str(candidate.get("id") or "") != str(routine_id or ""):
            continue
        history = [item for item in (candidate.get("history") or []) if isinstance(item, dict)]
        for item in history:
            if str(item.get("id") or "") == str(row.get("id") or ""):
                item["token_cost"] = clamp_tokens(tokens)
                break
        candidate["history"] = history
        return True
    return False


def settle_routine_tokens(
    agent_id: str,
    routine_id: str,
    *,
    tokens: Any,
    basis: str = TOKEN_BASIS_MEASURED,
    conversation_id: str = "",
    history_id: str = "",
) -> dict[str, Any]:
    """Debit a run's real usage and record it on the run's history row.

    Exactly-once: the run's history row remembers what it was already
    debited, so a pre-run prompt charge and a post-run measured charge
    settle the *same* run — the seat ends up debited the measured total, not
    the sum. Usage is clamped at zero and never debits a negative amount. A
    debit the seat budget refuses (hard-stop) is reported, not swallowed:
    ``refused`` is True and ``reason`` carries the refusal, while the row
    still records the run's true usage.

    The row is located and the usage stamped inside one store mutation, so a
    run that lands while a fire is appending history is settled on the row
    that is really on disk (#1666).
    """
    agent = normalize_agent_id(agent_id)
    wanted = str(routine_id or "").strip()
    total = clamp_tokens(tokens)

    def mutator(store: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        rows = _agent_rows(store, agent)
        routine = next((item for item in rows if item.get("id") == wanted), None)
        if routine is None:
            raise KeyError(f"Routine '{routine_id}' not found.")
        row = _target_history_row(
            routine, conversation_id=conversation_id, history_id=history_id
        )
        if row is None:
            return {
                "row_id": "",
                "conversation_id": str(conversation_id or ""),
                "tokens": total,
                "charged": 0,
                "basis": str(basis or ""),
                "refused": False,
                "reason": "no history row to settle",
            }, False
        row_id = str(row.get("id") or "")
        prior = _settlements.get(row_id) or {}
        already = clamp_tokens(prior.get("charged"))
        charged, refused, reason = _debit_seat_tokens(agent, max(0, total - already))
        settled = _record_settlement(
            row_id,
            tokens=total,
            charged=already + charged,
            basis=basis,
            conversation_id=str(row.get("conversation_id") or conversation_id or ""),
            refused=refused,
            reason=reason,
        )
        dirty = bool(total) and _stamp_row_tokens(store, agent, wanted, row, total)
        return {
            **settled,
            "charged": charged,
            "charged_total": clamp_tokens(already + charged),
        }, dirty

    with _settlement_lock:
        return _mutate_store(mutator)


def _pending_key(agent_id: str, conversation_id: str) -> str:
    return f"{normalize_agent_id(agent_id)}|{str(conversation_id or '')}"


def _stash_pending_usage(agent_id: str, conversation_id: str, tokens: int, basis: str) -> None:
    key = _pending_key(agent_id, conversation_id)
    _pending_usage[key] = {
        "tokens": clamp_tokens(tokens),
        "basis": str(basis or TOKEN_BASIS_MEASURED),
    }
    if len(_pending_usage) > _MAX_PENDING_USAGE:
        for stale in list(_pending_usage)[: len(_pending_usage) - _MAX_PENDING_USAGE]:
            _pending_usage.pop(stale, None)


def _pop_pending_usage(agent_id: str, conversation_id: str) -> dict[str, Any] | None:
    return _pending_usage.pop(_pending_key(agent_id, conversation_id), None)


def _find_run_for_conversation(
    agent_id: str, conversation_id: str, routine_id: str = ""
) -> tuple[str, dict[str, Any]] | None:
    """Locate (routine_id, history row) for a conversation's run, if written.

    Only ever matches a conversation, or the newest row of a routine the
    caller named explicitly — an unattributable measurement must not land on
    some other run's row.
    """
    agent = normalize_agent_id(agent_id)
    wanted_conv = str(conversation_id or "")
    if not wanted_conv and not routine_id:
        return None
    fallback: tuple[str, dict[str, Any]] | None = None
    for routine in list_routines(agent):
        if routine_id and str(routine.get("id") or "") != str(routine_id):
            continue
        history = [row for row in (routine.get("history") or []) if isinstance(row, dict)]
        if wanted_conv:
            for row in history:
                if str(row.get("conversation_id") or "") == wanted_conv:
                    return str(routine.get("id") or ""), row
        if routine_id and fallback is None and history:
            fallback = (str(routine.get("id") or ""), history[0])
    return fallback


def record_routine_token_usage(
    agent_id: str,
    conversation_id: str,
    *,
    tokens: Any,
    basis: str = TOKEN_BASIS_MEASURED,
    routine_id: str = "",
) -> dict[str, Any]:
    """Report a run's real usage (from the live job thread) for settlement.

    The live job runs on its own thread, so its usage can land before
    ``fire_routine`` has written the run's history row. In that case the
    measurement is stashed against the conversation and drained by the fire,
    so the debit is not lost and the row ends up carrying the measured total.
    """
    agent = normalize_agent_id(agent_id)
    total = clamp_tokens(tokens)
    found = _find_run_for_conversation(agent, conversation_id, routine_id)
    if found is None:
        unattributable = not str(conversation_id or "")
        if not unattributable:
            _stash_pending_usage(agent, conversation_id, total, basis)
        return {
            "row_id": "",
            "conversation_id": str(conversation_id or ""),
            "tokens": total,
            "charged": 0,
            "basis": str(basis or ""),
            "refused": False,
            "reason": "no run row to attribute this usage to",
            "pending": not unattributable,
        }
    target_routine_id, row = found
    return settle_routine_tokens(
        agent,
        target_routine_id,
        tokens=total,
        basis=basis,
        conversation_id=conversation_id,
        history_id=str(row.get("id") or ""),
    )


def routine_token_usage_for_conversation(agent_id: str, conversation_id: str) -> dict[str, Any] | None:
    """Settled usage for a conversation's run, or None when there is no run row."""
    if not str(conversation_id or ""):
        return None
    with _settlement_lock:
        found = _find_run_for_conversation(agent_id, conversation_id)
        if found is None:
            return None
        _routine_id, row = found
        row_id = str(row.get("id") or "")
        settled = _settlements.get(row_id) or {}
    return {
        "row_id": row_id,
        "conversation_id": str(row.get("conversation_id") or conversation_id or ""),
        "tokens": clamp_tokens(settled.get("tokens", row.get("token_cost"))),
        "basis": str(settled.get("basis") or ""),
        "refused": bool(settled.get("refused")),
        "reason": str(settled.get("reason") or ""),
    }


def fire_routine(
    agent_id: str,
    routine_id: str,
    *,
    source: str,
    prompt: str | None = None,
    event: str = "",
    conversation_id: str = "",
    summary: str = "",
    token_cost: int | None = None,
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the instruction, record duration/status, and append history.

    Checkout is an operator-plane execution lock for this agent routine.
    Overlapping fires and budget hard-stops record an error and do not run
    the instruction again.

    Budget semantics (see the seat-budget accounting block above):

    * **Before the run** — the run's prompt cost is debited inside the same
      locked update that takes the checkout. If a seat budget exists and
      cannot cover it, ``BudgetHardStop`` refuses the run: the instruction
      never executes, nothing is debited, and the refusal is a loud error
      history row. A seat already at its limit is refused the same way.
    * **After the run** — when a live turn reports its own usage, that
      measured total replaces the prompt estimate and only the difference is
      debited, so a run is never charged twice. If the seat's hard-stop
      refuses that post-run debit, the run still stands, the row records the
      true usage, and the refusal is returned and logged rather than hidden.

    ``token_cost`` is for callers that already know the cost (an explicit
    ``int`` is taken as declared and debited as-is). Leave it ``None`` and the
    run is charged its own measured usage, falling back to the prompt
    estimate when no turn reports any.
    """
    from swarm.core.operator_plane import (
        ROUTINE_LEASE_S,
        BudgetHardStop,
        TaskBusy,
        begin_execution,
        end_execution,
        routine_task_id,
    )

    routine = get_routine(agent_id, routine_id)
    if routine is None:
        raise KeyError(f"Routine '{routine_id}' not found.")
    instruction = prompt if prompt is not None else str(routine.get("instruction") or "")
    agent = normalize_agent_id(agent_id)
    task_id = routine_task_id(agent, str(routine_id))
    worker_id = f"{os.getpid()}:{threading.get_ident()}:{uuid.uuid4().hex}"
    held = False
    # The run's floor cost: what the caller declared, else the tokenizer count
    # of the instruction this run hands to the agent. A live turn replaces it
    # with measured usage once the turn reports back.
    declared_cost = token_cost is not None
    pre_charge = (
        clamp_tokens(token_cost)
        if declared_cost
        else clamp_tokens(estimate_instruction_tokens(instruction, _routine_model(routine)))
    )
    pre_basis = TOKEN_BASIS_DECLARED if declared_cost else TOKEN_BASIS_PROMPT_ESTIMATE
    try:
        begin_execution(
            task_id=task_id,
            worker_id=worker_id,
            scope="seat",
            scope_id=agent,
            tokens=pre_charge,
            lease_s=ROUTINE_LEASE_S,
        )
        held = True
    except BudgetHardStop as exc:
        return _blocked_routine(
            agent_id,
            routine_id,
            source=source,
            event=event,
            conversation_id=conversation_id,
            message=str(exc),
        )
    except TaskBusy as exc:
        return _blocked_routine(
            agent_id,
            routine_id,
            source=source,
            event=event,
            conversation_id=conversation_id,
            message=str(exc),
        )
    started = time.monotonic()
    status = HISTORY_STATUS_SUCCESS
    error = ""
    try:
        try:
            run_instruction(agent_id, instruction, source)
        except Exception as exc:
            logger.exception("Routine %s failed", routine_id)
            status = HISTORY_STATUS_ERROR
            error = str(exc) or "Routine execution failed."
        duration_ms = int((time.monotonic() - started) * 1000)
        from swarm.core.activity_log import current_activity_actor, emit_activity

        emit_activity(
            actor_type="system" if source == SOURCE_SCHEDULE else "user",
            actor_id=current_activity_actor(default=f"system:{source}"),
            action="routine.fired",
            entity_type="routine",
            entity_id=str(routine_id),
            agent_id=normalize_agent_id(agent_id),
            detail={"source": source, "status": status},
        )
        updated = append_history(
            agent_id,
            routine_id,
            source=source,
            status=status,
            event=event,
            conversation_id=conversation_id,
            summary=error or summary,
            duration_ms=duration_ms,
            token_cost=pre_charge,
            artifact=artifact,
            error=error,
        )
        _settle_pre_charge(agent, routine_id, updated, pre_charge, pre_basis, conversation_id)
        return _refreshed_routine(agent, routine_id, updated)
    finally:
        if held:
            end_execution(task_id=task_id, worker_id=worker_id)


def _settle_pre_charge(
    agent_id: str,
    routine_id: str,
    updated: dict[str, Any],
    pre_charge: int,
    basis: str,
    conversation_id: str,
) -> None:
    """Book the pre-run debit on the run's row, then drain raced usage.

    The pre-run debit happened inside ``begin_execution``; recording it here
    is what lets a later measured report charge only the difference. A live
    job thread that finished before this row existed has already stashed its
    measured usage — draining it here settles the run on the measured total.
    """
    history = [row for row in (updated.get("history") or []) if isinstance(row, dict)]
    if not history:
        return
    with _settlement_lock:
        row = history[0]
        row_id = str(row.get("id") or "")
        if row_id and row_id not in _settlements:
            _record_settlement(
                row_id,
                tokens=pre_charge,
                charged=pre_charge,
                basis=basis,
                conversation_id=conversation_id,
            )
        pending = _pop_pending_usage(agent_id, conversation_id)
    if pending is None:
        return
    try:
        settled = settle_routine_tokens(
            agent_id,
            routine_id,
            tokens=pending.get("tokens"),
            basis=str(pending.get("basis") or TOKEN_BASIS_MEASURED),
            conversation_id=conversation_id,
        )
    except Exception:
        # The run already executed and its row is written; a settlement
        # failure must not turn a completed run into a failed request.
        logger.exception("Could not settle routine %s token usage", routine_id)
        return
    if settled.get("refused"):
        logger.warning(
            "Routine %s overran its seat budget after the run: %s",
            routine_id,
            settled.get("reason") or "charge refused",
        )


def _refreshed_routine(
    agent_id: str, routine_id: str, fallback: dict[str, Any]
) -> dict[str, Any]:
    """Re-read the routine so a post-run token stamp is visible to callers."""
    return get_routine(agent_id, routine_id) or fallback


def dry_run_preview(routine: dict[str, Any] | None) -> dict[str, Any]:
    """Documented trigger-match + prompt preview. No live side effects.

    #1405 — builder Test is a dry-run: it never calls ``run_instruction``,
    never dispatches a live job, and never merges a PR or sends a message.
    """
    row = public_routine(routine if isinstance(routine, dict) else None)
    trigger = row.get("trigger") if isinstance(row.get("trigger"), dict) else {}
    prompt = str(row.get("instruction") or "")
    return {
        "dry_run": True,
        "side_effects": DRY_RUN_SIDE_EFFECTS,
        "note": DRY_RUN_NOTE,
        "trigger_summary": trigger_summary(trigger),
        "trigger_kind": str(trigger.get("kind") or ""),
        "trigger_match": {
            "kind": str(trigger.get("kind") or ""),
            "summary": trigger_summary(trigger),
            "configured": bool(trigger),
        },
        "prompt": prompt,
        "model": str(row.get("model") or ""),
        "armed": bool(row.get("active")),
        "would_run_if_triggered": bool(row.get("active")),
    }


def test_run(agent_id: str, routine_id: str) -> dict[str, Any]:
    """Non-destructive dry-run preview of trigger match + prompt (#1405).

    Does not fire the instruction, append history, or dispatch live jobs.
    Use :func:`run_now` for an operator-initiated live run.
    """
    routine = get_routine(agent_id, routine_id)
    if routine is None:
        raise KeyError(f"Routine '{routine_id}' not found.")
    return {**routine, "preview": dry_run_preview(routine)}


def run_now(agent_id: str, routine_id: str) -> dict[str, Any]:
    """Operator run-now. Same path as a scheduled fire; source is run_now."""
    return fire_routine(agent_id, routine_id, source=SOURCE_RUN_NOW)


def tick_due_routines(now: datetime | None = None) -> list[dict[str, Any]]:
    """Fire due interval/cron/one_shot routines.

    Each fire takes a local operator-plane execution lock so an overlapping
    fire on this host cannot run the same routine twice.
    """
    moment = now or utcnow()
    fired: list[dict[str, Any]] = []
    for row in list_all_routines():
        if not row.get("active"):
            continue
        trigger = row.get("trigger") if isinstance(row.get("trigger"), dict) else {}
        if str(trigger.get("kind") or "") not in TIME_TRIGGER_KINDS:
            continue
        last_run = _last_run_dt(list(row.get("history") or []))
        if not is_due(trigger, now=moment, last_run=last_run, next_run=row.get("next_run")):
            continue
        agent_id = str(row.get("agent_id") or "")
        updated = fire_routine(
            agent_id,
            str(row.get("id") or ""),
            source=SOURCE_SCHEDULE,
            event=str(trigger.get("kind") or SOURCE_SCHEDULE),
            summary=f"Scheduled {trigger.get('kind')} run.",
        )
        fired.append({"agent_id": normalize_agent_id(agent_id), "routine": updated})
    return fired


def deliver_mailbox_message(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Fire matching Active mailbox_message routines. Tests inject the event."""
    incoming = payload if isinstance(payload, dict) else {}
    content = reject_secrets(str(incoming.get("content") or incoming.get("body") or incoming.get("text") or ""), "content")
    event = {
        "sender": reject_secrets(str(incoming.get("sender") or incoming.get("sender_id") or "").strip(), "sender"),
        "content": content,
        "subject": reject_secrets(str(incoming.get("subject") or "").strip(), "subject"),
        "body": content,
        "text": content,
        "message": content,
    }
    fired: list[dict[str, Any]] = []
    for row in list_all_routines():
        if not row.get("active"):
            continue
        trigger = row.get("trigger") if isinstance(row.get("trigger"), dict) else {}
        if not mailbox_event_matches(trigger, event):
            continue
        agent_id = str(row.get("agent_id") or "")
        briefing = "\n".join(
            part
            for part in (
                f"Mailbox message from {event['sender'] or 'unknown'}.",
                f"Subject: {event['subject']}" if event["subject"] else "",
                event["content"],
                "",
                "---",
                "Routine instruction:",
                str(row.get("instruction") or ""),
            )
            if part is not None
        ).strip()
        updated = fire_routine(
            agent_id,
            str(row.get("id") or ""),
            source=SOURCE_MAILBOX_MESSAGE,
            prompt=briefing,
            event=TRIGGER_MAILBOX_MESSAGE,
            summary=f"Mailbox from {event['sender'] or 'unknown'}.",
        )
        fired.append({"agent_id": normalize_agent_id(agent_id), "routine": updated})
    return fired


def _actor_matches(trigger_actor: str, event_actor: str) -> bool:
    wanted = (trigger_actor or ACTOR_ANYONE).strip().lower()
    if wanted == ACTOR_ANYONE:
        return True
    return wanted == (event_actor or "").strip().lower()


def _github_login(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("login") or "").strip()
    return ""


def _performer_login(
    event_type: str,
    *,
    comment_user: dict[str, Any],
    sender: dict[str, Any],
    pusher: dict[str, Any],
    author: str,
) -> str:
    """Login matched by the composer "from" chip.

    Comment events use the comment author. Other events use the GitHub
    user who performed the action (``sender.login``). That is not the
    issue or pull-request opener, and not ``pusher.name`` (a git author
    string). ``author`` stays the opener for briefings and
    ``exclude_authors``.
    """
    if event_type.startswith("issue_comment"):
        return _github_login(comment_user) or _github_login(sender) or author
    sender_login = _github_login(sender)
    if event_type == "push":
        return sender_login or str(pusher.get("name") or "").strip() or author
    if sender_login:
        return sender_login
    return author


def _inbound_owner_repo(incoming: dict[str, Any]) -> Any:
    """Repository on an inbound event, using the stored-trigger alias rules.

    ``repository_full_name`` fills a blank ``owner_repo``. Whitespace and
    slash-only fields are blank, so ``name`` and ``owner.name`` still apply.
    A repository object's owner wins over a different top-level owner.
    A qualified ``full_name`` stays that repo.
    """
    alias = incoming.get("repository_full_name")
    current = incoming.get("owner_repo")
    if alias and (current is None or (isinstance(current, str) and not _bare_repo_text(current))):
        incoming = {**incoming, "owner_repo": alias}
    return _coerce_owner_repo(incoming)


def parse_github_merge_event(payload: dict[str, Any] | None) -> dict[str, str]:
    """Accept a fake merge event or a GitHub-shaped pull_request payload.

    Live GitHub is never called. Tests inject this payload. No tokens.
    The repository is paired with the same rules as a stored trigger.
    """
    incoming = payload if isinstance(payload, dict) else {}
    pull = incoming.get("pull_request") if isinstance(incoming.get("pull_request"), dict) else {}
    sender = incoming.get("sender") if isinstance(incoming.get("sender"), dict) else {}
    owner_repo = _inbound_owner_repo(incoming)

    merged = incoming.get("merged")
    if merged is None:
        merged = pull.get("merged")
    action = str(incoming.get("action") or incoming.get("event") or EVENT_MERGED).strip().lower()
    if action in {"closed", EVENT_MERGED}:
        event = EVENT_MERGED
    else:
        event = action
    if event != EVENT_MERGED:
        raise ValueError("Only GitHub PR-merged events are accepted.")
    if merged is False:
        raise ValueError("Pull request is not merged.")

    merged_by = pull.get("merged_by")
    merged_by_login = merged_by.get("login") if isinstance(merged_by, dict) else None
    actor = (
        incoming.get("actor")
        or incoming.get("merged_by")
        or merged_by_login
        or sender.get("login")
        or ACTOR_ANYONE
    )
    return {
        "owner_repo": normalize_owner_repo(owner_repo),
        "event": EVENT_MERGED,
        "actor": normalize_actor(actor),
    }


def deliver_github_pr_merged(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Fire matching Active routines. Inactive rows stay quiet.

    This is the inbound merge-event delivery. Tests inject a fake event.
    Live GitHub delivery is a follow-on; this path is not a silent no-op.
    """
    event = parse_github_merge_event(payload)
    store = _read_store()
    fired: list[dict[str, Any]] = []
    for agent_id, rows in list((store.get("agents") or {}).items()):
        if not isinstance(rows, list):
            continue
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            routine = public_routine(raw)
            trigger = routine["trigger"]
            if not routine["active"]:
                continue
            if trigger["kind"] != TRIGGER_GITHUB_PR_MERGED:
                continue
            if owner_repo_is_fill_in(trigger.get("owner_repo")):
                continue
            if trigger["owner_repo"] != event["owner_repo"]:
                continue
            if trigger["event"] != EVENT_MERGED:
                continue
            if not _actor_matches(trigger["actor"], event["actor"]):
                continue
            updated = fire_routine(
                agent_id,
                routine["id"],
                source=SOURCE_GITHUB_PR_MERGED,
                event=EVENT_MERGED,
            )
            fired.append({"agent_id": normalize_agent_id(agent_id), "routine": updated})
    return fired


def github_webhook_secret() -> str:
    """HMAC secret for inbound GitHub webhooks. Empty means unsigned deliveries are refused."""
    return (os.environ.get(ENV_GITHUB_WEBHOOK_SECRET) or "").strip()


def verify_github_webhook_signature(
    body: bytes,
    signature_header: str | None,
    *,
    secret: str | None = None,
) -> bool:
    """Validate ``X-Hub-Signature-256`` against the configured webhook secret."""
    expected_secret = (secret if secret is not None else github_webhook_secret()).strip()
    header = str(signature_header or "").strip()
    if not expected_secret or not header.startswith("sha256="):
        return False
    digest = hmac.new(expected_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest("sha256=" + digest, header)


def _label_names(raw: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(raw, list):
        return names
    for item in raw:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        if name:
            names.append(name)
    return names


def _ref_branch(ref: Any) -> str:
    text = str(ref or "").strip()
    prefix = "refs/heads/"
    if text.startswith(prefix):
        return text[len(prefix) :]
    if text.startswith("refs/"):
        return ""
    return text


def _webhook_owner_repo(incoming: dict[str, Any]) -> str:
    try:
        return normalize_owner_repo(_inbound_owner_repo(incoming))
    except ValueError:
        return ""


def parse_github_webhook_event(
    payload: dict[str, Any] | None,
    event_header: str | None = None,
) -> dict[str, Any]:
    """Normalize a GitHub webhook JSON body + ``X-GitHub-Event`` header."""
    incoming = payload if isinstance(payload, dict) else {}
    header = str(event_header or incoming.get("event") or "").strip()
    action = str(incoming.get("action") or "").strip()
    if header == "push":
        event_type = "push"
    elif header and action:
        event_type = f"{header}.{action}"
    else:
        event_type = header or action

    issue = incoming.get("issue") if isinstance(incoming.get("issue"), dict) else {}
    pull = incoming.get("pull_request") if isinstance(incoming.get("pull_request"), dict) else {}
    comment = incoming.get("comment") if isinstance(incoming.get("comment"), dict) else {}
    target = pull or issue
    sender = incoming.get("sender") if isinstance(incoming.get("sender"), dict) else {}
    pusher = incoming.get("pusher") if isinstance(incoming.get("pusher"), dict) else {}
    head_commit = incoming.get("head_commit") if isinstance(incoming.get("head_commit"), dict) else {}
    repo_obj = incoming.get("repository") if isinstance(incoming.get("repository"), dict) else {}
    user = target.get("user") if isinstance(target.get("user"), dict) else {}
    comment_user = comment.get("user") if isinstance(comment.get("user"), dict) else {}
    issue_pull = issue.get("pull_request")
    if pull or (isinstance(issue_pull, dict) and issue_pull) or issue_pull:
        object_kind = GITHUB_OBJECT_PULL_REQUEST
    elif issue:
        object_kind = GITHUB_OBJECT_ISSUE
    else:
        object_kind = ""

    number_raw = target.get("number") if target.get("number") is not None else incoming.get("number")
    number: int | None
    try:
        number = int(number_raw) if number_raw is not None and str(number_raw).strip() != "" else None
    except (TypeError, ValueError):
        number = None

    title = str(target.get("title") or head_commit.get("message") or incoming.get("title") or "")
    if "\n" in title:
        title = title.split("\n", 1)[0]
    body = str(
        comment.get("body") or target.get("body") or head_commit.get("message") or incoming.get("body") or ""
    )
    author = str(
        comment_user.get("login") or user.get("login") or pusher.get("name") or sender.get("login") or ""
    ).strip()
    actor_login = _performer_login(
        event_type,
        comment_user=comment_user,
        sender=sender,
        pusher=pusher,
        author=author,
    )
    html_url = str(
        target.get("html_url")
        or incoming.get("compare")
        or repo_obj.get("html_url")
        or ""
    ).strip()
    labels = _label_names(target.get("labels"))
    branch = ""
    if event_type == "push":
        branch = _ref_branch(incoming.get("ref"))
    elif pull:
        base = pull.get("base") if isinstance(pull.get("base"), dict) else {}
        head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
        branch = str(base.get("ref") or head.get("ref") or "").strip()
    diff = str(pull.get("diff_url") or incoming.get("compare") or "").strip()

    if number is not None:
        event_label = f"{event_type} #{number}"
    elif event_type == "push":
        sha = str(head_commit.get("id") or incoming.get("after") or "")[:7]
        event_label = f"push {branch}".strip()
        if sha:
            event_label = f"{event_label} {sha}".strip()
    else:
        event_label = event_type or "github_event"

    return {
        "event_type": event_type,
        "owner_repo": _webhook_owner_repo(incoming),
        "number": number,
        "title": title.strip(),
        "body": body,
        "author": author,
        "actor_login": actor_login,
        "html_url": html_url,
        "labels": labels,
        "branch": branch,
        "diff": diff,
        "event_label": event_label.strip(),
        "object_kind": object_kind,
    }


def github_event_conversation_id(event: dict[str, Any]) -> str:
    """Stable conversation id for a GitHub webhook event (e.g. conv-github-pr-42)."""
    event_type = str(event.get("event_type") or "")
    number = event.get("number")
    object_kind = str(event.get("object_kind") or "").strip().lower()
    if number is not None:
        if object_kind == GITHUB_OBJECT_PULL_REQUEST or event_type.startswith("pull_request"):
            return f"conv-github-pr-{number}"
        if (
            object_kind == GITHUB_OBJECT_ISSUE
            or event_type.startswith("issues")
            or event_type.startswith("issue_comment")
        ):
            return f"conv-github-issue-{number}"
    label = str(event.get("event_label") or event_type or "event")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")[:80]
    return f"conv-github-{slug or 'event'}"


def format_github_event_briefing(event: dict[str, Any], instruction: str) -> str:
    """Prompt for the target agent: event context plus the routine instruction."""
    lines = [
        f"GitHub event: {event.get('event_label') or event.get('event_type') or TRIGGER_GITHUB_EVENT}",
        f"Repository: {event.get('owner_repo') or ''}",
    ]
    if event.get("title"):
        lines.append(f"Title: {event['title']}")
    if event.get("author"):
        lines.append(f"Author: {event['author']}")
    actor_login = str(event.get("actor_login") or "").strip()
    if actor_login and actor_login.lower() != str(event.get("author") or "").strip().lower():
        lines.append(f"Actor: {actor_login}")
    if event.get("html_url"):
        lines.append(f"URL: {event['html_url']}")
    if event.get("branch"):
        lines.append(f"Branch: {event['branch']}")
    labels = event.get("labels") if isinstance(event.get("labels"), list) else []
    if labels:
        lines.append("Labels: " + ", ".join(str(item) for item in labels))
    if event.get("diff"):
        lines.append(f"Diff: {event['diff']}")
    body = str(event.get("body") or "").strip()
    if body:
        lines.extend(["", "Body:", body])
    instr = str(instruction or "").strip()
    if instr:
        lines.extend(["", "---", "Routine instruction:", instr])
    return "\n".join(lines).strip()


def github_event_filters_match(trigger: dict[str, Any], event: dict[str, Any]) -> bool:
    filters = trigger.get("filters") if isinstance(trigger.get("filters"), dict) else {}
    wanted_labels = filters.get("labels") if isinstance(filters.get("labels"), list) else []
    if wanted_labels:
        have = {str(item).strip().lower() for item in (event.get("labels") or [])}
        need = {str(item).strip().lower() for item in wanted_labels if str(item).strip()}
        if need and not (need & have):
            return False
    wanted_branch = str(filters.get("branch") or "").strip()
    if wanted_branch and str(event.get("branch") or "").strip().lower() != wanted_branch.lower():
        return False
    excluded = filters.get("exclude_authors") if isinstance(filters.get("exclude_authors"), list) else []
    if excluded:
        author = str(event.get("author") or "").strip().lower()
        blocked = {str(item).strip().lower() for item in excluded if str(item).strip()}
        if author and author in blocked:
            return False
    wanted_actor = str(filters.get("actor") or "").strip()
    if wanted_actor and wanted_actor.lower() != ACTOR_ANYONE:
        performer = str(event.get("actor_login") or event.get("author") or "")
        if not _actor_matches(wanted_actor, performer):
            return False
    wanted_object = str(filters.get("object_kind") or "").strip().lower()
    if wanted_object:
        have = str(event.get("object_kind") or "").strip().lower()
        if have != wanted_object:
            return False
    return True


def spawn_github_event_session(agent_id: str, conversation_id: str, prompt: str) -> str:
    """Persist a chat session for the webhook run. Best-effort; never raises."""
    cid = str(conversation_id or "").strip() or f"conv-github-{_new_id()[:12]}"
    try:
        from swarm.core.chat_store import save as save_chat

        save_chat(
            GITHUB_WEBHOOK_USER_KEY,
            normalize_agent_id(agent_id),
            [{"role": "user", "content": prompt}],
            conversation_id=cid,
            session_id=cid,
        )
    except Exception:
        logger.exception("Could not persist GitHub webhook session %s", cid)
    return cid


# --- #1667: GitHub webhook delivery dedupe ----------------------------------------
#
# GitHub redelivers a delivery it did not get a fast 2xx for, and it routinely
# does so *after* a restart. Without a dedupe key the redelivery was a second
# full run: ``github_event_conversation_id`` is per issue, so the same turn was
# appended to the same conversation again, and the operator-plane lease answered
# the duplicate with a "busy" error row — a user-visible error where a no-op
# belongs.
#
# Two keys are recorded per delivery and either one suppresses a redelivery:
#
#   ``id:``    the ``X-GitHub-Delivery`` header value, when the caller forwards
#              it. This is the precise key GitHub documents.
#   ``sha256:``a digest of the event header plus the signed body. GitHub resends
#              the byte-identical body, so this catches a redelivery even on a
#              caller that cannot reach the header, and it keeps the shipped
#              endpoint idempotent on its own.
#
# The record is a bounded file next to the store, not an in-process set: a
# restart is exactly when a redelivery shows up, and a cache would forget the
# delivery it has to suppress. It is claimed *before* the routines run, so a
# duplicate that arrives while the first is still running is a no-op rather than
# a second fire; a run that raises releases the claim so GitHub's retry can
# have another go.
#
# Known limit: an operator who deliberately replays a byte-identical event is
# indistinguishable from a redelivery and is suppressed. Re-running a routine by
# hand is "Run now"; replaying a webhook is not an operation this store offers.

GITHUB_DELIVERY_HEADER = "X-GitHub-Delivery"
DELIVERY_LOG_SCHEMA = 1
# GitHub retries a delivery for ~24h; a few hundred ids is far more headroom.
MAX_TRACKED_DELIVERIES = 512
_delivery_lock = threading.RLock()
_DELIVERY_ID_RE = re.compile(r"[A-Za-z0-9._:-]{1,200}")


def delivery_log_path() -> Path:
    """Sidecar recording delivered GitHub webhook ids (#1667)."""
    return Path(f"{routines_path()}.webhook_deliveries.json")


def delivery_id_key(value: Any) -> str:
    """Normalise a delivery id, or "" when it cannot be a dedupe key.

    Bounded and plain on purpose: the value arrives in a request header and is
    written to disk, so a hostile or broken id must not be able to grow the
    record without limit. An unusable id is simply not a key — the delivery then
    behaves as it did before #1667 rather than being recorded.
    """
    text = str(value or "").strip()
    return text if _DELIVERY_ID_RE.fullmatch(text) else ""


def delivery_keys(
    payload: Any,
    *,
    event_header: str = "",
    delivery_id: str = "",
) -> list[str]:
    """Every key that identifies this delivery, most precise first."""
    keys: list[str] = []
    header_id = delivery_id_key(delivery_id)
    if header_id:
        keys.append(f"id:{header_id}")
    try:
        blob = json.dumps(
            [str(event_header or ""), payload], sort_keys=True, default=str
        )
    except (TypeError, ValueError):
        blob = repr(payload)
    keys.append("sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest())
    return keys


def _read_delivery_log(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A missing or unreadable record must not block a delivery: the worst
        # case is the pre-#1667 behaviour (a redelivery is not recognised).
        logger.warning("Could not read the delivery record at %s", path, exc_info=True)
        return []
    keys = data.get("keys") if isinstance(data, dict) else None
    if not isinstance(keys, list):
        return []
    return [str(item) for item in keys if isinstance(item, str)]


def _write_delivery_log(path: Path, keys: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": DELIVERY_LOG_SCHEMA, "keys": keys[-MAX_TRACKED_DELIVERIES:]}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _claim_delivery(keys: list[str]) -> bool:
    """Record *keys* as delivered. False when this delivery was already seen.

    Fails closed: a record that cannot be locked or written raises ``OSError``
    so the caller answers non-2xx and GitHub retries, rather than running the
    event again with nothing to suppress the next redelivery.
    """
    path = delivery_log_path()
    pending = set(keys)
    with _delivery_lock, _locked_file(
        path, busy="Could not lock the GitHub delivery record."
    ):
        seen = _read_delivery_log(path)
        if pending & set(seen):
            return False
        kept = [key for key in seen if key not in pending]
        _write_delivery_log(path, kept + keys)
        return True


def _release_delivery(keys: list[str]) -> None:
    """Forget a claim whose run failed, so a redelivery can be retried."""
    path = delivery_log_path()
    pending = set(keys)
    with _delivery_lock:
        try:
            with _locked_file(
                path, busy="Could not lock the GitHub delivery record."
            ):
                seen = _read_delivery_log(path)
                kept = [key for key in seen if key not in pending]
                if len(kept) != len(seen):
                    _write_delivery_log(path, kept)
        except OSError:
            logger.warning(
                "Could not release the GitHub delivery claim", exc_info=True
            )


def deliver_github_event(
    payload: dict[str, Any] | None,
    *,
    event_header: str | None = None,
    delivery_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fire matching Active ``github_event`` routines for one webhook payload.

    A delivery already recorded (see the dedupe block above) is a no-op that
    fires nothing, so the caller still answers 2xx: GitHub stops redelivering,
    no second turn reaches the conversation, and no "busy" error row appears.
    """
    event = parse_github_webhook_event(payload, event_header)
    keys = delivery_keys(
        payload,
        event_header=str(event_header or ""),
        delivery_id=str(delivery_id or ""),
    )
    if not _claim_delivery(keys):
        logger.info("Ignoring a redelivered GitHub webhook (already delivered)")
        return []
    try:
        return _deliver_github_event(event)
    except Exception:
        _release_delivery(keys)
        raise


def _deliver_github_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    store = _read_store()
    fired: list[dict[str, Any]] = []
    owner_repo = str(event.get("owner_repo") or "").lower()
    event_type = str(event.get("event_type") or "")
    event_label = str(event.get("event_label") or event_type)
    for agent_id, rows in list((store.get("agents") or {}).items()):
        if not isinstance(rows, list):
            continue
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            routine = public_routine(raw)
            trigger = routine["trigger"]
            if not routine["active"]:
                continue
            if trigger.get("kind") != TRIGGER_GITHUB_EVENT:
                continue
            if trigger.get("event_type") != event_type:
                continue
            if owner_repo_is_fill_in(trigger.get("owner_repo")):
                continue
            if str(trigger.get("owner_repo") or "").lower() != owner_repo:
                continue
            if not github_event_filters_match(trigger, event):
                continue
            prompt = format_github_event_briefing(event, str(routine.get("instruction") or ""))
            conversation_id = github_event_conversation_id(event)
            spawn_github_event_session(agent_id, conversation_id, prompt)
            if live_dispatch_enabled():
                _dispatch_live_job(
                    agent_id,
                    conversation_id,
                    prompt,
                    routine,
                    github_event=event,
                )
            updated = fire_routine(
                agent_id,
                routine["id"],
                source=SOURCE_GITHUB_WEBHOOK,
                prompt=prompt,
                event=event_label,
                conversation_id=conversation_id,
                summary=f"Agent ran routine {routine.get('name')} for {event_label}.",
            )
            fired.append({"agent_id": normalize_agent_id(agent_id), "routine": updated})
    return fired



# --- #862: presets + live dispatch --------------------------------------------------

ROUTINE_PRESETS: list[dict[str, Any]] = [
    {
        "key": "github_issue_solver",
        "name": "GitHub Issue Solver (Issue → PR)",
        "role": "developer",
        "description": (
            "Fires on issues.opened: investigates the issue in the repo, "
            "develops a fix with tests on fix/issue-<num>, and opens a PR "
            "whose body closes the issue."
        ),
        "instruction": (
            "You are the developer agent for this repository. Investigate the "
            "issue above: read the referenced code, reproduce the defect, and "
            "implement a minimal fix with tests. Work on a branch named "
            "fix/issue-<number>. Verify the relevant test suites pass, push "
            "the branch, and open a pull request titled after the issue with "
            "a body containing 'Closes #<number>'. Report the PR URL."
        ),
        "tools": [TOOL_OPEN_PULL_REQUEST],
        "max_turns": 3,
        "trigger": {
            "kind": "github_event",
            "event_type": "issues.opened",
            "owner_repo": "",
            "filters": {
                "exclude_authors": ["open-swarm[bot]", "github-actions[bot]", "app/open-swarm"],
            },
        },
    },
    {
        "key": "github_pr_reviewer",
        "name": "GitHub PR Reviewer (PR → Review & Test)",
        "role": "reviewer",
        "description": (
            "Fires on pull_request.opened: checks out the PR branch, runs the "
            "test suites and linters, reviews the diff for correctness and "
            "security, and posts the review verdict as a PR comment."
        ),
        "instruction": (
            "You are the QA/reviewer agent for this repository — you never "
            "author the change under review. Check out the PR branch, run the "
            "relevant test suites and linters in isolation, and review the "
            "diff for correctness, regressions, and security. Post your "
            "findings as a PR comment: a verdict (approve / request changes) "
            "with the failing commands and reasons if any."
        ),
        "max_turns": 2,
        "trigger": {
            "kind": "github_event",
            "event_type": "pull_request.opened",
            "owner_repo": "",
            "filters": {
                "exclude_authors": ["open-swarm[bot]", "github-actions[bot]", "app/open-swarm"],
            },
        },
    },
    {
        "key": "ocr_code_review",
        "name": "Open Code Review (PR → ocr review)",
        "role": "skeptic",
        "description": (
            "Fires on pull_request.opened: runs `ocr review --format json` "
            "on the PR checkout and posts the skeptic verdict and gate "
            "classification. The ocr CLI uses its own configured model "
            "endpoint; no hosted Alibaba account is required."
        ),
        "instruction": (
            "You are the reviewer for this pull request — you never author "
            "the change under review. Check out the PR branch, then run "
            "`ocr review --format json` (add `--from <base> --to <head>` when "
            "both refs are known). Read the JSON: report a skeptic verdict "
            "(pass or request changes) and a gate classification (safe or "
            "hold), and quote each finding with its file and line. If `ocr` "
            "is not installed, say so and stop. Do not configure an Alibaba "
            "account; `ocr` uses the OpenAI- or Anthropic-compatible endpoint "
            "already set with `ocr config provider`."
        ),
        "max_turns": 2,
        "trigger": {
            "kind": "github_event",
            "event_type": "pull_request.opened",
            "owner_repo": "",
            "filters": {
                "exclude_authors": ["open-swarm[bot]", "github-actions[bot]", "app/open-swarm"],
            },
        },
    },
]


def routine_presets() -> list[dict[str, Any]]:
    """Public preset templates for the routines UI (deep-copied)."""
    return json.loads(json.dumps(ROUTINE_PRESETS))

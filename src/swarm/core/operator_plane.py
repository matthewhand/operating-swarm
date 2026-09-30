"""Operator control plane borrowed from Paperclip (#1360).

Paperclip is a peer control plane ("the company"), not a model seat. This
module does **not** subclass ``KindBase`` and is not a ``REMOTE_IMPL_IDS``
entry. It adds four local primitives on top of rosters and routines:

* per-seat and per-team budgets with a hard-stop
* atomic task checkout (execution lock) so a routine cannot double-run
* revisioned approval gates with append-only rollback
* portable ``os-org-pack`` export/import with secret scrubbing

Spend is an integer counter. Token budgets count tokens. Cost budgets count
micros of a currency unit (1 unit = 1_000_000 micros) so the store never
holds binary floats. A hard-stop refuses the charge that would pass the
limit and refuses later work until an operator resets usage or raises the
limit. There is no calendar window: usage is unbounded until reset.

The store file lives next to the routines file (or
``SWARM_OPERATOR_PLANE_PATH``). Checkout is atomic on this host via a
process thread lock plus ``flock``. It is not a multi-host distributed
claim.
"""

from __future__ import annotations

import contextlib
import copy
import fcntl
import json
import logging
import os
import re
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from swarm.core.schedule_triggers import reject_secrets

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_PATH = "SWARM_OPERATOR_PLANE_PATH"
PACK_SCHEMA = 1
PACK_KIND = "os-org-pack"
SCOPES = ("seat", "team")
COLLISION_MODES = ("rename", "skip", "error")
DEFAULT_LEASE_S = 900
ROUTINE_LEASE_S = 600
MAX_COUNTER = 10**15
MAX_DOCUMENT_CHARS = 256_000
MAX_DEPTH = 32
SCRUBBED = "[scrubbed]"

_IDENT_RE = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
_SECRET_VALUE_RE = re.compile(
    r"(ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+|"
    r"sk-[A-Za-z0-9_\-]{8,}|xai-[A-Za-z0-9_\-]{8,}|"
    r"Bearer\s+[A-Za-z0-9._\-]{12,})",
    re.IGNORECASE,
)
_SECRET_KEY_SUFFIXES = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "passwd",
    "token",
    "private_key",
    "credential",
    "credentials",
)
_SECRET_KEYS = frozenset(
    {
        *_SECRET_KEY_SUFFIXES,
        "authorization",
        "cookie",
        "set-cookie",
        "headers",
        "env",
        "client_secret",
        "access_token",
        "refresh_token",
        "id_token",
        "auth_token",
        "webhook_secret",
    }
)
_SENSITIVE_QUERY = frozenset(
    {"token", "api_key", "apikey", "key", "auth", "auth_token", "password", "secret"}
)

_thread_lock = threading.RLock()


class OperatorPlaneError(Exception):
    """Store or pack failure that is not a caller validation error."""


class BudgetHardStop(OperatorPlaneError):
    """A seat or team is out of budget and hard-stop is on."""

    def __init__(
        self,
        *,
        scope: str,
        scope_id: str,
        metric: str,
        limit: int,
        used: int,
        attempted: int,
    ) -> None:
        self.scope = scope
        self.scope_id = scope_id
        self.metric = metric
        self.limit = limit
        self.used = used
        self.attempted = attempted
        super().__init__(
            f"Budget hard-stop for {scope} {scope_id}: {metric} "
            f"used {used} limit {limit} (refused {attempted})."
        )


class TaskBusy(OperatorPlaneError):
    """Another live worker holds this task."""

    def __init__(self, task_id: str, holder: str) -> None:
        self.task_id = task_id
        self.holder = holder
        super().__init__(f"Task {task_id} is already checked out by {holder}.")


class TaskNotHeld(OperatorPlaneError):
    """Release requested by a worker that does not hold the task."""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id} is not held by this worker.")


class ApprovalError(OperatorPlaneError):
    """The gate revision cannot take this decision."""


class OrgPackError(OperatorPlaneError):
    """The portable org pack is missing, colliding, or invalid."""


def routine_task_id(agent_id: str, routine_id: str) -> str:
    """Execution-lock id for one agent routine."""
    return f"routine:{agent_id}:{routine_id}"


def store_path() -> Path:
    """JSON store. Override with ``SWARM_OPERATOR_PLANE_PATH``.

    Otherwise the file sits next to the routines store, so a test that
    relocates ``SWARM_AGENT_ROUTINES_PATH`` also relocates execution locks
    and budgets away from the operator's real config directory.
    """
    override = (os.environ.get(ENV_PATH) or "").strip()
    if override:
        return Path(override)
    from swarm.core.routines import routines_path

    return routines_path().with_name("operator_plane.json")


def _empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "budgets": {}, "checkouts": {}, "gates": {}}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _ident(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not _IDENT_RE.match(text):
        raise ValueError(
            f"{field} must be 1-256 characters of letters, digits, '.', '_', ':', or '-'."
        )
    return text


def _scope(value: Any) -> str:
    scope = str(value or "").strip().lower()
    if scope not in SCOPES:
        raise ValueError("scope must be seat or team.")
    return scope


def _nonneg_int(value: Any, field: str, *, allow_none: bool = False) -> int | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError(f"{field} must be an integer.")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer.")
    if value < 0 or value > MAX_COUNTER:
        raise ValueError(f"{field} is out of range.")
    return value


def _lease_s(value: Any) -> int:
    if value is None or value == "":
        return DEFAULT_LEASE_S
    parsed = _nonneg_int(value, "lease_s")
    assert parsed is not None
    if parsed > 86_400:
        raise ValueError("lease_s cannot exceed 86400.")
    return parsed


def _actor(value: Any) -> str:
    text = reject_secrets(str(value or "").strip(), "actor")
    if not text:
        raise ValueError("actor is required.")
    if len(text) > 80:
        raise ValueError("actor is too long (max 80).")
    return text


def _budget_key(scope: str, scope_id: str) -> str:
    return f"{scope}:{scope_id}"


def _is_secret_key(name: str) -> bool:
    lowered = re.sub(r"[\s\-]+", "_", (name or "").strip().lower())
    if lowered in _SECRET_KEYS:
        return True
    return any(lowered.endswith("_" + suffix) for suffix in _SECRET_KEY_SUFFIXES)


def _scrub_url(text: str) -> str:
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.query:
        return text
    kept = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_secret_key(key) and key.lower() not in _SENSITIVE_QUERY
    ]
    return urlunparse(parsed._replace(query=urlencode(kept)))


def _redact_string(text: str, path: str, scrubbed: list[str]) -> str:
    redacted = _SECRET_VALUE_RE.sub(SCRUBBED, text)
    if redacted != text:
        scrubbed.append(path)
        text = redacted
    if text.startswith("http://") or text.startswith("https://"):
        cleaned = _scrub_url(text)
        if cleaned != text:
            scrubbed.append(path)
            text = cleaned
    return text


def _scrub_node(value: Any, path: str, scrubbed: list[str], depth: int) -> Any:
    if depth > MAX_DEPTH:
        raise ValueError("Document is nested too deeply to export.")
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            child = f"{path}.{name}" if path else name
            if _is_secret_key(name):
                out[name] = SCRUBBED
                scrubbed.append(child)
                continue
            out[name] = _scrub_node(item, child, scrubbed, depth + 1)
        return out
    if isinstance(value, list):
        return [
            _scrub_node(item, f"{path}[{index}]", scrubbed, depth + 1)
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        return _redact_string(value, path or "<root>", scrubbed)
    if value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("Non-finite numbers cannot be exported.")
        return value
    raise ValueError(f"Unsupported value at {path or '<root>'}.")


def scrub_document(value: Any) -> tuple[Any, list[str]]:
    """Return a copy with credential-shaped keys and token strings removed."""
    scrubbed: list[str] = []
    cleaned = _scrub_node(value, "", scrubbed, 0)
    deduped: list[str] = []
    for item in scrubbed:
        if item not in deduped:
            deduped.append(item)
    return cleaned, deduped


def _json_copy(value: Any, field: str) -> Any:
    try:
        encoded = json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON-serializable.") from exc
    if len(encoded) > MAX_DOCUMENT_CHARS:
        raise ValueError(f"{field} is too large.")
    return json.loads(encoded)


def _read_store(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _empty()
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw) if raw.strip() else _empty()
    except (OSError, json.JSONDecodeError) as exc:
        raise OperatorPlaneError("Could not read the operator plane store.") from exc
    if not isinstance(parsed, dict):
        raise OperatorPlaneError("Operator plane store must be an object.")
    if parsed.get("schema", SCHEMA) != SCHEMA:
        raise OperatorPlaneError("Unsupported operator plane schema.")
    for key in ("budgets", "checkouts", "gates"):
        if not isinstance(parsed.get(key), dict):
            parsed[key] = {}
    parsed["schema"] = SCHEMA
    return parsed


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def _locked_read() -> dict[str, Any]:
    path = store_path()
    if not path.is_file():
        return _empty()
    lock_path = path.with_name(path.name + ".lock")
    with _thread_lock, open(lock_path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            return copy.deepcopy(_read_store(path))
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _locked_update(mutator):
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with _thread_lock, open(lock_path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            data = _read_store(path)
            try:
                return mutator(data)
            finally:
                _atomic_write(path, data)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _public_budget(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": row["scope"],
        "scope_id": row["scope_id"],
        "token_limit": row["token_limit"],
        "cost_micros_limit": row["cost_micros_limit"],
        "tokens_used": row["tokens_used"],
        "cost_micros_used": row["cost_micros_used"],
        "hard_stop": row["hard_stop"],
        "stopped": row["stopped"],
        "stop_reason": row.get("stop_reason") or "",
    }


def _exhausted_metric(row: dict[str, Any]) -> str | None:
    if not row.get("hard_stop", True):
        return None
    token_limit = row.get("token_limit")
    if token_limit is not None and row.get("tokens_used", 0) >= token_limit:
        return "tokens"
    cost_limit = row.get("cost_micros_limit")
    if cost_limit is not None and row.get("cost_micros_used", 0) >= cost_limit:
        return "cost_micros"
    return None


def _mark_stopped(row: dict[str, Any], metric: str) -> None:
    row["stopped"] = True
    row["stop_reason"] = metric
    logger.info(
        "Budget hard-stop %s %s (%s)",
        row.get("scope"),
        row.get("scope_id"),
        metric,
    )


def _ensure_open(data: dict[str, Any], scope: str, scope_id: str) -> None:
    row = data["budgets"].get(_budget_key(scope, scope_id))
    if not isinstance(row, dict):
        return
    if row.get("stopped"):
        metric = str(row.get("stop_reason") or "tokens")
        limit = (
            row.get("token_limit")
            if metric == "tokens"
            else row.get("cost_micros_limit")
        )
        used = (
            row.get("tokens_used")
            if metric == "tokens"
            else row.get("cost_micros_used")
        )
        raise BudgetHardStop(
            scope=scope,
            scope_id=scope_id,
            metric=metric,
            limit=int(limit or 0),
            used=int(used or 0),
            attempted=0,
        )
    metric = _exhausted_metric(row)
    if metric is None:
        return
    _mark_stopped(row, metric)
    limit = (
        row.get("token_limit") if metric == "tokens" else row.get("cost_micros_limit")
    )
    used = row.get("tokens_used") if metric == "tokens" else row.get("cost_micros_used")
    raise BudgetHardStop(
        scope=scope,
        scope_id=scope_id,
        metric=metric,
        limit=int(limit or 0),
        used=int(used or 0),
        attempted=0,
    )


def _apply_charge(
    data: dict[str, Any],
    scope: str,
    scope_id: str,
    tokens: int,
    cost_micros: int,
) -> dict[str, Any] | None:
    row = data["budgets"].get(_budget_key(scope, scope_id))
    if not isinstance(row, dict):
        return None
    if tokens == 0 and cost_micros == 0:
        return _public_budget(row)
    if row.get("hard_stop", True):
        token_limit = row.get("token_limit")
        if token_limit is not None and row["tokens_used"] + tokens > token_limit:
            _mark_stopped(row, "tokens")
            raise BudgetHardStop(
                scope=scope,
                scope_id=scope_id,
                metric="tokens",
                limit=int(token_limit),
                used=int(row["tokens_used"]),
                attempted=tokens,
            )
        cost_limit = row.get("cost_micros_limit")
        if (
            cost_limit is not None
            and row["cost_micros_used"] + cost_micros > cost_limit
        ):
            _mark_stopped(row, "cost_micros")
            raise BudgetHardStop(
                scope=scope,
                scope_id=scope_id,
                metric="cost_micros",
                limit=int(cost_limit),
                used=int(row["cost_micros_used"]),
                attempted=cost_micros,
            )
    row["tokens_used"] = int(row["tokens_used"]) + tokens
    row["cost_micros_used"] = int(row["cost_micros_used"]) + cost_micros
    return _public_budget(row)


def set_budget_policy(
    *,
    scope: str,
    scope_id: str,
    token_limit: Any = None,
    cost_micros_limit: Any = None,
    hard_stop: bool = True,
    reset_usage: bool = False,
) -> dict[str, Any]:
    """Create or replace a seat/team budget. Usage is kept unless reset."""
    scope = _scope(scope)
    scope_id = _ident(scope_id, "scope_id")
    token_limit = _nonneg_int(token_limit, "token_limit", allow_none=True)
    cost_micros_limit = _nonneg_int(
        cost_micros_limit, "cost_micros_limit", allow_none=True
    )
    if not isinstance(hard_stop, bool):
        raise ValueError("hard_stop must be a boolean.")

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        key = _budget_key(scope, scope_id)
        current = data["budgets"].get(key)
        if reset_usage or not isinstance(current, dict):
            tokens_used = 0
            cost_used = 0
        else:
            tokens_used = int(current.get("tokens_used") or 0)
            cost_used = int(current.get("cost_micros_used") or 0)
        row = {
            "scope": scope,
            "scope_id": scope_id,
            "token_limit": token_limit,
            "cost_micros_limit": cost_micros_limit,
            "tokens_used": tokens_used,
            "cost_micros_used": cost_used,
            "hard_stop": hard_stop,
            "stopped": False,
            "stop_reason": "",
        }
        metric = _exhausted_metric(row)
        if metric is not None:
            _mark_stopped(row, metric)
        data["budgets"][key] = row
        return _public_budget(row)

    return _locked_update(mutate)


def reset_budget(*, scope: str, scope_id: str) -> dict[str, Any]:
    """Clear usage and lift a hard-stop. Limits stay as configured."""
    scope = _scope(scope)
    scope_id = _ident(scope_id, "scope_id")

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        key = _budget_key(scope, scope_id)
        current = data["budgets"].get(key)
        if not isinstance(current, dict):
            raise KeyError(f"No budget for {scope} {scope_id}.")
        current["tokens_used"] = 0
        current["cost_micros_used"] = 0
        current["stopped"] = False
        current["stop_reason"] = ""
        metric = _exhausted_metric(current)
        if metric is not None:
            _mark_stopped(current, metric)
        return _public_budget(current)

    return _locked_update(mutate)


def list_budgets() -> list[dict[str, Any]]:
    data = _locked_read()
    rows = [
        _public_budget(row) for row in data["budgets"].values() if isinstance(row, dict)
    ]
    rows.sort(key=lambda row: (row["scope"], row["scope_id"]))
    return rows


def charge_budget(
    *,
    scope: str,
    scope_id: str,
    tokens: Any = 0,
    cost_micros: Any = 0,
) -> dict[str, Any] | None:
    """Debit a budget. No policy means unlimited (returns None).

    A hard-stop refuses the debit that would pass the limit and does not
    apply it. Later debits fail until reset.
    """
    scope = _scope(scope)
    scope_id = _ident(scope_id, "scope_id")
    token_value = _nonneg_int(tokens, "tokens")
    cost_value = _nonneg_int(cost_micros, "cost_micros")
    assert token_value is not None and cost_value is not None

    def mutate(data: dict[str, Any]) -> dict[str, Any] | None:
        _ensure_open(data, scope, scope_id)
        return _apply_charge(data, scope, scope_id, token_value, cost_value)

    return _locked_update(mutate)


def _public_checkout(row: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    expires = _parse_iso(row.get("lease_expires_at"))
    return {
        "task_id": row["task_id"],
        "worker_id": row["worker_id"],
        "checked_out_at": row["checked_out_at"],
        "lease_expires_at": row["lease_expires_at"],
        "expired": expires is None or expires <= now,
    }


def _checkout(
    data: dict[str, Any],
    task_id: str,
    worker_id: str,
    lease_s: int,
    moment: datetime,
) -> dict[str, Any]:
    current = data["checkouts"].get(task_id)
    if isinstance(current, dict):
        expires = _parse_iso(current.get("lease_expires_at"))
        holder = str(current.get("worker_id") or "")
        live = expires is not None and expires > moment
        if live and holder != worker_id:
            raise TaskBusy(task_id, holder)
    row = {
        "task_id": task_id,
        "worker_id": worker_id,
        "checked_out_at": _iso(moment),
        "lease_expires_at": _iso(moment + timedelta(seconds=lease_s)),
    }
    data["checkouts"][task_id] = row
    return _public_checkout(row, now=moment)


def _release(data: dict[str, Any], task_id: str, worker_id: str) -> None:
    current = data["checkouts"].get(task_id)
    if not isinstance(current, dict) or current.get("worker_id") != worker_id:
        raise TaskNotHeld(task_id)
    data["checkouts"].pop(task_id, None)


def checkout_task(
    task_id: str,
    worker_id: str,
    *,
    lease_s: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically take a task. The same worker refreshes its lease.

    A lease of 0 expires immediately so another worker can take the task.
    """
    task_id = _ident(task_id, "task_id")
    worker_id = _ident(worker_id, "worker_id")
    lease = _lease_s(lease_s)
    moment = now or _utcnow()

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        return _checkout(data, task_id, worker_id, lease, moment)

    return _locked_update(mutate)


def release_task(task_id: str, worker_id: str) -> None:
    """Release a checkout. Only the holding worker may release it."""
    task_id = _ident(task_id, "task_id")
    worker_id = _ident(worker_id, "worker_id")

    def mutate(data: dict[str, Any]) -> None:
        _release(data, task_id, worker_id)

    _locked_update(mutate)


def list_checkouts(*, now: datetime | None = None) -> list[dict[str, Any]]:
    moment = now or _utcnow()
    data = _locked_read()
    rows = [
        _public_checkout(row, now=moment)
        for row in data["checkouts"].values()
        if isinstance(row, dict)
    ]
    rows.sort(key=lambda row: row["task_id"])
    return rows


def begin_execution(
    *,
    task_id: str,
    worker_id: str,
    scope: str,
    scope_id: str,
    tokens: Any = 0,
    cost_micros: Any = 0,
    lease_s: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Hard-stop, charge, and checkout in one locked update.

    If the charge would pass the limit, the checkout is rolled back inside
    the same update so a refused run does not leave a lock behind.
    """
    task_id = _ident(task_id, "task_id")
    worker_id = _ident(worker_id, "worker_id")
    scope = _scope(scope)
    scope_id = _ident(scope_id, "scope_id")
    token_value = _nonneg_int(tokens, "tokens")
    cost_value = _nonneg_int(cost_micros, "cost_micros")
    assert token_value is not None and cost_value is not None
    lease = _lease_s(ROUTINE_LEASE_S if lease_s is None else lease_s)
    moment = now or _utcnow()

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        _ensure_open(data, scope, scope_id)
        checkout = _checkout(data, task_id, worker_id, lease, moment)
        if token_value or cost_value:
            try:
                _apply_charge(data, scope, scope_id, token_value, cost_value)
            except BudgetHardStop:
                _release(data, task_id, worker_id)
                raise
        return checkout

    return _locked_update(mutate)


def end_execution(*, task_id: str, worker_id: str) -> None:
    """Release a checkout taken by ``begin_execution``. Missing locks are ignored."""
    try:
        release_task(task_id, worker_id)
    except (TaskNotHeld, TaskBusy, ValueError):
        logger.info("Execution lock already clear for %s", task_id)


def _gate(data: dict[str, Any], subject_id: str) -> dict[str, Any]:
    row = data["gates"].get(subject_id)
    if not isinstance(row, dict):
        row = {"subject_id": subject_id, "current_revision": 0, "revisions": []}
        data["gates"][subject_id] = row
    if not isinstance(row.get("revisions"), list):
        row["revisions"] = []
    return row


def _public_revision(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "revision": row["revision"],
        "status": row["status"],
        "action": row["action"],
        "snapshot": copy.deepcopy(row.get("snapshot")),
        "actor": row.get("actor") or "",
        "at": row.get("at") or "",
        "restores": row.get("restores"),
        "reason": row.get("reason") or "",
        "scrubbed": list(row.get("scrubbed") or []),
    }


def _public_gate(row: dict[str, Any]) -> dict[str, Any]:
    revisions = [_public_revision(item) for item in row.get("revisions") or []]
    current = int(row.get("current_revision") or 0)
    snapshot = None
    for item in revisions:
        if item["revision"] == current and item["status"] == "approved":
            snapshot = item["snapshot"]
    pending = [item["revision"] for item in revisions if item["status"] == "pending"]
    return {
        "subject_id": row["subject_id"],
        "current_revision": current,
        "pending_revision": pending[-1] if pending else None,
        "snapshot": snapshot,
        "revisions": revisions,
    }


def _next_revision(row: dict[str, Any]) -> int:
    numbers = [
        int(item.get("revision") or 0)
        for item in row.get("revisions") or []
        if isinstance(item, dict)
    ]
    return (max(numbers) if numbers else 0) + 1


def propose_gate(
    subject_id: str,
    snapshot: Any,
    *,
    actor: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append a pending revision. Older pending revisions are superseded.

    The live approved snapshot does not change until ``decide_gate``.
    Credential-shaped fields in the snapshot are scrubbed before storage.
    """
    subject_id = _ident(subject_id, "subject_id")
    actor = _actor(actor)
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object.")
    copied = _json_copy(snapshot, "snapshot")
    cleaned, scrubbed = scrub_document(copied)
    moment = now or _utcnow()

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        row = _gate(data, subject_id)
        for item in row["revisions"]:
            if isinstance(item, dict) and item.get("status") == "pending":
                item["status"] = "superseded"
        revision = {
            "revision": _next_revision(row),
            "status": "pending",
            "action": "propose",
            "snapshot": cleaned,
            "actor": actor,
            "at": _iso(moment),
            "restores": None,
            "reason": "",
            "scrubbed": scrubbed,
        }
        row["revisions"].append(revision)
        return _public_gate(row)

    return _locked_update(mutate)


def decide_gate(
    subject_id: str,
    revision: int,
    *,
    approved: bool,
    actor: str,
    reason: str = "",
) -> dict[str, Any]:
    """Approve or reject one pending revision."""
    subject_id = _ident(subject_id, "subject_id")
    actor = _actor(actor)
    number = _nonneg_int(revision, "revision")
    if not isinstance(approved, bool):
        raise ValueError("approved must be a boolean.")
    note = reject_secrets(str(reason or "").strip(), "reason")
    if len(note) > 280:
        raise ValueError("reason is too long (max 280).")

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        row = data["gates"].get(subject_id)
        if not isinstance(row, dict):
            raise ApprovalError(f"No gate for {subject_id}.")
        match = None
        for item in row.get("revisions") or []:
            if isinstance(item, dict) and int(item.get("revision") or 0) == number:
                match = item
                break
        if match is None:
            raise ApprovalError(f"Revision {number} was not found.")
        if match.get("status") != "pending":
            raise ApprovalError(
                f"Revision {number} is {match.get('status')}, not pending."
            )
        match["status"] = "approved" if approved else "rejected"
        match["reason"] = note
        match["decided_by"] = actor
        if approved:
            row["current_revision"] = number
        return _public_gate(row)

    return _locked_update(mutate)


def rollback_gate(
    subject_id: str,
    to_revision: int,
    *,
    actor: str,
    reason: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Append an approved revision that restores an earlier approved snapshot."""
    subject_id = _ident(subject_id, "subject_id")
    actor = _actor(actor)
    number = _nonneg_int(to_revision, "to_revision")
    note = reject_secrets(str(reason or "").strip(), "reason")
    if len(note) > 280:
        raise ValueError("reason is too long (max 280).")
    moment = now or _utcnow()

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        row = data["gates"].get(subject_id)
        if not isinstance(row, dict):
            raise ApprovalError(f"No gate for {subject_id}.")
        match = None
        for item in row.get("revisions") or []:
            if isinstance(item, dict) and int(item.get("revision") or 0) == number:
                match = item
                break
        if match is None:
            raise ApprovalError(f"Revision {number} was not found.")
        if match.get("status") != "approved":
            raise ApprovalError(
                f"Revision {number} is {match.get('status')} and cannot be restored."
            )
        current_number = int(row.get("current_revision") or 0)
        if current_number == number:
            raise ApprovalError(f"Revision {number} is already current.")
        current_row = next(
            (
                item
                for item in row.get("revisions") or []
                if isinstance(item, dict)
                and int(item.get("revision") or 0) == current_number
            ),
            None,
        )
        if (
            isinstance(current_row, dict)
            and current_row.get("action") == "rollback"
            and current_row.get("restores") == number
        ):
            raise ApprovalError(f"Revision {number} is already the live snapshot.")
        for item in row["revisions"]:
            if isinstance(item, dict) and item.get("status") == "pending":
                item["status"] = "superseded"
        revision = {
            "revision": _next_revision(row),
            "status": "approved",
            "action": "rollback",
            "snapshot": copy.deepcopy(match.get("snapshot")),
            "actor": actor,
            "at": _iso(moment),
            "restores": number,
            "reason": note,
            "scrubbed": list(match.get("scrubbed") or []),
        }
        row["revisions"].append(revision)
        row["current_revision"] = revision["revision"]
        return _public_gate(row)

    return _locked_update(mutate)


def gate_state(subject_id: str) -> dict[str, Any]:
    subject_id = _ident(subject_id, "subject_id")
    data = _locked_read()
    row = data["gates"].get(subject_id)
    if not isinstance(row, dict):
        raise KeyError(f"No gate for {subject_id}.")
    return _public_gate(row)


def list_gates() -> list[dict[str, Any]]:
    data = _locked_read()
    rows = []
    for row in data["gates"].values():
        if not isinstance(row, dict):
            continue
        public = _public_gate(row)
        rows.append(
            {
                "subject_id": public["subject_id"],
                "current_revision": public["current_revision"],
                "pending_revision": public["pending_revision"],
            }
        )
    rows.sort(key=lambda item: item["subject_id"])
    return rows


def _policy_limits(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": row["scope"],
        "scope_id": row["scope_id"],
        "token_limit": row["token_limit"],
        "cost_micros_limit": row["cost_micros_limit"],
        "hard_stop": row["hard_stop"],
    }


def _agent_index(teams: list[dict[str, Any]]) -> list[dict[str, str]]:
    index: list[dict[str, str]] = []
    for team in teams:
        team_id = str(team.get("id") or "")
        for member in team.get("members") or []:
            if not isinstance(member, dict):
                continue
            index.append(
                {
                    "id": str(member.get("id") or ""),
                    "name": str(member.get("name") or member.get("id") or ""),
                    "kind": str(member.get("kind") or ""),
                    "role": str(member.get("role") or ""),
                    "team_id": team_id,
                }
            )
    return index


def _qualify(prefix: str, paths: list[str]) -> list[str]:
    qualified: list[str] = []
    for path in paths:
        if path.startswith("["):
            qualified.append(f"{prefix}{path}")
        elif path:
            qualified.append(f"{prefix}.{path}")
    return qualified


def _portable_routine(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": str(row.get("agent_id") or ""),
        "source_id": str(row.get("id") or row.get("source_id") or ""),
        "name": str(row.get("name") or ""),
        "instruction": str(row.get("instruction") or ""),
        "active": bool(row.get("active", True)),
        "trigger": row.get("trigger") if isinstance(row.get("trigger"), dict) else {},
    }


def export_org(
    *,
    name: str,
    teams: list[Any] | None = None,
    routines: list[Any] | None = None,
    budgets: list[Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a secret-scrubbed org pack. Does not write the roster store."""
    from swarm.core.team_rosters import normalize_roster, serialize_roster

    pack_name = reject_secrets(str(name or "").strip() or "org", "name")
    if len(pack_name) > 80:
        raise ValueError("name is too long (max 80).")
    cleaned_teams, team_paths = scrub_document(list(teams or []))
    scrubbed = _qualify("teams", team_paths)
    normalized_teams = []
    for raw in cleaned_teams:
        if not isinstance(raw, dict):
            raise OrgPackError("Each team must be an object.")
        normalized_teams.append(serialize_roster(normalize_roster(raw)))
    cleaned_routines, routine_paths = scrub_document(
        [
            _portable_routine(row)
            for row in list(routines or [])
            if isinstance(row, dict)
        ]
    )
    scrubbed.extend(_qualify("routines", routine_paths))
    cleaned_budgets, budget_paths = scrub_document(list(budgets or []))
    scrubbed.extend(_qualify("budgets", budget_paths))
    moment = now or _utcnow()
    return {
        "schema": PACK_SCHEMA,
        "kind": PACK_KIND,
        "name": pack_name,
        "exported_at": _iso(moment),
        "teams": normalized_teams,
        "agents": _agent_index(normalized_teams),
        "routines": cleaned_routines,
        "budgets": cleaned_budgets,
        "scrubbed": scrubbed,
    }


def export_live_org(
    *, name: str = "org", now: datetime | None = None
) -> dict[str, Any]:
    """Export saved rosters, routine definitions, and budget limits."""
    from swarm.core.routines import list_all_routines
    from swarm.core.team_rosters import load_team_rosters

    budgets = [_policy_limits(row) for row in list_budgets()]
    return export_org(
        name=name,
        teams=list(load_team_rosters().values()),
        routines=list_all_routines(),
        budgets=budgets,
        now=now,
    )


def _fresh_id(base: str, taken: set[str]) -> str:
    for number in range(2, 1001):
        candidate = f"{base}-{number}"
        if candidate not in taken and _IDENT_RE.match(candidate):
            return candidate
    raise OrgPackError(f"Could not rename team id {base}.")


def _rewrite_team(raw: dict[str, Any], id_map: dict[str, str]) -> dict[str, Any]:
    team = copy.deepcopy(raw)
    current = str(team.get("id") or "").strip()
    team["id"] = id_map.get(current, current)
    members = team.get("members")
    if members is None:
        members = team.get("agent_team") or []
        team["members"] = members
    if isinstance(members, list):
        for member in members:
            if not isinstance(member, dict):
                continue
            team_id = str(member.get("team_id") or "")
            if team_id in id_map:
                member["team_id"] = id_map[team_id]
            source = str(member.get("source") or "")
            if source.startswith("team:"):
                target = source[len("team:") :]
                if target in id_map:
                    member["source"] = "team:" + id_map[target]
    return team


def prepare_import(
    pack: Any,
    *,
    existing_ids: set[str] | None = None,
    on_collision: str = "rename",
) -> dict[str, Any]:
    """Validate a pack and plan team renames. Does not write."""
    from swarm.core.routines import public_routine
    from swarm.core.team_rosters import normalize_roster, serialize_roster

    if not isinstance(pack, dict):
        raise OrgPackError("Org pack must be an object.")
    if pack.get("kind") != PACK_KIND:
        raise OrgPackError("Org pack kind must be os-org-pack.")
    if pack.get("schema") != PACK_SCHEMA:
        raise OrgPackError("Unsupported org pack schema.")
    mode = str(on_collision or "").strip().lower()
    if mode not in COLLISION_MODES:
        raise ValueError("on_collision must be rename, skip, or error.")
    cleaned, _paths = scrub_document(pack)
    teams_in = cleaned.get("teams") or []
    if not isinstance(teams_in, list):
        raise OrgPackError("teams must be an array.")
    seen_in_pack: set[str] = set()
    for raw in teams_in:
        if not isinstance(raw, dict):
            raise OrgPackError("Each team must be an object.")
        rid = str(raw.get("id") or "").strip()
        if not rid:
            raise OrgPackError("Team id is required.")
        if rid in seen_in_pack:
            raise OrgPackError(f"Duplicate team id in pack: {rid}.")
        seen_in_pack.add(rid)
    taken = {str(item) for item in (existing_ids or set())}
    id_map: dict[str, str] = {}
    renames: list[dict[str, str]] = []
    skipped: list[str] = []
    for raw in teams_in:
        rid = str(raw.get("id") or "").strip()
        if rid in taken:
            if mode == "error":
                raise OrgPackError(f"Team id collision: {rid}.")
            if mode == "skip":
                skipped.append(rid)
                continue
            renamed = _fresh_id(rid, taken)
            id_map[rid] = renamed
            taken.add(renamed)
            renames.append({"from": rid, "to": renamed})
        else:
            id_map[rid] = rid
            taken.add(rid)
    teams: list[dict[str, Any]] = []
    for raw in teams_in:
        rid = str(raw.get("id") or "").strip()
        if rid not in id_map:
            continue
        rewritten = _rewrite_team(raw, id_map)
        try:
            teams.append(serialize_roster(normalize_roster(rewritten)))
        except ValueError as exc:
            raise OrgPackError(str(exc)) from exc
    routines_in = cleaned.get("routines") or []
    if not isinstance(routines_in, list):
        raise OrgPackError("routines must be an array.")
    routines: list[dict[str, Any]] = []
    for raw in routines_in:
        if not isinstance(raw, dict):
            raise OrgPackError("Each routine must be an object.")
        agent_id = str(raw.get("agent_id") or "").strip()
        if not agent_id:
            raise OrgPackError("Routine agent_id is required.")
        payload = {
            "name": raw.get("name") or "Imported routine",
            "instruction": raw.get("instruction") or "",
            "active": raw.get("active", True),
            "trigger": raw.get("trigger")
            if isinstance(raw.get("trigger"), dict)
            else {},
        }
        try:
            public_routine(payload)
        except ValueError as exc:
            raise OrgPackError(str(exc)) from exc
        routines.append({"agent_id": agent_id, **payload})
    budgets_in = cleaned.get("budgets") or []
    if not isinstance(budgets_in, list):
        raise OrgPackError("budgets must be an array.")
    budgets: list[dict[str, Any]] = []
    for raw in budgets_in:
        if not isinstance(raw, dict):
            raise OrgPackError("Each budget must be an object.")
        hard_stop = raw.get("hard_stop", True)
        if not isinstance(hard_stop, bool):
            raise OrgPackError("hard_stop must be a boolean.")
        budgets.append(
            {
                "scope": _scope(raw.get("scope")),
                "scope_id": _ident(raw.get("scope_id"), "scope_id"),
                "token_limit": _nonneg_int(
                    raw.get("token_limit"), "token_limit", allow_none=True
                ),
                "cost_micros_limit": _nonneg_int(
                    raw.get("cost_micros_limit"),
                    "cost_micros_limit",
                    allow_none=True,
                ),
                "hard_stop": hard_stop,
            }
        )
    return {
        "name": str(cleaned.get("name") or "org"),
        "teams": teams,
        "routines": routines,
        "budgets": budgets,
        "renames": renames,
        "skipped_teams": skipped,
        "agents": cleaned.get("agents")
        if isinstance(cleaned.get("agents"), list)
        else [],
    }


def install_org_pack(pack: Any, *, on_collision: str = "rename") -> dict[str, Any]:
    """Install teams, budget limits, and routines from a pack.

    Team id collisions follow ``on_collision``. Duplicate routines are
    skipped (the existing routine is kept). Imported budgets reset usage
    so a pack cannot smuggle spend into the ledger. Agent index entries
    are not turned into seats.
    """
    from swarm.core.routines import DuplicateRoutineError, create_routine
    from swarm.core.team_rosters import load_team_rosters, upsert_roster

    plan = prepare_import(
        pack,
        existing_ids=set(load_team_rosters()),
        on_collision=on_collision,
    )
    installed = []
    for team in plan["teams"]:
        installed.append(upsert_roster(team))
    for policy in plan["budgets"]:
        set_budget_policy(
            scope=policy["scope"],
            scope_id=policy["scope_id"],
            token_limit=policy["token_limit"],
            cost_micros_limit=policy["cost_micros_limit"],
            hard_stop=policy["hard_stop"],
            reset_usage=True,
        )
    created = 0
    skipped_routines: list[dict[str, str]] = []
    for routine in plan["routines"]:
        agent_id = routine["agent_id"]
        payload = {
            "name": routine["name"],
            "instruction": routine["instruction"],
            "active": routine["active"],
            "trigger": routine["trigger"],
        }
        try:
            create_routine(agent_id, payload)
            created += 1
        except DuplicateRoutineError as exc:
            skipped_routines.append(
                {
                    "agent_id": agent_id,
                    "name": str(routine["name"]),
                    "existing_id": exc.existing_id,
                }
            )
    return {
        "object": "org_import",
        "name": plan["name"],
        "teams": [row.get("id") for row in installed],
        "renames": plan["renames"],
        "skipped_teams": plan["skipped_teams"],
        "budgets": [f"{row['scope']}:{row['scope_id']}" for row in plan["budgets"]],
        "routines_created": created,
        "routines_skipped": skipped_routines,
    }


def plane_summary() -> dict[str, Any]:
    """Read-only snapshot for the operator API. Not a seat kind."""
    return {
        "object": "operator_plane",
        "budgets": list_budgets(),
        "checkouts": list_checkouts(),
        "gates": list_gates(),
    }

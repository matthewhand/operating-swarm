"""#1314 — operator activity log (Paperclip-style ActivityEvent).

Append-only audit spine for operator mutations. Every write redacts
``ActivityEvent.detail`` before it hits disk so credential-shaped values
never persist or leave the API.

Layout::

    <SWARM_USER_DATA_DIR>/activity_log.jsonl

    {"id": "...", "actor_type": "system", "actor_id": "nightly",
     "action": "agent.updated", "entity_type": "agent", "entity_id": "support",
     "agent_id": null, "run_id": null, "responsible_user_id": null,
     "detail": {"from": "paused", "to": "active"},
     "created_at": "2026-09-27T00:00:00+00:00"}

Not a seat kind. Not session_logger (per-blueprint markdown). This is the
operator feed: who changed what, when, with secrets already stripped.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from filelock import FileLock, Timeout

from swarm.core.paths import ensure_swarm_directories_exist, get_user_data_dir_for_swarm
from swarm.utils.redact import redact_sensitive_data

logger = logging.getLogger(__name__)

ENV_LOG_PATH = "SWARM_ACTIVITY_LOG_PATH"
ENV_VISIBILITY = "SWARM_ACTIVITY_LOG_VISIBILITY"

ACTOR_TYPES = ("agent", "user", "system", "plugin")
ActorType = Literal["agent", "user", "system", "plugin"]

VISIBILITY_OFF = "off"
VISIBILITY_OPERATOR = "operator"
VISIBILITY_ALL = "all"
VISIBILITY_VALUES = (VISIBILITY_OFF, VISIBILITY_OPERATOR, VISIBILITY_ALL)
DEFAULT_VISIBILITY = VISIBILITY_OPERATOR
PREF_ACTIVITY_LOG_VISIBILITY = "activity_log_visibility"

MAX_ACTION_LEN = 128
MAX_ID_LEN = 256
MAX_CREATED_AT_LEN = 64
MAX_DETAIL_BYTES = 16_384
# Envelope (ids, action, timestamps, JSON keys) on top of the detail cap.
MAX_EVENT_BYTES = MAX_DETAIL_BYTES + 4_096
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
SCRUB_MASK = "[REDACTED]"
LOCK_TIMEOUT_SECONDS = 5.0
_PRIVATE_FILE_MODE = 0o600
_current_actor: ContextVar[str | None] = ContextVar("activity_actor", default=None)


class ActivityLogError(ValueError):
    """Malformed activity event (safe to surface to operators)."""


class ActivityLogBusy(ActivityLogError):
    """Another process holds the activity-log lock."""


@dataclass(frozen=True)
class ActivityEvent:
    """One append-only operator activity row."""

    id: str
    actor_type: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    agent_id: str | None
    run_id: str | None
    responsible_user_id: str | None
    detail: dict[str, Any] | None
    created_at: str

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize for the API. ``detail`` is re-redacted on the way out."""
        payload = asdict(self)
        payload["detail"] = redact_activity_detail(self.detail)
        return payload


def activity_log_path() -> Path:
    """JSONL path. ``SWARM_ACTIVITY_LOG_PATH`` wins for tests/sandboxes."""
    env = (os.environ.get(ENV_LOG_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_data_dir_for_swarm() / "activity_log.jsonl"


def activity_lock_path(path: Path) -> Path:
    """Sibling lock file. Shared by every process that appends or reads."""
    return Path(f"{path}.lock")


def _file_lock(path: Path) -> FileLock:
    return FileLock(activity_lock_path(path), timeout=LOCK_TIMEOUT_SECONDS)


def _harden_log_file(path: Path) -> None:
    """User-only mode, same idea as the sqlite file. Best-effort."""
    with contextlib.suppress(OSError):
        os.chmod(path, _PRIVATE_FILE_MODE)


def redact_activity_detail(detail: Any) -> dict[str, Any] | None:
    """Strip credential-shaped keys and token patterns from ``detail``.

    ``None`` / empty stays ``None``. Non-dicts are wrapped under ``value``
    so a caller cannot smuggle a bare secret string past the scrubber.
    """
    if detail is None:
        return None
    if not isinstance(detail, dict):
        detail = {"value": detail}
    if not detail:
        return None
    redacted = redact_sensitive_data(detail, mask=SCRUB_MASK)
    if not isinstance(redacted, dict):
        return None
    return dict(redacted)


def _clean_id(value: Any, *, field: str, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ActivityLogError(f"{field} is required")
        return None
    text = str(value).strip()
    if not text:
        if required:
            raise ActivityLogError(f"{field} is required")
        return None
    if len(text) > MAX_ID_LEN:
        raise ActivityLogError(f"{field} is too long")
    return text


def _normalize_actor_type(value: Any) -> str:
    raw = str(value or "system").strip().lower()
    if raw not in ACTOR_TYPES:
        raise ActivityLogError(f"actor_type must be one of: {', '.join(ACTOR_TYPES)}")
    return raw


def _normalize_action(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ActivityLogError("action is required")
    if len(text) > MAX_ACTION_LEN:
        raise ActivityLogError("action is too long")
    return text


def _normalize_created_at(value: str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    text = str(value).strip()
    if not text:
        return datetime.now(UTC).isoformat()
    if len(text) > MAX_CREATED_AT_LEN:
        raise ActivityLogError("created_at is too long")
    return text


def _detail_byte_length(detail: Any) -> int:
    try:
        blob = json.dumps(detail, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        raise ActivityLogError("detail is not serializable") from exc
    return len(blob.encode("utf-8"))


def _incoming_detail(payload: dict[str, Any]) -> Any:
    """Accept Paperclip ``details`` or OS ``detail``."""
    if "detail" in payload:
        return payload.get("detail")
    return payload.get("details")


def persist_activity(
    *,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_type: str = "system",
    agent_id: str | None = None,
    run_id: str | None = None,
    responsible_user_id: str | None = None,
    detail: Any = None,
    event_id: str | None = None,
    created_at: str | None = None,
    path: Path | None = None,
) -> ActivityEvent:
    """Append one redacted ``ActivityEvent``. Never writes raw secrets.

    ``detail`` is scrubbed *before* the frozen event exists, so the in-memory
    row never holds a credential. ``to_public_dict`` re-scrubs on serialize
    as defense in depth, not a second chance at a live secret.

    Appends take an exclusive file lock so two uvicorn workers (or a worker
    and a direct caller) cannot tear a JSONL line. ``threading.Lock`` only
    covers one process.
    """
    if detail is not None and _detail_byte_length(detail) > MAX_DETAIL_BYTES:
        raise ActivityLogError("activity event is too large")
    raw_id = str(event_id).strip() if event_id else ""
    event = ActivityEvent(
        id=_clean_id(raw_id or str(uuid.uuid4()), field="id", required=True) or "",
        actor_type=_normalize_actor_type(actor_type),
        actor_id=_clean_id(actor_id, field="actor_id", required=True) or "",
        action=_normalize_action(action),
        entity_type=_clean_id(entity_type, field="entity_type", required=True) or "",
        entity_id=_clean_id(entity_id, field="entity_id", required=True) or "",
        agent_id=_clean_id(agent_id, field="agent_id"),
        run_id=_clean_id(run_id, field="run_id"),
        responsible_user_id=_clean_id(responsible_user_id, field="responsible_user_id"),
        detail=redact_activity_detail(detail),
        created_at=_normalize_created_at(created_at),
    )
    blob = json.dumps(event.to_public_dict(), ensure_ascii=False, default=str)
    if len(blob.encode("utf-8")) > MAX_EVENT_BYTES:
        raise ActivityLogError("activity event is too large")
    dest = path or activity_log_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    line = blob + "\n"
    try:
        with _file_lock(dest):
            with dest.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            _harden_log_file(dest)
    except Timeout as exc:
        raise ActivityLogBusy("activity log is busy") from exc
    _persist_django_row(event)
    return event


def _row_from_json(raw: Any) -> ActivityEvent | None:
    if not isinstance(raw, dict):
        return None
    try:
        return ActivityEvent(
            id=str(raw.get("id") or ""),
            actor_type=str(raw.get("actor_type") or "").strip().lower(),
            actor_id=str(raw.get("actor_id") or ""),
            action=str(raw.get("action") or ""),
            entity_type=str(raw.get("entity_type") or ""),
            entity_id=str(raw.get("entity_id") or ""),
            agent_id=(str(raw["agent_id"]) if raw.get("agent_id") else None),
            run_id=(str(raw["run_id"]) if raw.get("run_id") else None),
            responsible_user_id=(
                str(raw["responsible_user_id"])
                if raw.get("responsible_user_id")
                else None
            ),
            detail=redact_activity_detail(_incoming_detail(raw)),
            created_at=str(raw.get("created_at") or ""),
        )
    except (TypeError, ValueError):
        return None


def _read_rows(path: Path) -> list[ActivityEvent]:
    try:
        with _file_lock(path):
            if not path.is_file():
                return []
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Could not read activity log at %s", path, exc_info=True)
                return []
    except Timeout as exc:
        raise ActivityLogBusy("activity log is busy") from exc
    events: list[ActivityEvent] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        event = _row_from_json(raw)
        if event is not None:
            events.append(event)
    return events


def _matches(
    event: ActivityEvent,
    *,
    actor_type: str | None,
    action: str | None,
    entity_type: str | None,
    entity_id: str | None,
    agent_id: str | None,
) -> bool:
    if actor_type and event.actor_type != actor_type:
        return False
    if action and not event.action.startswith(action):
        return False
    if entity_type and event.entity_type != entity_type:
        return False
    if entity_id and event.entity_id != entity_id:
        return False
    if agent_id and event.agent_id != agent_id:
        return False
    return True


def list_activity(
    *,
    actor_type: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    agent_id: str | None = None,
    owner_principal: str | None = None,
    limit: int = DEFAULT_LIMIT,
    path: Path | None = None,
) -> list[ActivityEvent]:
    """Newest-first page. Filters are exact except ``action`` (prefix)."""
    try:
        size = int(limit)
    except (TypeError, ValueError):
        size = DEFAULT_LIMIT
    size = max(1, min(size, MAX_LIMIT))
    actor = (actor_type or "").strip().lower() or None
    if actor and actor not in ACTOR_TYPES:
        raise ActivityLogError(f"actor_type must be one of: {', '.join(ACTOR_TYPES)}")
    action_prefix = (action or "").strip() or None
    etype = (entity_type or "").strip() or None
    eid = (entity_id or "").strip() or None
    aid = (agent_id or "").strip() or None
    owner = (owner_principal or "").strip() or None
    rows = _read_rows(path or activity_log_path())
    matched = [
        row
        for row in rows
        if _matches(
            row,
            actor_type=actor,
            action=action_prefix,
            entity_type=etype,
            entity_id=eid,
            agent_id=aid,
        )
        and (not owner or row.actor_id == owner or row.responsible_user_id == owner)
    ]
    matched.sort(key=lambda row: (row.created_at, row.id), reverse=True)
    return matched[:size]


def persist_from_payload(
    payload: dict[str, Any], *, actor_id_default: str = "operator"
) -> ActivityEvent:
    """Build an event from a POST body. ``detail`` / ``details`` both work."""
    if not isinstance(payload, dict):
        raise ActivityLogError("body must be an object")
    actor_id = payload.get("actor_id") or actor_id_default
    return persist_activity(
        actor_type=str(payload.get("actor_type") or "system"),
        actor_id=str(actor_id),
        action=str(payload.get("action") or ""),
        entity_type=str(payload.get("entity_type") or ""),
        entity_id=str(payload.get("entity_id") or ""),
        agent_id=payload.get("agent_id"),
        run_id=payload.get("run_id"),
        responsible_user_id=payload.get("responsible_user_id"),
        detail=_incoming_detail(payload),
    )


def public_list(events: Iterable[ActivityEvent]) -> list[dict[str, Any]]:
    return [event.to_public_dict() for event in events]


def set_activity_actor(actor_id: str | None):
    """Bind the current mutation principal for emit hooks (request-scoped)."""
    return _current_actor.set((actor_id or "").strip() or None)


def reset_activity_actor(token) -> None:
    _current_actor.reset(token)


def current_activity_actor(default: str = "system") -> str:
    return _current_actor.get() or default


@contextmanager
def bound_activity_actor(actor_id: str | None) -> Iterator[str]:
    """Bind ``actor_id`` for the duration of a mutation request."""
    principal = (actor_id or "").strip() or None
    token = set_activity_actor(principal)
    try:
        yield principal or "system"
    finally:
        reset_activity_actor(token)


def emit_activity(
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_id: str | None = None,
    actor_type: str = "user",
    agent_id: str | None = None,
    run_id: str | None = None,
    responsible_user_id: str | None = None,
    detail: Any = None,
) -> ActivityEvent | None:
    """Best-effort persist. Mutations must not fail if the log write fails."""
    try:
        return persist_activity(
            actor_type=actor_type,
            actor_id=actor_id or current_activity_actor(),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            agent_id=agent_id,
            run_id=run_id,
            responsible_user_id=responsible_user_id,
            detail=detail,
        )
    except Exception:
        logger.warning("activity emit failed action=%s entity=%s", action, entity_id, exc_info=True)
        return None


def coerce_visibility(value: Any) -> str:
    """Lenient visibility parse. Unknown values fall back to the default."""
    text = str(value or "").strip().lower()
    return text if text in VISIBILITY_VALUES else DEFAULT_VISIBILITY


def normalize_visibility(value: Any) -> str:
    text = str(value or DEFAULT_VISIBILITY).strip().lower()
    if text not in VISIBILITY_VALUES:
        raise ActivityLogError(
            f"activity_log_visibility must be one of: {', '.join(VISIBILITY_VALUES)}"
        )
    return text


def visibility_path() -> Path:
    return activity_log_path().with_name("activity_log_visibility")


def get_activity_log_visibility() -> str:
    env = (os.environ.get(ENV_VISIBILITY) or "").strip().lower()
    if env in VISIBILITY_VALUES:
        return env
    path = visibility_path()
    if path.is_file():
        try:
            raw = path.read_text(encoding="utf-8").strip().lower()
            if raw in VISIBILITY_VALUES:
                return raw
        except OSError:
            logger.debug("activity visibility read failed", exc_info=True)
    return DEFAULT_VISIBILITY


def set_activity_log_visibility(value: Any) -> str:
    mode = normalize_visibility(value)
    path = visibility_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(mode + "\n", encoding="utf-8")
    return mode


def is_operator_request(request) -> bool:
    """Staff/superuser or a presenting API token is an operator.

    Unauthenticated callers are operators only when API auth is off
    (single-user / test default).
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
    if getattr(request, "auth", None):
        return True
    from django.conf import settings as django_settings

    return not bool(getattr(django_settings, "ENABLE_API_AUTH", False))


def request_actor_id(request) -> str:
    try:
        from swarm.auth import request_principal

        principal = request_principal(request)
        if principal:
            return principal
    except Exception:
        logger.debug("activity principal lookup failed", exc_info=True)
    return "operator"


def _persist_django_row(event: ActivityEvent) -> None:
    try:
        from swarm.models.activity import ActivityEventRow

        ActivityEventRow.objects.update_or_create(
            event_id=event.id,
            defaults={
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "action": event.action,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "agent_id": event.agent_id or "",
                "run_id": event.run_id or "",
                "responsible_user_id": event.responsible_user_id or "",
                "detail": event.detail,
                "created_at": event.created_at,
            },
        )
    except Exception:
        logger.debug("activity django persist skipped", exc_info=True)

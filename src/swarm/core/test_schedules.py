"""Test schedule store (#222) — recurring fleet proofs beside Routines.

File-backed JSON next to ``agent_routines.json``. Triggers are time-based
only (``interval``, ``cron``, ``one_shot``). Target is an agent/seat or a
fleet subset; check names a harness/script/blueprint smoke.

Empty stores seed the fleet-proof entries (disabled) so the Test schedule
pane has first-class rows. Schedules tick in-process with Routines
(``schedule_engine``). No distributed claims. No secrets.

Layout::

    <user-config>/test_schedules.json

    {
      "schema": 1,
      "schedules": [ { "id", "name", "active", "trigger", "target", "check", "history" } ]
    }
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm
from swarm.core.schedule_triggers import (
    TEST_SCHEDULE_TRIGGER_KINDS,
    TIME_TRIGGER_KINDS,
    TRIGGER_CRON,
    TRIGGER_INTERVAL,
    TRIGGER_ONE_SHOT,
    compute_next_run,
    is_due,
    parse_dt,
    public_history_extras,
    public_time_trigger,
    reject_secrets,
    time_trigger_summary,
    to_iso,
    utcnow,
)

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_TEST_SCHEDULES_PATH = "SWARM_TEST_SCHEDULES_PATH"
SOURCE_RUN_NOW = "run_now"
SOURCE_SCHEDULE = "schedule"
HISTORY_STATUS_SUCCESS = "success"
HISTORY_STATUS_ERROR = "error"
HISTORY_STATUS_FAIL = "fail"

TARGET_AGENT = "agent"
TARGET_FLEET = "fleet"
CHECK_HARNESS_HEALTH = "harness_health"
CHECK_BLUEPRINT_SMOKE = "blueprint_smoke"
CHECK_SCRIPT = "script"
CHECK_REMOTE_HARNESS = "remote_harness"
CHECK_KINDS = frozenset(
    {CHECK_HARNESS_HEALTH, CHECK_BLUEPRINT_SMOKE, CHECK_SCRIPT, CHECK_REMOTE_HARNESS}
)

SEED_REMOTE_HEALTH = "seed-remote-harness-health"
SEED_BLUEPRINT_SMOKE = "seed-blueprint-smoke"
SEED_FLEET_PROVE = "seed-fleet-prove"

CheckRunner = Callable[[dict[str, Any]], dict[str, Any]]
FailureNotifier = Callable[[dict[str, Any], dict[str, Any]], None]

_cache: dict[str, Any] | None = None
_check_runner: CheckRunner | None = None
_failure_notifier: FailureNotifier | None = None
_fired_checks: list[dict[str, Any]] = []
_notified_failures: list[dict[str, Any]] = []


def test_schedules_path() -> Path:
    env = (os.environ.get(ENV_TEST_SCHEDULES_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "test_schedules.json"


def reset_test_schedules_cache() -> None:
    global _cache
    _cache = None
    _fired_checks.clear()
    _notified_failures.clear()


def set_check_runner(runner: CheckRunner | None) -> None:
    global _check_runner
    _check_runner = runner


def set_failure_notifier(notifier: FailureNotifier | None) -> None:
    global _failure_notifier
    _failure_notifier = notifier


def fired_checks() -> list[dict[str, Any]]:
    return list(_fired_checks)


def notified_failures() -> list[dict[str, Any]]:
    return list(_notified_failures)


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return utcnow().isoformat()


def seed_schedules() -> list[dict[str, Any]]:
    """First-class fleet proof rows. Disabled so an empty fleet does not fire."""
    return [
        public_schedule(
            {
                "id": SEED_REMOTE_HEALTH,
                "name": "Remote harness health",
                "active": False,
                "trigger": {"kind": TRIGGER_INTERVAL, "seconds": 3600},
                "target": {"kind": TARGET_FLEET, "fleet": "all"},
                "check": {"kind": CHECK_HARNESS_HEALTH, "name": "remote_health"},
                "history": [],
            }
        ),
        public_schedule(
            {
                "id": SEED_BLUEPRINT_SMOKE,
                "name": "Blueprint smoke tests",
                "active": False,
                "trigger": {"kind": TRIGGER_INTERVAL, "seconds": 6 * 3600},
                "target": {"kind": TARGET_FLEET, "fleet": "all"},
                "check": {"kind": CHECK_BLUEPRINT_SMOKE, "name": "blueprint_smoke"},
                "history": [],
            }
        ),
        public_schedule(
            {
                "id": SEED_FLEET_PROVE,
                "name": "Fleet remote prove",
                "active": False,
                "trigger": {"kind": TRIGGER_CRON, "expression": "0 3 * * *"},
                "target": {"kind": TARGET_FLEET, "fleet": "all"},
                "check": {"kind": CHECK_SCRIPT, "name": "fleet_prove"},
                "history": [],
            }
        ),
    ]


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "schedules": seed_schedules()}


def _read_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = test_schedules_path()
    if not path.is_file():
        _cache = _empty_store()
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read test schedules at %s", path, exc_info=True)
        _cache = _empty_store()
        return _cache
    if not isinstance(data, dict):
        _cache = _empty_store()
        return _cache
    rows = data.get("schedules")
    if not isinstance(rows, list):
        rows = []
    _cache = {"schema": SCHEMA, "schedules": list(rows)}
    return _cache


def _write_store(store: dict[str, Any]) -> None:
    global _cache
    path = test_schedules_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "schedules": store.get("schedules") or []}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _cache = payload


def public_target(raw: Any) -> dict[str, str]:
    incoming = raw if isinstance(raw, dict) else {}
    kind = str(incoming.get("kind") or TARGET_AGENT).strip() or TARGET_AGENT
    if kind not in {TARGET_AGENT, TARGET_FLEET}:
        raise ValueError("target.kind must be agent or fleet.")
    if kind == TARGET_FLEET:
        fleet = reject_secrets(str(incoming.get("fleet") or "all").strip() or "all", "target.fleet")
        return {"kind": TARGET_FLEET, "fleet": fleet}
    agent_id = normalize_agent_id(incoming.get("agent_id") or incoming.get("seat") or "")
    return {"kind": TARGET_AGENT, "agent_id": agent_id}


def public_check(raw: Any) -> dict[str, str]:
    incoming = raw if isinstance(raw, dict) else {}
    kind = str(incoming.get("kind") or CHECK_SCRIPT).strip() or CHECK_SCRIPT
    if kind not in CHECK_KINDS:
        raise ValueError(
            "check.kind must be harness_health, blueprint_smoke, script, or remote_harness."
        )
    name = reject_secrets(str(incoming.get("name") or kind).strip() or kind, "check.name")
    out = {"kind": kind, "name": name}
    command = reject_secrets(str(incoming.get("command") or "").strip(), "check.command")
    if command:
        out["command"] = command
    return out


def public_history_row(raw: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    ran_at = str(raw.get("ran_at") or "").strip()
    if not ran_at:
        return None
    status = str(raw.get("status") or HISTORY_STATUS_SUCCESS).strip() or HISTORY_STATUS_SUCCESS
    source = str(raw.get("source") or SOURCE_RUN_NOW).strip() or SOURCE_RUN_NOW
    row: dict[str, Any] = {
        "id": str(raw.get("id") or "").strip() or _new_id(),
        "ran_at": ran_at,
        "status": status,
        "source": source,
    }
    summary = reject_secrets(str(raw.get("summary") or "").strip(), "summary")
    if summary:
        row["summary"] = summary
    row.update(public_history_extras(raw))
    return row


def _last_run_dt(history: list[dict[str, Any]]) -> datetime | None:
    if not history:
        return None
    return parse_dt(history[0].get("ran_at"))


def public_schedule(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = raw if isinstance(raw, dict) else {}
    history: list[dict[str, Any]] = []
    for item in incoming.get("history") or []:
        row = public_history_row(item if isinstance(item, dict) else None)
        if row:
            history.append(row)
    history.sort(key=lambda row: row["ran_at"], reverse=True)
    trigger = public_time_trigger(
        incoming.get("trigger") if isinstance(incoming.get("trigger"), dict) else {"kind": TRIGGER_INTERVAL, "seconds": 3600},
        allowed=TEST_SCHEDULE_TRIGGER_KINDS,
    )
    next_run = str(incoming.get("next_run") or "").strip() or None
    if not next_run:
        nxt = compute_next_run(trigger, last_run=_last_run_dt(history))
        next_run = to_iso(nxt) if nxt else None
    return {
        "id": str(incoming.get("id") or "").strip() or _new_id(),
        "name": reject_secrets(str(incoming.get("name") or "").strip() or "New test schedule", "name"),
        "active": bool(incoming.get("active", True)),
        "trigger": trigger,
        "target": public_target(incoming.get("target")),
        "check": public_check(incoming.get("check")),
        "history": history,
        "next_run": next_run,
        "when_to_run": time_trigger_summary(trigger),
    }


def list_schedules() -> list[dict[str, Any]]:
    store = _read_store()
    out: list[dict[str, Any]] = []
    for item in store.get("schedules") or []:
        if isinstance(item, dict):
            out.append(public_schedule(item))
    return out


def get_schedule(schedule_id: str) -> dict[str, Any] | None:
    wanted = str(schedule_id or "").strip()
    if not wanted:
        return None
    for row in list_schedules():
        if row["id"] == wanted:
            return row
    return None


def _persist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public_rows = [public_schedule(row) for row in rows]
    _write_store({"schema": SCHEMA, "schedules": public_rows})
    return public_rows


def create_schedule(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = payload if isinstance(payload, dict) else {}
    schedule = public_schedule(
        {
            "id": _new_id(),
            "name": incoming.get("name") or "New test schedule",
            "active": incoming.get("active", True),
            "trigger": incoming.get("trigger"),
            "target": incoming.get("target"),
            "check": incoming.get("check"),
            "history": [],
        }
    )
    rows = list_schedules()
    rows.append(schedule)
    _persist(rows)
    return schedule


def update_schedule(schedule_id: str, patch: dict[str, Any] | None = None) -> dict[str, Any]:
    current = get_schedule(schedule_id)
    if current is None:
        raise KeyError(f"Test schedule '{schedule_id}' not found.")
    incoming = patch if isinstance(patch, dict) else {}
    unknown = [
        key
        for key in incoming
        if key not in {"name", "active", "trigger", "target", "check", "next_run"}
    ]
    if unknown:
        raise ValueError(f"Unknown test schedule field(s): {', '.join(sorted(unknown))}.")
    if "name" in incoming:
        current["name"] = reject_secrets(str(incoming.get("name") or "").strip() or current["name"], "name")
    if "active" in incoming:
        value = incoming["active"]
        if isinstance(value, bool):
            current["active"] = value
        elif isinstance(value, (int, float)) and value in (0, 1):
            current["active"] = bool(value)
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                current["active"] = True
            elif lowered in ("false", "0", "no", "off", ""):
                current["active"] = False
            else:
                raise ValueError("active must be a boolean.")
        else:
            raise ValueError("active must be a boolean.")
    if "trigger" in incoming:
        current["trigger"] = public_time_trigger(
            incoming.get("trigger") if isinstance(incoming.get("trigger"), dict) else None,
            allowed=TEST_SCHEDULE_TRIGGER_KINDS,
        )
        current["next_run"] = None
    if "target" in incoming:
        current["target"] = public_target(incoming.get("target"))
    if "check" in incoming:
        current["check"] = public_check(incoming.get("check"))
    rows = [current if row["id"] == current["id"] else row for row in list_schedules()]
    _persist(rows)
    return get_schedule(schedule_id) or current


def delete_schedule(schedule_id: str) -> bool:
    wanted = str(schedule_id or "").strip()
    rows = list_schedules()
    kept = [row for row in rows if row["id"] != wanted]
    if len(kept) == len(rows):
        return False
    _persist(kept)
    return True


def _default_check_runner(schedule: dict[str, Any]) -> dict[str, Any]:
    """Record the check. No live harness HTTP in the default path."""
    check = schedule.get("check") if isinstance(schedule.get("check"), dict) else {}
    name = str(check.get("name") or check.get("kind") or "check")
    _fired_checks.append(
        {
            "schedule_id": schedule.get("id"),
            "check": name,
            "target": schedule.get("target"),
        }
    )
    return {
        "status": HISTORY_STATUS_SUCCESS,
        "duration_ms": 0,
        "token_cost": 0,
        "summary": f"Recorded {name} (no live harness).",
        "artifact": {"kind": "report", "label": name, "url": ""},
    }


def _default_cos_note(schedule: dict[str, Any], row: dict[str, Any]) -> None:
    """Best-effort mailbox note to the CoS seat. Never raises."""
    try:
        from swarm.core.team_cos import resolve_chief_of_staff
        from swarm.core.team_rosters import load_team_rosters
        from swarm.core import chat_store

        cos_id = ""
        for roster in (load_team_rosters() or {}).values():
            member = resolve_chief_of_staff(roster if isinstance(roster, dict) else None)
            if isinstance(member, dict):
                cos_id = str(member.get("id") or member.get("agent_id") or "").strip()
            if cos_id:
                break
        if not cos_id:
            return
        name = str(schedule.get("name") or schedule.get("id") or "test schedule")
        status = str(row.get("status") or HISTORY_STATUS_ERROR)
        summary = str(row.get("error") or row.get("summary") or "failed")
        body = f"Test schedule '{name}' {status}: {summary}"
        record = chat_store.load("test-schedule", cos_id) or chat_store.empty_record(
            user_key="test-schedule", agent_id=cos_id
        )
        turns = list(record.get("messages") or [])
        turns.append({"role": "user", "content": body, "name": "test-schedule"})
        chat_store.save(
            "test-schedule",
            cos_id,
            turns,
            conversation_id=str(record.get("conversation_id") or ""),
        )
    except Exception:
        logger.exception("Could not notify CoS of test-schedule failure")


def notify_failure(schedule: dict[str, Any], row: dict[str, Any]) -> None:
    payload = {"schedule_id": schedule.get("id"), "name": schedule.get("name"), "row": row}
    _notified_failures.append(payload)
    notifier = _failure_notifier or _default_cos_note
    try:
        notifier(schedule, row)
    except Exception:
        logger.exception("Test-schedule failure notifier raised")


def append_history(
    schedule_id: str,
    *,
    source: str,
    status: str = HISTORY_STATUS_SUCCESS,
    summary: str = "",
    duration_ms: int | None = None,
    token_cost: int | None = None,
    artifact: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    schedule = get_schedule(schedule_id)
    if schedule is None:
        raise KeyError(f"Test schedule '{schedule_id}' not found.")
    row: dict[str, Any] = {
        "id": _new_id(),
        "ran_at": _now_iso(),
        "status": str(status or "").strip() or HISTORY_STATUS_SUCCESS,
        "source": source,
    }
    if summary:
        row["summary"] = summary
    if duration_ms is not None:
        row["duration_ms"] = max(0, int(duration_ms))
    if token_cost is not None:
        row["token_cost"] = max(0, int(token_cost))
    if artifact:
        row["artifact"] = artifact
    if error:
        row["error"] = error
    history = [row, *list(schedule.get("history") or [])]
    history.sort(key=lambda item: str(item.get("ran_at") or ""), reverse=True)
    schedule["history"] = history
    trigger = schedule.get("trigger") if isinstance(schedule.get("trigger"), dict) else {}
    if str(trigger.get("kind") or "") in TIME_TRIGGER_KINDS:
        nxt = compute_next_run(trigger, last_run=parse_dt(row["ran_at"]))
        schedule["next_run"] = to_iso(nxt) if nxt else None
        if str(trigger.get("kind") or "") == TRIGGER_ONE_SHOT and source in {
            SOURCE_SCHEDULE,
            SOURCE_RUN_NOW,
        }:
            schedule["active"] = False
            schedule["next_run"] = None
    rows = [schedule if item["id"] == schedule["id"] else item for item in list_schedules()]
    _persist(rows)
    updated = get_schedule(schedule_id) or schedule
    if str(row.get("status") or "") not in {HISTORY_STATUS_SUCCESS, "ok", "pass"}:
        notify_failure(updated, row)
    return updated


def fire_schedule(schedule_id: str, *, source: str) -> dict[str, Any]:
    schedule = get_schedule(schedule_id)
    if schedule is None:
        raise KeyError(f"Test schedule '{schedule_id}' not found.")
    runner = _check_runner or _default_check_runner
    started = time.monotonic()
    status = HISTORY_STATUS_SUCCESS
    error = ""
    summary = ""
    token_cost = 0
    artifact: dict[str, Any] | None = None
    try:
        result = runner(schedule) or {}
        status = str(result.get("status") or HISTORY_STATUS_SUCCESS).strip() or HISTORY_STATUS_SUCCESS
        summary = str(result.get("summary") or "")
        token_cost = int(result.get("token_cost") or 0)
        art = result.get("artifact")
        if isinstance(art, dict):
            artifact = art
        if result.get("error"):
            error = str(result.get("error"))
            if status == HISTORY_STATUS_SUCCESS:
                status = HISTORY_STATUS_ERROR
    except Exception as exc:
        logger.exception("Test schedule %s failed", schedule_id)
        status = HISTORY_STATUS_ERROR
        error = str(exc) or "Test schedule execution failed."
        summary = error
    duration_ms = int((time.monotonic() - started) * 1000)
    if status in {HISTORY_STATUS_FAIL, "failed", "error"}:
        status = HISTORY_STATUS_ERROR if status != HISTORY_STATUS_FAIL else HISTORY_STATUS_FAIL
    return append_history(
        schedule_id,
        source=source,
        status=status,
        summary=summary or error,
        duration_ms=duration_ms,
        token_cost=token_cost,
        artifact=artifact,
        error=error,
    )


def run_now(schedule_id: str) -> dict[str, Any]:
    return fire_schedule(schedule_id, source=SOURCE_RUN_NOW)


def tick_due_schedules(now: datetime | None = None) -> list[dict[str, Any]]:
    """Fire due test schedules. Single-process; no distributed lock."""
    moment = now or utcnow()
    fired: list[dict[str, Any]] = []
    for row in list_schedules():
        if not row.get("active"):
            continue
        trigger = row.get("trigger") if isinstance(row.get("trigger"), dict) else {}
        if str(trigger.get("kind") or "") not in TIME_TRIGGER_KINDS:
            continue
        last_run = _last_run_dt(list(row.get("history") or []))
        if not is_due(trigger, now=moment, last_run=last_run, next_run=row.get("next_run")):
            continue
        updated = fire_schedule(str(row.get("id") or ""), source=SOURCE_SCHEDULE)
        fired.append(updated)
    return fired


def open_failures() -> list[dict[str, Any]]:
    """Schedules whose latest history row is not success."""
    out: list[dict[str, Any]] = []
    for row in list_schedules():
        history = list(row.get("history") or [])
        if not history:
            continue
        status = str(history[0].get("status") or "").strip().lower()
        if status in {"success", "ok", "pass"}:
            continue
        out.append(row)
    return out

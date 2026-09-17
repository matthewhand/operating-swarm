"""Shared schedule trigger kinds for Routines and Test schedules (#222).

Stdlib-only. Time-based kinds (`interval`, `cron`, `one_shot`) plus the
mailbox-message event kind. GitHub kinds live in ``swarm.core.routines``.

Schedules run in the Django process (see ``schedule_engine``). No distributed
claims. No secrets in stored trigger fields.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

TRIGGER_INTERVAL = "interval"
TRIGGER_CRON = "cron"
TRIGGER_ONE_SHOT = "one_shot"
TRIGGER_MAILBOX_MESSAGE = "mailbox_message"

TIME_TRIGGER_KINDS = frozenset({TRIGGER_INTERVAL, TRIGGER_CRON, TRIGGER_ONE_SHOT})
ROUTINE_TRIGGER_KINDS = TIME_TRIGGER_KINDS | {TRIGGER_MAILBOX_MESSAGE}
TEST_SCHEDULE_TRIGGER_KINDS = TIME_TRIGGER_KINDS

MIN_INTERVAL_SECONDS = 1
MAX_INTERVAL_SECONDS = 30 * 24 * 60 * 60  # 30 days
MAX_CRON_SCAN_MINUTES = 366 * 24 * 60

_SECRET_RE = re.compile(
    r"(ghp_|github_pat_|sk-|xai-|Bearer\s+[A-Za-z0-9._\-]{12,})",
    re.IGNORECASE,
)
_INTERVAL_RE = re.compile(r"^(?P<n>\d+)\s*(?P<u>s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)?$", re.I)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Any) -> datetime | None:
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
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def to_iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat()


def reject_secrets(text: str, field: str) -> str:
    """Raise if *text* looks like a token. Empty string is fine."""
    value = str(text or "")
    if _SECRET_RE.search(value):
        raise ValueError(f"{field} must not contain secrets.")
    return value


def parse_interval_seconds(raw: Any) -> int:
    """Accept ``seconds`` int or ``every`` like ``30s`` / ``5m`` / ``1h``."""
    if isinstance(raw, dict):
        if raw.get("seconds") is not None:
            raw = raw.get("seconds")
        else:
            raw = raw.get("every") or raw.get("interval") or raw.get("every_seconds")
    if isinstance(raw, bool):
        raise ValueError("interval seconds must be a positive integer.")
    if isinstance(raw, (int, float)):
        seconds = int(raw)
    else:
        text = str(raw or "").strip().lower()
        match = _INTERVAL_RE.match(text)
        if not match:
            raise ValueError("interval must be seconds or a duration like 30s, 5m, 1h.")
        seconds = int(match.group("n"))
        unit = (match.group("u") or "s").lower()
        if unit.startswith("m"):
            seconds *= 60
        elif unit.startswith("h"):
            seconds *= 3600
        elif unit.startswith("d"):
            seconds *= 86400
    if seconds < MIN_INTERVAL_SECONDS or seconds > MAX_INTERVAL_SECONDS:
        raise ValueError(
            f"interval seconds must be between {MIN_INTERVAL_SECONDS} and {MAX_INTERVAL_SECONDS}."
        )
    return seconds


def normalize_cron_expression(value: Any) -> str:
    text = reject_secrets(str(value or "").strip(), "cron expression")
    parts = text.split()
    if len(parts) != 5:
        raise ValueError("cron expression must have 5 fields (min hour day month weekday).")
    for part in parts:
        if not re.fullmatch(r"[\d*/,?-]+", part):
            raise ValueError("cron expression contains an invalid field.")
    return " ".join(parts)


def _cron_field_values(expr: str, minimum: int, maximum: int) -> set[int]:
    out: set[int] = set()
    for chunk in expr.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        step = 1
        if "/" in chunk:
            chunk, step_text = chunk.split("/", 1)
            step = int(step_text)
            if step < 1:
                raise ValueError("cron step must be >= 1.")
        if chunk in {"*", "?"}:
            start, end = minimum, maximum
        elif "-" in chunk:
            start_text, end_text = chunk.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(chunk)
        if start > end:
            start, end = end, start
        for value in range(start, end + 1, step):
            if minimum <= value <= maximum:
                out.add(value)
    if not out:
        raise ValueError("cron field matched no values.")
    return out


def cron_matches(expression: str, when: datetime) -> bool:
    minute, hour, dom, month, dow = normalize_cron_expression(expression).split()
    dt = when.astimezone(timezone.utc)
    if dt.minute not in _cron_field_values(minute, 0, 59):
        return False
    if dt.hour not in _cron_field_values(hour, 0, 23):
        return False
    if dt.month not in _cron_field_values(month, 1, 12):
        return False
    day_ok = dt.day in _cron_field_values(dom, 1, 31)
    # cron weekday: 0/7 Sunday … 6 Saturday
    weekday = (dt.weekday() + 1) % 7
    dow_values = _cron_field_values(dow, 0, 7)
    if 7 in dow_values:
        dow_values.add(0)
    dow_ok = weekday in dow_values
    if dom == "*" and dow == "*":
        return True
    if dom == "*":
        return dow_ok
    if dow == "*":
        return day_ok
    return day_ok or dow_ok


def next_cron(expression: str, after: datetime) -> datetime | None:
    cursor = after.astimezone(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(MAX_CRON_SCAN_MINUTES):
        if cron_matches(expression, cursor):
            return cursor
        cursor += timedelta(minutes=1)
    return None


def public_time_trigger(raw: dict[str, Any] | None, *, allowed: frozenset[str]) -> dict[str, Any]:
    incoming = raw if isinstance(raw, dict) else {}
    kind = str(incoming.get("kind") or "").strip()
    if kind not in allowed:
        raise ValueError(f"Unsupported trigger kind {kind!r}.")
    if kind == TRIGGER_INTERVAL:
        seconds = parse_interval_seconds(
            incoming.get("seconds", incoming.get("every", incoming.get("interval")))
        )
        return {"kind": TRIGGER_INTERVAL, "seconds": seconds}
    if kind == TRIGGER_CRON:
        expression = incoming.get("expression") or incoming.get("cron") or incoming.get("schedule")
        return {"kind": TRIGGER_CRON, "expression": normalize_cron_expression(expression)}
    if kind == TRIGGER_ONE_SHOT:
        run_at = parse_dt(incoming.get("run_at") or incoming.get("at") or incoming.get("when"))
        if run_at is None:
            raise ValueError("one_shot trigger requires run_at (ISO-8601).")
        return {"kind": TRIGGER_ONE_SHOT, "run_at": to_iso(run_at)}
    sender = reject_secrets(str(incoming.get("sender") or "").strip(), "sender")
    pattern = reject_secrets(str(incoming.get("pattern") or incoming.get("subject") or "").strip(), "pattern")
    return {
        "kind": TRIGGER_MAILBOX_MESSAGE,
        "sender": sender,
        "pattern": pattern,
    }


def compute_next_run(
    trigger: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    last_run: datetime | None = None,
) -> datetime | None:
    data = trigger if isinstance(trigger, dict) else {}
    kind = str(data.get("kind") or "")
    moment = now or utcnow()
    if kind == TRIGGER_INTERVAL:
        seconds = int(data.get("seconds") or 0)
        if seconds < 1:
            return None
        base = last_run or moment
        nxt = base + timedelta(seconds=seconds)
        if nxt <= moment:
            nxt = moment + timedelta(seconds=seconds)
        return nxt
    if kind == TRIGGER_CRON:
        return next_cron(str(data.get("expression") or ""), moment)
    if kind == TRIGGER_ONE_SHOT:
        run_at = parse_dt(data.get("run_at"))
        if run_at is None:
            return None
        if last_run is not None:
            return None
        return run_at
    return None


def is_due(
    trigger: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    last_run: datetime | None = None,
    next_run: Any = None,
) -> bool:
    data = trigger if isinstance(trigger, dict) else {}
    kind = str(data.get("kind") or "")
    if kind not in TIME_TRIGGER_KINDS:
        return False
    moment = now or utcnow()
    nxt = parse_dt(next_run) if next_run else compute_next_run(data, now=moment, last_run=last_run)
    if nxt is None:
        return False
    if last_run is not None and last_run >= nxt:
        return False
    if kind == TRIGGER_CRON:
        if last_run is not None:
            last_minute = last_run.replace(second=0, microsecond=0)
            this_minute = moment.replace(second=0, microsecond=0)
            if last_minute == this_minute:
                return False
        return moment >= nxt and cron_matches(str(data.get("expression") or ""), moment)
    if kind == TRIGGER_ONE_SHOT:
        if last_run is not None:
            return False
        return moment >= nxt
    return moment >= nxt


def time_trigger_summary(trigger: dict[str, Any] | None) -> str:
    data = trigger if isinstance(trigger, dict) else {}
    kind = str(data.get("kind") or "")
    if kind == TRIGGER_INTERVAL:
        seconds = int(data.get("seconds") or 0)
        if seconds % 86400 == 0:
            days = seconds // 86400
            return f"Every {days} day{'s' if days != 1 else ''}…"
        if seconds % 3600 == 0:
            hours = seconds // 3600
            return f"Every {hours} hour{'s' if hours != 1 else ''}…"
        if seconds % 60 == 0:
            mins = seconds // 60
            return f"Every {mins} min…"
        return f"Every {seconds}s…"
    if kind == TRIGGER_CRON:
        return f"Cron {data.get('expression') or ''}…"
    if kind == TRIGGER_ONE_SHOT:
        run_at = parse_dt(data.get("run_at"))
        stamp = run_at.strftime("%Y-%m-%d %H:%M UTC") if run_at else "a set time"
        return f"Once at {stamp}…"
    if kind == TRIGGER_MAILBOX_MESSAGE:
        sender = str(data.get("sender") or "").strip() or "anyone"
        pattern = str(data.get("pattern") or "").strip()
        if pattern:
            return f"When mailbox from {sender} matches {pattern}…"
        return f"When a mailbox message arrives from {sender}…"
    return "When scheduled…"


def public_history_extras(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Optional duration / cost / artifact / error fields on a history row."""
    incoming = raw if isinstance(raw, dict) else {}
    extras: dict[str, Any] = {}
    duration = incoming.get("duration_ms")
    if duration is not None and str(duration).strip() != "":
        try:
            extras["duration_ms"] = max(0, int(duration))
        except (TypeError, ValueError):
            pass
    cost = incoming.get("token_cost")
    if cost is not None and str(cost).strip() != "":
        try:
            extras["token_cost"] = max(0, int(cost))
        except (TypeError, ValueError):
            pass
    artifact = incoming.get("artifact")
    if isinstance(artifact, dict):
        kind = reject_secrets(str(artifact.get("kind") or "").strip(), "artifact.kind")
        url = reject_secrets(str(artifact.get("url") or "").strip(), "artifact.url")
        label = reject_secrets(str(artifact.get("label") or "").strip(), "artifact.label")
        cleaned = {key: value for key, value in (("kind", kind), ("url", url), ("label", label)) if value}
        if cleaned:
            extras["artifact"] = cleaned
    error = reject_secrets(str(incoming.get("error") or "").strip(), "error")
    if error:
        extras["error"] = error
    return extras


def mailbox_event_matches(trigger: dict[str, Any], event: dict[str, Any]) -> bool:
    if str(trigger.get("kind") or "") != TRIGGER_MAILBOX_MESSAGE:
        return False
    wanted_sender = str(trigger.get("sender") or "").strip().lower()
    actual_sender = str(event.get("sender") or event.get("sender_id") or "").strip().lower()
    if wanted_sender and wanted_sender not in {"anyone", "*"} and wanted_sender != actual_sender:
        return False
    pattern = str(trigger.get("pattern") or "").strip().lower()
    if not pattern:
        return True
    haystack = " ".join(
        str(event.get(key) or "")
        for key in ("content", "body", "subject", "text", "message")
    ).lower()
    return pattern in haystack

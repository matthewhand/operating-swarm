"""REQ-84: teammate task cards with Open-in-{remote} chrome.

When a team tasks a configured remote worker (Hermes, OpenMousBot, Rakazo,
Herdr, nested open-swarm), the chat shows a title + Running/Done card with
an Open-in-{Kind} action. The href is the remote's persisted ``ui_url`` or
``base_url`` — never a guessed host, never a live LAN inventory, never
``OMB`` in user-facing copy.

Distinct from REQ-71 PR-opened cards (View PR only; no Open-in-harness).
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from swarm.core.remotes import (
    REMOTE_IDS,
    RemoteError,
    RemoteSpec,
    is_configured,
    kind_label,
    load_remote,
)

_KIND_ALIASES: dict[str, str] = {
    "openmausbot": "omb",
    "openmaus": "omb",
    "openmousbot": "omb",
    "rakoza": "rakazo",
    "open-swarm": "swarm",
    "openswarm": "swarm",
    "open_swarm": "swarm",
}

TEAMMATE_TASK_TYPE = "teammate_task"

# Button kind copy (Success #2). Nested swarm is "Operating Swarm", not "Swarm" / OMB.
OPEN_IN_KIND_LABELS: dict[str, str] = {
    "hermes": "Hermes",
    "omb": "OpenMousBot",
    "rakazo": "Rakazo",
    "herdr": "Herdr",
    "swarm": "Operating Swarm",
}

REMOTE_MEMBER_KINDS = frozenset({"remote", "herdr"})
_LIST_HEADS = frozenset({"list", "ls", "config"})
_OMB_WORD = re.compile(r"\bOMB\b")
_SENSITIVE_QUERY = frozenset(
    {"token", "api_key", "apikey", "key", "auth", "auth_token", "password", "secret"}
)


def normalize_remote_kind(value: str) -> str:
    """Canonical remote id (``omb``, ``swarm``, …) or empty."""
    rid = (value or "").strip().lower()
    rid = _KIND_ALIASES.get(rid, rid)
    if rid in REMOTE_IDS:
        return rid
    return ""


def open_in_kind_label(kind_id: str) -> str:
    """Kind word used after ``Open in``. Never the letters OMB."""
    rid = normalize_remote_kind(kind_id) or (kind_id or "").strip().lower()
    label = OPEN_IN_KIND_LABELS.get(rid) or kind_label(rid or kind_id)
    if _OMB_WORD.search(label or ""):
        return "OpenMousBot"
    return label


def open_in_button_label(kind_id: str) -> str:
    return f"Open in {open_in_kind_label(kind_id)}"


def is_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc:
        return False
    return True


def scrub_remote_url(raw: str) -> str:
    """Drop secret-looking query params. Keep the configured host/path."""
    from urllib.parse import parse_qsl, urlencode, urlunparse

    text = (raw or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        kept = [
            (key, val)
            for key, val in parse_qsl(parsed.query, keep_blank_values=True)
            if not any(s in key.lower() for s in _SENSITIVE_QUERY)
        ]
        return urlunparse(parsed._replace(query=urlencode(kept)))
    except Exception:
        return text


def configured_open_href(spec: RemoteSpec | None) -> str:
    """Configured UI/base URL only. Empty when missing — never invent."""
    if spec is None:
        return ""
    for raw in (spec.ui_url, spec.base_url):
        text = (raw or "").strip()
        if is_http_url(text):
            return scrub_remote_url(text)
    return ""


def task_status_for(message_text: str = "", op: str = "") -> str:
    action = (op or "").strip().lower()
    if action in _LIST_HEADS:
        return "Done"
    head = (message_text or "").strip().split()[:1]
    if head and head[0].lower().rstrip(":") in _LIST_HEADS:
        return "Done"
    return "Running"


def _as_trimmed(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _roster_remote_member(roster: dict[str, Any] | None, worker_id: str) -> dict[str, Any] | None:
    if not roster or not worker_id:
        return None
    wanted = worker_id.strip().lower()
    wanted_kind = normalize_remote_kind(wanted)
    for raw in roster.get("members") or []:
        if not isinstance(raw, dict):
            continue
        mid = str(raw.get("id") or "").strip().lower()
        kind = str(raw.get("kind") or "").strip().lower()
        if mid == wanted or (wanted_kind and normalize_remote_kind(mid) == wanted_kind):
            if kind in REMOTE_MEMBER_KINDS or normalize_remote_kind(mid):
                return raw
    return None


def remote_member_on_team(team_id: str, worker_id: str) -> dict[str, Any] | None:
    """Return the roster member when *worker_id* is a remote on that team."""
    tid = (team_id or "").strip()
    wid = (worker_id or "").strip()
    if not tid or not wid or wid.lower() in {"all", ""}:
        return None
    try:
        from swarm.core.team_rosters import get_roster
    except Exception:
        return None
    try:
        roster = get_roster(tid)
    except Exception:
        return None
    return _roster_remote_member(roster, wid)


def _load_configured_spec(
    worker_id: str,
    config: dict[str, Any] | None = None,
) -> RemoteSpec | None:
    rid = normalize_remote_kind(worker_id)
    if not rid:
        return None
    try:
        if not is_configured(rid, config):
            return None
        return load_remote(rid, config)
    except (RemoteError, Exception):
        return None


def build_teammate_task(
    *,
    team_id: str,
    worker_id: str,
    title: str = "",
    status: str = "",
    op: str = "",
    session_id: str = "",
    health_state: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a chrome payload, or None when this is not a same-team remote task.

    Solo / local API targets return None so they never grow an Open-in button.
    """
    member = remote_member_on_team(team_id, worker_id)
    if member is None:
        return None
    kind = normalize_remote_kind(str(member.get("id") or worker_id)) or normalize_remote_kind(
        str(member.get("kind") or "")
    )
    if not kind:
        return None

    payload: dict[str, Any] = {
        "type": TEAMMATE_TASK_TYPE,
        "team_id": team_id.strip(),
        "worker_id": str(member.get("id") or worker_id).strip(),
        "worker_kind": kind,
        "open_in_label": open_in_button_label(kind),
    }
    heading = _as_trimmed(title)
    if heading:
        payload["title"] = heading
    resolved_status = _as_trimmed(status) or task_status_for(heading, op)
    if resolved_status:
        payload["status"] = resolved_status
    sid = _as_trimmed(session_id)
    if sid:
        payload["session_id"] = sid

    spec = _load_configured_spec(kind, config)
    href = configured_open_href(spec) if spec is not None else ""
    if href:
        payload["href"] = href
    elif spec is None:
        payload["disabled_reason"] = f"{open_in_kind_label(kind)} is not configured"
    else:
        payload["disabled_reason"] = f"No UI URL configured for {open_in_kind_label(kind)}"

    state = _as_trimmed(health_state).upper()
    if state == "DOWN":
        payload["disabled_reason"] = f"{open_in_kind_label(kind)} is DOWN"
        payload.pop("href", None)

    if _OMB_WORD.search(json.dumps(payload)):
        payload["open_in_label"] = open_in_button_label("omb")
    return payload


def parse_teammate_task(value: Any) -> dict[str, Any] | None:
    """Return a chrome payload, or None when this is not a teammate-task event."""
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("{"):
            return None
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    obj = value
    for nested_key in ("result", "data", "event", "task"):
        nested = obj.get(nested_key)
        if isinstance(nested, dict) and str(nested.get("type") or "").strip() == TEAMMATE_TASK_TYPE:
            obj = nested
            break
    if str(obj.get("type") or "").strip() != TEAMMATE_TASK_TYPE:
        return None

    team_id = _as_trimmed(obj.get("team_id") or obj.get("teamId") or obj.get("team"))
    worker_id = _as_trimmed(
        obj.get("worker_id") or obj.get("workerId") or obj.get("remote_id") or obj.get("remoteId")
    )
    kind = normalize_remote_kind(
        _as_trimmed(obj.get("worker_kind") or obj.get("workerKind") or obj.get("kind") or worker_id)
    )
    if not team_id or not (worker_id or kind):
        return None

    payload: dict[str, Any] = {"type": TEAMMATE_TASK_TYPE, "team_id": team_id}
    if worker_id:
        payload["worker_id"] = worker_id
    if kind:
        payload["worker_kind"] = kind
        payload["open_in_label"] = open_in_button_label(kind)
    title = _as_trimmed(obj.get("title") or obj.get("name") or obj.get("prompt"))
    if title:
        payload["title"] = title
    status = _as_trimmed(obj.get("status") or obj.get("state"))
    if status and status.lower() not in {TEAMMATE_TASK_TYPE, "tool_status"}:
        payload["status"] = status
    session_id = _as_trimmed(obj.get("session_id") or obj.get("sessionId"))
    if session_id:
        payload["session_id"] = session_id

    href = obj.get("href") or obj.get("url") or obj.get("ui_url")
    if is_http_url(href):
        payload["href"] = scrub_remote_url(str(href).strip())
    reason = _as_trimmed(obj.get("disabled_reason") or obj.get("disabledReason"))
    if reason:
        payload["disabled_reason"] = reason
    if "href" not in payload and not reason and kind:
        spec = _load_configured_spec(kind, None)
        resolved = configured_open_href(spec) if spec is not None else ""
        if resolved:
            payload["href"] = resolved
        elif spec is None:
            payload["disabled_reason"] = f"{open_in_kind_label(kind)} is not configured"
        else:
            payload["disabled_reason"] = f"No UI URL configured for {open_in_kind_label(kind)}"
    return payload


def persist_teammate_task_message(
    messages: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    events: list[dict[str, Any]] | None = None,
) -> None:
    """Record teammate-task chrome on the UI side channel (never model turns)."""
    if events is None:
        return
    content = json.dumps(payload, separators=(",", ":"))
    for row in events:
        if row.get("role") == "status" and row.get("content") == content:
            return
    from swarm.core.transcript_roles import append_event

    append_event(messages, events, "status", content, kind=TEAMMATE_TASK_TYPE)


def teammate_tasks_for_team_send(
    *,
    team_id: str,
    target: str,
    title: str,
    op: str = "",
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Cards for a team compose send. One per tasked remote worker."""
    tid = (team_id or "").strip()
    tgt = (target or "").strip()
    if not tid:
        return []
    workers: list[str] = []
    if tgt.lower() in {"", "all"}:
        try:
            from swarm.core.team_rosters import get_roster

            roster = get_roster(tid) or {}
        except Exception:
            roster = {}
        for raw in roster.get("members") or []:
            if not isinstance(raw, dict):
                continue
            mid = str(raw.get("id") or "").strip()
            if remote_member_on_team(tid, mid):
                workers.append(mid)
    else:
        workers = [tgt]
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    for worker in workers:
        key = worker.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        payload = build_teammate_task(
            team_id=tid, worker_id=worker, title=title, op=op, config=config
        )
        if payload:
            cards.append(payload)
    return cards

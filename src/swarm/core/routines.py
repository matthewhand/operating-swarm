"""Per-agent Routines store (REQ-80 / #432, REQ-884 / #285, #222).

File-backed JSON so the computer-icon pane, Test run, GitHub events,
time-based schedules, and mailbox triggers share one source of truth.
Instruction is the runtime prompt, not UI chrome. No live GitHub HTTP, no
Neon. Schema 2 is backward-compatible with schema 1 files.

Trigger kinds: ``github_pr_merged``, ``github_event``, ``interval``,
``cron``, ``one_shot``, ``mailbox_message``.

Schedules tick inside the Django process (see ``schedule_engine``). No
distributed claims. No secrets in the store.

Layout::

    <user-config>/agent_routines.json

    {
      "schema": 2,
      "agents": {
        "<agent_id>": [
          {
            "id": "...",
            "name": "...",
            "instruction": "...",
            "active": true,
            "next_run": "...",
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

import hashlib
import hmac
import json
import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm
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
GITHUB_WEBHOOK_USER_KEY = "github-webhook"
GITHUB_EVENT_TYPES = frozenset(
    {
        "issues.opened",
        "pull_request.opened",
        "pull_request.review_requested",
        "push",
    }
)

_OWNER_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")

_cache: dict[str, Any] | None = None
_fired_prompts: list[dict[str, str]] = []
InstructionRunner = Callable[[str, str, str], None]
_instruction_runner: InstructionRunner | None = None


def routines_path() -> Path:
    """Path of the agent-routines JSON file."""
    env = (os.environ.get(ENV_ROUTINES_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "agent_routines.json"


def reset_routines_cache() -> None:
    """Drop the in-process cache and fired-prompt log (tests)."""
    global _cache
    _cache = None
    _fired_prompts.clear()


def set_instruction_runner(runner: InstructionRunner | None) -> None:
    """Install a hook used when a routine fires (Test run or merge)."""
    global _instruction_runner
    _instruction_runner = runner


def fired_prompts() -> list[dict[str, str]]:
    """Prompts recorded as this agent's instruction (no live LLM)."""
    return list(_fired_prompts)


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "agents": {}}


def _read_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = routines_path()
    if not path.is_file():
        _cache = _empty_store()
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read agent routines at %s", path, exc_info=True)
        _cache = _empty_store()
        return _cache
    if not isinstance(data, dict):
        _cache = _empty_store()
        return _cache
    agents = data.get("agents")
    if not isinstance(agents, dict):
        agents = {}
    _cache = {"schema": SCHEMA, "agents": dict(agents)}
    return _cache


def _write_store(store: dict[str, Any]) -> None:
    global _cache
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
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _cache = payload


def _new_id() -> str:
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_owner_repo(value: Any) -> str:
    """Accept ``owner/repo`` or ``{owner, repo}``. Empty string if unset."""
    if isinstance(value, dict):
        owner = str(value.get("owner") or "").strip()
        repo = str(value.get("repo") or "").strip()
        text = f"{owner}/{repo}" if owner and repo else ""
    else:
        text = str(value or "").strip().lstrip("/")
    if not text:
        return ""
    if not _OWNER_REPO_RE.match(text):
        raise ValueError("Repository must be owner/repo (GitHub only).")
    return text


def normalize_actor(value: Any) -> str:
    text = str(value or "").strip() or ACTOR_ANYONE
    if text.lower() == ACTOR_ANYONE:
        return ACTOR_ANYONE
    if "/" in text or text.startswith("ghp_") or text.startswith("github_pat_"):
        raise ValueError("Actor must be a GitHub login or Anyone.")
    return text


def _coerce_owner_repo(incoming: dict[str, Any]) -> Any:
    owner_repo = incoming.get("owner_repo")
    if not owner_repo:
        owner_repo = incoming.get("repository") or incoming.get("repo")
        if not owner_repo and incoming.get("owner"):
            owner_repo = {"owner": incoming.get("owner"), "repo": incoming.get("repo")}
    return owner_repo


def public_github_event_filters(raw: Any) -> dict[str, Any]:
    """Normalize optional github_event filters (labels, branch)."""
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
    return out


def public_trigger(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = raw if isinstance(raw, dict) else {}
    kind = str(incoming.get("kind") or TRIGGER_GITHUB_PR_MERGED).strip()
    if kind in {TRIGGER_INTERVAL, TRIGGER_CRON, TRIGGER_ONE_SHOT, TRIGGER_MAILBOX_MESSAGE}:
        return public_time_trigger(incoming, allowed=ROUTINE_TRIGGER_KINDS)
    if kind == TRIGGER_GITHUB_EVENT:
        event_type = str(incoming.get("event_type") or incoming.get("event") or "").strip()
        if event_type not in GITHUB_EVENT_TYPES:
            allowed = ", ".join(sorted(GITHUB_EVENT_TYPES))
            raise ValueError(f"github_event event_type must be one of: {allowed}.")
        owner_repo = normalize_owner_repo(_coerce_owner_repo(incoming))
        if not owner_repo:
            raise ValueError("github_event trigger requires owner/repo.")
        return {
            "kind": TRIGGER_GITHUB_EVENT,
            "event_type": event_type,
            "owner_repo": owner_repo,
            "filters": public_github_event_filters(incoming.get("filters")),
        }
    if kind != TRIGGER_GITHUB_PR_MERGED:
        raise ValueError(
            "Supported trigger kinds: github_pr_merged, github_event, interval, cron, one_shot, mailbox_message."
        )
    event = str(incoming.get("event") or EVENT_MERGED).strip().lower()
    if event != EVENT_MERGED:
        raise ValueError("GitHub PR-merged trigger event must be merged.")
    return {
        "kind": TRIGGER_GITHUB_PR_MERGED,
        "owner_repo": normalize_owner_repo(_coerce_owner_repo(incoming)),
        "event": EVENT_MERGED,
        "actor": normalize_actor(incoming.get("actor")),
    }


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
    trigger = public_trigger(incoming.get("trigger") if isinstance(incoming.get("trigger"), dict) else None)
    next_run = str(incoming.get("next_run") or "").strip() or None
    if not next_run:
        nxt = compute_next_run(trigger, last_run=_last_run_dt(history))
        next_run = to_iso(nxt) if nxt else None
    return {
        "id": str(incoming.get("id") or "").strip() or _new_id(),
        "name": name,
        "instruction": instruction,
        "active": bool(incoming.get("active", True)),
        "trigger": trigger,
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


def _persist_agent(agent_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agent = normalize_agent_id(agent_id)
    store = _read_store()
    agents = dict(store.get("agents") or {})
    public_rows = [public_routine(row) for row in rows]
    agents[agent] = public_rows
    _write_store({"schema": SCHEMA, "agents": agents})
    return public_rows


def create_routine(agent_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = payload if isinstance(payload, dict) else {}
    routine = public_routine(
        {
            "id": _new_id(),
            "name": incoming.get("name") or "New routine",
            "instruction": incoming.get("instruction") or "",
            "active": incoming.get("active", True),
            "trigger": incoming.get("trigger"),
            "history": [],
        }
    )
    rows = list_routines(agent_id)
    rows.append(routine)
    _persist_agent(agent_id, rows)
    return routine


def update_routine(agent_id: str, routine_id: str, patch: dict[str, Any] | None = None) -> dict[str, Any]:
    current = get_routine(agent_id, routine_id)
    if current is None:
        raise KeyError(f"Routine '{routine_id}' not found.")
    incoming = patch if isinstance(patch, dict) else {}
    unknown = [
        key
        for key in incoming
        if key not in {"name", "instruction", "active", "trigger", "next_run"}
    ]
    if unknown:
        raise ValueError(f"Unknown routine field(s): {', '.join(sorted(unknown))}.")
    if "name" in incoming:
        current["name"] = str(incoming.get("name") or "").strip() or current["name"]
    if "instruction" in incoming:
        current["instruction"] = "" if incoming.get("instruction") is None else str(incoming.get("instruction"))
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
        current["trigger"] = public_trigger(incoming.get("trigger") if isinstance(incoming.get("trigger"), dict) else None)
        current["next_run"] = None
    rows = [current if row["id"] == current["id"] else row for row in list_routines(agent_id)]
    _persist_agent(agent_id, rows)
    return get_routine(agent_id, routine_id) or current


def delete_routine(agent_id: str, routine_id: str) -> bool:
    wanted = str(routine_id or "").strip()
    rows = list_routines(agent_id)
    kept = [row for row in rows if row["id"] != wanted]
    if len(kept) == len(rows):
        return False
    _persist_agent(agent_id, kept)
    return True


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
    routine = get_routine(agent_id, routine_id)
    if routine is None:
        raise KeyError(f"Routine '{routine_id}' not found.")
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
                "url": f"/chat?agent={normalize_agent_id(agent_id)}&conversation={conversation_id}",
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
    history = [row, *list(routine.get("history") or [])]
    history.sort(key=lambda item: str(item.get("ran_at") or ""), reverse=True)
    routine["history"] = history
    trigger = routine.get("trigger") if isinstance(routine.get("trigger"), dict) else {}
    if str(trigger.get("kind") or "") in TIME_TRIGGER_KINDS:
        nxt = compute_next_run(trigger, last_run=parse_dt(row["ran_at"]))
        routine["next_run"] = to_iso(nxt) if nxt else None
        if str(trigger.get("kind") or "") == TRIGGER_ONE_SHOT and source in {
            SOURCE_SCHEDULE,
            SOURCE_RUN_NOW,
        }:
            routine["active"] = False
            routine["next_run"] = None
    rows = [routine if item["id"] == routine["id"] else item for item in list_routines(agent_id)]
    _persist_agent(agent_id, rows)
    return get_routine(agent_id, routine_id) or routine


def fire_routine(
    agent_id: str,
    routine_id: str,
    *,
    source: str,
    prompt: str | None = None,
    event: str = "",
    conversation_id: str = "",
    summary: str = "",
    token_cost: int = 0,
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the instruction, record duration/status, and append history."""
    routine = get_routine(agent_id, routine_id)
    if routine is None:
        raise KeyError(f"Routine '{routine_id}' not found.")
    instruction = prompt if prompt is not None else str(routine.get("instruction") or "")
    started = time.monotonic()
    status = HISTORY_STATUS_SUCCESS
    error = ""
    try:
        run_instruction(agent_id, instruction, source)
    except Exception as exc:
        logger.exception("Routine %s failed", routine_id)
        status = HISTORY_STATUS_ERROR
        error = str(exc) or "Routine execution failed."
    duration_ms = int((time.monotonic() - started) * 1000)
    return append_history(
        agent_id,
        routine_id,
        source=source,
        status=status,
        event=event,
        conversation_id=conversation_id,
        summary=error or summary,
        duration_ms=duration_ms,
        token_cost=token_cost,
        artifact=artifact,
        error=error,
    )


def test_run(agent_id: str, routine_id: str) -> dict[str, Any]:
    """Fire the Instruction once without waiting for the trigger."""
    return fire_routine(agent_id, routine_id, source=SOURCE_TEST_RUN)


def run_now(agent_id: str, routine_id: str) -> dict[str, Any]:
    """Operator run-now. Same path as a scheduled fire; source is run_now."""
    return fire_routine(agent_id, routine_id, source=SOURCE_RUN_NOW)


def tick_due_routines(now: datetime | None = None) -> list[dict[str, Any]]:
    """Fire due interval/cron/one_shot routines. Single-process; no distributed lock."""
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


def parse_github_merge_event(payload: dict[str, Any] | None) -> dict[str, str]:
    """Accept a fake merge event or a GitHub-shaped pull_request payload.

    Live GitHub is never called. Tests inject this payload. No tokens.
    """
    incoming = payload if isinstance(payload, dict) else {}
    pull = incoming.get("pull_request") if isinstance(incoming.get("pull_request"), dict) else {}
    repo_obj = incoming.get("repository") if isinstance(incoming.get("repository"), dict) else {}
    sender = incoming.get("sender") if isinstance(incoming.get("sender"), dict) else {}

    owner_repo = incoming.get("owner_repo") or incoming.get("repository_full_name")
    if not owner_repo:
        owner_repo = repo_obj.get("full_name") or incoming.get("repository")
    if isinstance(owner_repo, dict):
        owner_repo = None
    if not owner_repo and (incoming.get("owner") or repo_obj.get("owner")):
        owner = incoming.get("owner")
        if isinstance(repo_obj.get("owner"), dict):
            owner = owner or repo_obj["owner"].get("login")
        owner_repo = {"owner": owner, "repo": incoming.get("repo") or repo_obj.get("name")}

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
    repo_obj = incoming.get("repository") if isinstance(incoming.get("repository"), dict) else {}
    owner_repo = incoming.get("owner_repo") or repo_obj.get("full_name")
    if not owner_repo and (incoming.get("owner") or repo_obj.get("owner") or repo_obj.get("name")):
        owner = incoming.get("owner")
        if isinstance(repo_obj.get("owner"), dict):
            owner = owner or repo_obj["owner"].get("login")
        owner_repo = {"owner": owner, "repo": incoming.get("repo") or repo_obj.get("name")}
    try:
        return normalize_owner_repo(owner_repo)
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
    target = pull or issue
    sender = incoming.get("sender") if isinstance(incoming.get("sender"), dict) else {}
    pusher = incoming.get("pusher") if isinstance(incoming.get("pusher"), dict) else {}
    head_commit = incoming.get("head_commit") if isinstance(incoming.get("head_commit"), dict) else {}
    repo_obj = incoming.get("repository") if isinstance(incoming.get("repository"), dict) else {}
    user = target.get("user") if isinstance(target.get("user"), dict) else {}

    number_raw = target.get("number") if target.get("number") is not None else incoming.get("number")
    number: int | None
    try:
        number = int(number_raw) if number_raw is not None and str(number_raw).strip() != "" else None
    except (TypeError, ValueError):
        number = None

    title = str(target.get("title") or head_commit.get("message") or incoming.get("title") or "")
    if "\n" in title:
        title = title.split("\n", 1)[0]
    body = str(target.get("body") or head_commit.get("message") or incoming.get("body") or "")
    author = str(user.get("login") or pusher.get("name") or sender.get("login") or "").strip()
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
        "html_url": html_url,
        "labels": labels,
        "branch": branch,
        "diff": diff,
        "event_label": event_label.strip(),
    }


def github_event_conversation_id(event: dict[str, Any]) -> str:
    """Stable conversation id for a GitHub webhook event (e.g. conv-github-pr-42)."""
    event_type = str(event.get("event_type") or "")
    number = event.get("number")
    if event_type.startswith("pull_request") and number is not None:
        return f"conv-github-pr-{number}"
    if event_type.startswith("issues") and number is not None:
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


def deliver_github_event(
    payload: dict[str, Any] | None,
    *,
    event_header: str | None = None,
) -> list[dict[str, Any]]:
    """Fire matching Active ``github_event`` routines for one webhook payload."""
    event = parse_github_webhook_event(payload, event_header)
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
            if str(trigger.get("owner_repo") or "").lower() != owner_repo:
                continue
            if not github_event_filters_match(trigger, event):
                continue
            prompt = format_github_event_briefing(event, str(routine.get("instruction") or ""))
            conversation_id = github_event_conversation_id(event)
            spawn_github_event_session(agent_id, conversation_id, prompt)
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


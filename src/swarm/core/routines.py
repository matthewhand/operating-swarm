"""Per-agent Routines store (REQ-80 / #432).

File-backed JSON so the computer-icon pane, Test run, and GitHub PR-merged
delivery share one source of truth. Instruction is the runtime prompt, not
UI chrome. GitHub-only trigger in v1. No secrets, no live GitHub HTTP, no
Neon.

Layout::

    <user-config>/agent_routines.json

    {
      "schema": 1,
      "agents": {
        "<agent_id>": [
          {
            "id": "...",
            "name": "...",
            "instruction": "...",
            "active": true,
            "trigger": {
              "kind": "github_pr_merged",
              "owner_repo": "owner/repo",
              "event": "merged",
              "actor": "anyone"
            },
            "history": [
              {
                "id": "...",
                "ran_at": "...",
                "status": "success",
                "source": "test_run"
              }
            ]
          }
        ]
      }
    }
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_ROUTINES_PATH = "SWARM_AGENT_ROUTINES_PATH"
TRIGGER_GITHUB_PR_MERGED = "github_pr_merged"
EVENT_MERGED = "merged"
ACTOR_ANYONE = "anyone"
SOURCE_TEST_RUN = "test_run"
SOURCE_GITHUB_PR_MERGED = "github_pr_merged"
HISTORY_STATUS_SUCCESS = "success"

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


def public_trigger(raw: dict[str, Any] | None = None) -> dict[str, str]:
    incoming = raw if isinstance(raw, dict) else {}
    kind = str(incoming.get("kind") or TRIGGER_GITHUB_PR_MERGED).strip()
    if kind != TRIGGER_GITHUB_PR_MERGED:
        raise ValueError("v1 supports only the GitHub PR-merged trigger.")
    owner_repo = incoming.get("owner_repo")
    if not owner_repo:
        owner_repo = incoming.get("repository") or incoming.get("repo")
        if not owner_repo and incoming.get("owner"):
            owner_repo = {"owner": incoming.get("owner"), "repo": incoming.get("repo")}
    event = str(incoming.get("event") or EVENT_MERGED).strip().lower()
    if event != EVENT_MERGED:
        raise ValueError("v1 GitHub trigger event must be merged.")
    return {
        "kind": TRIGGER_GITHUB_PR_MERGED,
        "owner_repo": normalize_owner_repo(owner_repo),
        "event": EVENT_MERGED,
        "actor": normalize_actor(incoming.get("actor")),
    }


def public_history_row(raw: dict[str, Any] | None = None) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    ran_at = str(raw.get("ran_at") or "").strip()
    if not ran_at:
        return None
    status = str(raw.get("status") or HISTORY_STATUS_SUCCESS).strip() or HISTORY_STATUS_SUCCESS
    source = str(raw.get("source") or SOURCE_TEST_RUN).strip() or SOURCE_TEST_RUN
    row_id = str(raw.get("id") or "").strip() or _new_id()
    return {
        "id": row_id,
        "ran_at": ran_at,
        "status": status,
        "source": source,
    }


def public_routine(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    incoming = raw if isinstance(raw, dict) else {}
    history: list[dict[str, str]] = []
    for item in incoming.get("history") or []:
        row = public_history_row(item if isinstance(item, dict) else None)
        if row:
            history.append(row)
    history.sort(key=lambda row: row["ran_at"], reverse=True)
    name = str(incoming.get("name") or "").strip() or "New routine"
    instruction = incoming.get("instruction")
    if instruction is None:
        instruction = ""
    else:
        instruction = str(instruction)
    return {
        "id": str(incoming.get("id") or "").strip() or _new_id(),
        "name": name,
        "instruction": instruction,
        "active": bool(incoming.get("active", True)),
        "trigger": public_trigger(incoming.get("trigger") if isinstance(incoming.get("trigger"), dict) else None),
        "history": history,
    }


def trigger_summary(trigger: dict[str, Any] | None) -> str:
    """When-to-run subtitle for the Routines list."""
    data = public_trigger(trigger if isinstance(trigger, dict) else None)
    repo = data["owner_repo"] or "a GitHub repo"
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
        if key not in {"name", "instruction", "active", "trigger"}
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
    rows = [current if row["id"] == current["id"] else row for row in list_routines(agent_id)]
    _persist_agent(agent_id, rows)
    return current


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


def append_history(agent_id: str, routine_id: str, *, source: str) -> dict[str, Any]:
    routine = get_routine(agent_id, routine_id)
    if routine is None:
        raise KeyError(f"Routine '{routine_id}' not found.")
    row = {
        "id": _new_id(),
        "ran_at": _now_iso(),
        "status": HISTORY_STATUS_SUCCESS,
        "source": source,
    }
    history = [row, *list(routine.get("history") or [])]
    history.sort(key=lambda item: str(item.get("ran_at") or ""), reverse=True)
    routine["history"] = history
    rows = [routine if item["id"] == routine["id"] else item for item in list_routines(agent_id)]
    _persist_agent(agent_id, rows)
    return get_routine(agent_id, routine_id) or routine


def test_run(agent_id: str, routine_id: str) -> dict[str, Any]:
    """Fire the Instruction once without waiting for the trigger."""
    routine = get_routine(agent_id, routine_id)
    if routine is None:
        raise KeyError(f"Routine '{routine_id}' not found.")
    run_instruction(agent_id, str(routine.get("instruction") or ""), SOURCE_TEST_RUN)
    return append_history(agent_id, routine_id, source=SOURCE_TEST_RUN)


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
            run_instruction(agent_id, str(routine.get("instruction") or ""), SOURCE_GITHUB_PR_MERGED)
            updated = append_history(agent_id, routine["id"], source=SOURCE_GITHUB_PR_MERGED)
            fired.append({"agent_id": normalize_agent_id(agent_id), "routine": updated})
    return fired

"""Per-agent skills store (#1392).

File-backed JSON so CRUD, library attach, pack export/import, and first-run
``gettingStarted`` share one source of truth. Skills are **prose only**
(name / description / instructions) — no binaries, assets, or secrets.

Layout::

    <user-config>/agent_skills.json

    {
      "schema": 1,
      "agents": {
        "<agent_id>": {
          "skills": [
            {
              "name": "welcome-tour",
              "description": "...",
              "instructions": "...",
              "source": "authored",
              "first_run": true
            }
          ],
          "gettingStarted": {"skill": "welcome-tour"},
          "first_run_pending": true
        }
      }
    }

Library attach copies discovered ``SKILL.md`` prose onto the seat. Pack
import recreates the same records and marks ``gettingStarted`` for the
first conversation. SPA editor is #1393.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm
from swarm.core.schedule_triggers import reject_secrets
from swarm.core.skills import (
    MAX_DESCRIPTION,
    Skill,
    _NAME_RE,
    _RESERVED_WORDS,
    discover_skills,
)

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_SKILLS_PATH = "SWARM_AGENT_SKILLS_PATH"
SOURCE_AUTHORED = "authored"
SOURCE_LIBRARY = "library"
SOURCE_PACK = "pack"
SOURCES = (SOURCE_AUTHORED, SOURCE_LIBRARY, SOURCE_PACK)
MAX_INSTRUCTIONS = 32_000

_cache: dict[str, Any] | None = None


def skills_path() -> Path:
    """Path of the per-agent skills JSON file."""
    env = (os.environ.get(ENV_SKILLS_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "agent_skills.json"


def reset_agent_skills_cache() -> None:
    """Drop the in-process cache (tests)."""
    global _cache
    _cache = None


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "agents": {}}


def _empty_agent() -> dict[str, Any]:
    return {"skills": [], "gettingStarted": None, "first_run_pending": False}


def _read_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = skills_path()
    if not path.is_file():
        _cache = _empty_store()
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read agent skills at %s", path, exc_info=True)
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
    path = skills_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "agents": store.get("agents") or {}}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
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


def _agent_record(agent_id: str) -> dict[str, Any]:
    store = _read_store()
    raw = (store.get("agents") or {}).get(normalize_agent_id(agent_id))
    if not isinstance(raw, dict):
        return _empty_agent()
    skills: list[dict[str, Any]] = []
    for row in raw.get("skills") or []:
        if not isinstance(row, dict):
            continue
        try:
            skills.append(public_skill(row))
        except ValueError:
            continue
    try:
        started = public_getting_started(raw.get("gettingStarted") or raw.get("getting_started"))
    except ValueError:
        started = None
    return {
        "skills": skills,
        "gettingStarted": started,
        "first_run_pending": bool(raw.get("first_run_pending")),
    }


def _persist_agent(agent_id: str, record: dict[str, Any]) -> dict[str, Any]:
    agent = normalize_agent_id(agent_id)
    store = _read_store()
    agents = dict(store.get("agents") or {})
    public = {
        "skills": [public_skill(row) for row in record.get("skills") or []],
        "gettingStarted": public_getting_started(record.get("gettingStarted")),
        "first_run_pending": bool(record.get("first_run_pending")),
    }
    agents[agent] = public
    _write_store({"schema": SCHEMA, "agents": agents})
    return public


def validate_skill_name(name: str) -> str:
    """Normalize and validate a skill name (Agent Skills rules)."""
    text = reject_secrets(str(name or "").strip().lower(), "name")
    if not text:
        raise ValueError("name is required")
    if not _NAME_RE.match(text):
        raise ValueError(
            "name must be 1-64 chars of lowercase letters, digits, or hyphens"
        )
    if any(word in text for word in _RESERVED_WORDS):
        raise ValueError(f"name may not contain reserved words {_RESERVED_WORDS}")
    return text


def public_skill(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize one stored skill to the public prose record."""
    incoming = raw if isinstance(raw, dict) else {}
    name = validate_skill_name(str(incoming.get("name") or ""))
    description = reject_secrets(str(incoming.get("description") or "").strip(), "description")
    if len(description) > MAX_DESCRIPTION:
        raise ValueError(f"description exceeds {MAX_DESCRIPTION} chars")
    instructions = reject_secrets(
        str(
            incoming.get("instructions")
            or incoming.get("body")
            or incoming.get("content")
            or incoming.get("prose")
            or ""
        ).strip(),
        "instructions",
    )
    if not instructions:
        raise ValueError(f"skill '{name}' has no instructions")
    if len(instructions) > MAX_INSTRUCTIONS:
        raise ValueError(f"skill '{name}' instructions exceed {MAX_INSTRUCTIONS} chars")
    source = str(incoming.get("source") or SOURCE_AUTHORED).strip().lower()
    if source not in SOURCES:
        source = SOURCE_AUTHORED
    return {
        "name": name,
        "description": description,
        "instructions": instructions,
        "source": source,
        "first_run": bool(incoming.get("first_run")),
    }


def public_getting_started(raw: Any) -> dict[str, str] | None:
    """Normalize ``gettingStarted`` to ``{skill: name}`` or None."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        name = str(raw).strip()
        return {"skill": validate_skill_name(name)} if name else None
    if not isinstance(raw, dict):
        raise ValueError("gettingStarted must be an object with a skill name")
    name = str(raw.get("skill") or raw.get("name") or "").strip()
    if not name:
        return None
    return {"skill": validate_skill_name(name)}


def skill_to_library(row: dict[str, Any]) -> Skill:
    """In-memory Skill from a stored prose record (no assets)."""
    return Skill(
        name=row["name"],
        description=row.get("description") or "",
        instructions=row["instructions"],
    )


def agent_skill_catalog(agent_id: str) -> dict[str, Skill]:
    """``{name: Skill}`` overlay for this seat (prose only)."""
    return {row["name"]: skill_to_library(row) for row in list_skills(agent_id)}


def list_skills(agent_id: str) -> list[dict[str, Any]]:
    return list(_agent_record(agent_id)["skills"])


def get_skill(agent_id: str, name: str) -> dict[str, Any] | None:
    wanted = str(name or "").strip().lower()
    if not wanted:
        return None
    for row in list_skills(agent_id):
        if row["name"] == wanted:
            return row
    return None


def getting_started(agent_id: str) -> dict[str, str] | None:
    return _agent_record(agent_id)["gettingStarted"]


def first_run_pending(agent_id: str) -> bool:
    return bool(_agent_record(agent_id)["first_run_pending"])


def agent_skills_payload(agent_id: str) -> dict[str, Any]:
    """Public list payload for ``GET /v1/agents/<id>/skills/``."""
    record = _agent_record(agent_id)
    return {
        "object": "agent_skill_list",
        "agent_id": normalize_agent_id(agent_id),
        "skills": list(record["skills"]),
        "gettingStarted": record["gettingStarted"],
        "first_run_pending": bool(record["first_run_pending"]),
    }


def _require_getting_started_attached(record: dict[str, Any]) -> None:
    started = record.get("gettingStarted")
    if not started:
        return
    name = started.get("skill")
    names = {row["name"] for row in record.get("skills") or []}
    if name not in names:
        raise ValueError(
            f"gettingStarted.skill {name!r} must name an attached skill"
        )


def skill_seat_from_params(params: dict[str, Any] | None, *fallbacks: Any) -> str | None:
    """Seat id for the per-agent skill store.

    Chat turns identify the seat as ``agent`` (same key as folder and remote
    resolution) or ``agent_id``. Callers pass the blueprint id as a fallback
    when the payload omitted both. Blank values are skipped.
    """
    data = params if isinstance(params, dict) else {}
    for raw in (data.get("agent"), data.get("agent_id"), data.get("target_agent"), *fallbacks):
        text = str(raw or "").strip()
        if text:
            return text
    return None


def consume_applied_first_run(agent_id: str | None, applied: list[str] | None) -> None:
    """Clear first-run only when that gettingStarted skill was actually applied."""
    if not agent_id or not applied:
        return
    pending = peek_first_run_skill(agent_id)
    if pending and pending in applied:
        clear_first_run(agent_id)


def set_getting_started(agent_id: str, raw: Any, *, first_run: bool | None = None) -> dict[str, Any]:
    """Set ``gettingStarted.skill``. Must name an attached skill when present."""
    record = _agent_record(agent_id)
    record["gettingStarted"] = public_getting_started(raw)
    _require_getting_started_attached(record)
    if first_run is True:
        started = record["gettingStarted"]
        if not started or not started.get("skill"):
            raise ValueError("gettingStarted.skill is required to mark first-run")
        record["first_run_pending"] = True
        record["skills"] = [
            {**row, "first_run": row["name"] == started["skill"]}
            for row in record["skills"]
        ]
    elif first_run is False:
        record["first_run_pending"] = False
        record["skills"] = [{**row, "first_run": False} for row in record["skills"]]
    elif record["gettingStarted"] is None:
        record["first_run_pending"] = False
        record["skills"] = [{**row, "first_run": False} for row in record["skills"]]
    _persist_agent(agent_id, record)
    return agent_skills_payload(agent_id)


def mark_getting_started_first_run(agent_id: str) -> dict[str, Any]:
    """Flag the current gettingStarted skill for the next conversation."""
    record = _agent_record(agent_id)
    started = record.get("gettingStarted")
    if not started or not started.get("skill"):
        raise ValueError("gettingStarted.skill is required to mark first-run")
    return set_getting_started(agent_id, started, first_run=True)


def peek_first_run_skill(agent_id: str) -> str | None:
    """Name of the pending first-run skill, or None."""
    record = _agent_record(agent_id)
    if not record["first_run_pending"]:
        return None
    started = record.get("gettingStarted") or {}
    name = str(started.get("skill") or "").strip()
    if not name:
        return None
    if get_skill(agent_id, name) is None:
        return None
    return name


def clear_first_run(agent_id: str) -> None:
    """Clear the first-run flag after the skill has been applied."""
    record = _agent_record(agent_id)
    if not record["first_run_pending"] and not any(row.get("first_run") for row in record["skills"]):
        return
    record["first_run_pending"] = False
    record["skills"] = [{**row, "first_run": False} for row in record["skills"]]
    _persist_agent(agent_id, record)


def merge_pending_first_run(agent_id: str | None, params: dict[str, Any] | None) -> dict[str, Any]:
    """Copy params and prepend a pending gettingStarted skill (does not consume)."""
    incoming = dict(params or {})
    name = peek_first_run_skill(agent_id) if agent_id else None
    if not name:
        return incoming
    existing = incoming.get("skills")
    names: list[str] = []
    if isinstance(existing, str) and existing.strip():
        names.append(existing.strip())
    elif isinstance(existing, (list, tuple)):
        names.extend(str(item).strip() for item in existing if str(item).strip())
    raw = incoming.get("skill")
    if isinstance(raw, str) and raw.strip():
        names.append(raw.strip())
    if name not in names:
        incoming["skills"] = [name, *names]
    return incoming


def create_skill(agent_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a prose skill, or attach a library ``SKILL.md`` by name."""
    incoming = payload if isinstance(payload, dict) else {}
    attach = str(incoming.get("attach") or "").strip()
    name_hint = str(incoming.get("name") or attach or "").strip()
    has_body = bool(
        str(
            incoming.get("instructions")
            or incoming.get("body")
            or incoming.get("content")
            or incoming.get("prose")
            or ""
        ).strip()
    )
    if attach or (name_hint and not has_body):
        row = attach_library_skill(agent_id, attach or name_hint)
    else:
        row = public_skill({**incoming, "source": incoming.get("source") or SOURCE_AUTHORED})
        record = _agent_record(agent_id)
        if any(item["name"] == row["name"] for item in record["skills"]):
            raise ValueError(f"skill '{row['name']}' already exists on this agent")
        record["skills"].append(row)
        _persist_agent(agent_id, record)
    if incoming.get("gettingStarted") is True or incoming.get("getting_started") is True:
        set_getting_started(agent_id, {"skill": row["name"]})
    elif "gettingStarted" in incoming or "getting_started" in incoming:
        raw = incoming.get("gettingStarted", incoming.get("getting_started"))
        if raw:
            set_getting_started(agent_id, raw)
    return get_skill(agent_id, row["name"]) or row


def attach_library_skill(agent_id: str, name: str) -> dict[str, Any]:
    """Copy a discovered library skill onto the seat as prose."""
    wanted = validate_skill_name(name)
    catalog = discover_skills()
    skill = catalog.get(wanted)
    if skill is None:
        raise KeyError(f"Library skill '{wanted}' not found.")
    row = public_skill(
        {
            "name": skill.name,
            "description": skill.description,
            "instructions": skill.instructions,
            "source": SOURCE_LIBRARY,
        }
    )
    record = _agent_record(agent_id)
    if any(item["name"] == row["name"] for item in record["skills"]):
        raise ValueError(f"skill '{row['name']}' already exists on this agent")
    record["skills"].append(row)
    _persist_agent(agent_id, record)
    return row


def update_skill(agent_id: str, name: str, patch: dict[str, Any] | None = None) -> dict[str, Any]:
    current = get_skill(agent_id, name)
    if current is None:
        raise KeyError(f"Skill '{name}' not found.")
    incoming = patch if isinstance(patch, dict) else {}
    allowed = {
        "name",
        "description",
        "instructions",
        "body",
        "content",
        "prose",
        "first_run",
        "source",
        "gettingStarted",
        "getting_started",
    }
    unknown = [key for key in incoming if key not in allowed]
    if unknown:
        raise ValueError(f"Unknown skill field(s): {', '.join(sorted(unknown))}.")
    merged = dict(current)
    for key in ("name", "description", "instructions", "body", "content", "prose", "first_run", "source"):
        if key in incoming:
            merged[key] = incoming[key]
    row = public_skill(merged)
    record = _agent_record(agent_id)
    old_name = current["name"]
    if row["name"] != old_name and any(item["name"] == row["name"] for item in record["skills"]):
        raise ValueError(f"skill '{row['name']}' already exists on this agent")
    record["skills"] = [row if item["name"] == old_name else item for item in record["skills"]]
    started = record.get("gettingStarted")
    if started and started.get("skill") == old_name:
        record["gettingStarted"] = {"skill": row["name"]}
    if "gettingStarted" in incoming or "getting_started" in incoming:
        raw = incoming.get("gettingStarted", incoming.get("getting_started"))
        record["gettingStarted"] = public_getting_started(raw)
    _require_getting_started_attached(record)
    _persist_agent(agent_id, record)
    return get_skill(agent_id, row["name"]) or row


def delete_skill(agent_id: str, name: str) -> bool:
    wanted = str(name or "").strip().lower()
    record = _agent_record(agent_id)
    kept = [row for row in record["skills"] if row["name"] != wanted]
    if len(kept) == len(record["skills"]):
        return False
    record["skills"] = kept
    started = record.get("gettingStarted") or {}
    if started.get("skill") == wanted:
        record["gettingStarted"] = None
        record["first_run_pending"] = False
    _persist_agent(agent_id, record)
    return True


def replace_skills(
    agent_id: str,
    skills: list[dict[str, Any]],
    *,
    getting_started_raw: Any = None,
    first_run: bool = False,
    source: str = SOURCE_AUTHORED,
) -> dict[str, Any]:
    """Replace the seat's skill list (used by pack import)."""
    rows = [public_skill({**row, "source": row.get("source") or source}) for row in skills]
    seen: set[str] = set()
    for row in rows:
        if row["name"] in seen:
            raise ValueError(f"duplicate packed skill '{row['name']}'")
        seen.add(row["name"])
    record = {
        "skills": rows,
        "gettingStarted": public_getting_started(getting_started_raw),
        "first_run_pending": False,
    }
    _require_getting_started_attached(record)
    _persist_agent(agent_id, record)
    if first_run:
        mark_getting_started_first_run(agent_id)
    return agent_skills_payload(agent_id)

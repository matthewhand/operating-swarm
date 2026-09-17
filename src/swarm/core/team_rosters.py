"""Team roster composition store (REQ-20 / REQ-28).

A **team roster** is a composition contract: a named roster of members
plus per-team openai-agents wire toggles (handoff / as_tool).

Member shape (``team_rosters`` / ``agent_team`` members)::

    {id, name, kind: api|cli|remote|team|herdr, role, source}

``kind=team`` also carries ``team_id`` (the nested roster). Parent talks to
that child team as **one member** (send-to-all on the child), not every
grandchild — see ``docs/TEAM_ISOLATION.md``.

This is **not** the Django ``/teams/`` LLM-profile alias registry
(``teams.json``). Never write that file from this module.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from swarm.core.agent_roles import CANONICAL_ROLES, normalize_agent_role
from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm
from swarm.core.team_cos import apply_cos_fields, find_member

logger = logging.getLogger(__name__)

MEMBER_KINDS = ("api", "cli", "remote", "blueprint", "team", "herdr")
DEFAULT_WIRES = {"handoff": True, "as_tool": True}

# In-memory cache. Isolated from swarm.views.utils._dynamic_registry (teams.json).
_roster_registry: dict[str, dict[str, Any]] | None = None
_roster_lock = threading.RLock()


def team_rosters_path() -> Path:
    """XDG path for the composition store. Never ``teams.json``."""
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "team_rosters.json"


def slugify_roster_name(name: str) -> str:
    """Slugify a roster name (same character rules as the alias admin)."""
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")


def _default_source(member_id: str, kind: str, team_id: str | None = None) -> str:
    if kind == "api":
        return f"blueprint:{member_id}"
    if kind == "cli":
        return f"cli:{member_id}"
    if kind == "team":
        return f"team:{team_id or member_id}"
    if kind == "herdr":
        return f"herdr:{member_id}"
    return f"placeholder:remote:{member_id}"


def normalize_member(raw: Any) -> dict[str, str]:
    """Validate and normalize one roster / agent_team member. Raises ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("Each member must be an object.")
    member_id = str(raw.get("id") or "").strip()
    if not member_id:
        raise ValueError("Member id is required.")
    if len(member_id) > 64:
        raise ValueError("Member id too long (max 64).")

    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in MEMBER_KINDS:
        raise ValueError(f"Member kind must be one of {', '.join(MEMBER_KINDS)}.")

    role = normalize_agent_role(raw.get("role") or "default")
    if role not in CANONICAL_ROLES:
        raise ValueError(f"Member role must be one of {', '.join(CANONICAL_ROLES)}.")

    team_id = str(raw.get("team_id") or "").strip()
    if kind == "team":
        team_id = team_id or member_id
    elif team_id:
        # Non-team members may still record a home team; keep it if present.
        pass
    else:
        team_id = ""

    source = str(raw.get("source") or "").strip() or _default_source(member_id, kind, team_id or None)
    name = str(raw.get("name") or "").strip() or member_id
    if len(name) > 80:
        raise ValueError("Member name too long (max 80).")
    member = {"id": member_id, "name": name, "kind": kind, "role": role, "source": source}
    if team_id:
        member["team_id"] = team_id
    return member


def normalize_wires(raw: Any) -> dict[str, bool]:
    """Per-team wire toggles. Missing keys default on."""
    wires = dict(DEFAULT_WIRES)
    if raw is None:
        return wires
    if not isinstance(raw, dict):
        raise ValueError("wires must be an object.")
    for key in ("handoff", "as_tool"):
        if key in raw:
            val = raw[key]
            if not isinstance(val, bool):
                raise ValueError(f"wires.{key} must be a boolean.")
            wires[key] = val
    return wires


def normalize_roster(raw: dict[str, Any], *, roster_id: str | None = None) -> dict[str, Any]:
    """Normalize a roster document. Raises ValueError on bad input."""
    rid = (roster_id or raw.get("id") or "").strip()
    if not rid:
        raise ValueError("Roster id is required.")
    name = str(raw.get("name") or rid).strip() or rid
    members_in = raw.get("members") or raw.get("agent_team") or []
    if not isinstance(members_in, list):
        raise ValueError("members must be an array.")
    members = [normalize_member(m) for m in members_in]
    for member in members:
        if member.get("kind") == "team" and member.get("team_id") == rid:
            raise ValueError("A team cannot nest itself as a member.")
    blueprint_id = str(raw.get("blueprint_id") or raw.get("blueprint") or "").strip()
    out = {
        "id": rid,
        "name": name,
        "members": members,
        "wires": normalize_wires(raw.get("wires")),
    }
    if blueprint_id:
        if len(blueprint_id) > 64:
            raise ValueError("blueprint_id too long (max 64).")
        out["blueprint_id"] = blueprint_id
    return apply_cos_fields(out, raw)


def serialize_roster(entry: dict[str, Any]) -> dict[str, Any]:
    """Public JSON shape (OpenAPI / SPA)."""
    normalized = normalize_roster(entry, roster_id=entry.get("id"))
    payload = {
        "id": normalized["id"],
        "object": "team_roster",
        "name": normalized["name"],
        "members": normalized["members"],
        "wires": normalized["wires"],
        "chief_of_staff_id": normalized.get("chief_of_staff_id"),
        "chief_of_staff_instructions": normalized.get("chief_of_staff_instructions") or "",
    }
    if normalized.get("blueprint_id"):
        payload["blueprint_id"] = normalized["blueprint_id"]
    return payload


def load_team_rosters() -> dict[str, dict[str, Any]]:
    """Load the in-memory roster registry from ``team_rosters.json``."""
    global _roster_registry
    with _roster_lock:
        if _roster_registry is not None:
            return _roster_registry
        try:
            path = team_rosters_path()
            if path.exists():
                raw = path.read_text(encoding="utf-8")
                if not raw.strip():
                    _roster_registry = {}
                else:
                    parsed = json.loads(raw) or {}
                    if not isinstance(parsed, dict):
                        logger.error("team_rosters.json root must be an object; using empty registry.")
                        _roster_registry = {}
                    else:
                        _roster_registry = parsed
            else:
                _roster_registry = {}
        except Exception:
            logger.exception("Failed to load team_rosters.json; using empty registry.")
            _roster_registry = {}
        return _roster_registry


def save_team_rosters() -> None:
    """Persist the in-memory roster registry to ``team_rosters.json``.

    Never writes ``teams.json``.
    """
    path = team_rosters_path()
    if path.name != "team_rosters.json":
        raise RuntimeError("Refusing to persist team rosters to a non-roster path.")
    with _roster_lock:
        try:
            path.write_text(json.dumps(_roster_registry or {}, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to persist team rosters to %s", path)
            raise


def get_roster(roster_id: str) -> dict[str, Any] | None:
    with _roster_lock:
        return load_team_rosters().get(roster_id)


def upsert_roster(roster: dict[str, Any]) -> dict[str, Any]:
    """Insert or replace a roster and persist. Returns the stored document."""
    normalized = normalize_roster(roster)
    with _roster_lock:
        reg = load_team_rosters()
        stored = {
            "id": normalized["id"],
            "name": normalized["name"],
            "members": normalized["members"],
            "wires": normalized["wires"],
            "chief_of_staff_id": normalized.get("chief_of_staff_id"),
            "chief_of_staff_instructions": normalized.get("chief_of_staff_instructions") or "",
        }
        if normalized.get("blueprint_id"):
            stored["blueprint_id"] = normalized["blueprint_id"]
        reg[normalized["id"]] = stored
        save_team_rosters()
        return reg[normalized["id"]]


def delete_roster(roster_id: str) -> bool:
    """Remove a roster. Returns True if it existed."""
    with _roster_lock:
        reg = load_team_rosters()
        if roster_id not in reg:
            return False
        reg.pop(roster_id, None)
        save_team_rosters()
        return True


def reset_team_rosters(initial: dict[str, dict[str, Any]] | None = None) -> None:
    """Replace the in-memory cache (tests). Does not write disk unless save is called."""
    global _roster_registry
    with _roster_lock:
        _roster_registry = None if initial is None else dict(initial)


def static_team_rosters_path() -> Path:
    return Path(__file__).resolve().parents[1] / "static" / "team_rosters.json"


def load_static_demo_rosters() -> dict[str, dict[str, Any]]:
    """Demo rosters shipped in ``src/swarm/static/team_rosters.json`` (list or map)."""
    path = static_team_rosters_path()
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load static team_rosters.json")
        return {}
    rows: list[Any]
    if isinstance(parsed, dict) and isinstance(parsed.get("data"), list):
        rows = parsed["data"]
    elif isinstance(parsed, dict):
        rows = list(parsed.values())
    elif isinstance(parsed, list):
        rows = parsed
    else:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or "").strip()
        if rid:
            out[rid] = row
    return out


def resolve_roster(roster_id: str) -> dict[str, Any] | None:
    """User store first, then shipped demo rosters (demo SDLC / BA)."""
    want = str(roster_id or "").strip()
    if not want:
        return None
    found = get_roster(want)
    if found:
        return found
    return load_static_demo_rosters().get(want)


def blueprint_id_from_source(source: Any) -> str | None:
    text = str(source or "").strip()
    if not text.lower().startswith("blueprint:"):
        return None
    blueprint_id = text.split(":", 1)[1].strip()
    return blueprint_id or None


def advisor_blueprint_for_agent(
    roster_id: Any, agent_blueprint_id: Any
) -> str | None:
    """Blueprint id of the one advisor wired to ``agent_blueprint_id``.

    A team wire (handoff / as_tool — the per-roster ``wires`` toggles) to a
    member with ``role == 'advisor'`` marks the source agent as advised.
    When several advisors exist, the first in roster order wins (no
    double-fire). Returns None when the agent has no wired advisor or the
    member is not a blueprint-backed seat.
    """
    roster = resolve_roster(str(roster_id or "").strip())
    if not isinstance(roster, dict):
        return None
    wires = roster.get("wires")
    wired = isinstance(wires, dict) and (wires.get("handoff") or wires.get("as_tool"))
    if isinstance(wires, dict) and not wired:
        return None
    wanted = str(agent_blueprint_id or "").strip()
    if not wanted:
        return None
    members = roster.get("members")
    if not isinstance(members, list):
        return None
    for row in members:
        if not isinstance(row, dict):
            continue
        if str(row.get("role") or "") != "advisor":
            continue
        source = row.get("source")
        bid = blueprint_id_from_source(source)
        if bid and bid != wanted:
            return bid
    return None


def skeptic_blueprint_for_agent(
    roster_id: Any, agent_blueprint_id: Any
) -> str | None:
    """Blueprint id of the one skeptic wired to ``agent_blueprint_id``.

    Mirror of :func:`advisor_blueprint_for_agent` for the adversarial review
    loop: a team wire (handoff / as_tool) to a member with
    ``role == 'skeptic'`` marks the source agent as skeptic-reviewed. When
    several skeptics exist, the first in roster order wins (no double-fire).
    Returns None when the agent has no wired skeptic or the roster disables
    its wires.
    """
    roster = resolve_roster(str(roster_id or "").strip())
    if not isinstance(roster, dict):
        return None
    wires = roster.get("wires")
    wired = isinstance(wires, dict) and (wires.get("handoff") or wires.get("as_tool"))
    if isinstance(wires, dict) and not wired:
        return None
    wanted = str(agent_blueprint_id or "").strip()
    if not wanted:
        return None
    members = roster.get("members")
    if not isinstance(members, list):
        return None
    # The audited agent must be a roster member (by seat id or by the
    # blueprint its source points at). Stricter than the advisor resolver:
    # the rework loop re-prompts a specific worker, so misfires onto
    # non-member agents that merely share a blueprint id would be wrong.
    member_blueprints = {
        bid
        for row in members
        if isinstance(row, dict)
        and (bid := blueprint_id_from_source(row.get("source")))
    }
    if wanted not in member_blueprints and not any(
        isinstance(row, dict) and str(row.get("id") or "") == wanted
        for row in members
    ):
        return None
    for row in members:
        if not isinstance(row, dict):
            continue
        if str(row.get("role") or "") != "skeptic":
            continue
        source = row.get("source")
        bid = blueprint_id_from_source(source)
        if bid and bid != wanted:
            return bid
    return None


def blueprint_id_for_team_target(team_id: Any, target: Any = None) -> str | None:
    """Blueprint id for a team send, or None (stub / CLI / remote)."""
    roster = resolve_roster(str(team_id or "").strip())
    if not isinstance(roster, dict):
        return None
    members = roster.get("members")
    dest = str(target or "").strip() or "all"
    member = None
    if dest not in {"all", "*"}:
        member = find_member(members, dest)
    if member is None:
        cos_id = str(roster.get("chief_of_staff_id") or "").strip()
        if dest in {"all", "*", cos_id}:
            member = find_member(members, cos_id) if cos_id else None
    if member is None and isinstance(members, list):
        for row in members:
            if blueprint_id_from_source((row or {}).get("source") if isinstance(row, dict) else None):
                member = row
                break
    if not isinstance(member, dict):
        return None
    return blueprint_id_from_source(member.get("source"))


def iter_normalized_rosters(
    rosters: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return ``{id: normalized_roster}`` from an in-memory map or the store."""
    raw = rosters if rosters is not None else load_team_rosters()
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return out
    for rid, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            out[str(rid)] = normalize_roster(entry, roster_id=str(entry.get("id") or rid))
        except ValueError:
            logger.warning("Skipping invalid roster %s", rid)
    return out

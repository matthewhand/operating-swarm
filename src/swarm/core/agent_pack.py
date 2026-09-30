"""Agent pack: selected skills as prose + gettingStarted (#1392).

A pack is a recipe, not a clone. Skills travel as name / description /
instructions text. Binaries, assets, scripts, and secrets are refused.

``gettingStarted.skill`` must name one of the packed skills or validation
fails. Import recreates the skills on the seat and marks gettingStarted
for the first conversation.
"""

from __future__ import annotations

from typing import Any

from swarm.core.agent_skills import (
    SOURCE_PACK,
    get_skill,
    list_skills,
    public_getting_started,
    public_skill,
    replace_skills,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.core.skills import discover_skills

PACK_KIND = "swarm-agent-pack"
PACK_OBJECT = "agent_pack"

_BINARY_KEYS = frozenset(
    {
        "assets",
        "files",
        "scripts",
        "binary",
        "binaries",
        "content_b64",
        "base64",
        "attachment",
        "attachments",
        "path",
        "paths",
    }
)


class PackValidationError(ValueError):
    """Invalid agent pack. ``code`` is stable for API clients."""

    def __init__(self, message: str, *, code: str = "pack_invalid") -> None:
        super().__init__(message)
        self.code = code


def _reject_binaries(raw: Any, *, where: str) -> None:
    if isinstance(raw, dict):
        hits = sorted(key for key in raw if str(key).strip().lower() in _BINARY_KEYS)
        if hits:
            raise PackValidationError(
                f"{where} must be prose only; refused binary field(s): {', '.join(hits)}",
                code="pack_binaries",
            )
        for key, value in raw.items():
            _reject_binaries(value, where=f"{where}.{key}")
    elif isinstance(raw, list):
        for index, item in enumerate(raw):
            _reject_binaries(item, where=f"{where}[{index}]")


def _skill_prose(raw: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise PackValidationError(
            f"skills[{index}] must be an object with name and instructions",
            code="pack_skill_invalid",
        )
    _reject_binaries(raw, where=f"skills[{index}]")
    try:
        row = public_skill({**raw, "source": raw.get("source") or SOURCE_PACK})
    except ValueError as exc:
        raise PackValidationError(str(exc), code="pack_skill_invalid") from exc
    return {
        "name": row["name"],
        "description": row.get("description") or "",
        "instructions": row["instructions"],
    }


def validate_pack(raw: Any) -> dict[str, Any]:
    """Normalize a pack. Raises :class:`PackValidationError` on bad input.

    ``gettingStarted.skill`` is required and must name a packed skill.
    """
    if not isinstance(raw, dict):
        raise PackValidationError("pack must be a JSON object", code="pack_invalid")
    _reject_binaries(raw, where="pack")
    skills_raw = raw.get("skills")
    if skills_raw is None:
        raise PackValidationError("pack must include skills[]", code="pack_skills_missing")
    if not isinstance(skills_raw, list) or not skills_raw:
        raise PackValidationError("pack skills must be a non-empty list", code="pack_skills_missing")
    skills = [_skill_prose(item, index=index) for index, item in enumerate(skills_raw)]
    seen: set[str] = set()
    for row in skills:
        if row["name"] in seen:
            raise PackValidationError(
                f"duplicate packed skill '{row['name']}'",
                code="pack_skill_duplicate",
            )
        seen.add(row["name"])
    started_raw = raw.get("gettingStarted", raw.get("getting_started"))
    if started_raw is None or started_raw == "":
        raise PackValidationError(
            "gettingStarted.skill must name a packed skill",
            code="pack_getting_started_missing",
        )
    try:
        started = public_getting_started(started_raw)
    except ValueError as exc:
        raise PackValidationError(str(exc), code="pack_getting_started_invalid") from exc
    if not started or not started.get("skill"):
        raise PackValidationError(
            "gettingStarted.skill must name a packed skill",
            code="pack_getting_started_missing",
        )
    if started["skill"] not in seen:
        raise PackValidationError(
            f"gettingStarted.skill {started['skill']!r} must name a packed skill",
            code="pack_getting_started_missing",
        )
    kind = str(raw.get("kind") or PACK_KIND).strip() or PACK_KIND
    return {
        "object": PACK_OBJECT,
        "kind": kind,
        "skills": skills,
        "gettingStarted": started,
    }


def _resolve_selected(agent_id: str, name: str) -> dict[str, Any]:
    wanted = str(name or "").strip()
    attached = get_skill(agent_id, wanted)
    if attached is not None:
        return {
            "name": attached["name"],
            "description": attached.get("description") or "",
            "instructions": attached["instructions"],
        }
    catalog = discover_skills()
    skill = catalog.get(wanted) or catalog.get(wanted.lower())
    if skill is None:
        raise PackValidationError(
            f"skill {name!r} is not attached and was not found in the library",
            code="pack_skill_missing",
        )
    return {
        "name": skill.name,
        "description": skill.description or "",
        "instructions": skill.instructions,
    }


def build_pack(
    agent_id: str,
    *,
    skill_names: list[str] | None = None,
    getting_started: Any = None,
) -> dict[str, Any]:
    """Pack selected (or all attached) skills as prose.

    ``gettingStarted.skill`` comes from *getting_started* or the seat. It
    must name a packed skill.
    """
    if skill_names is None:
        selected = [
            {
                "name": row["name"],
                "description": row.get("description") or "",
                "instructions": row["instructions"],
            }
            for row in list_skills(agent_id)
        ]
    else:
        selected = [_resolve_selected(agent_id, str(name).strip()) for name in skill_names if str(name).strip()]
    started = getting_started
    if started is None:
        from swarm.core.agent_skills import getting_started as stored_getting_started

        started = stored_getting_started(agent_id)
    return validate_pack(
        {
            "kind": PACK_KIND,
            "skills": selected,
            "gettingStarted": started,
        }
    )


def import_pack(agent_id: str, raw: Any) -> dict[str, Any]:
    """Recreate packed skills on *agent_id* and mark gettingStarted first-run."""
    pack = validate_pack(raw)
    payload = replace_skills(
        agent_id,
        [{**row, "source": SOURCE_PACK} for row in pack["skills"]],
        getting_started_raw=pack["gettingStarted"],
        first_run=True,
        source=SOURCE_PACK,
    )
    payload["pack"] = pack
    payload["agent_id"] = normalize_agent_id(agent_id)
    payload["object"] = "agent_pack_import"
    return payload

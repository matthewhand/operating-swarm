"""Org-shared bot library (#1311).

Installation-global catalog of shareable bot recipes (not live computers,
not conversation history). Preset bots are always present and cannot be
deleted. A bot can be published to the org or shared with a whole team
(visibility=team + roster membership).

No secrets in stored fields. Templates are recipes: identity, description,
kind, role, and instructions only.

Layout::

    <user-config>/org_bot_library.json

    {
      "schema": 1,
      "org_id": "default",
      "bots": {
        "<bot_id>": { ... }
      }
    }
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# #1706 D.16 — org-library bots are seats, so they route through the one
# role-validity decision point rather than re-deriving the rule here.
from swarm.core.agent_roles import (
    CANONICAL_ROLES,
    normalize_agent_role,
    validate_role_for_kind,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.core.kind_bases import KIND_API, KIND_CLI
from swarm.core.paths import (
    ensure_swarm_directories_exist,
    get_user_config_dir_for_swarm,
)
from swarm.core.schedule_triggers import reject_secrets
from swarm.core.team_rosters import (
    MEMBER_NAME_MAX,
    add_member_if_absent,
    get_roster,
    remove_members_with_source,
)

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_LIBRARY_PATH = "SWARM_ORG_BOT_LIBRARY_PATH"
DEFAULT_ORG_ID = "default"

VISIBILITY_ORG = "org"
VISIBILITY_TEAM = "team"
VISIBILITY_PRIVATE = "private"
VISIBILITIES = (VISIBILITY_ORG, VISIBILITY_TEAM, VISIBILITY_PRIVATE)

SOURCE_PRESET = "preset"
SOURCE_USER = "user"

OBJECT_BOT = "org_library.bot"

KIND_BLUEPRINT = "blueprint"
BOT_KINDS = (KIND_API, KIND_CLI, KIND_BLUEPRINT)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SECRET_FIELD_KEYS = frozenset(
    {
        "api_key",
        "token",
        "secret",
        "password",
        "authorization",
        "credentials",
        "env",
        "headers",
        "cookie",
    }
)

PRESET_SUPPORT_ID = "preset-support"
PRESET_RESEARCHER_ID = "preset-researcher"
PRESET_REVIEWER_ID = "preset-reviewer"

PRESET_BOTS: tuple[dict[str, Any], ...] = (
    {
        "id": PRESET_SUPPORT_ID,
        "name": "Support",
        "description": "First-run onboarder. Create a team, add a remote, wire a CLI.",
        "kind": KIND_API,
        "role": "support",
        "instructions": (
            "Help the operator stand up a working roster. Never ask for raw "
            "secrets; collect env-var names only."
        ),
    },
    {
        "id": PRESET_RESEARCHER_ID,
        "name": "Researcher",
        "description": "Gather sources, cite claims, and hand off a linked brief.",
        "kind": KIND_API,
        "role": "default",
        "instructions": (
            "Research the assigned question. Link every claim. Do not publish "
            "or contact anyone."
        ),
    },
    {
        "id": PRESET_REVIEWER_ID,
        "name": "Reviewer",
        "description": "Check a draft against sources and list only blocking issues.",
        "kind": KIND_API,
        "role": "skeptic",
        "instructions": (
            "Review the draft against the cited sources. List only blocking "
            "issues. Do not rewrite unless asked."
        ),
    },
)

PRESET_IDS = frozenset(row["id"] for row in PRESET_BOTS)

_cache: dict[str, Any] | None = None
_lock = threading.RLock()


class OrgLibraryError(ValueError):
    """User-facing library failure."""


class PresetProtectedError(OrgLibraryError):
    """Preset bots cannot be deleted or have their preset flag cleared."""


class TeamNotFoundError(OrgLibraryError):
    """Whole-team share needs a real roster id."""


def library_path() -> Path:
    """Path of the org-shared library JSON file."""
    override = (os.environ.get(ENV_LIBRARY_PATH) or "").strip()
    if override:
        return Path(override)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "org_bot_library.json"


def reset_org_bot_library(initial: dict[str, Any] | None = None) -> None:
    """Replace the in-memory cache (tests). Does not write disk unless saved."""
    global _cache
    with _lock:
        _cache = None if initial is None else dict(initial)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug_id(raw: Any) -> str:
    text = str(raw or "").strip()
    if _ID_RE.match(text):
        return text
    slug = normalize_agent_id(text)
    if slug and slug != "_default" and _ID_RE.match(slug):
        return slug
    raise OrgLibraryError("Bot id is required and must be a short slug.")


def _empty_document() -> dict[str, Any]:
    return {"schema": SCHEMA, "org_id": DEFAULT_ORG_ID, "bots": {}}


def _preset_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "object": OBJECT_BOT,
        "name": row["name"],
        "description": row["description"],
        "kind": row["kind"],
        "role": row["role"],
        "instructions": row["instructions"],
        "preset": True,
        "visibility": VISIBILITY_ORG,
        "team_ids": [],
        "source": SOURCE_PRESET,
        "created_by": "",
        "updated_at": "",
    }


def _ensure_presets(doc: dict[str, Any]) -> dict[str, Any]:
    bots = doc.setdefault("bots", {})
    if not isinstance(bots, dict):
        bots = {}
        doc["bots"] = bots
    for row in PRESET_BOTS:
        existing = bots.get(row["id"])
        if isinstance(existing, dict) and existing.get("source") == SOURCE_USER:
            # A user-published id must not clobber a shipped preset.
            continue
        merged = _preset_record(row)
        if isinstance(existing, dict):
            # Keep operator-edited name/description/instructions on presets.
            for key in ("name", "description", "instructions"):
                text = str(existing.get(key) or "").strip()
                if text:
                    merged[key] = text
            merged["updated_at"] = str(existing.get("updated_at") or "")
        bots[row["id"]] = merged
    return doc


def _load_unlocked() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = library_path()
    doc = _empty_document()
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            if raw.strip():
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    bots = parsed.get("bots")
                    doc["org_id"] = str(parsed.get("org_id") or DEFAULT_ORG_ID).strip() or DEFAULT_ORG_ID
                    if isinstance(bots, dict):
                        doc["bots"] = bots
    except Exception:
        logger.exception("Failed to load org bot library; using empty + presets.")
    _cache = _ensure_presets(doc)
    return _cache


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="org_bot_library.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _save_unlocked(doc: dict[str, Any]) -> None:
    """Persist *doc* and only then swap the process cache.

    Callers must pass a copy. A failed write leaves the previous cache in place.
    """
    global _cache
    prepared = _ensure_presets(doc)
    try:
        _atomic_write(library_path(), prepared)
    except Exception:
        logger.exception("Failed to persist org bot library.")
        raise
    _cache = prepared


def load_library() -> dict[str, Any]:
    """Return the live document (presets guaranteed)."""
    with _lock:
        return _load_unlocked()


def public_bot(row: dict[str, Any]) -> dict[str, Any]:
    """Stable public JSON shape. Never includes secret-bearing keys."""
    team_ids = [str(item).strip() for item in (row.get("team_ids") or []) if str(item).strip()]
    return {
        "id": str(row.get("id") or ""),
        "object": OBJECT_BOT,
        "name": str(row.get("name") or row.get("id") or ""),
        "description": str(row.get("description") or ""),
        "kind": str(row.get("kind") or KIND_API),
        "role": str(row.get("role") or "default"),
        "instructions": str(row.get("instructions") or ""),
        "preset": bool(row.get("preset")),
        "visibility": str(row.get("visibility") or VISIBILITY_ORG),
        "team_ids": team_ids,
        "source": str(row.get("source") or SOURCE_USER),
        "created_by": str(row.get("created_by") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def _reject_secret_keys(incoming: dict[str, Any]) -> None:
    for key in incoming:
        if str(key).strip().lower() in _SECRET_FIELD_KEYS:
            raise OrgLibraryError("Library entries must not contain secrets.")


def normalize_bot(raw: dict[str, Any], *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate and stamp one library bot. Raises OrgLibraryError."""
    if not isinstance(raw, dict):
        raise OrgLibraryError("Bot must be an object.")
    _reject_secret_keys(raw)

    merged = dict(existing or {})
    merged.update(raw)

    bot_id = _slug_id(merged.get("id") or (existing or {}).get("id"))
    try:
        name = reject_secrets(str(merged.get("name") or bot_id).strip() or bot_id, "name")
        description = reject_secrets(str(merged.get("description") or "").strip(), "description")
        instructions = reject_secrets(str(merged.get("instructions") or "").strip(), "instructions")
    except ValueError as exc:
        raise OrgLibraryError(str(exc)) from exc

    kind = str(merged.get("kind") or KIND_API).strip().lower()
    if kind not in BOT_KINDS:
        raise OrgLibraryError(f"Bot kind must be one of {', '.join(BOT_KINDS)}.")

    role = normalize_agent_role(merged.get("role") or "default")
    if role not in CANONICAL_ROLES:
        raise OrgLibraryError(f"Bot role must be one of {', '.join(sorted(CANONICAL_ROLES))}.")
    # #1706 D.16 — reject a role this seat kind cannot carry, with the single
    # rule's own message. The view turns OrgLibraryError into a 400.
    role_error = validate_role_for_kind(role, kind)
    if role_error:
        raise OrgLibraryError(role_error)

    visibility = str(merged.get("visibility") or VISIBILITY_ORG).strip().lower()
    if visibility not in VISIBILITIES:
        raise OrgLibraryError(f"Visibility must be one of {', '.join(VISIBILITIES)}.")

    team_ids: list[str] = []
    for item in merged.get("team_ids") or []:
        tid = str(item or "").strip()
        if tid:
            team_ids.append(tid)
    extra_team = str(merged.get("team_id") or "").strip()
    if extra_team and extra_team not in team_ids:
        team_ids.append(extra_team)
    if visibility == VISIBILITY_TEAM and not team_ids:
        raise OrgLibraryError("Team visibility requires a team_id.")

    # Shipped ids only. A client-supplied preset flag must not make a bot undeletable.
    is_preset = bot_id in PRESET_IDS
    source = SOURCE_PRESET if is_preset else SOURCE_USER
    if is_preset:
        visibility = VISIBILITY_ORG
        team_ids = []

    return {
        "id": bot_id,
        "object": OBJECT_BOT,
        "name": name[:MEMBER_NAME_MAX],
        "description": description[:2000],
        "kind": kind,
        "role": role,
        "instructions": instructions[:8000],
        "preset": is_preset,
        "visibility": visibility,
        "team_ids": team_ids,
        "source": source,
        "created_by": str(merged.get("created_by") or "").strip()[:64],
        "updated_at": _utcnow(),
    }


def list_bots(*, team_id: str | None = None, include_private: bool = False) -> list[dict[str, Any]]:
    """Org-visible presets + org bots, plus team-shared bots for *team_id*."""
    want_team = str(team_id or "").strip()
    with _lock:
        doc = _load_unlocked()
        rows: list[dict[str, Any]] = []
        for raw in doc.get("bots", {}).values():
            if not isinstance(raw, dict):
                continue
            visibility = str(raw.get("visibility") or VISIBILITY_ORG)
            if visibility == VISIBILITY_PRIVATE and not include_private:
                continue
            if visibility == VISIBILITY_TEAM:
                team_ids = [str(item).strip() for item in (raw.get("team_ids") or [])]
                if want_team and want_team not in team_ids:
                    continue
                if not want_team:
                    continue
            rows.append(public_bot(raw))
        rows.sort(key=lambda row: (not row["preset"], row["name"].lower(), row["id"]))
        return rows


def get_bot(bot_id: str) -> dict[str, Any] | None:
    ident = str(bot_id or "").strip()
    if not ident:
        return None
    with _lock:
        raw = _load_unlocked().get("bots", {}).get(ident)
        return public_bot(raw) if isinstance(raw, dict) else None


def publish_bot(body: dict[str, Any], *, created_by: str = "") -> dict[str, Any]:
    """Create or replace a user bot in the org library."""
    incoming = dict(body or {})
    if created_by and not incoming.get("created_by"):
        incoming["created_by"] = created_by
    with _lock:
        doc = copy.deepcopy(_load_unlocked())
        bots = doc.setdefault("bots", {})
        existing = bots.get(str(incoming.get("id") or "").strip())
        if incoming.get("id") in PRESET_IDS or (isinstance(existing, dict) and existing.get("preset")):
            raise PresetProtectedError("Preset bots are shipped with the org library.")
        stored = normalize_bot(incoming, existing=existing if isinstance(existing, dict) else None)
        bots[stored["id"]] = stored
        _save_unlocked(doc)
        return public_bot(stored)


def delete_bot(bot_id: str) -> bool:
    """Remove a non-preset bot. Raises PresetProtectedError for presets."""
    ident = str(bot_id or "").strip()
    if not ident:
        return False
    if ident in PRESET_IDS:
        raise PresetProtectedError("Preset bots cannot be removed.")
    with _lock:
        doc = copy.deepcopy(_load_unlocked())
        bots = doc.get("bots") or {}
        raw = bots.get(ident)
        if not isinstance(raw, dict):
            return False
        if raw.get("preset") or raw.get("source") == SOURCE_PRESET:
            raise PresetProtectedError("Preset bots cannot be removed.")
        bots.pop(ident, None)
        doc["bots"] = bots
        _save_unlocked(doc)
        remove_members_with_source(f"org-library:{ident}")
        return True


def _add_bot_to_roster(bot: dict[str, Any], team_id: str) -> dict[str, Any]:
    """Attach *bot* to *team_id*. Caller must hold the library lock."""
    if get_roster(team_id) is None:
        raise TeamNotFoundError(f"Team '{team_id}' was not found.")
    try:
        return add_member_if_absent(
            team_id,
            {
                "id": bot["id"],
                "name": bot["name"],
                "kind": bot["kind"] if bot["kind"] in ("api", "cli", "blueprint") else "api",
                "role": bot["role"],
                "source": f"org-library:{bot['id']}",
            },
        )
    except KeyError as exc:
        raise TeamNotFoundError(f"Team '{team_id}' was not found.") from exc


def share_with_team(bot_id: str, team_id: str) -> dict[str, Any]:
    """Whole-team share: team visibility + roster membership.

    The recipient team gets the recipe on its roster. This does not copy
    conversation history, computer state, or secrets.

    Library visibility updates only after the roster accepts the member, under
    one lock, so a missing team or a rejected member cannot hide the recipe
    and concurrent shares cannot drop a teammate's roster write.
    """
    ident = str(bot_id or "").strip()
    tid = str(team_id or "").strip()
    if not ident:
        raise OrgLibraryError("Bot id is required.")
    if not tid:
        raise OrgLibraryError("team_id is required for whole-team share.")

    with _lock:
        doc = copy.deepcopy(_load_unlocked())
        raw = (doc.get("bots") or {}).get(ident)
        if not isinstance(raw, dict):
            raise OrgLibraryError(f"Bot '{ident}' was not found.")
        pending: dict[str, Any] | None
        if raw.get("preset") or ident in PRESET_IDS:
            # Presets stay org-wide; still attach them to the roster.
            bot = public_bot(raw)
            pending = None
        else:
            team_ids = [str(item).strip() for item in (raw.get("team_ids") or []) if str(item).strip()]
            if tid not in team_ids:
                team_ids.append(tid)
            pending = normalize_bot(
                {
                    **raw,
                    "visibility": VISIBILITY_TEAM,
                    "team_ids": team_ids,
                    "team_id": tid,
                },
                existing=raw,
            )
            bot = public_bot(pending)
        try:
            roster = _add_bot_to_roster(bot, tid)
        except OrgLibraryError:
            raise
        except ValueError as exc:
            raise OrgLibraryError(str(exc)) from exc
        if pending is not None:
            doc["bots"][ident] = pending
            _save_unlocked(doc)
    return {"bot": bot, "team_id": tid, "roster_id": roster.get("id") or tid}


# Keep the test helper importable without a circular surprise.
__all__ = (
    "BOT_KINDS",
    "OBJECT_BOT",
    "PRESET_BOTS",
    "PRESET_IDS",
    "PRESET_RESEARCHER_ID",
    "PRESET_REVIEWER_ID",
    "PRESET_SUPPORT_ID",
    "VISIBILITIES",
    "VISIBILITY_ORG",
    "VISIBILITY_PRIVATE",
    "VISIBILITY_TEAM",
    "OrgLibraryError",
    "PresetProtectedError",
    "TeamNotFoundError",
    "delete_bot",
    "get_bot",
    "library_path",
    "list_bots",
    "load_library",
    "normalize_bot",
    "publish_bot",
    "public_bot",
    "reset_org_bot_library",
    "share_with_team",
)

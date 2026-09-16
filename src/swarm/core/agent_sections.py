"""Persisted rail sections (Issue #219).

CoS tools create / rename / archive sections and move agents — the server-side
counterpart of REQ-209 localStorage (``swarm_rail_sections``). Membership is
the OpenMousBot comms grouping; talk ACL is a separate write through
``agent_mailbox_acl``.

Layout::

    <user-config>/agent_sections.json

    {
      "schema": 1,
      "sections": [{"id": "sec_ab12", "name": "Review", "archived": false, "internal_only": false}],
      "membership": {"skeptic_a": "sec_ab12"}
    }

Never ``teams.json``. No secrets. No Neon.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_SECTIONS_PATH = "SWARM_AGENT_SECTIONS_PATH"
STORE_NAME = "agent_sections.json"
UNASSIGNED_SECTION_ID = "unassigned"
UNASSIGNED_SECTION_NAME = "Unassigned"
SECTION_ID_PREFIX = "sec_"

_cache: dict[str, Any] | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_unassigned_section(section_id: str | None) -> bool:
    return not section_id or section_id == UNASSIGNED_SECTION_ID


def new_section_id() -> str:
    return f"{SECTION_ID_PREFIX}{uuid.uuid4().hex[:12]}"


def sections_path() -> Path:
    env = (os.environ.get(ENV_SECTIONS_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / STORE_NAME


def reset_sections_cache() -> None:
    """Drop the in-process cache (tests). Does not write disk."""
    global _cache
    _cache = None


def empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "sections": [], "membership": {}}


def _read_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = sections_path()
    if not path.is_file():
        _cache = empty_store()
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read rail sections at %s", path, exc_info=True)
        _cache = empty_store()
        return _cache
    _cache = normalize_store(data)
    return _cache


def _write_store(store: dict[str, Any]) -> None:
    global _cache
    path = sections_path()
    if path.name != STORE_NAME and ENV_SECTIONS_PATH not in os.environ:
        raise RuntimeError("Refusing to persist rail sections to a non-sections path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = normalize_store(store)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
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
    _cache = payload


def normalize_store(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_store()
    sections: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_sections = raw.get("sections")
    if isinstance(raw_sections, list):
        for item in raw_sections:
            row = _normalize_section(item)
            if row is None or row["id"] in seen:
                continue
            seen.add(row["id"])
            sections.append(row)
    membership: dict[str, str] = {}
    raw_membership = raw.get("membership")
    if isinstance(raw_membership, dict):
        known = {row["id"] for row in sections if not row.get("archived")}
        for agent_id, section_id in raw_membership.items():
            aid = normalize_agent_id(str(agent_id or "").strip()) if str(agent_id or "").strip() else ""
            sid = str(section_id or "").strip()
            if not aid or aid == "_default" or is_unassigned_section(sid) or sid not in known:
                continue
            membership[aid] = sid
    return {"schema": SCHEMA, "sections": sections, "membership": membership}


def _normalize_section(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    ident = str(raw.get("id") or "").strip()
    if not ident or ident == UNASSIGNED_SECTION_ID:
        return None
    name = raw.get("name")
    return {
        "id": ident,
        "name": str(name) if isinstance(name, str) else "",
        "archived": raw.get("archived") is True,
        "archived_at": str(raw.get("archived_at") or "") or None,
        "internal_only": raw.get("internal_only") is True or raw.get("internalOnly") is True,
    }


def public_section(row: dict[str, Any], *, members: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "id": row["id"],
        "name": row.get("name") or "",
        "archived": row.get("archived") is True,
        "internal_only": row.get("internal_only") is True,
    }
    if row.get("archived_at"):
        payload["archived_at"] = row["archived_at"]
    if members is not None:
        payload["members"] = list(members)
    return payload


@dataclass
class SectionStore:
    """In-memory or disk-backed rail-section state for one tool session."""

    payload: dict[str, Any] = field(default_factory=empty_store)
    persist: bool = False

    def snapshot(self) -> dict[str, Any]:
        return normalize_store(self.payload)

    def replace(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payload = normalize_store(payload)
        if self.persist:
            _write_store(self.payload)
        return self.payload


def default_section_store() -> SectionStore:
    return SectionStore(payload=_read_store(), persist=True)


def load_sections(store: SectionStore | None = None) -> dict[str, Any]:
    if store is None:
        return _read_store()
    return store.snapshot()


def save_sections(payload: dict[str, Any], store: SectionStore | None = None) -> dict[str, Any]:
    if store is None:
        _write_store(payload)
        return _read_store()
    return store.replace(payload)


def active_sections(payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = payload if payload is not None else _read_store()
    return [row for row in (data.get("sections") or []) if row.get("archived") is not True]


def find_section(section_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    ident = str(section_id or "").strip()
    if not ident:
        return None
    data = payload if payload is not None else _read_store()
    for row in data.get("sections") or []:
        if row.get("id") == ident:
            return row
    return None


def section_id_for_agent(agent_id: str, payload: dict[str, Any] | None = None) -> str:
    aid = normalize_agent_id(agent_id) if str(agent_id or "").strip() else ""
    if not aid or aid == "_default":
        return UNASSIGNED_SECTION_ID
    data = payload if payload is not None else _read_store()
    assigned = (data.get("membership") or {}).get(aid)
    row = find_section(assigned, data) if assigned else None
    if row is None or row.get("archived"):
        return UNASSIGNED_SECTION_ID
    return assigned


def member_ids(section_id: str, payload: dict[str, Any] | None = None) -> list[str]:
    ident = str(section_id or "").strip()
    if is_unassigned_section(ident):
        return []
    data = payload if payload is not None else _read_store()
    return sorted(
        aid for aid, sid in (data.get("membership") or {}).items() if sid == ident
    )


def membership_map(payload: dict[str, Any] | None = None) -> dict[str, str]:
    data = payload if payload is not None else _read_store()
    return dict(data.get("membership") or {})


__all__ = [
    "ENV_SECTIONS_PATH",
    "SCHEMA",
    "STORE_NAME",
    "UNASSIGNED_SECTION_ID",
    "UNASSIGNED_SECTION_NAME",
    "SectionStore",
    "active_sections",
    "default_section_store",
    "empty_store",
    "find_section",
    "is_unassigned_section",
    "load_sections",
    "member_ids",
    "membership_map",
    "new_section_id",
    "normalize_store",
    "public_section",
    "reset_sections_cache",
    "save_sections",
    "section_id_for_agent",
    "sections_path",
    "utc_now",
]

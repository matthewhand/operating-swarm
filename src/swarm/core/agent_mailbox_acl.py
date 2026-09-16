"""Persisted peer-mailbox ACL (REQ-162 / #573).

Per-agent **or** per-role whitelist XOR blacklist. Entries target:

* ``agent`` — a catalogued rail / roster agent id
* ``team`` — a composition roster id (every member of that team)
* ``role`` — a canonical role (``support``, ``gate``, ``skeptic``,
  ``chief_of_staff``, ``engineer``, ``suggestions``, ``default``)
* ``section`` — members of a CoS rail section (Issue #219)

Support (and CoS) default to **whitelist everything** (allow-all). Other
roles default to an empty **blacklist** (no extra cut on top of the team
union relationship graph). The Agent Editor writes this store — operators
do not hunt JSON files.

Layout::

    <user-config>/agent_mailbox_acl.json

    {
      "schema": 1,
      "agents": {"pat": {"mode": "blacklist", "entries": [{"kind": "agent", "id": "cos"}]}},
      "roles": {"support": {"mode": "whitelist", "entries": []}}
    }

Never ``teams.json``. No secrets. No Neon.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from swarm.core.agent_mailbox import AclEntry, AclPolicy
from swarm.core.agent_roles import (
    CANONICAL_ROLES,
    ROLE_ALIASES,
    ROLE_CHIEF_OF_STAFF,
    ROLE_SUPPORT,
    is_chief_of_staff,
    normalize_agent_role,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_ACL_PATH = "SWARM_MAILBOX_ACL_PATH"
STORE_NAME = "agent_mailbox_acl.json"
AclScope = Literal["agent", "role"]
AclSource = Literal["agent", "role", "default"]

ENTRY_KINDS: tuple[dict[str, str], ...] = (
    {
        "kind": "agent",
        "description": "A catalogued rail or roster agent id.",
    },
    {
        "kind": "team",
        "description": "A composition team roster id; matches every member of that team.",
    },
    {
        "kind": "role",
        "description": (
            "A canonical role: support, gate, skeptic, chief_of_staff, "
            "engineer, suggestions, or default."
        ),
    },
    {
        "kind": "section",
        "description": "Members of a CoS rail section (Issue #219).",
    },
)

_cache: dict[str, Any] | None = None


def is_allow_all_role(role: Any) -> bool:
    """Support and Chief of Staff are the open door (same-kind allow-all)."""
    canonical = normalize_agent_role(role)
    return canonical == ROLE_SUPPORT or canonical == ROLE_CHIEF_OF_STAFF or is_chief_of_staff(role)


def mailbox_acl_path() -> Path:
    env = (os.environ.get(ENV_ACL_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / STORE_NAME


def reset_mailbox_acl_cache() -> None:
    """Drop the in-process cache (tests). Does not write disk."""
    global _cache
    _cache = None


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "agents": {}, "roles": {}}


def _read_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = mailbox_acl_path()
    if not path.is_file():
        _cache = _empty_store()
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read mailbox ACL at %s", path, exc_info=True)
        _cache = _empty_store()
        return _cache
    if not isinstance(data, dict):
        _cache = _empty_store()
        return _cache
    agents = data.get("agents")
    roles = data.get("roles")
    _cache = {
        "schema": SCHEMA,
        "agents": dict(agents) if isinstance(agents, dict) else {},
        "roles": dict(roles) if isinstance(roles, dict) else {},
    }
    return _cache


def _write_store(store: dict[str, Any]) -> None:
    global _cache
    path = mailbox_acl_path()
    if path.name != STORE_NAME and ENV_ACL_PATH not in os.environ:
        raise RuntimeError("Refusing to persist mailbox ACL to a non-ACL path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA,
        "agents": store.get("agents") or {},
        "roles": store.get("roles") or {},
    }
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


def normalize_entry(raw: Any) -> AclEntry:
    """Validate one ACL entry. Raises ValueError."""
    if isinstance(raw, dict) and str(raw.get("kind") or "agent").strip().lower() == "role":
        ident = str(raw.get("id") or raw.get("name") or "").strip()
        key = ident.lower().replace(" ", "_").replace("-", "_")
        if key not in ROLE_ALIASES:
            raise ValueError(
                f"Unknown role {ident!r}. Use one of: {', '.join(CANONICAL_ROLES)}."
            )
    entry = AclEntry.from_raw(raw)
    if entry is None:
        raise ValueError("Each ACL entry needs kind (agent, team, role, or section) and id.")
    if len(entry.id) > 64:
        raise ValueError("ACL entry id too long (max 64).")
    return entry


def policy_from_stored(raw: Any, *, default_allow_all: bool = False) -> AclPolicy:
    """Parse a stored policy. Empty Support/CoS whitelist stays allow-all."""
    policy = AclPolicy.from_raw(raw)
    if policy.mode == "whitelist" and not policy.entries and default_allow_all:
        return replace(policy, allow_all=True)
    return policy


def default_policy_for_role(role: Any) -> AclPolicy:
    if is_allow_all_role(role):
        return AclPolicy(mode="whitelist", entries=(), allow_all=True)
    return AclPolicy(mode="blacklist", entries=())


@dataclass(frozen=True)
class ResolvedAcl:
    """Effective policy plus where it came from."""

    policy: AclPolicy
    source: AclSource
    role: str
    scope_id: str


def resolve_acl_policy(agent_id: str, role: Any = None) -> ResolvedAcl:
    """Agent override, else role policy, else Support allow-all / empty blacklist."""
    canonical = normalize_agent_role(role)
    agent = normalize_agent_id(agent_id) if str(agent_id or "").strip() else ""
    if agent == "_default":
        agent = ""
    store = _read_store()
    allow_all = is_allow_all_role(canonical)
    if agent and agent in store["agents"]:
        return ResolvedAcl(
            policy=policy_from_stored(store["agents"][agent], default_allow_all=allow_all),
            source="agent",
            role=canonical,
            scope_id=agent,
        )
    if canonical in store["roles"]:
        return ResolvedAcl(
            policy=policy_from_stored(store["roles"][canonical], default_allow_all=allow_all),
            source="role",
            role=canonical,
            scope_id=canonical,
        )
    return ResolvedAcl(
        policy=default_policy_for_role(canonical),
        source="default",
        role=canonical,
        scope_id=agent or canonical,
    )


def resolve_role_policy(role: Any) -> ResolvedAcl:
    canonical = normalize_agent_role(role)
    store = _read_store()
    allow_all = is_allow_all_role(canonical)
    if canonical in store["roles"]:
        return ResolvedAcl(
            policy=policy_from_stored(store["roles"][canonical], default_allow_all=allow_all),
            source="role",
            role=canonical,
            scope_id=canonical,
        )
    return ResolvedAcl(
        policy=default_policy_for_role(canonical),
        source="default",
        role=canonical,
        scope_id=canonical,
    )


def _policy_payload(mode: Any, entries: Any) -> dict[str, Any]:
    text = str(mode or "").strip().lower()
    if text not in ("whitelist", "blacklist"):
        raise ValueError("mode must be whitelist or blacklist (XOR).")
    if entries is None:
        raw_entries: list[Any] = []
    elif not isinstance(entries, list):
        raise ValueError("entries must be an array.")
    else:
        raw_entries = entries
    normalized = [normalize_entry(item).as_dict() for item in raw_entries]
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for item in normalized:
        key = (item["kind"], item["id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return {"mode": text, "entries": unique}


def put_agent_policy(agent_id: str, mode: Any, entries: Any) -> AclPolicy:
    agent = normalize_agent_id(agent_id)
    if not agent or agent == "_default":
        raise ValueError("agent id is required.")
    payload = _policy_payload(mode, entries)
    store = _read_store()
    agents = dict(store.get("agents") or {})
    agents[agent] = payload
    _write_store({"schema": SCHEMA, "agents": agents, "roles": store.get("roles") or {}})
    return policy_from_stored(payload, default_allow_all=False)


def delete_agent_policy(agent_id: str) -> None:
    agent = normalize_agent_id(agent_id)
    store = _read_store()
    agents = dict(store.get("agents") or {})
    if agent not in agents:
        return
    agents.pop(agent, None)
    _write_store({"schema": SCHEMA, "agents": agents, "roles": store.get("roles") or {}})


def put_role_policy(role: Any, mode: Any, entries: Any) -> AclPolicy:
    canonical = normalize_agent_role(role)
    if canonical not in CANONICAL_ROLES:
        raise ValueError(f"Unknown role {role!r}.")
    payload = _policy_payload(mode, entries)
    store = _read_store()
    roles = dict(store.get("roles") or {})
    roles[canonical] = payload
    _write_store({"schema": SCHEMA, "agents": store.get("agents") or {}, "roles": roles})
    return policy_from_stored(payload, default_allow_all=is_allow_all_role(canonical))


def delete_role_policy(role: Any) -> None:
    canonical = normalize_agent_role(role)
    store = _read_store()
    roles = dict(store.get("roles") or {})
    if canonical not in roles:
        return
    roles.pop(canonical, None)
    _write_store({"schema": SCHEMA, "agents": store.get("agents") or {}, "roles": roles})


def public_policy(resolved: ResolvedAcl, *, scope: AclScope) -> dict[str, Any]:
    inherited = resolved.source != scope
    return {
        "object": "mailbox_acl",
        "scope": scope,
        "id": resolved.scope_id,
        "role": resolved.role,
        "source": resolved.source,
        "inherited": inherited,
        "mode": resolved.policy.mode,
        "allow_all": resolved.policy.allow_all,
        "entries": [entry.as_dict() for entry in resolved.policy.entries],
        "entry_kinds": [dict(item) for item in ENTRY_KINDS],
    }


def public_store() -> dict[str, Any]:
    store = _read_store()
    return {
        "object": "mailbox_acl_store",
        "schema": SCHEMA,
        "agents": store.get("agents") or {},
        "roles": store.get("roles") or {},
        "entry_kinds": [dict(item) for item in ENTRY_KINDS],
        "defaults": {
            "support": {"mode": "whitelist", "allow_all": True},
            "chief_of_staff": {"mode": "whitelist", "allow_all": True},
            "other": {"mode": "blacklist", "allow_all": False},
        },
    }


__all__ = [
    "ENTRY_KINDS",
    "ENV_ACL_PATH",
    "SCHEMA",
    "STORE_NAME",
    "ResolvedAcl",
    "default_policy_for_role",
    "delete_agent_policy",
    "delete_role_policy",
    "is_allow_all_role",
    "mailbox_acl_path",
    "normalize_entry",
    "policy_from_stored",
    "public_policy",
    "public_store",
    "put_agent_policy",
    "put_role_policy",
    "reset_mailbox_acl_cache",
    "resolve_acl_policy",
    "resolve_role_policy",
]

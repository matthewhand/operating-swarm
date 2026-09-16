"""CoS section / topology tools (Issue #219).

TrueForge ``create_subagent`` mints temporary agents that die with the
session. Open Swarm CoS is a first-class operator: REQ-154 already persists
seats via ``create_agent``. This module is the missing rail-topology half —

* ``create_section`` / ``rename_section`` / ``archive_section``
* ``move_agent_to_section``
* ``set_talk_acl`` (writes ``agent_mailbox_acl``; XOR allow/deny)
* ``list_sections``

Only API-kind ``chief_of_staff`` gets these tools. Support keeps lifecycle
(REQ-154) but not topology. Ordinary roles never see them. Unknown agent or
section ids fail honestly — no silent no-ops.

NL: "put the two skeptics in a locked review section" →
``create_section(name, agent_ids, internal_only=true)`` (section + ACL).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from swarm.core.agent_kind import AgentKind, classify_agent_kind
from swarm.core.agent_lifecycle import looks_like_secret
from swarm.core.agent_mailbox import AclEntry
from swarm.core.agent_mailbox_acl import put_agent_policy, resolve_acl_policy
from swarm.core.agent_roles import (
    can_manage_topology,
    normalize_agent_role,
)
from swarm.core.agent_sections import (
    UNASSIGNED_SECTION_ID,
    SectionStore,
    active_sections,
    default_section_store,
    find_section,
    is_unassigned_section,
    load_sections,
    member_ids,
    new_section_id,
    public_section,
    save_sections,
    section_id_for_agent,
    utc_now,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.core.rail_seats import RAIL_ROLE_IDS
from swarm.core.team_isolation import role_of_member, teams_containing
from swarm.core.team_rosters import iter_normalized_rosters
from swarm.core.transcript_roles import append_event
from swarm.tool_executor import redact_sensitive_data

logger = logging.getLogger(__name__)

CREATE_SECTION_TOOL = "create_section"
RENAME_SECTION_TOOL = "rename_section"
ARCHIVE_SECTION_TOOL = "archive_section"
MOVE_AGENT_TOOL = "move_agent_to_section"
SET_TALK_ACL_TOOL = "set_talk_acl"
LIST_SECTIONS_TOOL = "list_sections"

V1_KIND: AgentKind = "api"
TEAM_TOKEN = "team"

ERROR_ROLE = "role_forbidden"
ERROR_CALLER_KIND = "caller_kind_unsupported"
ERROR_UNKNOWN_ID = "unknown_id"
ERROR_UNKNOWN_SECTION = "unknown_section"
ERROR_PROTECTED = "protected_section"
ERROR_SECRET = "secret_refused"
ERROR_XOR = "acl_xor"
ERROR_EMPTY = "empty_name"
ERROR_ALREADY_ARCHIVED = "already_archived"
ERROR_NO_TEAM = "no_team"


class TopologyError(Exception):
    """Tool-safe topology failure with a stable reason code."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": self.reason, "message": self.message}


def _as_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw or "").strip().lower()
    return text in {"1", "true", "yes", "on", "locked", "internal", "internal_only"}


def _as_id_list(raw: Any) -> list[str]:
    if raw is None or raw is False:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    if not text:
        return []
    if text[:1] in "[{":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def refuse_secrets(*values: Any) -> None:
    for value in values:
        if looks_like_secret(value):
            raise TopologyError(
                ERROR_SECRET,
                "Refusing secret-shaped text. Use agent/section ids only.",
            )


def _normalize_agent(agent_id: str) -> str:
    aid = normalize_agent_id(agent_id) if str(agent_id or "").strip() else ""
    if not aid or aid == "_default":
        raise TopologyError(ERROR_UNKNOWN_ID, "agent id is required.")
    return aid


@dataclass
class TopologyStores:
    sections: SectionStore = field(default_factory=SectionStore)
    rosters: dict[str, Any] | None = None
    library: dict[str, Any] | None = None
    remotes: dict[str, Any] | None = None
    known_ids: frozenset[str] = field(default_factory=frozenset)


def default_stores() -> TopologyStores:
    rosters = None
    library = None
    remotes = None
    try:
        from swarm.core.team_rosters import load_team_rosters

        rosters = load_team_rosters()
    except Exception:
        logger.debug("topology rosters load unavailable", exc_info=True)
    try:
        from swarm.views.blueprint_library_views import get_user_blueprint_library

        lib = get_user_blueprint_library()
        if isinstance(lib, dict):
            library = lib
    except Exception:
        logger.debug("topology library load unavailable", exc_info=True)
    try:
        from swarm.core.remotes import load_raw_config

        cfg, _path = load_raw_config()
        raw = cfg.get("remotes") if isinstance(cfg, dict) else None
        if isinstance(raw, dict):
            remotes = raw
    except Exception:
        logger.debug("topology remotes load unavailable", exc_info=True)
    return TopologyStores(
        sections=default_section_store(),
        rosters=rosters,
        library=library,
        remotes=remotes,
    )


@dataclass
class TopologyContext:
    """Bound caller + section store for one CoS tool session."""

    caller_id: str
    caller_kind: AgentKind = V1_KIND
    caller_role: str = "default"
    user_key: str = ""
    chat_base_dir: Path | None = None
    stores: TopologyStores = field(default_factory=TopologyStores)

    def payload(self) -> dict[str, Any]:
        return load_sections(self.stores.sections)

    def eligible(self) -> None:
        if self.caller_kind != V1_KIND:
            raise TopologyError(
                ERROR_CALLER_KIND,
                "section/topology tools are API-kind only in v1 (API CoS).",
            )
        if not can_manage_topology(self.caller_role):
            raise TopologyError(
                ERROR_ROLE,
                "Only Chief of Staff can create or reshape sections.",
            )

    def known_agent_ids(self) -> set[str]:
        ids = set(self.stores.known_ids)
        ids.update(RAIL_ROLE_IDS)
        if self.caller_id:
            ids.add(self.caller_id)
        for roster in iter_normalized_rosters(self.stores.rosters).values():
            for member in roster.get("members") or []:
                if member.get("kind") == "team":
                    continue
                mid = str(member.get("id") or "").strip()
                if mid:
                    ids.add(mid)
        for bucket in ("custom", "installed"):
            rows = (self.stores.library or {}).get(bucket) or []
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or row.get("archived") is True:
                    continue
                ident = str(row.get("id") or row.get("name") or "").strip()
                if ident:
                    ids.add(ident)
        for ident, row in (self.stores.remotes or {}).items():
            if isinstance(row, dict) and row.get("archived") is True:
                continue
            if ident:
                ids.add(str(ident))
        payload = self.payload()
        ids.update(payload.get("membership") or {})
        return ids

    def known_team_ids(self) -> set[str]:
        return set(iter_normalized_rosters(self.stores.rosters))

    def require_agent(self, agent_id: str) -> str:
        aid = _normalize_agent(agent_id)
        known = self.known_agent_ids()
        if known and aid not in known:
            raise TopologyError(ERROR_UNKNOWN_ID, f"Unknown agent {aid!r}.")
        return aid

    def require_section(self, section_id: str, *, allow_unassigned: bool = False) -> str:
        ident = str(section_id or "").strip()
        if allow_unassigned and is_unassigned_section(ident):
            return UNASSIGNED_SECTION_ID
        row = find_section(ident, self.payload())
        if row is None:
            raise TopologyError(ERROR_UNKNOWN_SECTION, f"Unknown section {ident!r}.")
        if row.get("archived") is True:
            raise TopologyError(ERROR_ALREADY_ARCHIVED, f"Section {ident!r} is archived.")
        return ident

    def create_section(
        self,
        name: str,
        agent_ids: Any = "",
        internal_only: Any = False,
    ) -> dict[str, Any]:
        try:
            self.eligible()
            refuse_secrets(name, agent_ids)
            title = str(name or "").strip()
            if not title:
                raise TopologyError(ERROR_EMPTY, "Section name is required.")
            members = [self.require_agent(item) for item in _as_id_list(agent_ids)]
            locked = _as_bool(internal_only)
            payload = self.payload()
            section = {
                "id": new_section_id(),
                "name": title,
                "archived": False,
                "archived_at": None,
                "internal_only": locked,
            }
            sections = list(payload.get("sections") or [])
            sections.append(section)
            membership = dict(payload.get("membership") or {})
            for aid in members:
                membership[aid] = section["id"]
            save_sections({"schema": 1, "sections": sections, "membership": membership}, self.stores.sections)
            acl = []
            if locked:
                acl = self._lock_members(section["id"], members)
            self._audit(f"Created section {section['id']} ({title})")
            logger.info("topology create_section caller=%s id=%s", self.caller_id, section["id"])
            return {
                "ok": True,
                "section": public_section(section, members=member_ids(section["id"], self.payload())),
                "acl": acl,
                "audit": f"Created section {section['id']}",
            }
        except TopologyError as exc:
            logger.info("topology create_section rejected %s (%s)", self.caller_id, exc.reason)
            return exc.as_dict()

    def rename_section(self, section_id: str, name: str) -> dict[str, Any]:
        try:
            self.eligible()
            refuse_secrets(section_id, name)
            ident = self.require_section(section_id)
            title = str(name or "").strip()
            if not title:
                raise TopologyError(ERROR_EMPTY, "Section name is required.")
            payload = self.payload()
            sections = []
            updated = None
            for row in payload.get("sections") or []:
                if row.get("id") == ident:
                    updated = {**row, "name": title}
                    sections.append(updated)
                else:
                    sections.append(row)
            save_sections(
                {"schema": 1, "sections": sections, "membership": payload.get("membership") or {}},
                self.stores.sections,
            )
            self._audit(f"Renamed section {ident}")
            return {
                "ok": True,
                "section": public_section(updated or {}, members=member_ids(ident, self.payload())),
                "audit": f"Renamed section {ident}",
            }
        except TopologyError as exc:
            return exc.as_dict()

    def archive_section(self, section_id: str) -> dict[str, Any]:
        try:
            self.eligible()
            refuse_secrets(section_id)
            ident = str(section_id or "").strip()
            if is_unassigned_section(ident):
                raise TopologyError(ERROR_PROTECTED, "Unassigned cannot be archived.")
            row = find_section(ident, self.payload())
            if row is None:
                raise TopologyError(ERROR_UNKNOWN_SECTION, f"Unknown section {ident!r}.")
            if row.get("archived") is True:
                raise TopologyError(ERROR_ALREADY_ARCHIVED, f"Section {ident!r} is already archived.")
            payload = self.payload()
            stamp = utc_now().isoformat()
            sections = []
            archived = None
            for item in payload.get("sections") or []:
                if item.get("id") == ident:
                    archived = {**item, "archived": True, "archived_at": stamp}
                    sections.append(archived)
                else:
                    sections.append(item)
            membership = {
                aid: sid
                for aid, sid in (payload.get("membership") or {}).items()
                if sid != ident
            }
            save_sections({"schema": 1, "sections": sections, "membership": membership}, self.stores.sections)
            self._audit(f"Archived section {ident}")
            return {
                "ok": True,
                "section": public_section(archived or {}),
                "audit": f"Archived section {ident}",
            }
        except TopologyError as exc:
            return exc.as_dict()

    def move_agent_to_section(self, agent_id: str, section_id: str) -> dict[str, Any]:
        try:
            self.eligible()
            refuse_secrets(agent_id, section_id)
            aid = self.require_agent(agent_id)
            target = self.require_section(section_id, allow_unassigned=True)
            payload = self.payload()
            membership = dict(payload.get("membership") or {})
            if is_unassigned_section(target):
                membership.pop(aid, None)
            else:
                membership[aid] = target
            save_sections(
                {"schema": 1, "sections": payload.get("sections") or [], "membership": membership},
                self.stores.sections,
            )
            self._audit(f"Moved agent {aid} to section {target}")
            return {
                "ok": True,
                "agent_id": aid,
                "section_id": target,
                "audit": f"Moved agent {aid} to section {target}",
            }
        except TopologyError as exc:
            return exc.as_dict()

    def set_talk_acl(self, agent_id: str, allow: Any = "", deny: Any = "") -> dict[str, Any]:
        try:
            self.eligible()
            refuse_secrets(agent_id, allow, deny)
            aid = self.require_agent(agent_id)
            allow_ids = _as_id_list(allow)
            deny_ids = _as_id_list(deny)
            if allow_ids and deny_ids:
                raise TopologyError(
                    ERROR_XOR,
                    "set_talk_acl is whitelist XOR blacklist — pass allow= or deny=, not both.",
                )
            if not allow_ids and not deny_ids:
                raise TopologyError(
                    ERROR_XOR,
                    "set_talk_acl needs allow= (whitelist) or deny= (blacklist).",
                )
            mode = "whitelist" if allow_ids else "blacklist"
            tokens = allow_ids or deny_ids
            entries = self._resolve_acl_tokens(aid, tokens)
            policy = put_agent_policy(aid, mode, entries)
            self._audit(f"Set talk ACL for {aid} ({mode})")
            resolved = resolve_acl_policy(aid, role_of_member(aid, self.stores.rosters))
            return {
                "ok": True,
                "agent_id": aid,
                "mode": policy.mode,
                "allow_all": policy.allow_all,
                "entries": [entry.as_dict() for entry in policy.entries],
                "source": resolved.source,
                "audit": f"Set talk ACL for {aid}",
            }
        except TopologyError as exc:
            return exc.as_dict()
        except ValueError as exc:
            return TopologyError(ERROR_XOR, str(exc)).as_dict()

    def list_sections(self) -> dict[str, Any]:
        try:
            self.eligible()
            payload = self.payload()
            rows = []
            for row in active_sections(payload):
                rows.append(public_section(row, members=member_ids(row["id"], payload)))
            return {"ok": True, "sections": rows, "unassigned": UNASSIGNED_SECTION_ID}
        except TopologyError as exc:
            return exc.as_dict()

    def _lock_members(self, section_id: str, members: Iterable[str]) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        entry = {"kind": "section", "id": section_id}
        for aid in members:
            policy = put_agent_policy(aid, "whitelist", [entry])
            applied.append({"agent_id": aid, "mode": policy.mode, "entries": [entry]})
        return applied

    def _resolve_acl_tokens(self, agent_id: str, tokens: list[str]) -> list[dict[str, str]]:
        agents = self.known_agent_ids()
        teams = self.known_team_ids()
        payload = self.payload()
        section_ids = {row["id"] for row in active_sections(payload)}
        entries: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for token in tokens:
            key = token.strip()
            if not key:
                continue
            lowered = key.lower()
            resolved: list[AclEntry] = []
            if lowered == TEAM_TOKEN or lowered.startswith("team:"):
                team_id = key.split(":", 1)[1].strip() if ":" in key else ""
                if team_id:
                    if teams and team_id not in teams:
                        raise TopologyError(ERROR_UNKNOWN_ID, f"Unknown team {team_id!r}.")
                    resolved.append(AclEntry(kind="team", id=team_id))
                else:
                    owned = teams_containing(agent_id, self.stores.rosters)
                    if not owned:
                        raise TopologyError(
                            ERROR_NO_TEAM,
                            f"Agent {agent_id!r} is not on a team; pass a roster id instead of 'team'.",
                        )
                    resolved.extend(AclEntry(kind="team", id=tid) for tid in sorted(owned))
            elif key in section_ids:
                resolved.append(AclEntry(kind="section", id=key))
            elif key in teams:
                resolved.append(AclEntry(kind="team", id=key))
            elif key in agents:
                resolved.append(AclEntry(kind="agent", id=key))
            else:
                raise TopologyError(
                    ERROR_UNKNOWN_ID,
                    f"Unknown agent or section {key!r}.",
                )
            for entry in resolved:
                pair = (entry.kind, entry.id)
                if pair in seen:
                    continue
                seen.add(pair)
                entries.append(entry.as_dict())
        if not entries:
            raise TopologyError(ERROR_UNKNOWN_ID, "ACL entries resolved to nothing.")
        return entries

    def as_callables(self) -> list[Any]:
        def create_section(
            name: str,
            agent_ids: str = "",
            internal_only: bool = False,
        ) -> dict[str, Any]:
            """Create a persistent rail section. Optional agent_ids join it; internal_only locks talk to members."""
            return self.create_section(name, agent_ids=agent_ids, internal_only=internal_only)

        def rename_section(section_id: str, name: str) -> dict[str, Any]:
            """Rename an existing custom rail section."""
            return self.rename_section(section_id, name)

        def archive_section(section_id: str) -> dict[str, Any]:
            """Archive a section. Members return to Unassigned."""
            return self.archive_section(section_id)

        def move_agent_to_section(agent_id: str, section_id: str) -> dict[str, Any]:
            """Move a persistent agent onto a section (or unassigned)."""
            return self.move_agent_to_section(agent_id, section_id)

        def set_talk_acl(agent_id: str, allow: str = "", deny: str = "") -> dict[str, Any]:
            """Whitelist XOR blacklist who this agent may talk to (agent ids, section ids, or 'team')."""
            return self.set_talk_acl(agent_id, allow=allow, deny=deny)

        def list_sections() -> dict[str, Any]:
            """List active rail sections and their members."""
            return self.list_sections()

        create_section.name = CREATE_SECTION_TOOL
        create_section.description = (
            "Create a persistent rail section (not a temp sub-agent). "
            "name is required. agent_ids is a comma-separated list of existing "
            "agent ids to move in. internal_only=true locks talk to members "
            "(writes mailbox ACL whitelist of this section)."
        )
        rename_section.name = RENAME_SECTION_TOOL
        rename_section.description = "Rename an existing custom rail section."
        archive_section.name = ARCHIVE_SECTION_TOOL
        archive_section.description = (
            "Archive a custom rail section. Members return to Unassigned. "
            "Unassigned itself cannot be archived."
        )
        move_agent_to_section.name = MOVE_AGENT_TOOL
        move_agent_to_section.description = (
            "Move an existing persistent agent into a section. "
            "section_id=unassigned removes membership."
        )
        set_talk_acl.name = SET_TALK_ACL_TOOL
        set_talk_acl.description = (
            "Set this agent's peer-mailbox talk ACL. Pass allow= (whitelist) OR "
            "deny= (blacklist), never both. Entries are agent ids, section ids, "
            "or the token team (the agent's roster). Unknown ids fail honestly. "
            "CoS stays allow-all for itself."
        )
        list_sections.name = LIST_SECTIONS_TOOL
        list_sections.description = "List active rail sections and member agent ids."
        return [
            create_section,
            rename_section,
            archive_section,
            move_agent_to_section,
            set_talk_acl,
            list_sections,
        ]

    def as_function_tools(self) -> list[Any]:
        try:
            from agents import function_tool
        except Exception:
            logger.debug("agents SDK not available; topology as_function_tools() -> []")
            return []

        def create_section(
            name: str,
            agent_ids: str = "",
            internal_only: bool = False,
        ) -> dict[str, Any]:
            """Create a persistent rail section. Optional agent_ids join it; internal_only locks talk to members."""
            return self.create_section(name, agent_ids=agent_ids, internal_only=internal_only)

        def rename_section(section_id: str, name: str) -> dict[str, Any]:
            """Rename an existing custom rail section."""
            return self.rename_section(section_id, name)

        def archive_section(section_id: str) -> dict[str, Any]:
            """Archive a section. Members return to Unassigned."""
            return self.archive_section(section_id)

        def move_agent_to_section(agent_id: str, section_id: str) -> dict[str, Any]:
            """Move a persistent agent onto a section (or unassigned)."""
            return self.move_agent_to_section(agent_id, section_id)

        def set_talk_acl(agent_id: str, allow: str = "", deny: str = "") -> dict[str, Any]:
            """Whitelist XOR blacklist who this agent may talk to (agent ids, section ids, or 'team')."""
            return self.set_talk_acl(agent_id, allow=allow, deny=deny)

        def list_sections() -> dict[str, Any]:
            """List active rail sections and their members."""
            return self.list_sections()

        return [
            function_tool(create_section),
            function_tool(rename_section),
            function_tool(archive_section),
            function_tool(move_agent_to_section),
            function_tool(set_talk_acl),
            function_tool(list_sections),
        ]

    def as_swarm_tools(self) -> list[Any]:
        from swarm.types import Tool

        tools = []
        for fn in self.as_callables():
            tools.append(
                Tool(
                    name=getattr(fn, "name", fn.__name__),
                    func=fn,
                    description=getattr(fn, "description", "") or "",
                )
            )
        return tools

    def tool_objects(self) -> list[Any]:
        if not can_manage_topology(self.caller_role) or self.caller_kind != V1_KIND:
            return []
        return self.as_function_tools() or self.as_swarm_tools()

    def _audit(self, line: str) -> None:
        text = str(redact_sensitive_data(line) or line)
        if not self.user_key:
            logger.info("topology audit (no user_key) %s: %s", self.caller_id, text)
            return
        try:
            from swarm.core import chat_store

            record = chat_store.load(self.user_key, self.caller_id, base_dir=self.chat_base_dir)
            if record is None:
                record = chat_store.empty_record(user_key=self.user_key, agent_id=self.caller_id)
            turns = list(record.get("messages") or [])
            events = list(record.get("ui_events") or [])
            append_event(turns, events, "status", text, kind="status")
            chat_store.save(
                self.user_key,
                self.caller_id,
                turns,
                conversation_id=str(record.get("conversation_id") or ""),
                ui_events=events,
                base_dir=self.chat_base_dir,
            )
        except Exception:
            logger.debug("topology audit write failed", exc_info=True)


def _iter_agents(blueprint: Any) -> list[Any]:
    found: list[Any] = []
    for attr in ("_agents", "agents"):
        value = getattr(blueprint, attr, None)
        if isinstance(value, dict):
            found.extend(value.values())
        elif isinstance(value, list):
            found.extend(value)
    starting = getattr(blueprint, "starting_agent", None)
    if starting is not None:
        found.append(starting)
    return found


def _tool_names(current: Iterable[Any] | None) -> set[str]:
    names: set[str] = set()
    for item in current or []:
        name = getattr(item, "name", None) or getattr(item, "__name__", "") or ""
        if name:
            names.add(str(name))
    return names


def attach_to_agent(agent: Any, ctx: TopologyContext) -> list[str]:
    extras = ctx.tool_objects()
    if not extras:
        return []
    attached: list[str] = []
    for attr in ("tools", "functions"):
        current = getattr(agent, attr, None)
        if current is None:
            try:
                setattr(agent, attr, [])
                current = getattr(agent, attr)
            except Exception:
                continue
        if not isinstance(current, list):
            continue
        have = _tool_names(current)
        for tool in extras:
            name = str(getattr(tool, "name", None) or getattr(tool, "__name__", "") or "")
            if not name or name in have:
                continue
            current.append(tool)
            have.add(name)
            attached.append(name)
    return attached


def attach_topology_tools(blueprint: Any, ctx: TopologyContext) -> list[str]:
    attached: list[str] = []
    for agent in _iter_agents(blueprint):
        attached.extend(attach_to_agent(agent, ctx))
    return attached


def install_topology_on_blueprint(blueprint: Any, ctx: TopologyContext) -> list[str]:
    """Stamp context, wrap ``create_starting_agent``, attach to existing agents."""
    role = ctx.caller_role
    meta = getattr(blueprint, "metadata", None)
    if (not role or role == "default") and isinstance(meta, dict) and meta.get("role"):
        ctx.caller_role = normalize_agent_role(meta.get("role"))
    blueprint._topology_context = ctx
    if ctx.caller_kind != V1_KIND or not can_manage_topology(ctx.caller_role):
        return []

    original = getattr(blueprint, "create_starting_agent", None)
    if callable(original) and not getattr(blueprint, "_topology_wrapped", False):
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            agent = original(*args, **kwargs)
            attach_to_agent(agent, ctx)
            return agent

        blueprint.create_starting_agent = wrapped
        blueprint._topology_wrapped = True

    return attach_topology_tools(blueprint, ctx)


def context_from_runtime(
    *,
    caller_id: str,
    user: Any = None,
    params: dict[str, Any] | None = None,
    blueprint: Any = None,
    stores: TopologyStores | None = None,
    chat_base_dir: Path | None = None,
) -> TopologyContext:
    params = params if isinstance(params, dict) else {}
    explicit_kind = params.get("kind") or params.get("agent_type")
    if isinstance(explicit_kind, str):
        explicit_kind = explicit_kind.strip().lower()
    else:
        explicit_kind = None
    kind = classify_agent_kind(
        caller_id,
        explicit=explicit_kind if explicit_kind in ("api", "cli", "remote", "blueprint") else None,
    )
    role = role_of_member(caller_id, None, fallback=params.get("role"))
    meta = getattr(blueprint, "metadata", None) if blueprint is not None else None
    if (not role or role == "default") and isinstance(meta, dict) and meta.get("role"):
        role = normalize_agent_role(meta.get("role"))

    user_key = ""
    if user is not None and getattr(user, "is_authenticated", False):
        try:
            from swarm.core import chat_store

            user_key = chat_store.user_key_for(user)
        except Exception:
            logger.debug("topology user_key unavailable", exc_info=True)

    return TopologyContext(
        caller_id=str(caller_id or "").strip(),
        caller_kind=kind,
        caller_role=normalize_agent_role(role),
        user_key=user_key,
        chat_base_dir=chat_base_dir,
        stores=stores or default_stores(),
    )


def install_topology_for_runtime(
    blueprint: Any,
    *,
    caller_id: str,
    user: Any = None,
    params: dict[str, Any] | None = None,
) -> TopologyContext:
    """Attach section/topology tools when the caller is API-kind CoS.

    Goes through ``ChiefOfStaffRole.attach_as_tool`` so the role owns the
    tool-attach surface (Issue #206 Phase 3) instead of blueprint ad-hoc wiring.
    """
    ctx = context_from_runtime(
        caller_id=caller_id,
        user=user,
        params=params,
        blueprint=blueprint,
    )
    from swarm.core.roles.registry import get_role

    role = get_role("chief_of_staff")
    if role is not None and hasattr(role, "attach_as_tool"):
        role.attach_as_tool(blueprint, ctx)
    else:
        install_topology_on_blueprint(blueprint, ctx)
    return ctx


__all__ = [
    "ARCHIVE_SECTION_TOOL",
    "CREATE_SECTION_TOOL",
    "ERROR_ALREADY_ARCHIVED",
    "ERROR_CALLER_KIND",
    "ERROR_EMPTY",
    "ERROR_NO_TEAM",
    "ERROR_PROTECTED",
    "ERROR_ROLE",
    "ERROR_SECRET",
    "ERROR_UNKNOWN_ID",
    "ERROR_UNKNOWN_SECTION",
    "ERROR_XOR",
    "LIST_SECTIONS_TOOL",
    "MOVE_AGENT_TOOL",
    "RENAME_SECTION_TOOL",
    "SET_TALK_ACL_TOOL",
    "TopologyContext",
    "TopologyError",
    "TopologyStores",
    "attach_to_agent",
    "attach_topology_tools",
    "context_from_runtime",
    "default_stores",
    "install_topology_for_runtime",
    "install_topology_on_blueprint",
]

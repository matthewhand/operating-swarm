"""Peer mailbox tools — ``list_agents`` + ``send_message`` (REQ-153 / #561).

v1 is **API↔API** and **not a global mesh**. Discoverability is:

    (same-team members ∪ relationship-edge members ∪ Support/CoS allow-all)
    ∩ same kind
    ∩ (whitelist / ¬blacklist)
    − hidden − archived − self

Handoff / ``as_tool`` graphs stay on openai-agents (REQ-156). This mailbox is
the rail-peer channel: an API agent can ask another API agent to do work
without the human copy-pasting between chats.

Eligible callers (v1): harness kind ``api`` (including Support). CLI / remote
/ herdr are out of scope until a later REQ.

Delivered payloads land on the **target** agent's chat JSON transcript
(``chat_store``) as a real user turn with ``name`` = sender id, plus hop
chrome ``Message from {sender}``. Writes are scoped to the caller's
``user_key`` (no cross-tenant). Secrets are redacted in logs — never persist
or log raw key-shaped payloads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Literal

from swarm.core.agent_kind import AgentKind, classify_agent_kind
from swarm.core.agent_relationships import RelationshipEdge, iter_edges
from swarm.core.agent_roles import (
    ROLE_CHIEF_OF_STAFF,
    ROLE_SUPPORT,
    is_chief_of_staff,
    normalize_agent_role,
)
from swarm.core.team_isolation import role_of_member, teams_containing
from swarm.core.team_rosters import iter_normalized_rosters
from swarm.core.transcript_roles import append_event, append_turn
from swarm.tool_executor import redact_sensitive_data

logger = logging.getLogger(__name__)

V1_KIND: AgentKind = "api"
LIST_TOOL_NAME = "list_agents"
SEND_TOOL_NAME = "send_message"

ERROR_UNKNOWN_ID = "unknown_id"
ERROR_KIND_MISMATCH = "kind_mismatch"
ERROR_TARGET_HIDDEN = "target_hidden"
ERROR_TARGET_ARCHIVED = "target_archived"
ERROR_NOT_DISCOVERABLE = "not_discoverable"
ERROR_CALLER_KIND = "caller_kind_unsupported"
ERROR_EMPTY_CONTENT = "empty_content"
ERROR_KIND_FILTER = "kind_not_supported"

AclMode = Literal["whitelist", "blacklist"]
AclEntryKind = Literal["agent", "team", "role"]


class PeerMailboxError(Exception):
    """Tool-safe mailbox failure with a stable reason code."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": self.reason, "message": self.message}


@dataclass(frozen=True)
class AclEntry:
    """One allow/deny entry. Kinds: agent, team, role (REQ-162 model)."""

    kind: AclEntryKind
    id: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id}

    @classmethod
    def from_raw(cls, raw: Any) -> "AclEntry | None":
        if isinstance(raw, str) and raw.strip():
            return cls(kind="agent", id=raw.strip())
        if not isinstance(raw, dict):
            return None
        kind = str(raw.get("kind") or "agent").strip().lower()
        if kind not in ("agent", "team", "role"):
            return None
        ident = str(raw.get("id") or raw.get("name") or "").strip()
        if not ident:
            return None
        if kind == "role":
            ident = normalize_agent_role(ident)
        return cls(kind=kind, id=ident)  # type: ignore[arg-type]


@dataclass(frozen=True)
class AclPolicy:
    """Per-agent (or per-role) whitelist XOR blacklist.

    Empty blacklist = no extra cut. Empty whitelist = nobody, except
    ``allow_all`` (Support / CoS default whitelist-everything).
    """

    mode: AclMode = "blacklist"
    entries: tuple[AclEntry, ...] = ()
    allow_all: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "allow_all": self.allow_all,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    @classmethod
    def from_raw(cls, raw: Any) -> "AclPolicy":
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            return cls()
        mode = str(raw.get("mode") or "blacklist").strip().lower()
        if mode not in ("whitelist", "blacklist"):
            mode = "blacklist"
        entries = tuple(
            entry
            for entry in (AclEntry.from_raw(item) for item in (raw.get("entries") or []))
            if entry is not None
        )
        allow_all = raw.get("allow_all") is True
        if mode == "whitelist" and not entries and allow_all:
            return cls(mode="whitelist", entries=(), allow_all=True)
        return cls(mode=mode, entries=entries, allow_all=False)  # type: ignore[arg-type]


@dataclass
class Peer:
    """One catalogued rail / roster seat."""

    id: str
    kind: AgentKind
    role: str = "default"
    teams: set[str] = field(default_factory=set)
    archived: bool = False
    source: str = ""


def _peer_from_member(member: dict[str, Any], team_id: str) -> Peer | None:
    if member.get("kind") == "team":
        return None
    mid = str(member.get("id") or "").strip()
    if not mid:
        return None
    explicit = str(member.get("kind") or "").strip().lower()
    if explicit == "herdr":
        kind = "remote"
    else:
        kind = classify_agent_kind(
            member.get("source") or mid,
            explicit=explicit if explicit in ("api", "cli", "remote", "blueprint") else None,
        )
    archived = member.get("archived") is True
    return Peer(
        id=mid,
        kind=kind,
        role=normalize_agent_role(member.get("role")),
        teams={team_id} if team_id else set(),
        archived=archived,
        source=str(member.get("source") or ""),
    )


def catalog_from_rosters(
    rosters: dict[str, Any] | None = None,
    extra: Iterable[Peer] | None = None,
) -> dict[str, Peer]:
    """Flatten roster people (not nested team slots) into a peer catalog."""
    catalog: dict[str, Peer] = {}
    for rid, roster in iter_normalized_rosters(rosters).items():
        for member in roster.get("members") or []:
            peer = _peer_from_member(member, rid)
            if peer is None:
                continue
            existing = catalog.get(peer.id)
            if existing is None:
                catalog[peer.id] = peer
                continue
            existing.teams.update(peer.teams)
            if is_chief_of_staff(peer.role) or normalize_agent_role(peer.role) == ROLE_SUPPORT:
                existing.role = peer.role
            existing.archived = existing.archived or peer.archived
    for peer in extra or []:
        existing = catalog.get(peer.id)
        if existing is None:
            catalog[peer.id] = Peer(
                id=peer.id,
                kind=peer.kind,
                role=peer.role,
                teams=set(peer.teams),
                archived=peer.archived,
                source=peer.source,
            )
            continue
        existing.teams.update(peer.teams)
        if is_chief_of_staff(peer.role) or normalize_agent_role(peer.role) == ROLE_SUPPORT:
            existing.role = peer.role
        existing.archived = existing.archived or peer.archived
    return catalog


def _side_agent_ids(kind: str, ident: str, catalog: dict[str, Peer]) -> set[str]:
    if kind == "agent":
        return {ident} if ident in catalog else set()
    if kind == "team":
        return {peer.id for peer in catalog.values() if ident in peer.teams}
    return set()


def related_peer_ids(
    caller_id: str,
    catalog: dict[str, Peer],
    edges: Iterable[RelationshipEdge],
) -> set[str]:
    """Peer ids mutually reachable via relationship edges."""
    found: set[str] = set()
    for edge in edges:
        left = _side_agent_ids(edge.from_kind, edge.from_id, catalog)
        right = _side_agent_ids(edge.to_kind, edge.to_id, catalog)
        if caller_id in left:
            found |= right
        if caller_id in right:
            found |= left
    found.discard(caller_id)
    return found


def _entry_matches(entry: AclEntry, peer: Peer) -> bool:
    if entry.kind == "agent":
        return peer.id == entry.id
    if entry.kind == "role":
        return normalize_agent_role(peer.role) == normalize_agent_role(entry.id)
    if entry.kind == "team":
        return entry.id in peer.teams
    return False


def apply_acl(ids: set[str], catalog: dict[str, Peer], policy: AclPolicy | None) -> set[str]:
    """REQ-162: whitelist ∩ / blacklist −.

    Empty blacklist is a no-op. Empty whitelist denies everyone unless
    ``allow_all`` (Support / CoS default).
    """
    if policy is None:
        return ids
    if policy.mode == "whitelist":
        if not policy.entries:
            return ids if policy.allow_all else set()
        return {
            ident
            for ident in ids
            if ident in catalog
            and any(_entry_matches(entry, catalog[ident]) for entry in policy.entries)
        }
    if not policy.entries:
        return ids
    matched = {
        ident
        for ident in ids
        if ident in catalog and any(_entry_matches(entry, catalog[ident]) for entry in policy.entries)
    }
    return ids - matched


def _is_allow_all_role(role: Any) -> bool:
    canonical = normalize_agent_role(role)
    return canonical == ROLE_SUPPORT or canonical == ROLE_CHIEF_OF_STAFF or is_chief_of_staff(role)


def _safe_log_payload(content: str) -> str:
    redacted = redact_sensitive_data(content)
    text = str(redacted if redacted is not None else "")
    if len(text) > 80:
        return text[:80] + "…"
    return text


@dataclass
class MailboxContext:
    """Bound caller + graph + tenant store for one tool session."""

    caller_id: str
    caller_kind: AgentKind = V1_KIND
    caller_role: str = "default"
    user_key: str = ""
    hidden_ids: frozenset[str] = field(default_factory=frozenset)
    archived_ids: frozenset[str] = field(default_factory=frozenset)
    rosters: dict[str, Any] | None = None
    extra_peers: tuple[Peer, ...] = ()
    relationships: Any | None = None
    acl: AclPolicy | None = None
    chat_base_dir: Path | None = None

    def catalog(self) -> dict[str, Peer]:
        extra = list(self.extra_peers)
        if self.caller_id and self.caller_id not in {p.id for p in extra}:
            extra.append(
                Peer(
                    id=self.caller_id,
                    kind=self.caller_kind,
                    role=normalize_agent_role(self.caller_role),
                    teams=teams_containing(self.caller_id, self.rosters),
                )
            )
        return catalog_from_rosters(self.rosters, extra=extra)

    def caller(self) -> Peer:
        catalog = self.catalog()
        existing = catalog.get(self.caller_id)
        if existing is not None:
            if self.caller_role and self.caller_role != "default":
                existing.role = normalize_agent_role(self.caller_role)
            if self.caller_kind:
                existing.kind = self.caller_kind
            return existing
        return Peer(
            id=self.caller_id,
            kind=self.caller_kind,
            role=normalize_agent_role(self.caller_role),
            teams=teams_containing(self.caller_id, self.rosters),
        )

    def _is_hidden(self, peer_id: str) -> bool:
        return peer_id in self.hidden_ids

    def _is_archived(self, peer: Peer) -> bool:
        return peer.archived or peer.id in self.archived_ids

    def discoverable_ids(self, *, kind: str = V1_KIND) -> set[str]:
        """Ids ``list_agents`` may return (same-kind, graph, ACL, not hidden/archived)."""
        if self.caller_kind != V1_KIND:
            return set()
        if kind != V1_KIND:
            return set()
        catalog = self.catalog()
        caller = self.caller()
        same_kind = {
            peer.id
            for peer in catalog.values()
            if peer.kind == V1_KIND and peer.id != caller.id
        }
        if _is_allow_all_role(caller.role):
            base = set(same_kind)
        else:
            team_mates = {
                peer.id
                for peer in catalog.values()
                if peer.id != caller.id
                and peer.kind == V1_KIND
                and (caller.teams & peer.teams)
            }
            related = {
                ident
                for ident in related_peer_ids(caller.id, catalog, iter_edges(self.relationships))
                if ident in catalog and catalog[ident].kind == V1_KIND
            }
            base = team_mates | related
        visible: set[str] = set()
        for ident in base:
            peer = catalog.get(ident)
            if peer is None:
                continue
            if self._is_hidden(ident) or self._is_archived(peer):
                continue
            visible.add(ident)
        return apply_acl(visible, catalog, self.acl)

    def list_peers(self, kind: str = V1_KIND) -> dict[str, Any]:
        want = str(kind or V1_KIND).strip().lower() or V1_KIND
        if self.caller_kind != V1_KIND:
            return PeerMailboxError(
                ERROR_CALLER_KIND,
                "Peer mailbox v1 is API↔API only. CLI/remote tools ship later.",
            ).as_dict()
        if want != V1_KIND:
            return PeerMailboxError(
                ERROR_KIND_FILTER,
                f"v1 list_agents only supports kind={V1_KIND!r} (got {want!r}).",
            ).as_dict()
        catalog = self.catalog()
        agents = []
        for ident in sorted(self.discoverable_ids(kind=want)):
            peer = catalog[ident]
            agents.append(
                {
                    "id": peer.id,
                    "kind": peer.kind,
                    "role": peer.role,
                    "teams": sorted(peer.teams),
                }
            )
        return {
            "ok": True,
            "kind": want,
            "agents": agents,
            "scope": "support_allow_all" if _is_allow_all_role(self.caller().role) else "team+relationships",
        }

    def _reject_send(self, target_id: str) -> None:
        if self.caller_kind != V1_KIND:
            raise PeerMailboxError(
                ERROR_CALLER_KIND,
                "Peer mailbox v1 is API↔API only. CLI/remote tools ship later.",
            )
        catalog = self.catalog()
        peer = catalog.get(target_id)
        if peer is None:
            raise PeerMailboxError(ERROR_UNKNOWN_ID, f"Unknown agent id {target_id!r}.")
        if self._is_archived(peer):
            raise PeerMailboxError(ERROR_TARGET_ARCHIVED, f"Agent {target_id!r} is archived.")
        if self._is_hidden(target_id):
            raise PeerMailboxError(ERROR_TARGET_HIDDEN, f"Agent {target_id!r} is hidden.")
        if peer.kind != V1_KIND or self.caller_kind != V1_KIND:
            raise PeerMailboxError(
                ERROR_KIND_MISMATCH,
                f"v1 send_message is same-kind API→API (target kind={peer.kind!r}).",
            )
        if target_id == self.caller_id:
            return
        if target_id not in self.discoverable_ids(kind=V1_KIND):
            raise PeerMailboxError(
                ERROR_NOT_DISCOVERABLE,
                f"Agent {target_id!r} is outside this caller's team/relationship graph or ACL.",
            )

    def send(self, agent_id: str, content: str) -> dict[str, Any]:
        target = str(agent_id or "").strip()
        body = content if isinstance(content, str) else str(content or "")
        if not target:
            err = PeerMailboxError(ERROR_UNKNOWN_ID, "Target agent id is required.")
            logger.info("mailbox send rejected: %s", err.reason)
            return err.as_dict()
        if not body.strip():
            err = PeerMailboxError(ERROR_EMPTY_CONTENT, "Message content is required.")
            logger.info("mailbox send rejected: %s", err.reason)
            return err.as_dict()
        try:
            self._reject_send(target)
        except PeerMailboxError as exc:
            logger.info(
                "mailbox send rejected %s -> %s (%s)",
                self.caller_id,
                target,
                exc.reason,
            )
            return exc.as_dict()

        delivered = self._deliver(target, body)
        logger.info(
            "mailbox send %s -> %s delivered=%s payload=%s",
            self.caller_id,
            target,
            delivered,
            _safe_log_payload(body),
        )
        result = {
            "ok": True,
            "target_id": target,
            "delivered": delivered,
            "sender_id": self.caller_id,
            "sender_hop": f"Messaged {target}",
        }
        if not delivered:
            result["warning"] = "delivery_skipped_no_user_key"
        return result

    def _deliver(self, target_id: str, content: str) -> bool:
        from swarm.core import chat_store

        if not self.user_key:
            logger.info("mailbox deliver skipped (no user_key) %s -> %s", self.caller_id, target_id)
            return False
        user_key = self.user_key
        base = self.chat_base_dir
        record = chat_store.load(user_key, target_id, base_dir=base)
        if record is None:
            record = chat_store.empty_record(user_key=user_key, agent_id=target_id)
        turns = list(record.get("messages") or [])
        events = list(record.get("ui_events") or [])
        stored = redact_sensitive_data(content)
        if not isinstance(stored, str):
            stored = str(stored)
        append_turn(
            turns,
            events,
            "user",
            stored,
            name=self.caller_id,
        )
        append_event(
            turns,
            events,
            "status",
            f"Message from {self.caller_id}",
            kind="hop",
        )
        path = chat_store.save(
            user_key,
            target_id,
            turns,
            conversation_id=str(record.get("conversation_id") or ""),
            ui_events=events,
            base_dir=base,
        )
        return path is not None

    def list_agents_tool(self, kind: str = V1_KIND) -> dict[str, Any]:
        return self.list_peers(kind=kind)

    def send_message_tool(self, agent_id: str, content: str) -> dict[str, Any]:
        return self.send(agent_id, content)

    def as_callables(self) -> list[Any]:
        """Plain callables with ``name`` / ``description`` (SDK-optional)."""

        def list_agents(kind: str = V1_KIND) -> dict[str, Any]:
            """List peer agents this caller may message (same kind, team-scoped)."""
            return self.list_peers(kind=kind)

        def send_message(agent_id: str, content: str) -> dict[str, Any]:
            """Send a message to a peer agent's chat transcript."""
            return self.send(agent_id, content)

        list_agents.name = LIST_TOOL_NAME
        list_agents.description = (
            "List peer agents you may message. v1: same kind (api), team members "
            "plus relationship edges. Support/CoS see all same-kind peers."
        )
        send_message.name = SEND_TOOL_NAME
        send_message.description = (
            "Send a message to another agent's chat transcript. v1: API→API only. "
            "Fails on unknown, hidden, archived, or cross-kind / out-of-graph ids."
        )
        return [list_agents, send_message]

    def as_function_tools(self) -> list[Any]:
        """openai-agents ``function_tool`` wrappers, or ``[]`` if the SDK is missing."""
        try:
            from agents import function_tool
        except Exception:
            logger.debug("agents SDK not available; mailbox as_function_tools() -> []")
            return []

        def list_agents(kind: str = V1_KIND) -> dict[str, Any]:
            """List peer agents this caller may message (same kind, team-scoped)."""
            return self.list_peers(kind=kind)

        def send_message(agent_id: str, content: str) -> dict[str, Any]:
            """Send a message to a peer agent's chat transcript."""
            return self.send(agent_id, content)

        return [function_tool(list_agents), function_tool(send_message)]

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
        return self.as_function_tools() or self.as_swarm_tools()


def _iter_agents(blueprint: Any) -> list[Any]:
    agents: list[Any] = []
    raw = getattr(blueprint, "agents", None)
    if isinstance(raw, dict):
        agents.extend(raw.values())
    elif isinstance(raw, list):
        agents.extend(raw)
    starting = getattr(blueprint, "starting_agent", None)
    if starting is not None and not callable(starting) and starting not in agents:
        agents.append(starting)
    return agents


def _tool_names(current: Iterable[Any] | None) -> set[str]:
    names: set[str] = set()
    for fn in current or []:
        name = getattr(fn, "name", None) or getattr(fn, "__name__", None)
        if name:
            names.add(str(name))
    return names


def attach_to_agent(agent: Any, ctx: MailboxContext) -> list[str]:
    """Append mailbox tools onto one Agent-like object."""
    if ctx.caller_kind != V1_KIND:
        return []
    extras = ctx.tool_objects()
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


def attach_mailbox_tools(blueprint: Any, ctx: MailboxContext) -> list[str]:
    """Attach ``list_agents`` / ``send_message`` to existing blueprint agents."""
    attached: list[str] = []
    for agent in _iter_agents(blueprint):
        attached.extend(attach_to_agent(agent, ctx))
    return attached


def install_mailbox_on_blueprint(blueprint: Any, ctx: MailboxContext) -> list[str]:
    """Stamp context, wrap ``create_starting_agent``, attach to existing agents.

    ``BlueprintBase.make_agent`` also reads ``_mailbox_context`` so later factory
    calls pick up the same tools.
    """
    role = ctx.caller_role
    meta = getattr(blueprint, "metadata", None)
    if (not role or role == "default") and isinstance(meta, dict) and meta.get("role"):
        ctx = replace(ctx, caller_role=normalize_agent_role(meta.get("role")))
    blueprint._mailbox_context = ctx
    if ctx.caller_kind != V1_KIND:
        return []

    original = getattr(blueprint, "create_starting_agent", None)
    if callable(original) and not getattr(blueprint, "_mailbox_wrapped", False):
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            agent = original(*args, **kwargs)
            attach_to_agent(agent, ctx)
            return agent

        blueprint.create_starting_agent = wrapped
        blueprint._mailbox_wrapped = True

    return attach_mailbox_tools(blueprint, ctx)


def hidden_ids_for_user(user: Any) -> frozenset[str]:
    """Hidden Bots list for a Django user. Empty when prefs/DB are unavailable."""
    if user is None or not getattr(user, "is_authenticated", False):
        return frozenset()
    try:
        from swarm.core.user_preferences import HIDDEN_KEY, coerce_values
        from swarm.models.preferences import UserPreference

        row = UserPreference.objects.filter(user=user).first()
        if row is None:
            return frozenset()
        values = coerce_values(row.values)
        return frozenset(str(item) for item in (values.get(HIDDEN_KEY) or []) if item)
    except Exception:
        logger.debug("mailbox hidden_ids_for_user unavailable", exc_info=True)
        return frozenset()


def context_from_runtime(
    *,
    caller_id: str,
    user: Any = None,
    params: dict[str, Any] | None = None,
    blueprint: Any = None,
    rosters: dict[str, Any] | None = None,
    relationships: Any | None = None,
    chat_base_dir: Path | None = None,
) -> MailboxContext:
    """Build a mailbox context from a chat/completions turn."""
    params = params if isinstance(params, dict) else {}
    explicit_kind = params.get("kind") or params.get("agent_type")
    if isinstance(explicit_kind, str):
        explicit_kind = explicit_kind.strip().lower()
    else:
        explicit_kind = None
    kind = classify_agent_kind(caller_id, explicit=explicit_kind if explicit_kind in ("api", "cli", "remote", "blueprint") else None)
    role = role_of_member(caller_id, rosters, fallback=params.get("role"))
    meta = getattr(blueprint, "metadata", None) if blueprint is not None else None
    if (not role or role == "default") and isinstance(meta, dict) and meta.get("role"):
        role = normalize_agent_role(meta.get("role"))

    user_key = ""
    if user is not None and getattr(user, "is_authenticated", False):
        try:
            from swarm.core import chat_store

            user_key = chat_store.user_key_for(user)
        except Exception:
            logger.debug("mailbox user_key unavailable", exc_info=True)

    hidden = set(hidden_ids_for_user(user))
    raw_hidden = params.get("hidden_agents") or params.get("hidden_ids")
    if isinstance(raw_hidden, list):
        hidden.update(str(item).strip() for item in raw_hidden if str(item).strip())
    raw_archived = params.get("archived_agents") or params.get("archived_ids")
    archived = set()
    if isinstance(raw_archived, list):
        archived.update(str(item).strip() for item in raw_archived if str(item).strip())
    try:
        from swarm.core.agent_lifecycle import catalog_archived_ids

        archived.update(catalog_archived_ids())
    except Exception:
        logger.debug("mailbox catalog archived_ids unavailable", exc_info=True)

    if "mailbox_acl" in params or "acl" in params:
        acl = AclPolicy.from_raw(params.get("mailbox_acl") or params.get("acl"))
    else:
        from swarm.core.agent_mailbox_acl import resolve_acl_policy

        acl = resolve_acl_policy(str(caller_id or "").strip(), role).policy
    return MailboxContext(
        caller_id=str(caller_id or "").strip(),
        caller_kind=kind,
        caller_role=normalize_agent_role(role),
        user_key=user_key,
        hidden_ids=frozenset(hidden),
        archived_ids=frozenset(archived),
        rosters=rosters,
        relationships=relationships,
        acl=acl,
        chat_base_dir=chat_base_dir,
    )


def install_mailbox_for_runtime(
    blueprint: Any,
    *,
    caller_id: str,
    user: Any = None,
    params: dict[str, Any] | None = None,
) -> MailboxContext:
    """Attach mailbox tools for an API-kind chat/completions run."""
    ctx = context_from_runtime(
        caller_id=caller_id,
        user=user,
        params=params,
        blueprint=blueprint,
    )
    install_mailbox_on_blueprint(blueprint, ctx)
    return ctx


__all__ = [
    "ERROR_CALLER_KIND",
    "ERROR_EMPTY_CONTENT",
    "ERROR_KIND_FILTER",
    "ERROR_KIND_MISMATCH",
    "ERROR_NOT_DISCOVERABLE",
    "ERROR_TARGET_ARCHIVED",
    "ERROR_TARGET_HIDDEN",
    "ERROR_UNKNOWN_ID",
    "LIST_TOOL_NAME",
    "SEND_TOOL_NAME",
    "V1_KIND",
    "AclEntry",
    "AclPolicy",
    "MailboxContext",
    "Peer",
    "PeerMailboxError",
    "apply_acl",
    "attach_mailbox_tools",
    "attach_to_agent",
    "catalog_from_rosters",
    "context_from_runtime",
    "hidden_ids_for_user",
    "install_mailbox_for_runtime",
    "install_mailbox_on_blueprint",
    "related_peer_ids",
]

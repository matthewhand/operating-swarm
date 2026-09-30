"""Peer mailbox tools — ``list_agents`` + ``send_message`` (REQ-153 / #561).

v1 is **API↔API** and **not a global mesh**. Discoverability is:

    (same-team members ∪ relationship-edge members ∪ Support/CoS allow-all)
    ∩ same kind
    ∩ (whitelist / ¬blacklist)
    ∩ (internal-only rail section members, Issue #163)
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

#1255: ``send_message`` also accepts ``agent_id="all"`` / ``broadcast=true`` to
fan out to every discoverable API peer. A target with a **live turn** cannot
take an interleaved turn, so inbound messages are queued FIFO in
``agent_turn_queue`` and flushed into its transcript (attributed) when the turn
ends — see ``install_mailbox_on_blueprint``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Literal

from swarm.core import agent_turn_queue
from swarm.core.agent_kind import AgentKind, classify_agent_kind
from swarm.core.agent_relationships import RelationshipEdge, iter_edges
from swarm.core.agent_roles import (
    ROLE_CHIEF_OF_STAFF,
    ROLE_SUPPORT,
    is_chief_of_staff,
    normalize_agent_role,
)
from swarm.core.agent_turn_queue import QueuedMessage
from swarm.core.section_talk import (
    REASON_INTERNAL_ONLY,
    REASON_TARGET_LOCKED,
    SectionTalkState,
    can_section_talk,
    filter_talk_targets,
    parse_section_talk_state,
)
from swarm.core.team_isolation import role_of_member, teams_containing
from swarm.core.team_rosters import iter_normalized_rosters
from swarm.core.transcript_roles import append_event, append_turn
from swarm.tool_executor import redact_sensitive_data

logger = logging.getLogger(__name__)

V1_KIND: AgentKind = "api"
LIST_TOOL_NAME = "list_agents"
SEND_TOOL_NAME = "send_message"

#: ``agent_id`` values that fan a message out to every discoverable peer.
BROADCAST_IDS = frozenset({"all", "*", "broadcast", "everyone"})

ERROR_UNKNOWN_ID = "unknown_id"
ERROR_KIND_MISMATCH = "kind_mismatch"
ERROR_TARGET_HIDDEN = "target_hidden"
ERROR_TARGET_ARCHIVED = "target_archived"
ERROR_NOT_DISCOVERABLE = "not_discoverable"
ERROR_CALLER_KIND = "caller_kind_unsupported"
ERROR_EMPTY_CONTENT = "empty_content"
ERROR_KIND_FILTER = "kind_not_supported"
ERROR_SECTION_LOCKED = "section_internal_only"

AclMode = Literal["whitelist", "blacklist"]
AclEntryKind = Literal["agent", "team", "role", "section"]


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
    """One allow/deny entry. Kinds: agent, team, role, section (REQ-162 / #219)."""

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
        if kind not in ("agent", "team", "role", "section"):
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
    sections: set[str] = field(default_factory=set)
    archived: bool = False
    source: str = ""
    name: str = ""
    description: str = ""

    def display_name(self) -> str:
        return self.name or self.id


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
        name=str(member.get("name") or "").strip(),
        description=str(member.get("description") or "").strip(),
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
            # #739/#979: CoS authority is roster-level (``chief_of_staff_id``);
            # the member stamp is demoted on write. Resolve the canonical role
            # so the catalog carries the same authority ``role_of_member``
            # promises (roster-level designation + legacy-tag recovery).
            peer.role = role_of_member(peer.id, rosters)
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
                sections=set(peer.sections),
                archived=peer.archived,
                source=peer.source,
                name=peer.name,
                description=peer.description,
            )
            continue
        existing.teams.update(peer.teams)
        existing.sections.update(peer.sections)
        if peer.name and not existing.name:
            existing.name = peer.name
        if peer.description and not existing.description:
            existing.description = peer.description
        if is_chief_of_staff(peer.role) or normalize_agent_role(peer.role) == ROLE_SUPPORT:
            existing.role = peer.role
        existing.archived = existing.archived or peer.archived
    return catalog


def _side_agent_ids(kind: str, ident: str, catalog: dict[str, Peer]) -> set[str]:
    if kind == "agent":
        return {ident} if ident in catalog else set()
    if kind == "team":
        return {peer.id for peer in catalog.values() if ident in peer.teams}
    if kind == "section":
        return {peer.id for peer in catalog.values() if ident in peer.sections}
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
    if entry.kind == "section":
        if entry.id in peer.sections:
            return True
        try:
            from swarm.core.agent_sections import section_id_for_agent

            return section_id_for_agent(peer.id) == entry.id
        except Exception:
            return False
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


def deliver_to_transcript(
    *,
    user_key: str,
    chat_base_dir: Path | str | None,
    sender_id: str,
    target_id: str,
    content: str,
) -> bool:
    """Append one attributed inbound turn to the target's chat transcript."""
    from swarm.core import chat_store

    if not user_key:
        logger.info("mailbox deliver skipped (no user_key) %s -> %s", sender_id, target_id)
        return False
    base = Path(chat_base_dir) if chat_base_dir else None
    record = chat_store.load_or_django(user_key, target_id, base_dir=base)
    if record is None:
        record = chat_store.empty_record(user_key=user_key, agent_id=target_id)
    turns = list(record.get("messages") or [])
    events = list(record.get("ui_events") or [])
    stored = redact_sensitive_data(content)
    if not isinstance(stored, str):
        stored = str(stored)
    append_turn(turns, events, "user", stored, name=sender_id)
    append_event(turns, events, "status", f"Message from {sender_id}", kind="hop")
    path = chat_store.save(
        user_key,
        target_id,
        turns,
        conversation_id=str(record.get("conversation_id") or ""),
        ui_events=events,
        base_dir=base,
    )
    return path is not None


def flush_pending_for(agent_id: str) -> list[dict[str, Any]]:
    """Drain an agent's queued inbound messages into its transcript (FIFO).

    Called when a target's live turn ends so queued peer messages are processed
    in arrival order, each attributed to its sender. Never raises.
    """
    from swarm.core.agent_turn_queue import drain

    results: list[dict[str, Any]] = []
    for item in drain(agent_id):
        try:
            delivered = deliver_to_transcript(
                user_key=item.user_key,
                chat_base_dir=item.chat_base_dir,
                sender_id=item.sender_id,
                target_id=agent_id,
                content=item.content,
            )
        except Exception:
            logger.exception("mailbox flush failed %s -> %s", item.sender_id, agent_id)
            delivered = False
        results.append(
            {
                "target_id": agent_id,
                "sender_id": item.sender_id,
                "delivered": delivered,
            }
        )
    return results


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
    section_talk: SectionTalkState | None = None

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
        catalog = catalog_from_rosters(self.rosters, extra=extra)
        try:
            from swarm.core.agent_sections import membership_map

            members = membership_map()
        except Exception:
            members = {}
        for peer in catalog.values():
            sid = members.get(peer.id)
            if sid:
                peer.sections.add(sid)
        return catalog

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

    def resolve_rig_target(self, agent_id: str) -> tuple[str, PeerMailboxError | None]:
        """Resolve a ``role@rig`` address to one peer id (#1224).

        Bare ids pass through unchanged. A qualified address resolves against
        the section (dynamic rig) / roster (static rig) topology; an unknown
        rig or role is an honest error, never a silent fallback to a sibling
        seat.
        """
        raw = str(agent_id or "").strip()
        if "@" not in raw:
            return raw, None
        from swarm.core import agent_sections
        from swarm.core.rig_addresses import build_rig_catalog, resolve_rig_address

        try:
            sections = agent_sections.load_sections()
        except Exception:
            sections = None
        catalog = build_rig_catalog(
            self.catalog().values(),
            rosters=self.rosters,
            sections=sections,
        )
        resolved = resolve_rig_address(raw, catalog=catalog)
        if not resolved.ok:
            return raw, PeerMailboxError(
                resolved.error or ERROR_UNKNOWN_ID, resolved.message
            )
        return resolved.agent_id, None

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
        visible = apply_acl(visible, catalog, self.acl)
        return filter_talk_targets(self.caller_id, visible, self.section_talk)

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
                    "name": peer.display_name(),
                    "kind": peer.kind,
                    "role": peer.role,
                    "specialty": peer.role,
                    "description": peer.description,
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
        decision = can_section_talk(self.caller_id, target_id, self.section_talk)
        if not decision.allowed and decision.reason in (
            REASON_INTERNAL_ONLY,
            REASON_TARGET_LOCKED,
        ):
            raise PeerMailboxError(
                ERROR_SECTION_LOCKED,
                f"Agent {target_id!r} is outside this caller's internal-only section.",
            )
        if target_id not in self.discoverable_ids(kind=V1_KIND):
            raise PeerMailboxError(
                ERROR_NOT_DISCOVERABLE,
                f"Agent {target_id!r} is outside this caller's team/relationship graph or ACL.",
            )

    def send(self, agent_id: str, content: str) -> dict[str, Any]:
        """Unicast. Queues (FIFO) when the target has a live turn (#1255)."""
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
        target, resolve_error = self.resolve_rig_target(target)
        if resolve_error is not None:
            logger.info(
                "mailbox send rejected %s -> %s (%s)",
                self.caller_id,
                target,
                resolve_error.reason,
            )
            return resolve_error.as_dict()
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

        queued = False
        if target != self.caller_id and agent_turn_queue.is_agent_busy(target):
            depth = agent_turn_queue.enqueue(
                target,
                QueuedMessage(
                    sender_id=self.caller_id,
                    content=body,
                    user_key=self.user_key,
                    chat_base_dir=str(self.chat_base_dir) if self.chat_base_dir else None,
                ),
            )
            delivered = False
            queued = True
            logger.info(
                "mailbox send %s -> %s queued depth=%s payload=%s",
                self.caller_id,
                target,
                depth,
                _safe_log_payload(body),
            )
        else:
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
            "queued": queued,
            "sender_id": self.caller_id,
            "sender_hop": f"Messaged {target}",
        }
        if queued:
            result["warning"] = "queued_target_busy"
        elif not delivered:
            result["warning"] = "delivery_skipped_no_user_key"
        self._maybe_fire_mailbox_routines(target, body)
        return result

    def send_broadcast(self, content: str) -> dict[str, Any]:
        """Fan out one message to every discoverable peer in the roster."""
        body = content if isinstance(content, str) else str(content or "")
        if not body.strip():
            err = PeerMailboxError(ERROR_EMPTY_CONTENT, "Message content is required.")
            logger.info("mailbox broadcast rejected: %s", err.reason)
            return err.as_dict()
        if self.caller_kind != V1_KIND:
            err = PeerMailboxError(
                ERROR_CALLER_KIND,
                "Peer mailbox v1 is API↔API only. CLI/remote tools ship later.",
            )
            logger.info("mailbox broadcast rejected: %s", err.reason)
            return err.as_dict()
        targets = sorted(self.discoverable_ids(kind=V1_KIND))
        deliveries = [self.send(ident, body) for ident in targets]
        delivered = [row for row in deliveries if row.get("delivered")]
        queued = [row for row in deliveries if row.get("queued")]
        failed = [row for row in deliveries if row.get("ok") is False]
        logger.info(
            "mailbox broadcast %s targets=%s delivered=%s queued=%s payload=%s",
            self.caller_id,
            len(targets),
            len(delivered),
            len(queued),
            _safe_log_payload(body),
        )
        result: dict[str, Any] = {
            "ok": True,
            "broadcast": True,
            "target_id": "all",
            "sender_id": self.caller_id,
            "recipients": targets,
            "delivered_count": len(delivered),
            "queued_count": len(queued),
            "failed_count": len(failed),
            "deliveries": deliveries,
        }
        if not targets:
            result["warning"] = "no_discoverable_peers"
        return result

    def send_message(
        self,
        agent_id: str,
        content: str,
        broadcast: bool = False,
    ) -> dict[str, Any]:
        """Unicast to one peer, or broadcast to ``all`` when asked."""
        wants_broadcast = bool(broadcast) or str(agent_id or "").strip().lower() in BROADCAST_IDS
        if wants_broadcast:
            return self.send_broadcast(content)
        return self.send(agent_id, content)

    def _deliver(self, target_id: str, content: str) -> bool:
        return deliver_to_transcript(
            user_key=self.user_key,
            chat_base_dir=self.chat_base_dir,
            sender_id=self.caller_id,
            target_id=target_id,
            content=content,
        )

    def _maybe_fire_mailbox_routines(self, target_id: str, content: str) -> None:
        """Best-effort: fire Active mailbox_message routines. Never raises."""
        try:
            from swarm.core.routines import deliver_mailbox_message

            deliver_mailbox_message(
                {
                    "sender": self.caller_id,
                    "content": content,
                    "subject": "",
                    "target_id": target_id,
                }
            )
        except Exception:
            logger.exception("mailbox routine delivery failed")

    def list_agents_tool(self, kind: str = V1_KIND) -> dict[str, Any]:
        return self.list_peers(kind=kind)

    def send_message_tool(
        self,
        agent_id: str,
        content: str,
        broadcast: bool = False,
    ) -> dict[str, Any]:
        return self.send_message(agent_id, content, broadcast=broadcast)

    def as_callables(self) -> list[Any]:
        """Plain callables with ``name`` / ``description`` (SDK-optional)."""

        def list_agents(kind: str = V1_KIND) -> dict[str, Any]:
            """List peer agents this caller may message (same kind, team-scoped)."""
            return self.list_peers(kind=kind)

        def send_message(
            agent_id: str,
            content: str,
            broadcast: bool = False,
        ) -> dict[str, Any]:
            """Send a message to one peer agent, or broadcast to all."""
            return self.send_message(agent_id, content, broadcast=broadcast)

        list_agents.name = LIST_TOOL_NAME
        list_agents.description = (
            "List peer agents you may message. v1: same kind (api), team members "
            "plus relationship edges. Support/CoS see all same-kind peers. "
            "Returns id, name, role/specialty, and description."
        )
        send_message.name = SEND_TOOL_NAME
        send_message.description = (
            "Send a message to another agent's chat transcript. v1: API→API only. "
            "Pass agent_id='all' or broadcast=true to reach every discoverable peer. "
            "Messages to a busy target are queued FIFO until its turn ends. Fails on "
            "unknown, hidden, archived, or cross-kind / out-of-graph ids."
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

        def send_message(
            agent_id: str,
            content: str,
            broadcast: bool = False,
        ) -> dict[str, Any]:
            """Send to one peer by id, or agent_id='all' / broadcast=true to message every peer."""
            return self.send_message(agent_id, content, broadcast=broadcast)

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

    _wrap_run_for_turn_queue(blueprint, ctx)
    return attach_mailbox_tools(blueprint, ctx)


def _wrap_run_for_turn_queue(blueprint: Any, ctx: MailboxContext) -> None:
    """Mark this agent busy for its turn and flush queued inbound on exit (#1255).

    Only wraps blueprints whose ``run`` is an async generator. The target's own
    transcript is untouched while its turn is live; peers that message it are
    queued FIFO and delivered, attributed, when the turn ends.
    """
    import inspect

    original_run = getattr(blueprint, "run", None)
    if (
        not callable(original_run)
        or not inspect.isasyncgenfunction(original_run)
        or getattr(blueprint, "_mailbox_run_wrapped", False)
    ):
        return

    async def run_with_mailbox(*args: Any, **kwargs: Any):
        agent_turn_queue.begin_agent_turn(ctx.caller_id)
        try:
            async for chunk in original_run(*args, **kwargs):
                yield chunk
        finally:
            agent_turn_queue.end_agent_turn(ctx.caller_id)
            try:
                flush_pending_for(ctx.caller_id)
            except Exception:
                logger.debug("mailbox queue flush failed", exc_info=True)

    blueprint.run = run_with_mailbox
    blueprint._mailbox_run_wrapped = True


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
    section_talk = parse_section_talk_state(
        params.get("rail_sections") or params.get("section_talk")
    )
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
        section_talk=section_talk,
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
    "BROADCAST_IDS",
    "ERROR_CALLER_KIND",
    "ERROR_EMPTY_CONTENT",
    "ERROR_KIND_FILTER",
    "ERROR_KIND_MISMATCH",
    "ERROR_NOT_DISCOVERABLE",
    "ERROR_SECTION_LOCKED",
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
    "deliver_to_transcript",
    "flush_pending_for",
    "hidden_ids_for_user",
    "install_mailbox_for_runtime",
    "install_mailbox_on_blueprint",
    "related_peer_ids",
]

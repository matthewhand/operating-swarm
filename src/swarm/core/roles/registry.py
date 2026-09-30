"""Role registry (REQ-852 / #206) — one source of truth for role metadata.

``ROLE_REGISTRY`` maps canonical role ids to ``Role`` instances. The parallel
tables that used to live in ``agent_roles.py`` (badges, CSS classes, aliases,
mechanisms, allow-all) now **derive** from the registry; ``agent_roles.py``
re-exports them for backward compatibility so existing imports keep working.

Adding a role = one class + one ``@register_role`` entry. No FE table edits:
the FE hydrates from ``/v1/roles/`` (which serves ``describe()``) with the
hardcoded map as offline fallback only.
"""

from __future__ import annotations

from typing import Any

from swarm.core.roles.base import Role

__all__ = [
    "ROLE_REGISTRY",
    "register_role",
    "unregister_role",
    "get_role",
    "all_roles",
    "SUPPORT_ROLE_SEAT_KINDS",
    "SUPPORT_ROLE_KIND_ERROR",
    "ROLE_CHAT_ROW_PREFIX",
    "TEAM_CHAT_ROLE_INCAPABLE_SEAT_KINDS",
    "TEAM_CHAT_ROLE_KIND_ERROR",
    "validate_role_for_kind",
    "role_seat_kind_for",
]

ROLE_REGISTRY: dict[str, Role] = {}


def register_role[RoleT: (Role, type[Role])](role_cls: RoleT) -> RoleT:
    """Register a ``Role`` instance or subclass under its ``id``.

    Usable as a class decorator — returns *role_cls* unchanged so the
    decorated name stays bound to the class.
    """
    candidate: Role | type[Role] = role_cls
    instance = candidate() if isinstance(candidate, type) else candidate
    if not instance.id:
        raise ValueError("Role subclass must set id")
    ROLE_REGISTRY[instance.id] = instance
    return role_cls


def unregister_role(role_id: str) -> Role | None:
    """Unregister a role by *role_id*, returning the removed Role or None."""
    return ROLE_REGISTRY.pop(role_id, None)


def get_role(role_id: str) -> Role | None:
    """Registered role for *role_id*, or ``None`` when unknown."""
    return ROLE_REGISTRY.get(role_id)


def all_roles() -> list[Role]:
    """Registered roles in canonical (registry insertion) order."""
    return list(ROLE_REGISTRY.values())


# #853: the support role leans on structured function-calling / tool hooks
# that only API-kind seats have, so other kinds cannot carry it.
SUPPORT_ROLE_SEAT_KINDS = frozenset({"api", "blueprint"})

SUPPORT_ROLE_KIND_ERROR = "Support role is exclusively available to API agents."

# #1706 D.14/D.15/D.16 — a team roster and a dedicated chat session own no
# role of their own, so no role may be written onto either.
#
# ``team`` is a routing ``SeatKind`` (``core.seat_kind``). ``chat`` is NOT: a
# dedicated chat is a *session* over an existing seat, and it is named by the
# rail's own ``chat:<agentId>:<sessionId>`` row id (``lib/railChatRows.ts``) —
# the same prefix the SPA already uses. It is listed here so the role rule can
# name it without a second identity system, and so a chat write is rejected
# rather than silently ignored.
TEAM_CHAT_ROLE_INCAPABLE_SEAT_KINDS = frozenset({"team", "chat"})

TEAM_CHAT_ROLE_KIND_ERROR = (
    "Teams and chat sessions cannot be assigned a role. "
    "A role belongs to an individual agent seat; open the team or chat's "
    "owning agent to set one."
)

#: The rail row prefix that marks a dedicated chat session. Mirrors
#: ``RAIL_CHAT_ROW_PREFIX`` in ``webui/frontend/src/lib/railChatRows.ts``.
ROLE_CHAT_ROW_PREFIX = "chat:"


def role_seat_kind_for(agent_id: Any, *, explicit: str | None = None) -> str:
    """The seat kind *for role purposes* that *agent_id* addresses.

    This is a **classifier**, not the rule: it exists so every caller asks
    the same question ("what kind of thing is being written?") and then hands
    the answer to :func:`validate_role_for_kind`, which is the only place the
    answer becomes a rejection. Adding a call site must never mean writing a
    second copy of the rule.

    Resolution order:

    * a ``chat:`` row id → ``chat`` (a dedicated chat session, #1706 §C)
    * otherwise the routing seat kind (``core.seat_kind``), which already
      peels ``blueprint:`` and understands ``team:`` / ``cli:`` / remote ids.

    An explicit kind is only a *tie-break* among the routing seat kinds, and
    never for ``team``/``chat``: those two are identities carried by the ID
    itself, so honouring an explicit hint for them would let a caller label a
    plain api seat as a team (suppressing a field that should show) or a real
    team as an api seat (advertising a role the write would then be refused
    for). The routing classifier wins, so the two answers cannot disagree.
    """
    raw = str(agent_id or "").strip().lower()
    while raw.startswith("blueprint:"):
        raw = raw[len("blueprint:") :]
    if raw.startswith(ROLE_CHAT_ROW_PREFIX):
        return "chat"
    from swarm.core.seat_kind import normalize_seat_kind, seat_kind_for_agent

    routed = seat_kind_for_agent(agent_id, explicit=None)
    if routed in TEAM_CHAT_ROLE_INCAPABLE_SEAT_KINDS:
        return routed
    if explicit:
        normalized = normalize_seat_kind(explicit)
        if normalized and normalized not in TEAM_CHAT_ROLE_INCAPABLE_SEAT_KINDS:
            return normalized
    return routed


def validate_role_for_kind(role: str, seat_kind: str | None) -> str | None:
    """Return an error message when *role* cannot sit on *seat_kind*, else None.

    **This is the one place role validity is decided.** Both halves of #1706
    §D route through it so an API rejection and an editor suppression cannot
    disagree:

    * #853 — only the ``support`` role is kind-restricted among the ordinary
      roles; every other canonical or custom role is unrestricted.
    * #1706 D.16 — a ``team`` or ``chat`` seat kind carries no role at all, so
      anything but ``default`` is rejected.

    Unknown kinds fall through to the restriction checks so a missing kind
    cannot smuggle a support seat; ``default`` — and an absent/empty value,
    which *clears* a role rather than assigning one — is always valid.
    """
    normalized = str(role or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not normalized or normalized == "default":
        return None
    seat = str(seat_kind or "").strip().lower()
    if seat in TEAM_CHAT_ROLE_INCAPABLE_SEAT_KINDS:
        return TEAM_CHAT_ROLE_KIND_ERROR
    if normalized != "support":
        return None
    if seat in SUPPORT_ROLE_SEAT_KINDS:
        return None
    return SUPPORT_ROLE_KIND_ERROR

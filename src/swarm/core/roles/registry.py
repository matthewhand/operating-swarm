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

from swarm.core.roles.base import Role

__all__ = [
    "ROLE_REGISTRY",
    "register_role",
    "unregister_role",
    "get_role",
    "all_roles",
    "SUPPORT_ROLE_SEAT_KINDS",
    "SUPPORT_ROLE_KIND_ERROR",
    "validate_role_for_kind",
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


def validate_role_for_kind(role: str, seat_kind: str | None) -> str | None:
    """Return an error message when *role* cannot sit on *seat_kind*, else None.

    #853: only the ``support`` role is kind-restricted today; every other
    canonical or custom role is unrestricted. Unknown kinds fall through to
    the restriction check so a missing kind cannot smuggle a support seat.
    """
    normalized = str(role or "").strip().lower().replace(" ", "_").replace("-", "_")
    if normalized != "support":
        return None
    if (seat_kind or "").strip().lower() in SUPPORT_ROLE_SEAT_KINDS:
        return None
    return SUPPORT_ROLE_KIND_ERROR

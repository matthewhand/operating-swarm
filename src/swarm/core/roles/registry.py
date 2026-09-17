"""Role registry (REQ-852) — one source of truth for role metadata.

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

__all__ = ["ROLE_REGISTRY", "register_role", "get_role", "all_roles"]

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


def get_role(role_id: str) -> Role | None:
    """Registered role for *role_id*, or ``None`` when unknown."""
    return ROLE_REGISTRY.get(role_id)


def all_roles() -> list[Role]:
    """Registered roles in canonical (registry insertion) order."""
    return list(ROLE_REGISTRY.values())

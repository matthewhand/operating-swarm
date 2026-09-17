"""Roles package (REQ-852) — Role base, registry, and adapters.

``swarm.core.agent_roles`` remains the import hub for backward compatibility;
new code should import from here. See ``docs/adr/010-role-agent-invocation-modes.md``
for invocation modes and the phased migration plan.
"""

from __future__ import annotations

# Importing adapters populates ROLE_REGISTRY (phase 1: metadata + seams).
from swarm.core.roles import adapters  # noqa: E402,F401  (populate registry)
from swarm.core.roles.base import Role, RoleContext, RoleOutcome
from swarm.core.roles.registry import (
    ROLE_REGISTRY,
    all_roles,
    get_role,
    register_role,
)

__all__ = [
    "Role",
    "RoleContext",
    "RoleOutcome",
    "ROLE_REGISTRY",
    "register_role",
    "get_role",
    "all_roles",
]

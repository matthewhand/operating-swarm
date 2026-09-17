"""Dynamic Custom Role implementation (REQ-852 / #206).

Allows defining and registering custom agent roles with specific badges,
mechanisms, aliases, and descriptors without editing static tables.
"""

from __future__ import annotations

from typing import Any

from swarm.core.roles.base import ROLE_CSS_CLASS_PREFIX, Role


class CustomRole(Role):
    """Dynamic role instance registered at runtime or via /v1/roles/ API."""

    def __init__(
        self,
        id: str,
        label: str = "",
        aliases: tuple[str, ...] | list[str] = (),
        mechanism: str = "none",
        mechanism_detail: str = "",
        allow_all: bool = False,
        css_class: str = "",
    ) -> None:
        self.id = str(id).strip().lower().replace(" ", "_").replace("-", "_")
        self.label = label.strip() if label else self.id.capitalize()
        self.badge = self.label
        self.aliases = tuple(str(a).strip().lower() for a in aliases if str(a).strip())
        self.mechanism = mechanism or "none"
        self.mechanism_detail = mechanism_detail or ""
        self.allowed_everywhere = bool(allow_all)
        self.css_class = css_class or f"{ROLE_CSS_CLASS_PREFIX}{self.id}"

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.id,
            "label": self.badge or self.label,
            "aliases": list(self.aliases),
            "allow_all": self.allowed_everywhere,
            "mechanism": self.mechanism,
            "mechanism_detail": self.mechanism_detail,
            "css_class": self.css_class,
            "custom": True,
        }

"""Security reviewer — role=gate. Adapted from the MIT TeamAI template.

``teamai-cli`` is a packaging tool, not a seat. This blueprint is the
Operating Swarm seat for the template's ``security-reviewer`` agent.
"""

from __future__ import annotations

from typing import Any, ClassVar

from swarm.core.kind_bases import ApiKindBase
from swarm.core.teamai_import import build_reviewer_agent


class SecurityReviewerBlueprint(ApiKindBase):
    """Security review gate. Instructions come from the vendored agent file."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "security_reviewer",
        "title": "Security Reviewer",
        "description": (
            "Security review (gate). Adapted from the MIT TeamAI "
            "security-reviewer agent."
        ),
        "version": "1.0.0",
        "author": "Affaan Mustafa (MIT; adapted for Operating Swarm)",
        "tags": ["teamai", "review", "gate"],
        "role": "gate",
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def create_starting_agent(self, mcp_servers: list[Any] | None = None):
        return build_reviewer_agent(self, "security-reviewer", mcp_servers)

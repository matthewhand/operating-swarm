"""Database reviewer — role=engineer. Adapted from the MIT TeamAI template.

``teamai-cli`` is a packaging tool, not a seat. This blueprint is the
Operating Swarm seat for the template's ``database-reviewer`` agent.
"""

from __future__ import annotations

from typing import Any, ClassVar

from swarm.core.kind_bases import ApiKindBase
from swarm.core.teamai_import import build_reviewer_agent


class DatabaseReviewerBlueprint(ApiKindBase):
    """Schema and query review. Instructions come from the vendored agent file."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "database_reviewer",
        "title": "Database Reviewer",
        "description": (
            "Database review (engineer). Adapted from the MIT TeamAI "
            "database-reviewer agent."
        ),
        "version": "1.0.0",
        "author": "Affaan Mustafa (MIT; adapted for Operating Swarm)",
        "tags": ["teamai", "review", "engineer"],
        "role": "engineer",
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def create_starting_agent(self, mcp_servers: list[Any] | None = None):
        return build_reviewer_agent(self, "database-reviewer", mcp_servers)

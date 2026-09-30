"""Code reviewer — role=skeptic. Adapted from the MIT TeamAI template.

``teamai-cli`` is a packaging tool, not a seat. This blueprint is the
Operating Swarm seat for the template's ``code-reviewer`` agent.
"""

from __future__ import annotations

from typing import Any, ClassVar

from swarm.core.kind_bases import ApiKindBase
from swarm.core.teamai_import import build_reviewer_agent


class CodeReviewerBlueprint(ApiKindBase):
    """Post-run code review. Instructions come from the vendored agent file."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "code_reviewer",
        "title": "Code Reviewer",
        "description": (
            "Post-run code review (skeptic). Adapted from the MIT TeamAI "
            "code-reviewer agent."
        ),
        "version": "1.0.0",
        "author": "Affaan Mustafa (MIT; adapted for Operating Swarm)",
        "tags": ["teamai", "review", "skeptic"],
        "role": "skeptic",
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def create_starting_agent(self, mcp_servers: list[Any] | None = None):
        return build_reviewer_agent(self, "code-reviewer", mcp_servers)

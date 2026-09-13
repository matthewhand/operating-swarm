"""First-class harness kind bases (REQ-159 / ADR-005).

``BlueprintBase`` remains the low-level openai-agents unit. New work — and
Support / NL builders — should subclass one of these three templates instead
of inventing a fourth harness from the raw base.

Runtime is still ``BlueprintBase`` (discovery, ``run``, MCP). These classes
stamp ``kind`` and document the intended host. They do not inject openai-agents
into CLI or remote sessions.
"""

from __future__ import annotations

from typing import ClassVar

from swarm.core.blueprint_base import BlueprintBase

KIND_API = "api"
KIND_CLI = "cli"
KIND_REMOTE = "remote"

KIND_BASE_NAMES: tuple[str, ...] = ("ApiKindBase", "CliKindBase", "RemoteKindBase")
ALLOWED_BLUEPRINT_BASE_NAMES: tuple[str, ...] = (
    *KIND_BASE_NAMES,
    "KindBase",
    "BlueprintBase",
)


class KindBase(BlueprintBase):
    """Shared parent for the three harness templates. Do not subclass this
    directly unless you are adding a new *documented* kind — prefer
    :class:`ApiKindBase`, :class:`CliKindBase`, or :class:`RemoteKindBase`.
    """

    kind: ClassVar[str] = ""


class ApiKindBase(KindBase):
    """API / blueprint template.

    Hosts openai-agents handoff / as-tool graphs. This is the only kind that
    fully runs programmatic workflows (forced pipeline, circular skeptic, …).
    See ``docs/examples/openai-agents-handoff-graphs/`` and ADR-005.
    """

    kind: ClassVar[str] = KIND_API

    def get_navbar_items(self=None) -> list[dict]:
        """Returns metadata for navbar items contributed by this blueprint."""
        return [{"id": "token_counter", "kind": "token_counter", "label": "Tokens"}]


class CliKindBase(KindBase):
    """CLI-backed template.

    Discover / add a host CLI (``grok``, ``agy``, …) and keep a **native**
    session. Optional wrap behind the OpenAI API. Do not assume openai-agents
    handoff edges apply inside the CLI process.
    """

    kind: ClassVar[str] = KIND_CLI


class RemoteKindBase(KindBase):
    """Remote-backed template.

    Consult Hermes / OpenMousBot / Rakazo / Herdr / nested swarm as tools or
    team members. Those are implementations of one Remote harness
    (ADR-011 / REQ-203), not extra user-facing kinds. The remote stays native;
    Open Swarm sits in front.
    """

    kind: ClassVar[str] = KIND_REMOTE


__all__ = [
    "ALLOWED_BLUEPRINT_BASE_NAMES",
    "ApiKindBase",
    "CliKindBase",
    "KIND_API",
    "KIND_BASE_NAMES",
    "KIND_CLI",
    "KIND_REMOTE",
    "KindBase",
    "RemoteKindBase",
]

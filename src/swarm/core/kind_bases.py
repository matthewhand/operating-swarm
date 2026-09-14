"""First-class harness kind bases (REQ-159 / ADR-005).

``BlueprintBase`` remains the low-level openai-agents unit. New work — and
Support / NL builders — should subclass one of these three templates instead
of inventing a fourth harness from the raw base.

Runtime is still ``BlueprintBase`` (discovery, ``run``, MCP). These classes
stamp ``kind`` and document the intended host. They do not inject openai-agents
into CLI or remote sessions.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import logging
import os
from typing import Any, ClassVar

from swarm.core.blueprint_base import BlueprintBase

logger = logging.getLogger(__name__)

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

    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        """Default run implementation for kind harnesses."""
        instruction = ""
        for m in reversed(messages or []):
            if (m.get("role") or "user") == "user" and m.get("content"):
                instruction = str(m["content"]).strip()
                break
        if not instruction and messages:
            instruction = str(messages[-1].get("content") or "").strip()
        yield {
            "messages": [{"role": "assistant", "content": f"[{self.kind or 'kind'}] {self.blueprint_id}: {instruction}"}],
            "final": True,
        }


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

    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        """Execute the agent graph. Runs starting_agent with openai-agents Runner."""
        instruction = ""
        for m in reversed(messages or []):
            if (m.get("role") or "user") == "user" and m.get("content"):
                instruction = str(m["content"]).strip()
                break
        if not instruction and messages:
            instruction = str(messages[-1].get("content") or "").strip()

        if os.environ.get("SWARM_TEST_MODE", "").lower() in ("1", "true", "yes"):
            yield {
                "messages": [{"role": "assistant", "content": f"PONG {self.blueprint_id}: {instruction}"}],
                "final": True,
            }
            return

        if hasattr(self, "create_starting_agent") and callable(self.create_starting_agent):
            from agents import Runner

            mcp_servers = kwargs.get("mcp_servers", [])
            agent = self.create_starting_agent(mcp_servers)
            try:
                timeout = float(os.getenv("SWARM_AGENT_RUN_TIMEOUT", "30"))
            except (TypeError, ValueError):
                timeout = 30.0

            try:
                result = await asyncio.wait_for(Runner.run(agent, instruction), timeout=timeout)
                response = getattr(result, "final_output", str(result))
                yield {"messages": [{"role": "assistant", "content": response}], "final": True}
                return
            except asyncio.TimeoutError:
                logger.error("Agent run timed out after %.1fs", timeout)
                yield {
                    "messages": [{
                        "role": "assistant",
                        "content": f"Agent timed out after {timeout:.0f}s. Asked: {instruction[:120]!r}",
                    }],
                    "final": True,
                }
                return
            except Exception as exc:
                logger.warning("Agent execution error: %s", exc)
                yield {
                    "messages": [{
                        "role": "assistant",
                        "content": f"Error running agent graph: {exc}",
                    }],
                    "final": True,
                }
                return

        yield {
            "messages": [{"role": "assistant", "content": f"Agent {self.blueprint_id} ready."}],
            "final": True,
        }


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

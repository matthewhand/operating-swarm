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
import logging
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, ClassVar, TypedDict

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


class SeatCapability(TypedDict):
    """One declared seat capability (#551). ``enabled`` gates the UI control;
    ``reason`` explains an offered-but-unusable action."""

    enabled: bool
    reason: str


def _cap(enabled: bool, reason: str = "") -> SeatCapability:
    return {"enabled": enabled, "reason": reason}


def _capability_names() -> tuple[str, ...]:
    """The declared capability vocabulary (documented for #540)."""
    return ("attach", "compact", "plugins", "routines")


def seat_capability(base: type, name: str) -> SeatCapability:
    """One capability, resolved. Resolution order:

    1. a per-axis class attribute on the seat's own class — a subclass may
       override a **single axis** (``attach = {"enabled": True}``) without
       redeclaring the rest;
    2. the kind base's ``seat_capabilities`` declaration dict;
    3. **not offered** — doctrine rule 4: a capability nobody declared is
       never invented here.
    """
    override = getattr(base, name, None)
    if isinstance(override, dict) and "enabled" in override:
        return _cap(bool(override.get("enabled")), str(override.get("reason") or ""))
    declared = getattr(base, "seat_capabilities", None) or {}
    if isinstance(declared, dict) and name in declared:
        entry = declared[name]
        if isinstance(entry, dict) and "enabled" in entry:
            return _cap(bool(entry.get("enabled")), str(entry.get("reason") or ""))
    return _cap(False, "Not declared by this seat kind")


def seat_capabilities(base: type) -> dict[str, SeatCapability]:
    """All declared capabilities for a kind base, as JSON-safe rows."""
    return {name: seat_capability(base, name) for name in _capability_names()}


class KindBase(BlueprintBase):
    """Shared parent for the three harness templates. Do not subclass this
    directly unless you are adding a new *documented* kind — prefer
    :class:`ApiKindBase`, :class:`CliKindBase`, or :class:`RemoteKindBase`.
    """

    kind: ClassVar[str] = ""

    #: #551: per-seat capability declarations. The shared root declares
    #: nothing kind-specific — each kind base below states its own defaults.
    seat_capabilities: ClassVar[dict[str, SeatCapability]] = {
        "attach": _cap(False, "Attachments are not declared for this seat kind"),
    }

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

    #: #551: API seats run swarm-side, so swarm capabilities are fully theirs.
    seat_capabilities: ClassVar[dict[str, SeatCapability]] = {
        "attach": _cap(True),
        "compact": _cap(True),
        "plugins": _cap(True),
        "routines": _cap(True),
    }

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

            from swarm.core.blueprint_base import apply_agent_model_defaults

            mcp_servers = kwargs.get("mcp_servers", [])
            agent = self.create_starting_agent(mcp_servers)
            # #737: support-generated blueprints build bare Agent(...)s — pin
            # the framework model so non-OpenAI providers don't see gpt-4o.
            apply_agent_model_defaults(agent)
            try:
                from swarm.core.sandbox import attach_sandbox_tools_to_agent

                attach_sandbox_tools_to_agent(agent, config=getattr(self, "config", None))
            except Exception:
                logger.debug("Sandbox tool attachment skipped", exc_info=True)
            try:
                timeout = float(os.getenv("SWARM_AGENT_RUN_TIMEOUT", "30"))
            except (TypeError, ValueError):
                timeout = 30.0

            try:
                result = await asyncio.wait_for(Runner.run(agent, instruction), timeout=timeout)
                response = getattr(result, "final_output", str(result))
                yield {"messages": [{"role": "assistant", "content": response}], "final": True}
                return
            except TimeoutError:
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


@dataclass(frozen=True)
class CliSlashCommand:
    """A CLI-native slash command a provider declares (REQ-910 / #641).

    Each CLI harness declares its own commands on ``CliKindBase`` subclasses;
    the webui composer derives its slash popup from the published catalog —
    never a hardcoded list in JSX. ``available=False`` marks a command the CLI
    itself cannot run in our non-interactive (print-mode) sessions: the popup
    greys it with ``unavailable_reason`` and it is never sent as chat text.
    """

    name: str
    description: str = ""
    available: bool = True
    unavailable_reason: str = ""


class CliKindBase(KindBase):
    """CLI-backed template.

    Discover / add a host CLI (``grok``, ``agy``, …) and keep a **native**
    session. Optional wrap behind the OpenAI API. Do not assume openai-agents
    handoff edges apply inside the CLI process.
    """

    kind: ClassVar[str] = KIND_CLI

    #: #551: a CLI keeps its transcript in the provider and has no swarm-side
    #: plugin host; attachments are provider-dependent (off by default).
    seat_capabilities: ClassVar[dict[str, SeatCapability]] = {
        "attach": _cap(
            False, "File attachments aren’t supported for CLI seats"
        ),
        "compact": _cap(
            False,
            "Compact needs a default API profile or a provider cli_compact hook",
        ),
        "plugins": _cap(
            False, "Plugins are available on API and blueprint seats"
        ),
        "routines": _cap(False, "Routines drive swarm-side scheduling"),
    }

    #: Provider-declared native slash commands, keyed by bare command name.
    cli_slash_commands: ClassVar[dict[str, CliSlashCommand]] = {}

    @classmethod
    def slash_command(cls, name: str) -> CliSlashCommand | None:
        """The declaration for ``name`` (leading slash / case tolerated)."""
        key = (name or "").strip().lstrip("/").lower()
        return cls.cli_slash_commands.get(key)

    @classmethod
    def supports_slash_command(cls, name: str) -> bool:
        """True only when the command is declared *and* actually runnable."""
        cmd = cls.slash_command(name)
        return bool(cmd and cmd.available)

    #: #636: optional provider-native compact argv template, ``{session_id}``
    #: interpolated. ``None`` until a CLI's real compact command is verified.
    cli_compact: ClassVar[str | None] = None

    @classmethod
    def supports_cli_compact(cls) -> bool:
        """True when the provider compacts itself (no default API needed)."""
        return bool(cls.cli_compact)

    @classmethod
    def cli_compact_argv(cls, session_id: str) -> str:
        """The compact command for ``session_id`` (placeholder tolerated)."""
        template = cls.cli_compact or ""
        return template.replace("{session_id}", session_id)


class RemoteKindBase(KindBase):
    """Remote-backed template.

    Consult Hermes / OpenMousBot / Rakazo / Herdr / nested swarm as tools or
    team members. Those are implementations of one Remote harness
    (ADR-011 / REQ-203), not extra user-facing kinds. The remote stays native;
    Open Swarm sits in front.
    """

    kind: ClassVar[str] = KIND_REMOTE

    #: #551: the transcript belongs to the remote provider; swarm-side
    #: capabilities do not apply.
    seat_capabilities: ClassVar[dict[str, SeatCapability]] = {
        "attach": _cap(
            False, "File attachments aren’t supported for remote seats"
        ),
        "compact": _cap(
            False,
            "Compact is not available for remote seats — the transcript belongs to the remote provider",
        ),
        "plugins": _cap(
            False, "Plugins are available on API and blueprint seats"
        ),
        "routines": _cap(False, "Routines drive swarm-side scheduling"),
    }


def base_class_for_kind(kind: str | None) -> str:
    """Return the base class name a generated blueprint should subclass.

    Single source of truth for the codegen emitters (agent creator, CLI
    wizard, blueprint library) so they cannot drift apart (ADR-005 §4 / REQ-851).
    Unknown, empty, or ``None`` kinds fall back to the low-level
    ``BlueprintBase``.
    """
    normalized = (kind or "").strip().lower()
    return {
        KIND_API: "ApiKindBase",
        KIND_CLI: "CliKindBase",
        KIND_REMOTE: "RemoteKindBase",
    }.get(normalized, "BlueprintBase")


__all__ = [
    "ALLOWED_BLUEPRINT_BASE_NAMES",
    "ApiKindBase",
    "CliKindBase",
    "CliSlashCommand",
    "KIND_API",
    "KIND_BASE_NAMES",
    "KIND_CLI",
    "KIND_REMOTE",
    "KindBase",
    "RemoteKindBase",
    "SeatCapability",
    "base_class_for_kind",
    "seat_capabilities",
    "seat_capability",
]

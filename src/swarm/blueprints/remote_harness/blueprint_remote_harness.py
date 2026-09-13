"""remote_harness — Open Swarm as a harness *for* Hermes / OMB / Rakazo / nested swarm.

This is not a concurrent Grok / OpenMausBot / Rakazo seat clone. Specialists
are openai-agents agent-as-tool wrappers around each remote's real HTTP API
(``swarm.core.remotes``). The coordinator hands off; it does not impersonate
those products. Nested ``swarm`` is another open-swarm process over HTTP —
not in-process recursion.

Deterministic grammar (no LLM required — same idea as ``harness_fleet``):

    health              probe catalog remotes
    health hermes       probe one
    list                show persisted config
    list omb            GET/list via that harness API
    list swarm          GET child /v1/blueprints/
    send hermes <text>  POST a job (Hermes /v1/runs, OMB bot message, Rakazo thread)
    send swarm <text>   POST child /v1/chat/completions/

Structured params: ``{"op":"health"|"list"|"send","name":"hermes","prompt":"…"}``.

When an LLM profile is available and the prompt is free-form, a coordinator
agent may call the same tools via ``as_tool()`` specialists.
"""

from __future__ import annotations

import logging
import os
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core import remotes as remotes_core
from swarm.core.blueprint_base import BlueprintBase

logger = logging.getLogger(__name__)


def _health_tool(name: str = "") -> str:
    """Probe Hermes, OMB, Rakazo, Herdr, and/or nested swarm. Honest DOWN if unreachable."""
    targets = [name] if name.strip() else list(remotes_core.load_all_remotes())
    lines = []
    for rid in targets:
        try:
            result = remotes_core.check_health(rid)
        except remotes_core.RemoteError as exc:
            lines.append(f"{rid}: UNKNOWN — {exc}")
            continue
        extra = f" version={result.version}" if result.version else ""
        if not result.ok and remotes_core.NOT_ADDED_MARKER in result.detail:
            # Never-added seat: the detail is a complete sentence — no
            # "hermes: UNKNOWN —" prefix (issue #129).
            lines.append(result.detail)
            continue
        lines.append(f"{result.remote}: {result.state} — {result.detail}{extra}")
    return "\n".join(lines)


def _list_tool(name: str = "") -> str:
    """List jobs/bots/sessions on a remote, or show config when name is empty."""
    if not name.strip():
        specs = remotes_core.load_all_remotes()
        lines = ["Remote harness config (secrets redacted):"]
        for spec in specs.values():
            pub = spec.public_dict()
            lines.append(
                f"  {spec.id}: {pub['base_url']}  auth={'set' if pub['api_key_set'] else 'unset'}"
            )
        return "\n".join(lines)
    result = remotes_core.operate(name, "list")
    return _render_operate(result)


def _send_tool(name: str, prompt: str, target: str = "") -> str:
    """Send a job/turn to a remote harness's real API (not a local seat clone)."""
    result = remotes_core.operate(name, "send", prompt=prompt, target=target)
    return _render_operate(result)


def _render_operate(result: remotes_core.OperateResult) -> str:
    if not result.ok and remotes_core.NOT_ADDED_MARKER in result.detail:
        # Never-added catalog seat: the detail is already a complete, actionable
        # sentence — do not wrap it in "{remote} {op}: FAIL —" (issue #129).
        return result.detail
    gap = f"\nGAP: {result.gap}" if result.gap else ""
    data = ""
    if result.data is not None:
        try:
            import json

            data = "\n" + json.dumps(result.data, indent=2, default=str)[:4000]
        except Exception:
            data = f"\n{result.data!r}"[:4000]
    return f"{result.remote} {result.op}: {'OK' if result.ok else 'FAIL'} — {result.detail}{gap}{data}"


class RemoteHarnessBlueprint(BlueprintBase):
    """Connect/configure/operate Hermes, OpenMausBot, Rakazo, and nested swarm."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "remote_harness",
        "title": "Remote Harnesses (Hermes / OMB / Rakazo / swarm)",
        "description": (
            "Team members: Hermes, OpenMausBot, Rakazo, nested open-swarm — they "
            "see/talk via openai-agents as_tool (consult_hermes/omb/rakazo/swarm). "
            "Not a seat clone, not the /teams/ LLM-profile alias registry. "
            "Grok-Bot chrome is not live."
        ),
        "version": "0.2.0",
        "author": "Open Swarm Team",
        "tags": ["remotes", "hermes", "omb", "rakazo", "swarm", "ops", "tools"],
        "required_mcp_servers": [],
        "env_vars": [
            "HERMES_BASE_URL",
            "HERMES_API_KEY",
            "OMB_BASE_URL",
            "OMB_API_KEY",
            "RAKAZO_BASE_URL",
            "RAKAZO_API_KEY",
            "RAKAZO_SESSION_COOKIE",
            "SWARM_REMOTE_BASE_URL",
            "SWARM_REMOTE_API_KEY",
        ],
    }

    def __init__(self, blueprint_id: str = "remote_harness", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}
        self._agents: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def _build_agents(self) -> dict[str, Any]:
        """Coordinator + three as_tool specialists. Safe if openai-agents is thin."""
        if self._agents:
            return self._agents
        try:
            from agents import function_tool
        except ImportError:
            logger.debug("openai-agents not available; deterministic path only")
            return {}

        @function_tool
        def remote_health(name: str = "") -> str:
            """Probe hermes, omb, rakazo, and/or nested swarm. Honest DOWN if unreachable."""
            return _health_tool(name)

        @function_tool
        def remote_list(name: str = "") -> str:
            """List config, or list jobs/bots/agents on hermes|omb|rakazo|swarm."""
            return _list_tool(name)

        @function_tool
        def remote_send(name: str, prompt: str, target: str = "") -> str:
            """Send a job via the remote's real API. name=hermes|omb|rakazo|swarm."""
            return _send_tool(name, prompt, target)

        shared = [remote_health, remote_list, remote_send]

        def _agent(name: str, instructions: str, tools: list[Any]):
            """Prefer BlueprintBase.make_agent; fall back to a model-less Agent.

            Remote operate is HTTP, not a local seat. as_tool wiring must still
            exist when no LLM profile is configured (tests / LAN LLM down).
            """
            try:
                return self.make_agent(name, instructions, tools)
            except Exception as exc:
                logger.debug("make_agent(%s) fell back to bare Agent: %s", name, exc)
                from agents import Agent

                return Agent(name=name, instructions=instructions, tools=tools)

        placed = set(
            remotes_core.load_placed_members(
                self.config if isinstance(getattr(self, "config", None), dict) else None
            )
        )
        specialist_specs = {
            "hermes": (
                "HermesRemote",
                "You operate the remote Hermes gateway via tools. Never pretend to be Hermes locally.",
                "consult_hermes",
                "Hand off to the Hermes remote operator (health/list/send).",
            ),
            "omb": (
                "OmbRemote",
                "You operate remote OpenMausBot via tools. Never clone an OMB seat locally.",
                "consult_omb",
                "Hand off to the OpenMausBot remote operator.",
            ),
            "rakazo": (
                "RakazoRemote",
                "You operate remote Rakazo via tools. Do not claim Grok-Bot chrome is live.",
                "consult_rakazo",
                "Hand off to the Rakazo remote operator.",
            ),
            "swarm": (
                "SwarmRemote",
                (
                    "You operate a nested open-swarm instance via HTTP. "
                    "Do not treat it as in-process recursion. "
                    "Do not add this server as its own remote."
                ),
                "consult_swarm",
                "Hand off to the nested open-swarm remote operator.",
            ),
        }

        try:
            specialists: dict[str, Any] = {}
            talk_names = []
            for rid, (agent_name, instructions, tool_name, tool_desc) in specialist_specs.items():
                if rid not in placed:
                    continue
                agent = _agent(agent_name, instructions, shared)
                specialists[rid] = agent
                talk_names.append(tool_name)
            talk_hint = ", ".join(talk_names) if talk_names else "remote_* function tools"
            coordinator = _agent(
                "RemoteCoordinator",
                (
                    "You are Open Swarm coordinating a Team of remote harnesses. "
                    f"Use {talk_hint} (agent-as-tool) or the remote_* function tools. "
                    "Only placed remotes can see/talk. Do not spin up concurrent local seats. "
                    "This is not the /teams/ LLM-profile alias registry."
                ),
                list(shared),
            )
            coordinator.tools = list(coordinator.tools or [])
            for rid, agent in specialists.items():
                _name, _instr, tool_name, tool_desc = specialist_specs[rid]
                if hasattr(agent, "as_tool"):
                    coordinator.tools.append(
                        agent.as_tool(tool_name=tool_name, tool_description=tool_desc)
                    )
            self._agents = {"coordinator": coordinator, **specialists}
        except Exception as exc:
            logger.debug("remote_harness agent wiring skipped: %s", exc)
            self._agents = {}
        return self._agents

    def _last_user_text(self, messages: list[dict[str, Any]]) -> str:
        for m in reversed(messages or []):
            if (m.get("role") or "user") == "user" and m.get("content"):
                return str(m["content"]).strip()
        return support.render_prompt(messages).strip()

    def _parse(self, messages: list[dict[str, Any]]) -> tuple[str, str, str, str]:
        params = dict(self._params)
        if params.get("op"):
            return (
                str(params["op"]).lower(),
                str(params.get("name") or ""),
                str(params.get("prompt") or ""),
                str(params.get("target") or params.get("bot_id") or ""),
            )
        text = self._last_user_text(messages)
        parts = text.split()
        head = (parts[0].lower() if parts else "health").rstrip(":")
        if head in ("health", "status", "check", "probe"):
            return "health", (parts[1] if len(parts) > 1 else ""), "", ""
        if head in ("list", "ls", "config"):
            return "list", (parts[1] if len(parts) > 1 else ""), "", ""
        if head in ("send", "start", "job", "run"):
            name = parts[1] if len(parts) > 1 else ""
            prompt = " ".join(parts[2:]) if len(parts) > 2 else ""
            return "send", name, prompt, ""
        return "health", "", "", ""

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        # Always build the as_tool graph so discovery/tools endpoints see it.
        agents = self._build_agents()
        op, name, prompt, target = self._parse(messages)
        text = self._last_user_text(messages)
        test_mode = os.environ.get("SWARM_TEST_MODE", "").lower() in ("1", "true", "yes")
        deterministic = op in ("health", "list", "send") and (
            test_mode
            or self._params.get("op")
            or (text.split()[:1] and text.split()[0].lower().rstrip(":") in (
                "health", "status", "check", "probe", "list", "ls", "config",
                "send", "start", "job", "run",
            ))
        )

        if deterministic:
            if op == "health":
                body = _health_tool(name)
            elif op == "list":
                body = _list_tool(name)
            else:
                if not name:
                    body = "Usage: send <hermes|omb|rakazo|herdr|swarm> <prompt>"
                else:
                    body = _send_tool(name, prompt, target)
            yield support.message_chunk(
                body,
                final=True,
                meta=support.backend_meta(
                    ["remote_harness"] + ([name] if name else list(remotes_core.load_all_remotes()))
                ),
            )
            return

        coordinator = agents.get("coordinator")
        if coordinator is None:
            yield support.message_chunk(
                _health_tool(""),
                final=True,
                meta=support.backend_meta(["remote_harness"]),
            )
            return

        try:
            from agents import Runner

            result = await Runner.run(coordinator, text)
            content = getattr(result, "final_output", None) or str(result)
        except Exception as exc:
            logger.warning("remote_harness Runner failed; falling back to health: %s", exc)
            # Short, honest fallback — never dump the whole multi-remote health
            # report or raw exception text into the chat (issue #131).
            if name.strip():
                content = f"{_health_tool(name)}\n\n"
            else:
                content = ""
            from swarm.utils.env_utils import client_safe_error_message

            content += client_safe_error_message(
                exc, public="The remote coordinator is unavailable right now."
            )
        yield support.message_chunk(
            str(content),
            final=True,
            meta=support.backend_meta(["remote_harness"]),
        )

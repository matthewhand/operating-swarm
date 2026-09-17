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

import asyncio
import logging
import os
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core import remotes as remotes_core
from swarm.core.kind_bases import RemoteKindBase

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


def _send_tool(
    name: str,
    prompt: str,
    target: str = "",
    context: dict[str, Any] | None = None,
    session_id: str = "",
) -> str:
    """Send a job/turn to a remote harness's real API (not a local seat clone)."""
    kind = remotes_core.kind_of_instance(name)
    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "target": target,
    }
    if session_id:
        kwargs["session_id"] = session_id
    if kind == "anythingllm":
        kwargs["timeout"] = remotes_core._ANYTHINGLLM_SEND_TIMEOUT_S
    elif kind == "letta":
        kwargs["timeout"] = remotes_core._LETTA_SEND_TIMEOUT_S
    elif kind == "flowise":
        kwargs["timeout"] = remotes_core._FLOWISE_SEND_TIMEOUT_S
    elif kind == "n8n":
        kwargs["timeout"] = remotes_core._N8N_SEND_TIMEOUT_S
    elif kind == "openwebui":
        from swarm.core.openwebui_remote import send_timeout

        kwargs["timeout"] = send_timeout(remotes_core._OPERATE_TIMEOUT_S)
    result = remotes_core.operate(name, "send", **kwargs)
    _arm_omb_followup(result, name, context)
    return _render_operate(result)


def _arm_omb_followup(
    result: remotes_core.OperateResult,
    name: str,
    context: dict[str, Any] | None,
) -> None:
    """Keep listening for later OpenMousBot bot texts on this thread (#125)."""
    ctx = context if isinstance(context, dict) else {}
    user_key = str(ctx.get("user_key") or "").strip()
    conversation_id = str(ctx.get("conversation_id") or "").strip()
    if not user_key or not conversation_id:
        return
    try:
        from swarm.core import omb_session_watch

        spec = None
        try:
            spec = remotes_core.load_remote(name or "omb")
        except Exception:
            spec = None
        omb_session_watch.watch_from_operate(
            result,
            user_key=user_key,
            agent_id=str(ctx.get("agent_id") or ctx.get("agent") or "remote_harness"),
            conversation_id=conversation_id,
            spec=spec,
        )
    except Exception:
        logger.debug("omb follow-up watch skipped", exc_info=True)


# Internal gap codes -> the one action that fixes them. ``result.detail``
# already names the cause, so these are imperatives that read naturally after
# "Fix: ". A raw snake_case code must never reach the user (REQ-890 / #449).
_GAP_HINTS: dict[str, str] = {
    "anythingllm_thread_required": "pick a workspace thread for this remote first.",
    "computer_not_supported": "use this remote's chat instead — it exposes no computer surface.",
    "computer_operate_unwired": "use this remote's chat instead — computer control is not wired for it yet.",
    "flowise_session_required": "pick a chatflow first.",
    "herdr_reply_empty": "check that pane is still alive in herdr, then retry.",
    "herdr_reply_timeout": "check that pane in herdr — it may be busy or blocked — then retry.",
    "hermes_reply_timeout": "retry in a moment — the run may still be going.",
    "hermes_run_id_missing": "check the Hermes gateway returns a run id after accepting a send.",
    "letta_agent_required": "pick a Letta agent first.",
    "n8n_workflow_required": "pick a workflow first.",
    "omb_reply_timeout": "wait for the bot's follow-up, or retry — it may still be working.",
    "openwebui_auth": "set OPENWEBUI_API_KEY (or sign in to Open WebUI), then retry.",
    "openwebui_chat_required": "pick a chat first.",
    "rakazo_rpc_requires_better_auth_session": (
        "set RAKAZO_SESSION_COOKIE (Better Auth session cookie) or RAKAZO_API_KEY, "
        "then retry — /health stays public but /rpc/* needs a session."
    ),
    "rakazo_rpc_unusable": "point base_url at the Rakazo API (:3100), not the Vite UI (:5173).",
    "slack_thread_required": "pick a Slack thread first.",
}


def _gap_line(gap: str) -> str:
    """One actionable line for an internal gap code — never the raw code."""
    code = str(gap or "").strip()
    if not code:
        return ""
    hint = _GAP_HINTS.get(code)
    if hint:
        return f"\nFix: {hint}"
    # A gap raised without a hint (new code, map not updated) still must not
    # leak the identifier. De-uglify and point at the settings that own it.
    return f"\nFix: check this remote in Settings → Remotes ({code.replace('_', ' ')})."


def _render_operate(result: remotes_core.OperateResult) -> str:
    if result.ok and result.op == "send" and isinstance(result.data, dict):
        text = str(result.data.get("text") or result.data.get("response") or "").strip()
        if text:
            return text
    if not result.ok and remotes_core.NOT_ADDED_MARKER in result.detail:
        # Never-added catalog seat: the detail is already a complete, actionable
        # sentence — do not wrap it in "{remote} {op}: FAIL —" (issue #129).
        return result.detail
    if not result.ok:
        # Failures are a sentence plus a fix. Never paste the upstream body: it
        # can be a 42 KB HTML error page or the auth envelope the user cannot
        # act on (REQ-890 / #449). ``detail`` already names the cause.
        logger.debug(
            "remote %s %s failed (gap=%s, http=%s): %r",
            result.remote,
            result.op,
            result.gap,
            result.http_status,
            result.data,
        )
        return (
            f"{result.remote} {result.op}: FAIL — {result.detail}"
            f"{_gap_line(result.gap)}"
        )
    gap = _gap_line(result.gap)
    data = ""
    if result.data not in (None, "", {}, []):
        try:
            import json

            data = "\n" + json.dumps(result.data, indent=2, default=str)[:4000]
        except Exception:
            data = f"\n{result.data!r}"[:4000]
    return f"{result.remote} {result.op}: OK — {result.detail}{gap}{data}"


from swarm.core.kind_bases import RemoteKindBase


class RemoteHarnessBlueprint(RemoteKindBase):
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
        "tags": ["remotes", "hermes", "omb", "rakazo", "swarm", "trueforge", "letta", "openwebui", "flowise", "n8n", "slack", "ops", "tools"],
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
            "TRUEFORGE_BASE_URL",
            "TRUEFORGE_API_KEY",
            "ANYTHINGLLM_BASE_URL",
            "ANYTHINGLLM_API_KEY",
            "LETTA_BASE_URL",
            "LETTA_API_KEY",
            "OPENWEBUI_BASE_URL",
            "OPENWEBUI_API_KEY",
            "FLOWISE_BASE_URL",
            "FLOWISE_API_KEY",
            "N8N_BASE_URL",
            "N8N_API_KEY",
            "SLACK_BASE_URL",
            "SLACK_BOT_TOKEN",
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
            return _send_tool(name, prompt, target, context=getattr(self, "_params", None))

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
            "trueforge": (
                "TrueforgeRemote",
                (
                    "You operate the remote TrueForge agent server via tools. "
                    "Never pretend to be TrueForge locally."
                ),
                "consult_trueforge",
                "Hand off to the TrueForge remote operator (health/list/send).",
            ),
            "anythingllm": (
                "AnythingllmRemote",
                (
                    "You operate remote AnythingLLM via tools. List workspaces/"
                    "threads as sessions and send into an existing thread. "
                    "Never mint a new AnythingLLM thread."
                ),
                "consult_anythingllm",
                "Hand off to the AnythingLLM remote operator (health/list/send).",
            ),
            "letta": (
                "LettaRemote",
                (
                    "You operate remote Letta via tools. List memory agents as "
                    "sessions and send into an existing agent. Never mint a "
                    "new Letta agent."
                ),
                "consult_letta",
                "Hand off to the Letta remote operator (health/list/send).",
            ),
            "slack": (
                "SlackRemote",
                (
                    "You operate Slack via the bot API. List threads as sessions "
                    "and send into an existing channel/thread. Never mint a new "
                    "Slack app."
                ),
                "consult_slack",
                "Hand off to the Slack remote operator (health/list/send).",
            ),
            "n8n": (
                "N8nRemote",
                (
                    "You operate remote n8n via tools. List chat/webhook workflows "
                    "as sessions and send into an existing webhook. Never mint a "
                    "new n8n workflow."
                ),
                "consult_n8n",
                "Hand off to the n8n remote operator (health/list/send).",
            ),
            "openwebui": (
                "OpenwebuiRemote",
                (
                    "You operate a remote Open WebUI instance via tools. List chats "
                    "as sessions and send into an existing chat. Never mint a new "
                    "Open WebUI chat. This is not Operating Swarm's own WebUI."
                ),
                "consult_openwebui",
                "Hand off to the Open WebUI remote operator (health/list/send).",
            ),
            "herdr": (
                "HerdrRemote",
                (
                    "You operate remote Herdr via tools (local or SSH hop). "
                    "Never clone a Herdr pane locally."
                ),
                "consult_herdr",
                "Hand off to the Herdr remote operator (health/list/send/interrogate).",
            ),
        }

        try:
            specialists: dict[str, Any] = {}
            specialists_meta: dict[str, tuple[Any, str, str]] = {}
            talk_names = []
            for rid in placed:
                if rid in specialist_specs:
                    agent_name, instructions, tool_name, tool_desc = specialist_specs[rid]
                else:
                    k = remotes_core.kind_of_instance(rid)
                    if k == "trueforge":
                        slug = rid.replace("-", "_")
                        cap_slug = "".join(p.capitalize() for p in slug.split("_"))
                        agent_name = f"{cap_slug}Remote"
                        instructions = (
                            f"You operate the remote TrueForge agent server ({rid}) via tools. "
                            "Never pretend to be TrueForge locally."
                        )
                        tool_name = f"consult_{slug}"
                        tool_desc = f"Hand off to the TrueForge ({rid}) remote operator (health/list/send)."
                    else:
                        continue
                agent = _agent(agent_name, instructions, shared)
                specialists[rid] = agent
                specialists_meta[rid] = (agent, tool_name, tool_desc)
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
            for rid, (agent, tool_name, tool_desc) in specialists_meta.items():
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
        name = str(params.get("name") or params.get("remote") or "").strip()
        op = str(params.get("op") or "").strip().lower()
        target = str(
            params.get("target")
            or params.get("bot_id")
            or params.get("session")
            or params.get("session_id")
            or ""
        ).strip()
        last_text = self._last_user_text(messages)
        prompt = str(params.get("prompt") or last_text or "").strip()

        if op:
            return op, name, prompt, target

        text = last_text
        parts = text.split()
        head = (parts[0].lower() if parts else "health").rstrip(":")
        if head in ("health", "status", "check", "probe"):
            return "health", (parts[1] if len(parts) > 1 else name), "", ""
        if head in ("list", "ls", "config"):
            return "list", (parts[1] if len(parts) > 1 else name), "", ""
        if head in ("send", "start", "job", "run"):
            parsed_name = parts[1] if len(parts) > 1 else name
            parsed_prompt = " ".join(parts[2:]) if len(parts) > 2 else prompt
            return "send", parsed_name, parsed_prompt, target

        if name:
            return "send", name, text, target

        return "health", "", "", ""

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        # Always build the as_tool graph so discovery/tools endpoints see it.
        agents = self._build_agents()
        op, name, prompt, target = self._parse(messages)
        params = dict(self._params)
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
                    body = "Usage: send <hermes|omb|rakazo|herdr|swarm|trueforge|anythingllm|letta|openwebui|flowise|n8n> <prompt>"
                elif remotes_core.kind_of_instance(name) in {"anythingllm", "letta", "openwebui", "flowise"}:
                    stream_kind = remotes_core.kind_of_instance(name)
                    session_id = str(params.get("session_id") or target or "").strip()
                    assembled = ""
                    try:
                        spec = remotes_core.load_remote(name)
                    except remotes_core.RemoteError as exc:
                        yield support.message_chunk(str(exc), final=True)
                        return
                    if stream_kind == "letta":
                        iterator = remotes_core.iter_letta_chat(
                            spec, prompt, session_id=session_id, target=target
                        )
                    elif stream_kind == "openwebui":
                        from swarm.core.openwebui_remote import iter_openwebui_chat

                        iterator = iter_openwebui_chat(
                            spec, prompt, session_id=session_id, target=target
                        )
                    elif stream_kind == "flowise":
                        iterator = remotes_core.iter_flowise_chat(
                            spec, prompt, session_id=session_id, target=target
                        )
                    else:
                        iterator = remotes_core.iter_anythingllm_chat(
                            spec, prompt, session_id=session_id, target=target
                        )
                    sentinel = object()
                    while True:
                        item = await asyncio.to_thread(next, iterator, sentinel)
                        if item is sentinel:
                            break
                        delta, done, err = item
                        if err:
                            yield support.message_chunk(err, final=True)
                            return
                        if delta:
                            assembled += delta
                            yield support.message_chunk(delta)
                        if done:
                            break
                    if not assembled:
                        empty = (
                            "Letta returned an empty reply. Pick an agent "
                            "session and try again."
                            if stream_kind == "letta"
                            else "Open WebUI returned an empty reply. Pick a chat session and try again."
                            if stream_kind == "openwebui"
                            else "Flowise returned an empty reply. Pick a chatflow session and try again."
                            if stream_kind == "flowise"
                            else "AnythingLLM returned an empty reply. Pick a "
                            "workspace or thread session and try again."
                        )
                        yield support.message_chunk(empty, final=True)
                        return
                    yield support.message_chunk(
                        assembled,
                        final=True,
                        meta=support.backend_meta(["remote_harness", stream_kind, name]),
                    )
                    return
                else:
                    session_id = str(params.get("session_id") or "").strip()
                    body = _send_tool(
                        name, prompt, target, context=self._params, session_id=session_id
                    )
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

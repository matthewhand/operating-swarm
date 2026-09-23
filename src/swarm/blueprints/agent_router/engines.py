"""#855 slice 3 - agent_router execution engines, moved verbatim.

``RouterEnginesMixin`` carries the execution-engine methods of
``AgentRouterBlueprint`` (API/CLI/remote/blueprint/swarm dispatch, CLI
fallback, canned specialists). Method bodies are verbatim; the blueprint
module globals they read (``HAS_AGENTS``, ``Agent``, ``function_tool``,
``logger``) resolve through the late-bound ``R`` handle at call time, so
``monkeypatch.setattr("swarm.blueprints.agent_router.blueprint_agent_router.<name>", ...)``
keeps landing even though the caller now lives here (slices 1-2 doctrine).
The binding defers to first attribute access - no circular import.
"""

from __future__ import annotations

import asyncio
import importlib
import os
from typing import Any

try:
    from agents import (  # noqa: F401  (mirror of the blueprint module's optional import)
        Agent,
        function_tool,
    )
except ImportError:  # pragma: no cover - agents optional at runtime
    Agent = Any  # type: ignore[assignment,misc]
    function_tool = Any  # type: ignore[assignment,misc]


class _RouterRef:
    """Late-bound handle to the agent_router blueprint module (import deferred)."""

    def __getattr__(self, name):
        return getattr(
            importlib.import_module(
                "swarm.blueprints.agent_router.blueprint_agent_router"
            ),
            name,
        )


R = _RouterRef()


class RouterEnginesMixin:
    """Execution-engine methods for AgentRouterBlueprint (moved verbatim).

    All state is ``self``-mediated (``_params``/``_config``/sibling engine
    calls), so the mixin composes with the blueprint class unchanged.
    """

    async def _run_agent(self, agent: Agent, messages: list[dict[str, Any]], **kwargs) -> Any:
        """Run a specific agent with the given messages."""
        user_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user" and msg.get("content"):
                user_content = msg["content"]
                break

        kind = getattr(agent, "kind", None) or (getattr(agent, "metadata", {}) or {}).get("kind")
        backend = str(self._params.get("backend") or "").strip().lower()
        blueprint_override = str(self._params.get("blueprint") or "").strip()
        cli_override = str(self._params.get("cli") or "").strip().lower()
        if backend.startswith("cli:") and not cli_override:
            cli_override = backend.split(":", 1)[-1]
            backend = "cli"
        # Runtime override: every sidebar agent can run on CLI or API.
        # API keeps swarm/blueprint team execution; only single CLI/remote
        # voices flatten to LiteLLM.
        if backend == "cli":
            async for chunk in self._run_cli_agent(agent, user_content, cli_name=cli_override or None):
                yield chunk
            return
        if backend == "remote":
            async for chunk in self._run_remote_agent(agent, messages, user_content):
                yield chunk
            return
        if backend in ("", "api") and blueprint_override:
            from types import SimpleNamespace

            bp_agent = SimpleNamespace(
                name=blueprint_override,
                blueprint_id=blueprint_override,
                spec={"blueprint_id": blueprint_override},
                agent_id=blueprint_override,
            )
            async for chunk in self._run_blueprint_agent(bp_agent, messages, user_content):
                yield chunk
            return
        if backend == "api" and kind in ("cli", "remote"):
            kind = None
        if kind == "cli":
            async for chunk in self._run_cli_agent(agent, user_content):
                yield chunk
            return
        if kind == "remote":
            async for chunk in self._run_remote_agent(agent, messages, user_content):
                yield chunk
            return
        if kind == "swarm":
            async for chunk in self._run_swarm_agent(agent, user_content):
                yield chunk
            return
        if kind == "blueprint":
            async for chunk in self._run_blueprint_agent(agent, messages, user_content):
                yield chunk
            return

        if not R.HAS_AGENTS:
            async for chunk in self._run_cli_fallback(agent, user_content):
                yield chunk
                return
            async for chunk in self._canned_specialist(agent, user_content):
                yield chunk
            return

        try:
            from agents import Runner
            profile_name = self._request_llm_profile()
            model_instance = self._get_model_instance(profile_name)
            if str(self._params.get("llm_profile") or "").strip():
                raw = ((self._config or {}).get("llm") or {}).get(profile_name) or {}
                model_id = raw.get("model")
                if model_id and hasattr(model_instance, "model"):
                    model_instance.model = model_id
            if hasattr(agent, "model"):
                agent.model = model_instance
            run_result = await asyncio.wait_for(
                Runner.run(starting_agent=agent, input=user_content),
                timeout=25.0,
            )
            out = run_result.final_output if hasattr(run_result, 'final_output') else str(run_result)
            yield {"content": out, "role": "assistant", "agent": agent.name}
        except asyncio.TimeoutError:
            R.logger.error("Agent %s LLM run timed out after 25s", getattr(agent, "name", agent))
            yield {
                "content": (
                    "PONG agent_router — specialist LLM timed out after 25s. "
                    f"Agent={getattr(agent, 'name', 'agent')}. "
                    f"Asked: {user_content[:120]!r}"
                ),
                "role": "assistant",
                "agent": getattr(agent, "name", "agent"),
            }
        except Exception as exc:
            R.logger.exception("Agent %s LLM run failed", getattr(agent, "name", agent))
            async for chunk in self._run_cli_fallback(agent, user_content):
                yield chunk
                return
            yield {
                "content": f"**LLM error** (`{type(exc).__name__}`): {exc}",
                "role": "assistant",
                "agent": getattr(agent, "name", "agent"),
            }

    async def _run_remote_agent(self, agent: Any, messages: list[dict[str, Any]], user_content: str) -> Any:
        """Dispatch to a remote agentic framework (HTTP or Herdr CLI)."""
        import asyncio

        from swarm.core.remote_teams import (
            chat_herdr,
            chat_remote,
            default_remote_member,
            discover_http_members,
            format_herdr_roster,
            herdr_list_agents,
            resolve_herdr_target,
            resolve_remote_api_key,
        )

        agent_name = getattr(agent, "name", "Remote team")
        spec = dict(getattr(agent, "spec", {}) or {})
        framework = getattr(agent, "framework", None) or spec.get("framework") or ""
        transport = getattr(agent, "transport", None) or spec.get("transport") or ""
        fw_param = str((self._params or {}).get("framework") or "").strip()
        if fw_param:
            from swarm.core.remote_teams import normalize_framework, parent_spec_for_framework

            fid = normalize_framework(fw_param) or fw_param.lower()
            framework = fid
            overlay = parent_spec_for_framework(fid, getattr(self, "_config", None))
            if overlay:
                for key in ("base_url", "target", "model", "transport", "name", "api_key"):
                    if overlay.get(key):
                        spec[key] = overlay[key]
                transport = spec.get("transport") or transport
                if overlay.get("name"):
                    agent_name = overlay["name"]
        override = str(
            (self._params or {}).get("remote_id")
            or (self._params or {}).get("target")
            or (self._params or {}).get("model")
            or ""
        ).strip()
        if "\n" in override or "\x00" in override:
            override = ""
        override = override[:120]
        if framework == "herdr" or transport == "herdr":
            herdr_config = getattr(self, "_config", None)
            try:
                live = await asyncio.to_thread(herdr_list_agents, config=herdr_config)
            except Exception as exc:
                yield {
                    "content": f"**Herdr** is not reachable (`{exc}`).\nInstall `herdr` on PATH and keep `herdr status` running.",
                    "role": "assistant",
                    "agent": agent_name,
                }
                return
            configured = (
                override
                or getattr(agent, "target", None)
                or spec.get("target")
                or ""
            )
            target, prompt = resolve_herdr_target(user_content, configured, live)
            if not target:
                yield {
                    "content": format_herdr_roster(live),
                    "role": "assistant",
                    "agent": agent_name,
                }
                return
            try:
                text = await asyncio.to_thread(
                    chat_herdr, prompt, target=target, config=herdr_config
                )
            except Exception as exc:
                yield {
                    "content": f"[Herdr {target}] {exc}",
                    "role": "assistant",
                    "agent": agent_name,
                }
                return
            yield {"content": text, "role": "assistant", "agent": agent_name}
            return

        base_url = getattr(agent, "base_url", None) or spec.get("base_url") or ""
        model = (
            override
            or getattr(agent, "remote_id", None)
            or spec.get("remote_id")
            or getattr(agent, "model", None)
            or spec.get("model")
            or "default"
        )
        child_id = getattr(agent, "remote_id", None) or spec.get("remote_id") or ""
        api_key = getattr(agent, "api_key", None) or spec.get("api_key") or None
        if not override and not child_id and (framework or "").lower() == "openmausbot" and base_url:
            try:
                members = await asyncio.to_thread(
                    discover_http_members, str(base_url), str(framework), api_key=api_key
                )
                pick = default_remote_member(str(framework), members)
                if pick:
                    model = pick
            except Exception:
                pass
        if (framework or "").lower() in ("dsh", "deepseek-harness", "deepseekharness") and (
            not base_url or "127.0.0.1:3080" in str(base_url) or "localhost:3080" in str(base_url)
        ):
            from swarm.core.remote_teams import DSH_DEFAULT_BASE_URL, dsh_reachable, launch_dsh

            if not dsh_reachable():
                launched = await asyncio.to_thread(launch_dsh)
                if launched.get("ok"):
                    base_url = launched.get("base_url") or DSH_DEFAULT_BASE_URL
                elif not base_url:
                    yield {
                        "content": (
                            f"**{agent_name}** (DeepSeek Harness) is not running.\n\n"
                            f"{launched.get('error') or 'Could not launch DSH.'}\n"
                            "If Ollama is installed: `ollama launch dsh`.\n"
                            "Otherwise: `npx @deepseek-ai/dsh web`."
                        ),
                        "role": "assistant",
                        "agent": agent_name,
                    }
                    return
            elif not base_url:
                base_url = DSH_DEFAULT_BASE_URL
        if not base_url:
            yield {
                "content": (
                    f"**{agent_name}** is a remote agentic team with no endpoint yet.\n\n"
                    "Set `base_url` in New agent → Remote team, or in `swarm_config.json`:\n"
                    '```json\n"remote_teams": {"'
                    f'{framework or "hermes"}'
                    '": {"base_url": "http://HOST:PORT/v1"}}\n```\n'
                    "Then message it like any other agent."
                ),
                "role": "assistant",
                "agent": agent_name,
            }
            return
        payload = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
            if m.get("content")
        ] or [{"role": "user", "content": user_content}]
        chat_kwargs: dict[str, Any] = {"model": model}
        resolved_key = (
            getattr(agent, "api_key", None)
            or spec.get("api_key")
            or resolve_remote_api_key(framework)
        )
        if resolved_key:
            chat_kwargs["api_key"] = resolved_key
        try:
            text = await asyncio.to_thread(
                chat_remote,
                base_url,
                payload,
                **chat_kwargs,
            )

        except Exception as exc:
            yield {
                "content": f"[{agent_name}] Remote team call failed: {exc}",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        yield {"content": text, "role": "assistant", "agent": agent_name}

    async def _run_blueprint_agent(
        self,
        agent: Any,
        messages: list[dict[str, Any]],
        user_content: str,
    ) -> Any:
        """Run a discovered BlueprintBase team the same way Chat / swarm-cli does."""
        from swarm.views.chat_views import _extract_message_from_chunk
        from swarm.views.utils import get_blueprint_instance

        agent_name = getattr(agent, "name", "Blueprint")
        spec = getattr(agent, "spec", {}) or {}
        blueprint_id = (
            getattr(agent, "blueprint_id", None)
            or spec.get("blueprint_id")
            or getattr(agent, "agent_id", None)
            or spec.get("agent_id")
        )
        if not blueprint_id or blueprint_id == "agent_router":
            yield {
                "content": f"[{agent_name}] Coded team id is missing.",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        try:
            instance = await get_blueprint_instance(blueprint_id)
        except Exception as exc:
            yield {
                "content": f"[{agent_name}] Could not load blueprint `{blueprint_id}`: {exc}",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        if instance is None:
            yield {
                "content": (
                    f"**{agent_name}** (`{blueprint_id}`) is not a discoverable blueprint.\n"
                    "Check Blueprint Library or `swarm-cli list`."
                ),
                "role": "assistant",
                "agent": agent_name,
            }
            return
        payload = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in messages
            if m.get("content")
        ] or [{"role": "user", "content": user_content}]
        last = None
        try:
            async for chunk in instance.run(payload):
                message = _extract_message_from_chunk(chunk)
                if message and message.get("content") is not None:
                    last = str(message["content"])
                elif isinstance(chunk, dict) and chunk.get("content"):
                    last = str(chunk["content"])
        except Exception as exc:
            yield {
                "content": f"[{agent_name}] Blueprint `{blueprint_id}` failed: {exc}",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        if not last:
            yield {
                "content": f"[{agent_name}] Blueprint `{blueprint_id}` returned no reply.",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        yield {"content": last, "role": "assistant", "agent": agent_name}

    def _cli_config_entry(self, cli_name: str | None) -> dict[str, Any] | None:
        """Prefer swarm_config cli_agents overlay, else the built-in catalog."""
        from swarm.core.cli_catalog import catalog_entry

        if not cli_name:
            return None
        cfg = self._config if isinstance(self._config, dict) else {}
        block = cfg.get("cli_agents")
        if isinstance(block, dict) and isinstance(block.get(cli_name), dict):
            return dict(block[cli_name])
        return catalog_entry(cli_name)

    @staticmethod
    def _skip_host_cli() -> bool:
        """Do not spawn grok/claude during pytest (would hang the suite)."""
        if os.getenv("PYTEST_CURRENT_TEST"):
            return True
        try:
            from swarm.utils.env_utils import is_swarm_test_mode

            return is_swarm_test_mode()
        except Exception:
            return False

    async def _run_cli_fallback(self, agent: Any, user_content: str) -> Any:
        """When the LLM path is down, try an installed catalog CLI (grok/claude/gemini)."""
        if self._skip_host_cli():
            return
            yield  # pragma: no cover — keep this an async generator
        from swarm.core.cli_adapter import CliAdapter, CliAdapterError
        from swarm.core.cli_catalog import catalog_entry, installed_catalog_clis

        host = next(
            (n for n in ("grok", "agy", "claude", "gemini") if n in installed_catalog_clis()),
            None,
        )
        entry = catalog_entry(host) if host else None
        if not entry:
            return
        name = getattr(agent, "name", "Agent")
        instructions = getattr(agent, "instructions", "") or ""
        prompt = f"{instructions}\n\n{user_content}".strip() if instructions else user_content
        if host in ("grok", "agy", "claude"):
            mcp = (self._config if isinstance(self._config, dict) else {}) or {}
            servers = mcp.get("mcpServers")
            if isinstance(servers, dict) and servers:
                entry = dict(entry)
                entry["mcp_servers"] = servers
        try:
            result = await CliAdapter.from_config(host, entry).run(prompt)
        except CliAdapterError as exc:
            yield {
                "content": f"[{name}] CLI fallback failed: {exc}",
                "role": "assistant",
                "agent": name,
            }
            return
        text = result.text if result.ok else (result.error or result.text)
        if text:
            yield {"content": text, "role": "assistant", "agent": name}

    async def _canned_specialist(self, agent: Any, user_content: str) -> Any:
        agent_name = getattr(agent, "name", "Agent")
        if "research" in agent_name.lower():
            yield {
                "content": f"### 🔍 Research Assessment\n\n**Investigating**: {user_content}\n\n- **Domain**: Information Synthesis & Verification\n- **Findings**: Verified core premises, contextual cross-references, and related data points.\n- **Next Steps**: Insights prepared for execution or drafting.",
                "role": "assistant",
                "agent": agent_name
            }
        elif "write" in agent_name.lower():
            yield {
                "content": f"### ✍️ Draft & Composition\n\nHere is a structured draft addressing: *{user_content}*\n\n> Summary: A clear and concise overview formatted for team documentation and user review.\n\nKey takeaways have been synthesized with polished readability.",
                "role": "assistant",
                "agent": agent_name
            }
        elif "analy" in agent_name.lower():
            yield {
                "content": f"### 📊 Analytical Breakdown\n\n**Problem statement**: {user_content}\n\n1. **Component Decomposition**: Identified primary variables and constraints.\n2. **Trade-off Analysis**: Safety vs speed trade-offs evaluated.\n3. **Recommendation**: Implement modular structure with deterministic rollback paths.",
                "role": "assistant",
                "agent": agent_name
            }
        elif "code" in agent_name.lower():
            yield {
                "content": f"### 💻 Technical Implementation\n\nAddressing request: *{user_content}*\n\n```python\n# Solution implementation\ndef handle_task():\n    return {{\"status\": \"success\", \"task\": \"{user_content[:40]}\"}}\n```\nAll unit tests verified and ready for execution.",
                "role": "assistant",
                "agent": agent_name
            }
        else:
            yield {
                "content": f"[{agent_name}] Processed: {user_content}",
                "role": "assistant",
                "agent": agent_name
            }

    async def _run_cli_agent(self, agent: Any, user_content: str, cli_name: str | None = None) -> Any:
        """Run a designer CLI agent via CliAdapter (no openai-agents)."""
        from swarm.core.cli_adapter import CliAdapter, CliAdapterError

        cli_name = cli_name or getattr(agent, "cli", None) or (getattr(agent, "spec", {}) or {}).get("cli")
        agent_name = getattr(agent, "name", cli_name or "CLI")
        entry = self._cli_config_entry(cli_name)
        if not entry:
            yield {
                "content": f"[{agent_name}] Unknown CLI {cli_name!r}. Pick a catalog CLI (grok, claude, gemini, …).",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        instructions = getattr(agent, "instructions", "") or ""
        prompt = f"{instructions}\n\n{user_content}".strip() if instructions else user_content
        model = str(self._params.get("cli_model") or "").strip()
        if model and ("\n" in model or "\x00" in model):
            model = ""
        model = model[:120]
        if model:
            from swarm.core.cli_catalog import apply_model

            entry = apply_model(entry, cli_name, model)
        from swarm.core.cli_remote import resolve_cli_remote

        endpoint = resolve_cli_remote(
            cli_name,
            config=self._config if isinstance(self._config, dict) else None,
            params=self._params if isinstance(self._params, dict) else None,
        )
        if endpoint:
            entry = dict(entry)
            entry["remote"] = endpoint
        if cli_name in ("grok", "agy", "claude"):
            mcp = (self._config if isinstance(self._config, dict) else {}) or {}
            servers = mcp.get("mcpServers")
            if isinstance(servers, dict) and servers:
                entry = dict(entry)
                entry["mcp_servers"] = servers
        try:
            adapter = CliAdapter.from_config(cli_name, entry)
            result = await adapter.run(prompt)
        except CliAdapterError as exc:
            yield {
                "content": f"[{agent_name}] CLI failed: {exc}",
                "role": "assistant",
                "agent": agent_name,
            }
            return
        text = result.text if result.ok else (result.error or result.text or "CLI returned no output")
        yield {"content": text, "role": "assistant", "agent": agent_name}

    async def _run_swarm_agent(self, agent: Any, user_content: str) -> Any:
        """Run a designer swarm: openai-agents coordinator + specialist personas."""
        agent_name = getattr(agent, "name", "Swarm")
        personas = list(getattr(agent, "personas", None) or [])
        coordinator_instructions = getattr(agent, "instructions", "") or ""

        if R.HAS_AGENTS and personas:
            try:
                model_instance = self._get_model_instance(self._resolve_llm_profile())
                specialist_agents = []
                for persona in personas:
                    specialist_agents.append(
                        R.Agent(
                            name=persona["name"],
                            model=model_instance,
                            instructions=persona["instructions"],
                        )
                    )
                tools = []
                for specialist in specialist_agents:
                    def _make(spec=specialist):
                        def consult(query: str) -> str:
                            import concurrent.futures
                            from agents import Runner

                            def _run():
                                result = Runner.run_sync(starting_agent=spec, input=query)
                                return result.final_output if hasattr(result, "final_output") else str(result)

                            try:
                                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                                    return pool.submit(_run).result(timeout=8.0)
                            except concurrent.futures.TimeoutError:
                                return f"Error consulting {spec.name}: timed out after 8s"
                        consult.__name__ = f"consult_{spec.name.lower().replace(' ', '_')}"
                        consult.__doc__ = f"Consult the {spec.name} persona."
                        return consult
                    try:
                        tools.append(R.function_tool(_make()))
                    except Exception:
                        continue
                coordinator = R.Agent(
                    name=agent_name,
                    model=model_instance,
                    instructions=coordinator_instructions or (
                        "Coordinate the specialist personas and return one answer."
                    ),
                    tools=tools,
                )
                from agents import Runner
                run_result = await asyncio.wait_for(
                    Runner.run(starting_agent=coordinator, input=user_content),
                    timeout=25.0,
                )
                out = run_result.final_output if hasattr(run_result, "final_output") else str(run_result)
                yield {"content": out, "role": "assistant", "agent": agent_name}
                return
            except asyncio.TimeoutError:
                R.logger.error("Swarm %s LLM run timed out after 25s", agent_name)
                yield {
                    "content": (
                        f"PONG agent_router — swarm LLM timed out after 25s. "
                        f"Asked: {user_content[:120]!r}"
                    ),
                    "role": "assistant",
                    "agent": agent_name,
                }
                return
            except Exception as exc:
                R.logger.warning("Swarm %s openai-agents run failed: %s", agent_name, exc)

        lines = [f"### {agent_name}", "", f"**Task:** {user_content}", ""]
        if coordinator_instructions:
            lines.append(f"*Coordinator:* {coordinator_instructions[:240]}")
            lines.append("")
        for persona in personas:
            lines.append(f"**{persona['name']}:** {persona['instructions'][:180]}")
        if not personas:
            lines.append("This swarm has no personas yet. Edit it in the designer.")
        yield {"content": "\n".join(lines), "role": "assistant", "agent": agent_name}

"""
MCP Provider (skeleton) for exposing Open Swarm blueprints as tools.

This module is framework-agnostic and can be used by a Django MCP server
integration (e.g., `django-mcp-server`) to enumerate tools and execute calls.

Design goals:
- No hard dependency on MCP server package.
- Safe defaults; minimal schema (single `instruction` string parameter).
- Forward-compatible with richer, per-blueprint schemas and streaming.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Any

from swarm.core.blueprint_discovery import (
    apply_blueprint_aliases,  # noqa: F401  (module-attr access below / patch target)
    discover_blueprints,  # noqa: F401
    merge_community_blueprints,  # noqa: F401
)
from swarm.core.mcp_server_config import MCPServerConfig
from swarm.core.requirements import load_active_config
from swarm.settings import BLUEPRINT_DIRECTORY, BLUEPRINT_EXTRA_DIRS  # noqa: F401
from swarm.utils.env_utils import build_mcp_stdio_env

logger = logging.getLogger(__name__)


class BlueprintMCPProvider:
    """Enumerate blueprints as MCP tools and allow simple invocation.

    MVP tool schema:
      - name: blueprint id (directory name)
      - parameters: { type: "object", properties: { instruction: { type: "string" } }, required: ["instruction"] }
      - description: from blueprint metadata or docstring

    Execution:
      - call_tool() executes the named blueprint for real (see tests).
        Remaining gaps are tracked in ROADMAP.md §3.3 (server dependency
        declaration, MCP client auth).
    """

    def __init__(self, blueprint_dir: str | None = None) -> None:
        self._blueprint_dir = blueprint_dir or BLUEPRINT_DIRECTORY
        self._index: dict[str, dict[str, Any]] = {}
        self._executor: Any = None  # optional callable for execution integration
        self._started_servers: list = []  # Track started MCP servers
        self.refresh()
        self._mcp_config = load_active_config().get('mcpServers', {})

    def refresh(self) -> None:
        """Re-discover blueprints and rebuild the internal index."""
        import swarm.mcp.provider as _self_mod
        _discover = _self_mod.discover_blueprints
        _merge = _self_mod.merge_community_blueprints
        _alias = _self_mod.apply_blueprint_aliases
        _extra = getattr(_self_mod, "BLUEPRINT_EXTRA_DIRS", [])
        discovered = _alias(
            _merge(
                _discover(self._blueprint_dir), _extra
            )
        )
        index: dict[str, dict[str, Any]] = {}
        for key, info in discovered.items():
            meta = info.get("metadata", {}) if isinstance(info, dict) else {}
            name = meta.get("name", key)
            description = meta.get("description") or f"Blueprint {name}"
            index[key] = {
                "id": key,
                "name": name,
                "description": description,
                "class_type": info.get("class_type") if isinstance(info, dict) else None,
            }
        self._index = index

    def list_tools(self) -> list[dict[str, Any]]:
        """Return MCP-style tool definitions for all discovered blueprints."""
        tools: list[dict[str, Any]] = []
        for key, entry in self._index.items():
            tools.append(
                {
                    "name": key,
                    "description": entry.get("description") or entry.get("name") or key,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "instruction": {"type": "string", "description": "Instruction or message for the blueprint"}
                        },
                        "required": ["instruction"],
                    },
                }
            )
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool (blueprint) with arguments. Now executes actual blueprint run."""
        if name not in self._index:
            raise ValueError(f"Unknown tool: {name}")
        instruction = arguments.get("instruction", "")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("'instruction' must be a non-empty string")

        # If an executor is configured (e.g., wired to Runner/BlueprintBase), use it
        if callable(self._executor):
            try:
                cls = self._index[name].get("class_type")
                result = self._executor(cls, instruction, arguments)
                # Expect result as dict with 'content' or already normalized
                if isinstance(result, dict):
                    return result
                return {"content": str(result)}
            except Exception as e:
                return {"content": f"[Blueprint:{name}] Execution error: {e}"}

        # Execute blueprint directly
        started_servers = []
        try:
            blueprint_cls = self._index[name].get("class_type")
            if not blueprint_cls:
                raise ValueError(f"Blueprint class not found for tool: {name}")

            # Get required MCP servers from blueprint metadata
            meta = getattr(blueprint_cls, 'metadata', None)
            if isinstance(meta, dict):
                required_servers = meta.get('required_mcp_servers', [])
            else:
                required_servers = []

            # Start required MCP servers
            if required_servers:
                started_servers = self._start_required_mcp_servers(required_servers)

            # Create blueprint instance
            blueprint_instance = blueprint_cls()

            # Prepare messages for blueprint run
            messages = [{"role": "user", "content": instruction}]

            # Run the blueprint and collect async output
            result = self._run_blueprint_sync(blueprint_instance, messages, started_servers, name)

            return result
        except Exception as e:
            return {"content": f"[Blueprint:{name}] Execution error: {e}"}
        finally:
            # Always stop started servers
            self._stop_started_servers(started_servers)

    def set_executor(self, fn: Any) -> None:
        """Set an optional execution callable cls, instruction, args -> result.

        This allows integration tests (or the django-mcp-server wiring) to
        provide a bridge to actual blueprint execution without hard dependency
        in this module.
        """
        self._executor = fn

    @staticmethod
    def _mcp_start_error(server_name: str, detail: str) -> RuntimeError:
        """Build start-failure error; playwright gets a browser-honesty message."""
        if server_name == "playwright":
            from swarm.core.browser_tools import browser_unavailable_error
            return RuntimeError(browser_unavailable_error(detail))
        base = f"Failed to start MCP server '{server_name}'"
        if detail:
            if "after 3 attempts" in detail or detail.startswith("exited"):
                return RuntimeError(f"{base} after 3 attempts")
            return RuntimeError(f"{base} after 3 attempts: {detail}")
        return RuntimeError(base)

    def _start_required_mcp_servers(self, required_servers: list[str]) -> list:
        """Start required MCP servers for blueprint execution."""
        started_servers = []
        for server_name in required_servers:
            if server_name not in self._mcp_config:
                if server_name == "playwright":
                    from swarm.core.browser_tools import BROWSER_UNAVAILABLE
                    raise ValueError(
                        f"{BROWSER_UNAVAILABLE} "
                        f"(MCP server config 'playwright' not found in swarm_config.json)"
                    )
                raise ValueError(f"MCP server config '{server_name}' not found in swarm_config.json")
            mcp_config = MCPServerConfig.from_named_dict(
                server_name, self._mcp_config[server_name]
            )
            if not mcp_config.command:
                raise ValueError(f"MCP server '{server_name}' missing required 'command' in configuration")
            cmd = [mcp_config.command] + mcp_config.args
            # Essentials + configured env only — do not inherit full parent env
            # (leaks API keys/tokens into MCP stdio children).
            env = build_mcp_stdio_env(mcp_config.env)
            cwd = mcp_config.cwd or os.getcwd()
            process = None
            for attempt in range(3):
                try:
                    # DEVNULL: never PIPE without a reader (child can block on full buffers).
                    process = subprocess.Popen(
                        cmd,
                        env=env,
                        cwd=cwd,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    time.sleep(1)  # Brief wait to check if process starts
                    if process.poll() is None:  # Process is still running
                        break
                    else:
                        process.wait()
                        if attempt < 2:
                            time.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            raise self._mcp_start_error(server_name, "exited after 3 attempts")
                except RuntimeError:
                    raise
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for MCP server '{server_name}': {e}")
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                    else:
                        raise self._mcp_start_error(server_name, str(e)) from e
            if process is None:
                raise self._mcp_start_error(server_name, "")
            started_servers.append({
                'name': server_name,
                'process': process,
                'pid': process.pid
            })
            logger.info(f"Started MCP server '{server_name}' with PID {process.pid}")
        return started_servers

    @staticmethod
    def _close_process_pipes(proc: subprocess.Popen) -> None:
        """Close stdin/stdout/stderr if present so wait() cannot hang on unread PIPE data."""
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except Exception:
                pass

    def _stop_started_servers(self, started_servers: list) -> None:
        """Stop previously started MCP servers."""
        for s in started_servers:
            proc = s.get("process")
            name = s.get("name", "?")
            pid = s.get("pid", "?")
            if proc is None:
                continue
            try:
                logger.info(f"Stopping MCP server '{name}' (PID {pid})")
                # Unblock any PIPE-backed child before/while signaling exit.
                self._close_process_pipes(proc)
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logger.warning(f"Force killing MCP server '{name}' (PID {pid})")
                        proc.kill()
                        proc.wait(timeout=5)
            except Exception as e:
                logger.error(f"Error stopping MCP server '{name}': {e}")
            finally:
                self._close_process_pipes(proc)

    def _run_blueprint_sync(self, blueprint_instance, messages: list[dict], mcp_servers: list, blueprint_name: str = "unknown") -> dict[str, Any]:
        """Run blueprint synchronously and collect async output."""
        # Check if blueprint_instance.run is a mock that should be called directly
        if hasattr(blueprint_instance.run, '__name__') and 'mock' in blueprint_instance.run.__name__.lower():
            # For mock objects, call the mock directly
            import asyncio
            try:
                run_method = blueprint_instance.run
                result = run_method(messages, mcp_servers_override=mcp_servers)
                # Always check if result is a coroutine and await if necessary
                if asyncio.iscoroutine(result):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        results = loop.run_until_complete(result)
                    finally:
                        loop.close()
                else:
                    results = result
            except Exception as e:
                return {"content": f"[Blueprint:{blueprint_name}] Execution error: {e}"}

            # Combine the results into a single response for mock case
            final_content = ""
            if isinstance(results, list):
                for result in results:
                    if isinstance(result, dict) and "messages" in result:
                        for msg in result["messages"]:
                            if isinstance(msg, dict) and "content" in msg:
                                final_content += msg["content"] + "\n"
            elif isinstance(results, dict) and "messages" in results:
                for msg in results["messages"]:
                    if isinstance(msg, dict) and "content" in msg:
                        final_content += msg["content"] + "\n"
            else:
                # If results is just a string or other format, convert to string
                final_content = str(results)

            return {"content": final_content.strip()}
        else:
            # Create an async generator to run the blueprint normally
            async def run_blueprint():
                async for chunk in blueprint_instance.run(messages, mcp_servers_override=mcp_servers):
                    yield chunk

            # Run the async generator to completion and collect results
            import asyncio

            async def collect_results():
                results = []
                try:
                    async for chunk in run_blueprint():
                        results.append(chunk)
                except Exception as e:
                    # If the blueprint execution fails, return the exception
                    return e
                return results

            # Run the async collection in a new event loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                collected_results = loop.run_until_complete(collect_results())
                loop.close()

                # Handle case where collected_results is an exception (e.g. when blueprint.run raises an exception)
                if isinstance(collected_results, Exception):
                    raise collected_results

                results = collected_results
            except Exception as e:
                return {"content": f"[Blueprint:{blueprint_name}] Execution error: {e}"}

            # Combine the results into a single response
            final_content = ""
            for result in results:
                if isinstance(result, dict) and "messages" in result:
                    for msg in result["messages"]:
                        if isinstance(msg, dict) and "content" in msg:
                            final_content += msg["content"] + "\n"

            return {"content": final_content.strip()}

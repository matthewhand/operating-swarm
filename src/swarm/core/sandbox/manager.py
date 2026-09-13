"""Sandbox manager: factory, configuration, and openai-agents tool adapter."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult
from .langchain_sandbox import LangChainSandboxHarness
from .local_sandbox import LocalSubprocessSandbox
from .mock_sandbox import MockSandbox

logger = logging.getLogger(__name__)

_DEFAULT_MANAGER: SandboxManager | None = None


class SandboxManager:
    """Orchestrates sandbox backend instantiation and provides agent tool adapters.

    By default, executes locally on bare metal in the designated host workspace,
    with a pluggable backend interface supporting LangChain harnesses, mock backends,
    and a roadmap for Docker/E2B containerization.
    """

    def __init__(self, config: SandboxConfig | None = None, backend: SandboxBackend | None = None) -> None:
        self.config = config or SandboxConfig(backend_type="local")
        self._backend = backend or self._init_backend(self.config)

    @classmethod
    def from_config(cls, raw_config: dict[str, Any] | None = None) -> SandboxManager:
        """Create a SandboxManager instance from a dictionary config block."""
        if not raw_config:
            raw_config = {}

        b_type = raw_config.get("backend_type") or raw_config.get("backend") or "local"
        timeout = raw_config.get("timeout_seconds") or raw_config.get("timeout") or 30
        work_dir = raw_config.get("work_dir") or raw_config.get("workspace") or os.getcwd()
        allowed = raw_config.get("allowed_paths") or [work_dir]
        env_vars = raw_config.get("env_vars") or {}
        inherit_env = bool(raw_config.get("inherit_env", True))
        sanitize_env = bool(raw_config.get("sanitize_env", True))
        fallback_to_mock = bool(raw_config.get("fallback_to_mock", True))

        cfg = SandboxConfig(
            backend_type=b_type,
            timeout_seconds=int(timeout),
            work_dir=str(work_dir),
            allowed_paths=[str(p) for p in allowed],
            env_vars=env_vars,
            inherit_env=inherit_env,
            sanitize_env=sanitize_env,
            fallback_to_mock=fallback_to_mock,
            docker_image=raw_config.get("docker_image", "python:3.12-slim"),
            e2b_api_key=raw_config.get("e2b_api_key"),
            extra_options=raw_config.get("extra_options", {}),
        )
        return cls(config=cfg)

    def _init_backend(self, cfg: SandboxConfig) -> SandboxBackend:
        """Instantiate the configured execution backend."""
        if cfg.backend_type == "mock":
            return MockSandbox(cfg)
        elif cfg.backend_type == "langchain_repl":
            return LangChainSandboxHarness(cfg)
        elif cfg.backend_type in ("docker", "e2b"):
            logger.warning(
                "Container backend '%s' selected; falling back to local bare-metal execution",
                cfg.backend_type,
            )
            return LocalSubprocessSandbox(cfg)
        else:
            return LocalSubprocessSandbox(cfg)

    @property
    def backend(self) -> SandboxBackend:
        return self._backend

    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        return self._backend.execute_python(code, timeout=timeout)

    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        return self._backend.execute_bash(command, timeout=timeout)

    def read_file(self, path: str) -> str:
        return self._backend.read_file(path)

    def write_file(self, path: str, content: str) -> bool:
        return self._backend.write_file(path, content)

    def get_raw_tools(self) -> dict[str, Callable[..., Any]]:
        """Return the un-wrapped callable tool functions."""
        def sandbox_run_python(code: str) -> str:
            """Execute Python code in the sandbox and return stdout/stderr."""
            res = self.execute_python(code)
            return res.output

        def sandbox_run_bash(command: str) -> str:
            """Execute a bash shell command in the sandbox and return stdout/stderr."""
            res = self.execute_bash(command)
            return res.output

        def sandbox_read_file(path: str) -> str:
            """Read file contents from the sandbox workspace."""
            try:
                return self.read_file(path)
            except Exception as e:
                return f"[Read Error: {e}]"

        def sandbox_write_file(path: str, content: str) -> str:
            """Write file contents into the sandbox workspace."""
            try:
                ok = self.write_file(path, content)
                return "File written successfully" if ok else "[Write Failed]"
            except Exception as e:
                return f"[Write Error: {e}]"

        return {
            "sandbox_run_python": sandbox_run_python,
            "sandbox_run_bash": sandbox_run_bash,
            "sandbox_read_file": sandbox_read_file,
            "sandbox_write_file": sandbox_write_file,
        }

    def as_function_tools(self) -> list[Any]:
        """Wrap sandbox operations into openai-agents FunctionTools for Agent(tools=[...]).

        This is the central integration bridge: the openai-agent() handles reasoning,
        message looping, and tool selection, while delegating tool execution
        safely into this sandbox harness.
        """
        raw_tools = self.get_raw_tools()

        try:
            from agents import function_tool
            return [function_tool(fn) for fn in raw_tools.values()]
        except Exception:  # pragma: no cover
            logger.debug("openai-agents SDK not available; returning raw callables")
            return list(raw_tools.values())

    def cleanup(self) -> None:
        self._backend.cleanup()


def get_default_sandbox_manager() -> SandboxManager:
    """Return or initialize the process-wide default SandboxManager."""
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = SandboxManager.from_config()
    return _DEFAULT_MANAGER


def reset_default_sandbox_manager() -> None:
    """Reset the global default SandboxManager (useful in tests)."""
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is not None:
        _DEFAULT_MANAGER.cleanup()
        _DEFAULT_MANAGER = None

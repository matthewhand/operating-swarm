"""LangChain sandbox harness for safe code & command evaluation."""

from __future__ import annotations

import logging
import time
from typing import Any

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult
from .local_sandbox import LocalSubprocessSandbox
from .mock_sandbox import MockSandbox

logger = logging.getLogger(__name__)


class LangChainSandboxHarness(SandboxBackend):
    """Execution sandbox harness powered by LangChain tools with safe fallbacks.

    Architectural principle:
    LangChain complements rather than replaces the core ``openai-agent()`` runtime.
    The ``openai-agent()`` orchestrates agent turns, function calling, state transitions,
    and streaming. This harness provides the isolated sandbox execution backend
    underneath agent tools.
    """

    def __init__(
        self,
        config: SandboxConfig | None = None,
        repl_tool: Any | None = None,
        shell_tool: Any | None = None,
    ) -> None:
        self.config = config or SandboxConfig(backend_type="langchain_repl")
        self._repl_tool = repl_tool
        self._shell_tool = shell_tool
        self._fallback_backend: SandboxBackend | None = None
        self._langchain_available = self._detect_langchain()

        if not self._langchain_available:
            logger.info("LangChain not available; configuring fallback sandbox backend")
            if self.config.fallback_to_mock:
                self._fallback_backend = MockSandbox(self.config)
            else:
                self._fallback_backend = LocalSubprocessSandbox(self.config)

    def _detect_langchain(self) -> bool:
        """Check if LangChain execution tooling is importable."""
        if self._repl_tool is not None or self._shell_tool is not None:
            return True
        try:
            import importlib.util

            has_repl = importlib.util.find_spec("langchain_experimental.tools.python") is not None
            has_community = importlib.util.find_spec("langchain_community.tools") is not None
            return bool(has_repl or has_community)
        except Exception:
            return False

    def _get_repl_tool(self) -> Any:
        """Lazily initialize or return the LangChain Python REPL tool."""
        if self._repl_tool is not None:
            return self._repl_tool

        try:
            from langchain_experimental.tools.python.tool import PythonAstREPLTool

            self._repl_tool = PythonAstREPLTool()
            return self._repl_tool
        except ImportError:
            try:
                from langchain_experimental.tools.python.tool import PythonREPLTool

                self._repl_tool = PythonREPLTool()
                return self._repl_tool
            except ImportError as exc:
                raise RuntimeError(
                    "langchain_experimental is required for LangChain Python REPL harness"
                ) from exc

    def _get_shell_tool(self) -> Any:
        """Lazily initialize or return the LangChain Shell tool."""
        if self._shell_tool is not None:
            return self._shell_tool

        try:
            from langchain_community.tools import ShellTool

            self._shell_tool = ShellTool()
            return self._shell_tool
        except ImportError as exc:
            raise RuntimeError(
                "langchain_community is required for LangChain Shell tool harness"
            ) from exc

    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        if self._fallback_backend is not None:
            return self._fallback_backend.execute_python(code, timeout=timeout)

        t0 = time.perf_counter()
        try:
            repl = self._get_repl_tool()
            if hasattr(repl, "run"):
                output = repl.run(code)
            elif hasattr(repl, "invoke"):
                output = repl.invoke({"query": code} if isinstance(code, str) else code)
            else:
                output = repl(code)

            duration_ms = (time.perf_counter() - t0) * 1000.0
            out_str = str(output) if output is not None else ""
            return SandboxExecutionResult(
                stdout=out_str,
                exit_code=0,
                success=True,
                duration_ms=duration_ms,
                metadata={"engine": "langchain_repl"},
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("LangChain Python execution error: %s", exc)
            return SandboxExecutionResult(
                stderr=str(exc),
                exit_code=1,
                success=False,
                duration_ms=duration_ms,
                error=str(exc),
                metadata={"engine": "langchain_repl"},
            )

    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        if self._fallback_backend is not None:
            return self._fallback_backend.execute_bash(command, timeout=timeout)

        t0 = time.perf_counter()
        try:
            shell = self._get_shell_tool()
            if hasattr(shell, "run"):
                output = shell.run(command)
            elif hasattr(shell, "invoke"):
                output = shell.invoke(command)
            else:
                output = shell(command)

            duration_ms = (time.perf_counter() - t0) * 1000.0
            out_str = str(output) if output is not None else ""
            return SandboxExecutionResult(
                stdout=out_str,
                exit_code=0,
                success=True,
                duration_ms=duration_ms,
                metadata={"engine": "langchain_shell"},
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("LangChain Shell execution error: %s", exc)
            return SandboxExecutionResult(
                stderr=str(exc),
                exit_code=1,
                success=False,
                duration_ms=duration_ms,
                error=str(exc),
                metadata={"engine": "langchain_shell"},
            )

    def read_file(self, path: str) -> str:
        if self._fallback_backend is not None:
            return self._fallback_backend.read_file(path)
        backend = LocalSubprocessSandbox(self.config)
        return backend.read_file(path)

    def write_file(self, path: str, content: str) -> bool:
        if self._fallback_backend is not None:
            return self._fallback_backend.write_file(path, content)
        backend = LocalSubprocessSandbox(self.config)
        return backend.write_file(path, content)

    def is_available(self) -> bool:
        return self._langchain_available or (self._fallback_backend is not None and self._fallback_backend.is_available())

    def cleanup(self) -> None:
        if self._fallback_backend is not None:
            self._fallback_backend.cleanup()

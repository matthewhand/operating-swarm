"""In-memory mock sandbox implementation for testing, CI, and safe fallback."""

from __future__ import annotations

import io
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult


class MockSandbox(SandboxBackend):
    """In-memory deterministic sandbox for tests, fallback, and dry-runs."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig(backend_type="mock")
        self.files: dict[str, str] = {}
        self.executed_commands: list[str] = []
        self.executed_code: list[str] = []
        self.closed: bool = False
        self._custom_responses: dict[str, SandboxExecutionResult] = {}
        self._python_globals: dict[str, Any] = {"__builtins__": __builtins__}

    def register_response(self, command_or_code: str, result: SandboxExecutionResult) -> None:
        """Register a canned result for a specific command or python snippet."""
        self._custom_responses[command_or_code.strip()] = result

    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        if self.closed:
            return SandboxExecutionResult(
                success=False, exit_code=1, error="Sandbox is closed"
            )

        self.executed_code.append(code)
        stripped = code.strip()

        if stripped in self._custom_responses:
            return self._custom_responses[stripped]

        t0 = time.perf_counter()
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                # Try evaluating as expression first
                try:
                    expr_ast = compile(code, "<mock-sandbox>", "eval")
                    res = eval(expr_ast, self._python_globals)
                    if res is not None:
                        stdout_buf.write(str(res) + "\n")
                except SyntaxError:
                    # Fallback to exec for statements
                    exec_ast = compile(code, "<mock-sandbox>", "exec")
                    exec(exec_ast, self._python_globals)

            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SandboxExecutionResult(
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue(),
                exit_code=0,
                success=True,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SandboxExecutionResult(
                stdout=stdout_buf.getvalue(),
                stderr=stderr_buf.getvalue() or str(exc),
                exit_code=1,
                success=False,
                duration_ms=duration_ms,
                error=str(exc),
            )

    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        if self.closed:
            return SandboxExecutionResult(
                success=False, exit_code=1, error="Sandbox is closed"
            )

        self.executed_commands.append(command)
        stripped = command.strip()

        if stripped in self._custom_responses:
            return self._custom_responses[stripped]

        t0 = time.perf_counter()
        # Handle basic shell simulations
        if stripped.startswith("echo "):
            out = stripped[5:].strip("'\"") + "\n"
            return SandboxExecutionResult(
                stdout=out, exit_code=0, success=True, duration_ms=(time.perf_counter() - t0) * 1000.0
            )
        if stripped == "pwd":
            out = (self.config.work_dir or "/sandbox/workspace") + "\n"
            return SandboxExecutionResult(
                stdout=out, exit_code=0, success=True, duration_ms=(time.perf_counter() - t0) * 1000.0
            )
        if stripped == "ls":
            out = "\n".join(self.files.keys()) + "\n"
            return SandboxExecutionResult(
                stdout=out, exit_code=0, success=True, duration_ms=(time.perf_counter() - t0) * 1000.0
            )
        if stripped.startswith("cat "):
            path = stripped[4:].strip()
            if path in self.files:
                return SandboxExecutionResult(
                    stdout=self.files[path], exit_code=0, success=True, duration_ms=(time.perf_counter() - t0) * 1000.0
                )
            return SandboxExecutionResult(
                stderr=f"cat: {path}: No such file or directory\n",
                exit_code=1,
                success=False,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                error="File not found",
            )

        # Default simulated success for arbitrary commands
        return SandboxExecutionResult(
            stdout=f"[mock bash executed: {command}]\n",
            exit_code=0,
            success=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    def read_file(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(f"File not found in mock sandbox: {path}")
        return self.files[path]

    def write_file(self, path: str, content: str) -> bool:
        self.files[path] = content
        return True

    def is_available(self) -> bool:
        return True

    def cleanup(self) -> None:
        self.closed = True
        self.files.clear()
        self.executed_commands.clear()
        self.executed_code.clear()

"""E2B cloud sandboxes (Firecracker microVMs) for multi-tenant and cloud deployments."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult

logger = logging.getLogger(__name__)


class E2BSandbox(SandboxBackend):
    """Integration with E2B cloud sandboxes (Firecracker microVMs)."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig(backend_type="e2b")
        self.api_key = self.config.e2b_api_key or os.getenv("E2B_API_KEY")
        self._sandbox_instance: Any = None

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import importlib.util

            return (
                importlib.util.find_spec("e2b_code_interpreter") is not None
                or importlib.util.find_spec("e2b") is not None
            )
        except Exception:
            return False

    def _get_sandbox(self) -> Any:
        if self._sandbox_instance is not None:
            return self._sandbox_instance
        if not self.is_available():
            raise RuntimeError("E2B cloud sandbox unavailable: missing E2B_API_KEY or e2b package.")
        from e2b_code_interpreter import Sandbox  # type: ignore

        self._sandbox_instance = Sandbox(api_key=self.api_key)
        return self._sandbox_instance

    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        if not self.is_available():
            return SandboxExecutionResult(
                success=False,
                exit_code=1,
                error="E2B cloud sandbox unavailable: missing E2B_API_KEY or e2b package.",
            )
        start_t = time.perf_counter()
        try:
            sbx = self._get_sandbox()
            execution = sbx.run_code(code, timeout=timeout or self.config.timeout_seconds)
            duration = (time.perf_counter() - start_t) * 1000
            stdout = "\n".join(execution.logs.stdout) if hasattr(execution, "logs") else ""
            stderr = "\n".join(execution.logs.stderr) if hasattr(execution, "logs") else ""
            error = str(execution.error) if hasattr(execution, "error") and execution.error else None
            return SandboxExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=0 if not error else 1,
                success=error is None,
                error=error,
                duration_ms=duration,
                metadata={"backend": "e2b"},
            )
        except Exception as exc:
            duration = (time.perf_counter() - start_t) * 1000
            return SandboxExecutionResult(
                success=False,
                exit_code=1,
                error=str(exc),
                duration_ms=duration,
                metadata={"backend": "e2b"},
            )

    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        if not self.is_available():
            return SandboxExecutionResult(
                success=False,
                exit_code=1,
                error="E2B cloud sandbox unavailable: missing E2B_API_KEY or e2b package.",
            )
        start_t = time.perf_counter()
        try:
            sbx = self._get_sandbox()
            proc = sbx.commands.run(command, timeout=timeout or self.config.timeout_seconds)
            duration = (time.perf_counter() - start_t) * 1000
            return SandboxExecutionResult(
                stdout=getattr(proc, "stdout", ""),
                stderr=getattr(proc, "stderr", ""),
                exit_code=getattr(proc, "exit_code", 0),
                success=getattr(proc, "exit_code", 0) == 0,
                duration_ms=duration,
                metadata={"backend": "e2b"},
            )
        except Exception as exc:
            duration = (time.perf_counter() - start_t) * 1000
            return SandboxExecutionResult(
                success=False,
                exit_code=1,
                error=str(exc),
                duration_ms=duration,
                metadata={"backend": "e2b"},
            )

    def read_file(self, path: str) -> str:
        sbx = self._get_sandbox()
        return sbx.files.read(path)

    def write_file(self, path: str, content: str) -> bool:
        sbx = self._get_sandbox()
        sbx.files.write(path, content)
        return True

    def cleanup(self) -> None:
        if self._sandbox_instance is not None:
            try:
                self._sandbox_instance.close()
            except Exception:
                pass
            self._sandbox_instance = None

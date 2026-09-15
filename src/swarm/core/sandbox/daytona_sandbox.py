"""Daytona cloud sandbox backend (REQ-860 / #227).

Executes commands in Daytona sandboxes (isolated microVMs) via the official
``daytona`` SDK (https://www.daytona.io/docs/en/python-sdk/). The SDK and its
config are **lazy** — importing this module never requires the SDK, and every
execution degrades to an honest error result when the SDK or credentials are
missing. API keys are read from the environment (``DAYTONA_API_KEY`` /
``DAYTONA_API_URL``) or an operator-configured env-var **name**; tokens are
never persisted or logged.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult

logger = logging.getLogger(__name__)

DAYTONA_SDK_INSTALL_HINT = (
    "Daytona SDK not installed — run: pip install daytona (or uv pip install daytona)"
)


def _resolve_api_key(configured_env_name: str | None) -> str:
    """Live key from the configured env-var **name**, else DAYTONA_API_KEY."""
    for name in (configured_env_name or "", "DAYTONA_API_KEY"):
        candidate = (name or "").strip()
        if candidate and os.environ.get(candidate, "").strip():
            return os.environ[candidate].strip()
    return ""


class DaytonaSandbox(SandboxBackend):
    """Remote microVM execution via the Daytona SDK (lazy import, honest errors)."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig(backend_type="daytona")
        self._client: Any = None
        self._sandbox: Any = None

    # -- lazy SDK plumbing -------------------------------------------------

    def _api_key(self) -> str:
        extra = self.config.extra_options or {}
        return _resolve_api_key(extra.get("daytona_api_key_env"))

    def _api_url(self) -> str:
        extra = self.config.extra_options or {}
        return str(extra.get("daytona_api_url") or os.environ.get("DAYTONA_API_URL", "")).strip()

    def _get_sandbox(self) -> Any:
        """Create (once) the Daytona client + a sandbox instance."""
        if self._sandbox is not None:
            return self._sandbox
        try:
            from daytona import Daytona, DaytonaConfig  # noqa: PLC0415 — lazy SDK
        except ImportError as exc:
            raise RuntimeError(DAYTONA_SDK_INSTALL_HINT) from exc

        api_key = self._api_key()
        if not api_key:
            raise RuntimeError(
                "Daytona API key missing — set DAYTONA_API_KEY (or the configured env name)"
            )
        kwargs: dict[str, Any] = {"api_key": api_key}
        api_url = self._api_url()
        if api_url:
            kwargs["api_url"] = api_url
        daytona = Daytona(DaytonaConfig(**kwargs))
        self._client = daytona
        self._sandbox = daytona.create()
        return self._sandbox

    # -- SandboxBackend contract -------------------------------------------

    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        return self._exec_command(
            ["python", "-c", code], timeout=timeout or self.config.timeout_seconds
        )

    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        return self._exec_command(
            ["bash", "-lc", command], timeout=timeout or self.config.timeout_seconds
        )

    def read_file(self, path: str) -> str:
        try:
            sandbox = self._get_sandbox()
            content = sandbox.fs.get_file(path)
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
            return str(content)
        except Exception as exc:  # SDK/network errors surface honestly
            logger.warning("Daytona read_file failed: %s", exc)
            return f"[Read Error: {exc}]"

    def write_file(self, path: str, content: str) -> bool:
        try:
            sandbox = self._get_sandbox()
            sandbox.fs.set_file(path, content)
            return True
        except Exception as exc:
            logger.warning("Daytona write_file failed: %s", exc)
            return False

    def is_available(self) -> bool:
        """True only when the SDK is importable AND a live key resolves."""
        try:
            import daytona  # noqa: F401, PLC0415 — availability probe only
        except ImportError:
            return False
        return bool(self._api_key())

    # -- internals ----------------------------------------------------------

    def _exec_command(self, argv: list[str], timeout: int) -> SandboxExecutionResult:
        started = time.monotonic()
        try:
            sandbox = self._get_sandbox()
            response = sandbox.process.exec(
                argv, timeout=timeout or self.config.timeout_seconds
            )
            exit_code = int(getattr(response, "exit_code", 0) or 0)
            stdout = str(getattr(response, "result", "") or "")
            stderr = str(getattr(response, "stderr", "") or "")
            return SandboxExecutionResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                success=exit_code == 0,
                error=None if exit_code == 0 else f"exit {exit_code}",
                duration_ms=(time.monotonic() - started) * 1000.0,
            )
        except Exception as exc:
            # Missing SDK / missing key / network failure — honest error result.
            logger.warning("Daytona exec failed: %s", exc)
            return SandboxExecutionResult(
                stdout="",
                stderr=str(exc),
                exit_code=-1,
                success=False,
                error=str(exc),
                duration_ms=(time.monotonic() - started) * 1000.0,
            )

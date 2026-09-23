"""Disabled sandbox (REQ-860 / #227): the default ``provider: "none"``.

Returns honest "sandboxing disabled" results for every operation. The
Settings surface attaches **no** execution tools when this provider is
selected — this backend exists so a misconfigured ``from_config`` path still
behaves predictably instead of silently executing on the host.
"""

from __future__ import annotations

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult

_DISABLED_DETAIL = (
    'Sandboxing is disabled (provider "none"). '
    "Enable a provider in Settings → Sandboxes to attach execution tools."
)


class DisabledSandbox(SandboxBackend):
    """No-op backend backing the default ``none`` provider."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig(backend_type="none")

    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        return SandboxExecutionResult(
            stdout="",
            stderr=_DISABLED_DETAIL,
            exit_code=-1,
            success=False,
            error="sandbox_disabled",
        )

    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        return SandboxExecutionResult(
            stdout="",
            stderr=_DISABLED_DETAIL,
            exit_code=-1,
            success=False,
            error="sandbox_disabled",
        )

    def read_file(self, path: str) -> str:
        return f"[Read Error: {_DISABLED_DETAIL}]"

    def write_file(self, path: str, content: str) -> bool:
        return False

    def is_available(self) -> bool:
        # The disabled backend always "works" — it honestly refuses.
        return True

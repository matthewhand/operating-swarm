"""Core data types and interfaces for the Swarm Sandbox abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


SandboxBackendType = Literal["mock", "local", "langchain_repl", "docker", "e2b"]


@dataclass
class SandboxExecutionResult:
    """Result of code or command execution within a sandbox."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    success: bool = True
    duration_ms: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "metadata": self.metadata,
        }

    @property
    def output(self) -> str:
        """Formatted combined output suitable for returning to an LLM."""
        if not self.success and self.error:
            msg = f"[Execution Error: {self.error}]"
            if self.stderr:
                msg += f"\nStderr:\n{self.stderr}"
            if self.stdout:
                msg += f"\nStdout:\n{self.stdout}"
            return msg.strip()
        if self.stderr and not self.stdout:
            return f"Stderr:\n{self.stderr}"
        if self.stderr and self.stdout:
            return f"Stdout:\n{self.stdout}\nStderr:\n{self.stderr}"
        return self.stdout or "(No output)"


@dataclass
class SandboxConfig:
    """Configuration for a sandbox backend."""

    backend_type: SandboxBackendType = "mock"
    timeout_seconds: int = 30
    work_dir: str | None = None
    allowed_paths: list[str] = field(default_factory=list)
    env_vars: dict[str, str] = field(default_factory=dict)
    inherit_env: bool = False
    sanitize_env: bool = True
    fallback_to_mock: bool = True
    docker_image: str = "python:3.12-slim"
    e2b_api_key: str | None = None
    extra_options: dict[str, Any] = field(default_factory=dict)


class SandboxBackend(ABC):
    """Abstract base class for all sandbox execution backends."""

    @abstractmethod
    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        """Execute a Python code snippet inside the sandbox."""
        raise NotImplementedError

    @abstractmethod
    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        """Execute a bash command string inside the sandbox."""
        raise NotImplementedError

    @abstractmethod
    def read_file(self, path: str) -> str:
        """Read text contents from a file path inside the sandbox."""
        raise NotImplementedError

    @abstractmethod
    def write_file(self, path: str, content: str) -> bool:
        """Write text contents to a file path inside the sandbox."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the backend and its dependencies/runtimes are available."""
        raise NotImplementedError

    def cleanup(self) -> None:
        """Clean up any temporary resources, containers, or connections."""
        pass

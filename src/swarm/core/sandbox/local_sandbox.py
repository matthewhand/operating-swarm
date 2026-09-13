"""Subprocess-isolated local execution sandbox with sanitization and guardrails."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult

logger = logging.getLogger(__name__)

# Sensitive environment variables that should NEVER be passed into untrusted subprocesses
BLOCKED_ENV_PREFIXES: Final[tuple[str, ...]] = (
    "OPENAI_",
    "ANTHROPIC_",
    "GROK_",
    "GEMINI_",
    "GITHUB_",
    "GH_",
    "AWS_",
    "AZURE_",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "KEY",
    "DATABASE_",
    "POSTGRES_",
    "REDIS_",
    "NEON_",
)


class LocalSubprocessSandbox(SandboxBackend):
    """Subprocess-based sandbox enforcing directory containment, timeouts, and sanitized env."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig(backend_type="local")
        self._temp_dir: tempfile.TemporaryDirectory | None = None

        if self.config.work_dir:
            self.work_dir = Path(self.config.work_dir).resolve()
            self.work_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="swarm_sandbox_")
            self.work_dir = Path(self._temp_dir.name).resolve()

        self.allowed_paths = [Path(p).resolve() for p in self.config.allowed_paths]
        if self.work_dir not in self.allowed_paths:
            self.allowed_paths.append(self.work_dir)

    def _build_env(self) -> dict[str, str]:
        """Build an isolated and sanitized environment dictionary."""
        env: dict[str, str] = {}
        if self.config.inherit_env:
            for k, v in os.environ.items():
                if self.config.sanitize_env and any(k.upper().startswith(p) for p in BLOCKED_ENV_PREFIXES):
                    continue
                env[k] = v
        else:
            # Minimal viable environment
            for safe_key in ("PATH", "SYSTEMROOT", "TMP", "TEMP", "USER", "HOME"):
                if safe_key in os.environ:
                    env[safe_key] = os.environ[safe_key]

        # Inject explicitly configured environment variables
        env.update(self.config.env_vars)
        return env

    def _validate_path(self, target_path: str | Path) -> Path:
        """Ensure path is within configured allowed paths."""
        resolved = Path(target_path).resolve()
        if not any(
            resolved == allowed or allowed in resolved.parents for allowed in self.allowed_paths
        ):
            raise PermissionError(f"Access to path '{resolved}' outside sandbox allowed paths is denied")
        return resolved

    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        t_limit = timeout or self.config.timeout_seconds
        t0 = time.perf_counter()
        env = self._build_env()

        try:
            cmd = [sys.executable, "-c", code]
            proc = subprocess.run(
                cmd,
                cwd=str(self.work_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=t_limit,
                check=False,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SandboxExecutionResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                success=(proc.returncode == 0),
                duration_ms=duration_ms,
                error=proc.stderr.strip() if proc.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SandboxExecutionResult(
                stderr=f"Execution timed out after {t_limit} seconds",
                exit_code=124,
                success=False,
                duration_ms=duration_ms,
                error=f"TimeoutExpired ({t_limit}s)",
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SandboxExecutionResult(
                stderr=str(exc),
                exit_code=1,
                success=False,
                duration_ms=duration_ms,
                error=str(exc),
            )

    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        t_limit = timeout or self.config.timeout_seconds
        t0 = time.perf_counter()
        env = self._build_env()

        try:
            # Execute command inside bash or sh
            shell_bin = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
            proc = subprocess.run(
                [shell_bin, "-c", command],
                cwd=str(self.work_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=t_limit,
                check=False,
            )
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SandboxExecutionResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                success=(proc.returncode == 0),
                duration_ms=duration_ms,
                error=proc.stderr.strip() if proc.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SandboxExecutionResult(
                stderr=f"Command timed out after {t_limit} seconds",
                exit_code=124,
                success=False,
                duration_ms=duration_ms,
                error=f"TimeoutExpired ({t_limit}s)",
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return SandboxExecutionResult(
                stderr=str(exc),
                exit_code=1,
                success=False,
                duration_ms=duration_ms,
                error=str(exc),
            )

    def read_file(self, path: str) -> str:
        resolved = self._validate_path(self.work_dir / path if not Path(path).is_absolute() else path)
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return resolved.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> bool:
        resolved = self._validate_path(self.work_dir / path if not Path(path).is_absolute() else path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return True

    def is_available(self) -> bool:
        return True

    def cleanup(self) -> None:
        if self._temp_dir is not None:
            try:
                self._temp_dir.cleanup()
            except Exception as e:
                logger.warning("Error cleaning up sandbox tempdir: %s", e)

"""Ephemeral Docker container execution sandbox."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult

logger = logging.getLogger(__name__)


class DockerSandbox(SandboxBackend):
    """Ephemeral Docker container per session (docker run --rm -v ...) with CPU/memory limits."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig(backend_type="docker")
        self.image = self.config.docker_image or "python:3.12-slim"
        self.work_dir = Path(self.config.work_dir or "/tmp").resolve()
        self.network = str(self.config.extra_options.get("network", "none"))
        self.cpus = str(self.config.extra_options.get("cpus", "1.0"))
        self.memory = str(self.config.extra_options.get("memory", "512m"))
        self._docker_bin = shutil.which("docker")

    def is_available(self) -> bool:
        if not self._docker_bin:
            return False
        try:
            res = subprocess.run(
                [self._docker_bin, "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            return res.returncode == 0
        except Exception:
            return False

    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        if not self.is_available():
            return SandboxExecutionResult(
                success=False,
                exit_code=127,
                error="Docker daemon unavailable or docker command not found on host.",
            )
        timeout_s = timeout or self.config.timeout_seconds
        start_t = time.perf_counter()

        cmd = [
            self._docker_bin,
            "run",
            "--rm",
            f"--network={self.network}",
            f"--cpus={self.cpus}",
            f"--memory={self.memory}",
            "-v",
            f"{self.work_dir}:/workspace",
            "-w",
            "/workspace",
            self.image,
            "sh",
            "-c",
            command,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            duration = (time.perf_counter() - start_t) * 1000
            return SandboxExecutionResult(
                stdout=proc.stdout,
                stderr=proc.stderr,
                exit_code=proc.returncode,
                success=proc.returncode == 0,
                duration_ms=duration,
                metadata={"backend": "docker", "image": self.image},
            )
        except subprocess.TimeoutExpired:
            duration = (time.perf_counter() - start_t) * 1000
            return SandboxExecutionResult(
                success=False,
                exit_code=124,
                error=f"Command timed out after {timeout_s} seconds",
                duration_ms=duration,
                metadata={"backend": "docker", "timeout": True},
            )
        except Exception as exc:
            duration = (time.perf_counter() - start_t) * 1000
            return SandboxExecutionResult(
                success=False,
                exit_code=1,
                error=str(exc),
                duration_ms=duration,
                metadata={"backend": "docker"},
            )

    def execute_python(self, code: str, timeout: int | None = None) -> SandboxExecutionResult:
        escaped_cmd = f"python3 -c {subprocess.list2cmdline([code])}"
        return self.execute_bash(escaped_cmd, timeout=timeout)

    def read_file(self, path: str) -> str:
        target = (self.work_dir / path).resolve()
        if not str(target).startswith(str(self.work_dir)):
            raise PermissionError(f"Path escape denied: {path}")
        return target.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> bool:
        target = (self.work_dir / path).resolve()
        if not str(target).startswith(str(self.work_dir)):
            raise PermissionError(f"Path escape denied: {path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return True

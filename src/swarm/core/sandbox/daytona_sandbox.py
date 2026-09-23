"""Daytona cloud sandbox backend (REQ-860 / #227, REQ-863 / #253).

Executes commands in Daytona sandboxes (isolated microVMs) via the official
``daytona`` SDK (https://www.daytona.io/docs/en/python-sdk/). The SDK and its
config are **lazy** — importing this module never requires the SDK, and every
execution degrades to an honest error result when the SDK or credentials are
missing. API keys are read from the environment (``DAYTONA_API_KEY`` /
``DAYTONA_API_URL``) or an operator-configured env-var **name**; tokens are
never persisted or logged.

REQ-863: ``cleanup()`` stops/deletes the remote microVM, create() requests an
idle auto-stop TTL, and ``sync_workspace()`` can seed the blank disk from a
local project directory.
"""

from __future__ import annotations

import atexit
import logging
import os
import shlex
import time
from pathlib import Path
from typing import Any

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult

logger = logging.getLogger(__name__)

DAYTONA_SDK_INSTALL_HINT = (
    "Daytona SDK not installed — run: pip install daytona (or uv pip install daytona)"
)

_SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".uv",
        "dist",
        "build",
        ".worktrees",
        "htmlcov",
        ".next",
        ".turbo",
    }
)

_DEFAULT_REMOTE_ROOT = "/home/daytona/project"
_DEFAULT_SYNC_MAX_FILES = 200
_DEFAULT_SYNC_MAX_BYTES = 512 * 1024


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
        self._atexit_registered = False

    # -- lazy SDK plumbing -------------------------------------------------

    def _api_key(self) -> str:
        extra = self.config.extra_options or {}
        return _resolve_api_key(extra.get("daytona_api_key_env"))

    def _api_url(self) -> str:
        extra = self.config.extra_options or {}
        return str(extra.get("daytona_api_url") or os.environ.get("DAYTONA_API_URL", "")).strip()

    def _auto_stop_interval(self) -> int:
        extra = self.config.extra_options or {}
        raw = extra.get("auto_stop_interval", getattr(self.config, "auto_stop_interval", 15))
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return 15

    def _register_cleanup(self) -> None:
        if self._atexit_registered:
            return
        atexit.register(self.cleanup)
        self._atexit_registered = True

    def _create_remote(self, daytona: Any) -> Any:
        """Create a microVM, requesting idle auto-stop when the SDK supports it."""
        minutes = self._auto_stop_interval()
        try:
            from daytona import CreateSandboxFromSnapshotParams  # noqa: PLC0415

            params = CreateSandboxFromSnapshotParams(
                language="python",
                auto_stop_interval=minutes,
            )
            return daytona.create(params)
        except Exception as exc:
            logger.debug("Daytona create-with-params failed (%s); trying kwargs/bare create", exc)
        try:
            return daytona.create(auto_stop_interval=minutes)
        except TypeError:
            return daytona.create()

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
        self._sandbox = self._create_remote(daytona)
        self._register_cleanup()
        extra = self.config.extra_options or {}
        if getattr(self.config, "sync_workspace", False) or extra.get("sync_workspace"):
            try:
                self.sync_workspace()
            except Exception as exc:
                logger.warning("Daytona workspace sync failed: %s", exc)
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
            content = self._download_bytes(sandbox, path)
            if isinstance(content, bytes):
                return content.decode("utf-8", errors="replace")
            return str(content)
        except Exception as exc:  # SDK/network errors surface honestly
            logger.warning("Daytona read_file failed: %s", exc)
            return f"[Read Error: {exc}]"

    def write_file(self, path: str, content: str) -> bool:
        try:
            sandbox = self._get_sandbox()
            return self._upload_bytes(sandbox, path, content.encode("utf-8"))
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

    # -- #719 file transfer surface (manager-facing, honest degrade) --------

    def upload_bytes(self, remote_path: str, data: bytes) -> bool:
        """Upload bytes into the sandbox; False (never raise) when unusable."""
        if not self.is_available():
            return False
        try:
            sandbox = self._get_sandbox()
            return bool(self._upload_bytes(sandbox, remote_path, data))
        except Exception as exc:
            logger.debug("Daytona upload_bytes failed: %s", exc)
            return False

    def download_bytes(self, remote_path: str) -> bytes | str:
        """Download bytes from the sandbox; an error string when unusable."""
        if not self.is_available():
            return "sandbox not configured — DAYTONA_API_KEY missing or SDK absent"
        try:
            sandbox = self._get_sandbox()
            return self._download_bytes(sandbox, remote_path)
        except Exception as exc:
            return f"download failed: {exc}"

    def cleanup(self) -> None:
        """Stop and delete the remote microVM so it cannot leak cloud billing.

        Tries client.delete / client.remove / sandbox.delete / *.stop in that
        order. Idempotent: a second call is a no-op.
        """
        sandbox = self._sandbox
        client = self._client
        self._sandbox = None
        self._client = None
        if sandbox is None:
            return
        sandbox_id = getattr(sandbox, "id", None) or "?"
        errors: list[str] = []

        def _call(label: str, fn: Any, *args: Any) -> bool:
            if not callable(fn):
                return False
            try:
                fn(*args)
                logger.info("Daytona sandbox %s destroyed via %s", sandbox_id, label)
                return True
            except Exception as exc:
                errors.append(f"{label}: {exc}")
                return False

        if client is not None:
            for name in ("delete", "remove"):
                if _call(f"client.{name}", getattr(client, name, None), sandbox):
                    return
        for name in ("delete", "remove"):
            if _call(f"sandbox.{name}", getattr(sandbox, name, None)):
                return
        if client is not None and _call("client.stop", getattr(client, "stop", None), sandbox):
            return
        if _call("sandbox.stop", getattr(sandbox, "stop", None)):
            return
        if errors:
            logger.warning("Daytona cleanup failed for %s: %s", sandbox_id, "; ".join(errors))

    def sync_workspace(
        self,
        local_dir: str | None = None,
        *,
        remote_root: str | None = None,
    ) -> int:
        """Upload files from *local_dir* (default ``work_dir``) into the sandbox.

        Skips VCS/build/venv trees and caps file count/size so a large repo
        cannot stall sandbox start. Returns the number of files uploaded.
        """
        extra = self.config.extra_options or {}
        root = Path(local_dir or self.config.work_dir or "").expanduser()
        if not root.is_dir():
            logger.debug("Daytona workspace sync skipped — not a directory: %s", root)
            return 0
        remote_root = (
            remote_root
            or str(extra.get("remote_root") or _DEFAULT_REMOTE_ROOT)
        ).rstrip("/")
        sandbox = self._sandbox
        if sandbox is None:
            sandbox = self._get_sandbox()
        max_files = int(extra.get("sync_max_files") or _DEFAULT_SYNC_MAX_FILES)
        max_bytes = int(extra.get("sync_max_bytes") or _DEFAULT_SYNC_MAX_BYTES)
        uploaded = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")
            ]
            for name in filenames:
                if uploaded >= max_files:
                    logger.info("Daytona workspace sync capped at %s files", max_files)
                    return uploaded
                local = Path(dirpath) / name
                try:
                    size = local.stat().st_size
                except OSError:
                    continue
                if size > max_bytes:
                    continue
                rel = local.relative_to(root).as_posix()
                remote = f"{remote_root}/{rel}"
                try:
                    data = local.read_bytes()
                except OSError:
                    continue
                if self._upload_bytes(sandbox, remote, data):
                    uploaded += 1
        logger.info("Daytona workspace sync uploaded %s files from %s", uploaded, root)
        return uploaded

    # -- internals ----------------------------------------------------------

    def _upload_bytes(self, sandbox: Any, remote_path: str, data: bytes) -> bool:
        fs = getattr(sandbox, "fs", None)
        if fs is None:
            return False
        if hasattr(fs, "upload_file"):
            try:
                fs.upload_file(data, remote_path)
                return True
            except TypeError:
                try:
                    fs.upload_file(remote_path, data)
                    return True
                except Exception as exc:
                    logger.debug("Daytona upload_file failed: %s", exc)
            except Exception as exc:
                logger.debug("Daytona upload_file failed: %s", exc)
        if hasattr(fs, "set_file"):
            try:
                fs.set_file(remote_path, data.decode("utf-8", errors="replace"))
                return True
            except Exception as exc:
                logger.debug("Daytona set_file failed: %s", exc)
        return False

    def _download_bytes(self, sandbox: Any, remote_path: str) -> bytes | str:
        fs = getattr(sandbox, "fs", None)
        if fs is None:
            raise RuntimeError("Daytona sandbox has no filesystem API")
        for name, args in (
            ("get_file", (remote_path,)),
            ("download_file", (remote_path,)),
            ("download", (remote_path,)),
        ):
            fn = getattr(fs, name, None)
            if not callable(fn):
                continue
            try:
                return fn(*args)
            except Exception:
                continue
        raise RuntimeError(f"Daytona filesystem cannot read {remote_path!r}")

    def _exec_command(self, argv: list[str], timeout: int) -> SandboxExecutionResult:
        started = time.monotonic()
        try:
            sandbox = self._get_sandbox()
            process = getattr(sandbox, "process", None)
            if process is None or not hasattr(process, "exec"):
                raise RuntimeError("Daytona sandbox has no process.exec")
            try:
                response = process.exec(argv, timeout=timeout or self.config.timeout_seconds)
            except TypeError:
                cmd = " ".join(shlex.quote(part) for part in argv)
                response = process.exec(cmd, timeout=timeout or self.config.timeout_seconds)
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

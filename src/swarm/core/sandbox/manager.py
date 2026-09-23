"""Sandbox manager: factory, configuration, and openai-agents tool adapter."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from .base import SandboxBackend, SandboxConfig, SandboxExecutionResult
from .daytona_sandbox import DaytonaSandbox
from .disabled_sandbox import DisabledSandbox
from .langchain_sandbox import LangChainSandboxHarness
from .local_sandbox import LocalSubprocessSandbox
from .mock_sandbox import MockSandbox

logger = logging.getLogger(__name__)

# REQ-860 / #227: Settings-facing provider names map to backend types.
# "none" is the default (no execution tools), "bare_metal" is the honest
# name for direct host execution (dangerous).
SANDBOX_PROVIDER_ALIASES: dict[str, str] = {
    "none": "none",
    "bare_metal": "local",
    "local": "local",
    "daytona": "daytona",
    "mock": "mock",
}

# Fresh installs attach no execution tools (REQ-863 / #253).
DEFAULT_SANDBOX_PROVIDER = "none"

_DEFAULT_MANAGER: SandboxManager | None = None


def _raw_provider_name(raw_config: dict[str, Any]) -> str:
    """Settings ``provider`` or legacy ``backend_type`` / ``backend``."""
    for key in ("provider", "backend_type", "backend"):
        value = raw_config.get(key)
        if value is not None and str(value).strip():
            return str(value).strip().lower()
    return ""


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
        """Create a SandboxManager instance from a dictionary config block.

        An empty dict keeps the legacy ``local`` backend (tests / explicit
        callers). Settings-driven construction uses :meth:`from_settings`,
        which defaults to ``none``.
        """
        if not raw_config:
            raw_config = {}

        raw_name = _raw_provider_name(raw_config)
        # Empty explicit config → legacy local. Settings path always passes provider.
        b_type = SANDBOX_PROVIDER_ALIASES.get(raw_name, raw_name) if raw_name else "local"
        is_bare_metal = raw_name == "bare_metal" or bool(
            raw_config.get("unrestricted_host") or raw_config.get("dangerous_confirmed")
        )
        timeout = raw_config.get("timeout_seconds") or raw_config.get("timeout") or 30
        work_dir = raw_config.get("work_dir") or raw_config.get("workspace") or os.getcwd()
        allowed = raw_config.get("allowed_paths") or [work_dir]
        env_vars = raw_config.get("env_vars") or {}
        inherit_env = bool(raw_config["inherit_env"]) if "inherit_env" in raw_config else True
        sanitize_env = (
            bool(raw_config["sanitize_env"]) if "sanitize_env" in raw_config else (not is_bare_metal)
        )
        fallback_to_mock = bool(raw_config.get("fallback_to_mock", True))
        extra = dict(raw_config.get("extra_options") or {})
        extra.setdefault("provider", raw_name or b_type)
        if is_bare_metal:
            extra["unrestricted_host"] = True
            extra["bare_metal"] = True
            extra["dangerous_confirmed"] = True

        auto_stop = raw_config.get("auto_stop_interval", extra.get("auto_stop_interval", 15))
        try:
            auto_stop_interval = max(0, int(auto_stop))
        except (TypeError, ValueError):
            auto_stop_interval = 15
        extra["auto_stop_interval"] = auto_stop_interval
        sync_workspace = bool(raw_config.get("sync_workspace", extra.get("sync_workspace", False)))
        extra["sync_workspace"] = sync_workspace

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
            extra_options=extra,
            unrestricted_host=is_bare_metal,
            auto_stop_interval=auto_stop_interval,
            sync_workspace=sync_workspace,
        )
        # Daytona settings (REQ-860): env-var *name* + optional API URL.
        if raw_config.get("daytona_api_key_env"):
            cfg.extra_options["daytona_api_key_env"] = str(raw_config["daytona_api_key_env"])
        if raw_config.get("daytona_api_url"):
            cfg.extra_options["daytona_api_url"] = str(raw_config["daytona_api_url"])
        return cls(config=cfg)

    @classmethod
    def from_settings(cls, config: dict[str, Any] | None = None) -> SandboxManager:
        """Build a manager from ``settings.sandbox`` (default provider ``none``)."""
        raw: dict[str, Any] = {}
        cfg = config
        if cfg is None:
            try:
                from swarm.core.remotes import load_raw_config

                cfg = load_raw_config()[0]
            except Exception:
                cfg = {}
        if isinstance(cfg, dict):
            settings = cfg.get("settings") if isinstance(cfg.get("settings"), dict) else {}
            block = settings.get("sandbox") if isinstance(settings.get("sandbox"), dict) else {}
            raw = dict(block) if isinstance(block, dict) else {}
        provider = str(raw.get("provider") or DEFAULT_SANDBOX_PROVIDER).strip().lower()
        raw["provider"] = provider if provider else DEFAULT_SANDBOX_PROVIDER
        return cls.from_config(raw)

    def _init_backend(self, cfg: SandboxConfig) -> SandboxBackend:
        """Instantiate the configured execution backend."""
        if cfg.backend_type == "none":
            return DisabledSandbox(cfg)
        if cfg.backend_type == "mock":
            return MockSandbox(cfg)
        elif cfg.backend_type == "langchain_repl":
            return LangChainSandboxHarness(cfg)
        elif cfg.backend_type == "daytona":
            return DaytonaSandbox(cfg)
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
        try:
            return self._backend.execute_python(code, timeout=timeout)
        except Exception as exc:
            result = self._not_configured_result()
            result.error = str(exc) if self._backend.is_available() else result.error
            return result

    def execute_bash(self, command: str, timeout: int | None = None) -> SandboxExecutionResult:
        try:
            return self._backend.execute_bash(command, timeout=timeout)
        except Exception as exc:
            result = self._not_configured_result()
            result.error = str(exc) if self._backend.is_available() else result.error
            return result

    def _not_configured_result(self) -> SandboxExecutionResult:
        """#719: the honest degrade — an explicit message, never a raise."""
        return SandboxExecutionResult(
            stdout="",
            stderr="",
            exit_code=1,
            success=False,
            error=(
                "Sandbox not configured — select a sandbox provider in Settings "
                "(or set this agent's sandbox opt-in) and supply DAYTONA_API_KEY."
            ),
        )

    def _backend_available(self) -> bool:
        available = getattr(self._backend, "is_available", None)
        return bool(available()) if callable(available) else True

    def _backend_upload(self, path: str, data: bytes) -> bool:
        """Upload bytes via the backend when supported; honest False otherwise."""
        available = getattr(self._backend, "is_available", None)
        if callable(available) and not available():
            return False
        uploader = getattr(self._backend, "upload_bytes", None)
        if not callable(uploader):
            return False
        try:
            return bool(uploader(path, data))
        except Exception as exc:
            logger.debug("sandbox upload failed: %s", exc)
            return False

    def _backend_download(self, path: str) -> bytes | str:
        """Download bytes via the backend; an explicit error string on failure."""
        downloader = getattr(self._backend, "download_bytes", None)
        if not callable(downloader):
            return "[Download Error: sandbox backend does not support file download]"
        try:
            out = downloader(path)
            return out if isinstance(out, bytes) else f"[Download Error: {out}]"
        except Exception as exc:
            return f"[Download Error: {exc}]"

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

        def sandbox_upload_file(path: str, content_b64: str) -> str:
            """Upload base64-encoded bytes to a path in the sandbox (#719)."""
            try:
                import base64

                data = base64.b64decode(content_b64, validate=True)
            except Exception as e:
                return f"[Upload Error: invalid base64: {e}]"
            if not self._backend_available():
                return "[Upload Error: sandbox not configured — DAYTONA_API_KEY missing or SDK absent]"
            ok = self._backend_upload(path, data)
            return f"Uploaded {len(data)} bytes to {path}" if ok else "[Upload Failed]"

        def sandbox_download_file(path: str) -> str:
            """Download a file from the sandbox as base64 text (#719)."""
            result = self._backend_download(path)
            if isinstance(result, bytes):
                import base64

                return base64.b64encode(result).decode("ascii")
            return result

        return {
            "sandbox_run_python": sandbox_run_python,
            "sandbox_run_bash": sandbox_run_bash,
            "sandbox_read_file": sandbox_read_file,
            "sandbox_write_file": sandbox_write_file,
            "sandbox_upload_file": sandbox_upload_file,
            "sandbox_download_file": sandbox_download_file,
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

    def tools_enabled(self) -> bool:
        """False for the default ``none`` / DisabledSandbox provider."""
        return not isinstance(self._backend, DisabledSandbox)


def get_default_sandbox_manager() -> SandboxManager:
    """Return or initialize the process-wide default SandboxManager.

    Driven by ``settings.sandbox`` so a fresh install stays on ``none``.
    """
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = SandboxManager.from_settings()
    return _DEFAULT_MANAGER


def reset_default_sandbox_manager() -> None:
    """Reset the global default SandboxManager (useful in tests)."""
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is not None:
        _DEFAULT_MANAGER.cleanup()
        _DEFAULT_MANAGER = None


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", None) or getattr(tool, "__name__", "") or "")


def sandbox_function_tools(*, config: dict[str, Any] | None = None) -> list[Any]:
    """openai-agents tools for the configured provider, or ``[]`` when ``none``."""
    manager = SandboxManager.from_settings(config)
    if not manager.tools_enabled():
        return []
    return manager.as_function_tools()


def merge_sandbox_tools(
    tools: list[Any] | None,
    *,
    config: dict[str, Any] | None = None,
) -> list[Any]:
    """Append sandbox tools that are not already present (matched by name)."""
    merged = list(tools or [])
    extra = sandbox_function_tools(config=config)
    if not extra:
        return merged
    existing = {_tool_name(t) for t in merged}
    for tool in extra:
        name = _tool_name(tool)
        if name and name in existing:
            continue
        merged.append(tool)
        if name:
            existing.add(name)
    return merged


def attach_sandbox_tools_to_agent(agent: Any, *, config: dict[str, Any] | None = None) -> Any:
    """Mutate ``agent.tools`` in place when a real sandbox provider is selected."""
    extra = sandbox_function_tools(config=config)
    if not extra or agent is None:
        return agent
    current = list(getattr(agent, "tools", None) or [])
    existing = {_tool_name(t) for t in current}
    changed = False
    for tool in extra:
        name = _tool_name(tool)
        if name and name in existing:
            continue
        current.append(tool)
        if name:
            existing.add(name)
        changed = True
    if not changed:
        return agent
    try:
        agent.tools = current
    except Exception:
        try:
            object.__setattr__(agent, "tools", current)
        except Exception:
            logger.debug("Could not attach sandbox tools to agent %r", agent, exc_info=True)
    return agent

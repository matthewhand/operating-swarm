"""Inject Swarm ``mcpServers`` into catalog CLI argv the way each CLI accepts.

OpenMausBot mounts MCP into the CLI process (Claude ``--mcp-config`` file, ACP
``session/new`` ``mcpServers``). Swarm's :class:`CliAdapter` is one-shot print
mode; this module only adds flags the CLI already documents. If the CLI has no
MCP flag, argv is left unchanged so print mode still works.

Secrets stay in the 0600 mcp.json ``env`` / ``headers`` — never on argv.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Catalog CLIs we will try to mount Swarm MCP into.
MCP_CLI_NAMES = frozenset({"grok", "agy", "claude"})

_HELP_CACHE: dict[str, str] = {}


def mcp_entry_disabled(spec: Any) -> bool:
    """True when a server config is explicitly off.

    Boolean ``False`` and ``"false"`` (any case, surrounding space) count.
    A missing ``enabled`` flag stays on.
    """
    if not isinstance(spec, Mapping):
        return False
    flag = spec.get("enabled")
    if flag is False:
        return True
    return isinstance(flag, str) and flag.strip().lower() == "false"


def normalize_mcp_servers(raw: Any) -> dict[str, dict[str, Any]]:
    """Keep stdio (command/args/env) and HTTP (url/type/headers) MCP entries."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, spec in raw.items():
        key = str(name).strip()
        if not key or not isinstance(spec, dict):
            continue
        if mcp_entry_disabled(spec):
            continue
        entry: dict[str, Any] = {}
        command = spec.get("command")
        if isinstance(command, str) and command.strip():
            entry["command"] = command
            args = spec.get("args")
            entry["args"] = [str(a) for a in args] if isinstance(args, list) else []
            env = spec.get("env")
            if isinstance(env, dict) and env:
                entry["env"] = {str(k): str(v) for k, v in env.items()}
        elif isinstance(spec.get("url"), str) and spec["url"].strip():
            entry["url"] = spec["url"]
            transport = spec.get("type") or spec.get("transport")
            if isinstance(transport, str) and transport.strip():
                entry["type"] = transport
            headers = spec.get("headers")
            if isinstance(headers, dict) and headers:
                entry["headers"] = {str(k): str(v) for k, v in headers.items()}
        else:
            continue
        out[key] = entry
    return out


def parse_mcp_help_flags(help_text: str) -> dict[str, bool]:
    """Detect ``--mcp-config`` vs ACP-only support from ``cli --help`` text."""
    text = help_text or ""
    lower = text.lower()
    mcp_config = "--mcp-config" in lower or "mcp-config" in lower
    acp = (
        "--acp" in lower
        or "agent client protocol" in lower
        or "session/new" in lower
        or "mcpservers" in lower.replace("_", "")
    )
    return {"mcp_config": mcp_config, "acp": acp}


def probe_cli_help(executable: str, *, timeout: float = 3.0) -> str:
    """Run ``executable --help``. Empty in pytest and on any probe failure.

    Resolves the binary with :func:`cli_catalog.which_cli` and runs it with
    the same ``PATH`` as CLI runs (``host_cli_path``).
    """
    if os.getenv("PYTEST_CURRENT_TEST"):
        return ""
    if not executable:
        return ""
    from swarm.core.cli_catalog import host_cli_path, which_cli

    resolved = (
        executable
        if os.path.sep in executable
        else (which_cli(executable) or executable)
    )
    if os.path.sep in resolved and not (
        os.path.isfile(resolved) and os.access(resolved, os.X_OK)
    ):
        return ""
    cached = _HELP_CACHE.get(resolved)
    if cached is not None:
        return cached
    text = ""
    env = os.environ.copy()
    env["PATH"] = host_cli_path(env.get("PATH", ""))
    try:
        proc = subprocess.run(
            [resolved, "--help"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        text = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    except Exception:
        text = ""
    _HELP_CACHE[resolved] = text
    return text


def write_mcp_config_file(servers: dict[str, dict[str, Any]]) -> str:
    """Write ``{mcpServers: ...}`` to a private temp file; return its path."""
    directory = tempfile.mkdtemp(prefix="swarm-mcp-")
    path = Path(directory) / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")
    os.chmod(path, 0o600)
    return str(path)


def cleanup_mcp_config_file(path: str | None) -> None:
    if not path:
        return
    try:
        shutil.rmtree(str(Path(path).parent), ignore_errors=True)
    except Exception:
        logger.debug("Could not remove MCP config %s", path, exc_info=True)


def inject_mcp_argv(
    cli_name: str,
    argv: list[str],
    servers: Any,
    *,
    help_text: str | None = None,
    executable: str | None = None,
) -> tuple[list[str], str | None]:
    """Return ``(argv, mcp_config_path)``. Path is None when nothing was injected.

    Claude always uses ``--mcp-config``. grok/agy use that flag only when
    ``--help`` (or *help_text*) documents it. ACP-only CLIs keep print-mode argv.
    """
    name = (cli_name or "").strip().lower()
    normalized = normalize_mcp_servers(servers)
    if not argv or not normalized or name not in MCP_CLI_NAMES:
        return list(argv), None

    use_mcp_config = name == "claude"
    if name in ("grok", "agy"):
        text = help_text if help_text is not None else probe_cli_help(executable or argv[0])
        flags = parse_mcp_help_flags(text)
        use_mcp_config = flags["mcp_config"]
        if not use_mcp_config:
            return list(argv), None

    if not use_mcp_config:
        return list(argv), None

    try:
        path = write_mcp_config_file(normalized)
    except OSError:
        logger.warning("MCP config file could not be written; running %s without MCP", name)
        return list(argv), None
    return list(argv) + ["--mcp-config", path], path

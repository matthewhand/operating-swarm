"""Herdr as a remotes kind (REQ-64 + REQ-100).

Settings + ``swarm-cli remotes`` persist ``remotes.herdr``. That is **opt-in**:
there is no baked LAN host. Missing config is a clear error, not a silent
other-host.

REQ-100 hop model
-----------------
* **Local Herdr:** Operating Swarm talks to Herdr on this host (official ``herdr``
  CLI; no SSH). Herdr drives the local CLIs it wraps (agy / pi / grok / …).
  A localhost HTTP base is optional and only when the user chose that
  (REQ-64 health/list ``GET /health``, ``GET /agents`` still fit).
* **Remote Herdr:** SSH to the Herdr host, then talk to Herdr there. Health /
  list / send / interrogate CLI X go over that SSH hop. This is **not** an
  HTTP remote like OpenMousBot / Hermes / Rakazo.

Tests stub SSH (and HTTP for the leftover local path). Do not point CI at a
live LAN Herdr. Identity is an env-var *name* only — never a private key.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from swarm.herdr.client import (
    HerdrClient,
    members_from_agent_list,
    members_from_workspace_list,
)
from swarm.herdr.ssh import (
    SSH_NOT_CONFIGURED,
    SSHNotConfiguredError,
    SSHTarget,
    SSHTransport,
    require_ssh_target,
)

KIND_ID = "herdr"
HEALTH_PATH = "/health"
LIST_PATH = "/agents"
API_KEY_ENV = "HERDR_API_KEY"
BASE_URL_ENV = "HERDR_BASE_URL"
SSH_HOST_ENV = "HERDR_SSH_HOST"
SSH_USER_ENV = "HERDR_SSH_USER"
SSH_PORT_ENV = "HERDR_SSH_PORT"
SSH_IDENTITY_ENV = "HERDR_SSH_IDENTITY"
SSH_AGENT_ENV = "HERDR_SSH_AGENT"
HERDR_MODE_LOCAL = "local"
HERDR_MODE_SSH = "ssh"

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})

HERDR_NOT_CONFIGURED = (
    "Herdr remote is not configured. Add kind=herdr in Settings as a local "
    "instance (localhost URL only when you choose that) or as SSH "
    "(host + user; ssh_identity_env name only — never a private key). "
    "Remote Herdr is SSH-shaped, not HTTP like OpenMousBot / Hermes / Rakazo. "
    "Or run: swarm-cli remotes set herdr --herdr-mode local. "
    "Refusing to guess another host."
)

HERDR_HTTP_REMOTE_REFUSED = (
    "Remote Herdr is SSH-shaped, not an HTTP remote like OpenMousBot / "
    "Hermes / Rakazo. For a local instance set herdr_mode=local (optional "
    "localhost URL). For a remote instance set ssh_host + ssh_user "
    "(optional ssh_identity_env / ssh_agent). Refusing to guess a host."
)

HERDR_SSH_NOT_CONFIGURED = SSH_NOT_CONFIGURED

HOP_MODEL = (
    "One hop: Operating Swarm SSHs to the Herdr host, then talks to Herdr on that "
    "host (official herdr CLI). Herdr wraps the CLIs it manages there "
    "(agy / pi / grok / …). Local Herdr skips SSH and talks to Herdr on "
    "this host. Distinct from HTTP remotes (OpenMousBot / Hermes / Rakazo)."
)


def not_configured_message() -> str:
    return HERDR_NOT_CONFIGURED


def is_localhost_base(base_url: str) -> bool:
    """True when the user configured a loopback base (omit ``herdr --remote``)."""
    raw = (base_url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = (parsed.hostname or "").strip().lower()
    return host in _LOCAL_HOSTS


def cli_remote_from_base(base_url: str) -> str:
    """Value for ``herdr --remote``. Empty means localhost (omit the flag).

    Raises ``ValueError`` when *base_url* is missing so callers cannot silently
    fall through to another host.
    """
    raw = (base_url or "").strip()
    if not raw:
        raise ValueError(HERDR_NOT_CONFIGURED)
    if is_localhost_base(raw):
        return ""
    return raw.rstrip("/")


def resolve_herdr_mode(spec: Any) -> str:
    """``local`` or ``ssh``. Explicit mode wins; else infer from fields."""
    explicit = str(getattr(spec, "herdr_mode", "") or "").strip().lower()
    if explicit in (HERDR_MODE_LOCAL, HERDR_MODE_SSH):
        return explicit
    if getattr(spec, "ssh_host", "") or getattr(spec, "ssh_user", ""):
        return HERDR_MODE_SSH
    base = str(getattr(spec, "base_url", "") or "").strip()
    if base and not is_localhost_base(base):
        return HERDR_MODE_SSH
    return HERDR_MODE_LOCAL


def ssh_target_from_spec(spec: Any) -> SSHTarget:
    """SSH target from a ``RemoteSpec`` (or duck-typed object)."""
    return require_ssh_target(
        host=str(getattr(spec, "ssh_host", "") or ""),
        user=str(getattr(spec, "ssh_user", "") or ""),
        port=getattr(spec, "ssh_port", 22),
        identity_env=str(getattr(spec, "ssh_identity_env", "") or ""),
        use_agent=bool(getattr(spec, "ssh_agent", True)),
    )


def herdr_client_from_spec(
    spec: Any,
    **kwargs: Any,
) -> HerdrClient:
    """Local ``herdr`` or SSH-wrapped ``herdr`` on the remote host.

    SSH hop runs ``herdr …`` *on that host* (no ``--remote``). Local omits
    SSH entirely. A leftover non-localhost HTTP base without SSH fields is
    a clear error — we do not treat Herdr as HTTP.
    """
    mode = resolve_herdr_mode(spec)
    transport = kwargs.pop("transport", None)
    ssh_runner = kwargs.pop("ssh_runner", None)
    ssh_environ = kwargs.pop("ssh_environ", None)
    if mode == HERDR_MODE_SSH:
        target = ssh_target_from_spec(spec)
        if transport is None:
            transport = SSHTransport(target, runner=ssh_runner, environ=ssh_environ)
        return HerdrClient(remote="", transport=transport, **kwargs)
    return HerdrClient(remote="", **kwargs)


def members_from_http_list(payload: Any, *, remote: str = "") -> list[dict[str, Any]]:
    """Map a stub/HTTP list body onto addable ``kind=herdr`` members."""
    if isinstance(payload, dict):
        if payload.get("agents") is not None or (
            isinstance(payload.get("result"), dict) and "agents" in payload["result"]
        ):
            found = members_from_agent_list(payload, remote=remote)
            if found:
                return found
        if payload.get("workspaces") is not None or (
            isinstance(payload.get("result"), dict) and "workspaces" in payload["result"]
        ):
            found = members_from_workspace_list(payload, remote=remote)
            if found:
                return found
        inner = payload.get("data") or payload.get("items") or payload.get("members")
        if inner is not None and inner is not payload:
            found = members_from_http_list(inner, remote=remote)
            if found:
                return found
    if isinstance(payload, list):
        as_agents = members_from_agent_list(payload, remote=remote)
        if as_agents:
            return as_agents
        return members_from_workspace_list({"workspaces": payload}, remote=remote)
    return []


def uses_local_http_health(spec: Any) -> bool:
    """REQ-64 leftover: local Herdr with a user-chosen localhost HTTP base."""
    if resolve_herdr_mode(spec) != HERDR_MODE_LOCAL:
        return False
    base = str(getattr(spec, "base_url", "") or "").strip()
    return bool(base) and is_localhost_base(base)


# Re-export for callers that imported SSH types from this module.
__all__ = [
    "API_KEY_ENV",
    "BASE_URL_ENV",
    "HEALTH_PATH",
    "HERDR_HTTP_REMOTE_REFUSED",
    "HERDR_MODE_LOCAL",
    "HERDR_MODE_SSH",
    "HERDR_NOT_CONFIGURED",
    "HERDR_SSH_NOT_CONFIGURED",
    "HOP_MODEL",
    "KIND_ID",
    "LIST_PATH",
    "SSHNotConfiguredError",
    "SSH_HOST_ENV",
    "SSH_USER_ENV",
    "cli_remote_from_base",
    "herdr_client_from_spec",
    "is_localhost_base",
    "members_from_http_list",
    "not_configured_message",
    "resolve_herdr_mode",
    "ssh_target_from_spec",
    "uses_local_http_health",
]

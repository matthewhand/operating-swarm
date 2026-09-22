"""SSH transport for remote Herdr (REQ-100 / #463).

Hop model
---------
Open Swarm SSHs to the **Herdr host**, then talks to Herdr there (official
``herdr`` CLI). Herdr wraps the CLIs it already manages on that host
(agy / pi / grok / …). One hop. This is **not** an HTTP remote like
OpenMousBot / Hermes / Rakazo, and we do not SSH past Herdr as a second
product hop.

Local Herdr never uses this module.

Tests stub the runner. CI must not open a live SSH session or guess a host.
Identity is an **env-var name** whose value is a key *path* — never a
private key in config or the repo.
"""

from __future__ import annotations

import getpass
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from swarm.services.secure_subprocess import execute_command_safe

Runner = Callable[..., subprocess.CompletedProcess]

SSH_NOT_CONFIGURED = (
    "Remote Herdr is SSH-shaped and needs ssh_host + ssh_user "
    "(optional ssh_port, ssh_identity_env, ssh_agent). "
    "This is not an HTTP remote like OpenMousBot / Hermes / Rakazo. "
    "Refusing to guess a host. Add kind=herdr in Settings as SSH, or: "
    "swarm-cli remotes set herdr --herdr-mode ssh --ssh-host <host> "
    "--ssh-user <user> --ssh-identity-env HERDR_SSH_IDENTITY."
)

SSH_IDENTITY_UNSET = (
    "ssh_identity_env is set but that environment variable is empty. "
    "Put a key *path* in the env var (name only in config). "
    "Never paste a private key. Refusing to guess a host."
)

SSH_IDENTITY_IS_KEY = (
    "ssh_identity_env resolved to key material, not a file path. "
    "Store the path to an identity file in that env var. "
    "Never persist or pass a private key."
)

_DEFAULT_PROCESS_TIMEOUT = 30


class SSHError(Exception):
    """Failure building or running an SSH hop to a Herdr host."""


class SSHNotConfiguredError(SSHError):
    """SSH remote Herdr is missing host/user (or a usable identity)."""


@dataclass(frozen=True)
class SSHTarget:
    """Connection details for one Herdr host. No private keys."""

    host: str
    user: str
    port: int = 22
    identity_env: str = ""
    use_agent: bool = True

    def destination(self) -> str:
        return f"{self.user}@{self.host}"

    def public_label(self) -> str:
        port = f":{self.port}" if self.port and self.port != 22 else ""
        return f"{self.user}@{self.host}{port}"


def looks_like_key_material(value: str) -> bool:
    """True when *value* looks like PEM / OpenSSH key text, not a path."""
    blob = (value or "").strip()
    if not blob:
        return False
    upper = blob.upper()
    if "BEGIN" in upper and "PRIVATE KEY" in upper:
        return True
    if blob.startswith(("ssh-rsa ", "ssh-ed25519 ", "ssh-dss ", "ecdsa-sha2-")):
        return True
    return bool("\n" in blob and "PRIVATE" in upper)


def _as_env_name(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("${") and raw.endswith("}") and len(raw) > 3:
        raw = raw[2:-1].strip()
    return raw


def resolve_identity_path(identity_env: str, environ: dict[str, str] | None = None) -> str:
    """Return the identity *file path* from ``identity_env``, or empty.

    Raises ``SSHNotConfiguredError`` when the env is named but unset, or
    when the value looks like key material.
    """
    name = _as_env_name(identity_env)
    if not name:
        return ""
    env = environ if environ is not None else os.environ
    raw = str(env.get(name) or "").strip()
    if not raw:
        raise SSHNotConfiguredError(SSH_IDENTITY_UNSET)
    if looks_like_key_material(raw):
        raise SSHNotConfiguredError(SSH_IDENTITY_IS_KEY)
    return raw


def require_ssh_target(
    *,
    host: str = "",
    user: str = "",
    port: int | str | None = 22,
    identity_env: str = "",
    use_agent: bool = True,
) -> SSHTarget:
    """Build an ``SSHTarget`` or raise a clear missing-config error."""
    h = (host or "").strip()
    u = (user or "").strip()
    if not h or not u:
        raise SSHNotConfiguredError(SSH_NOT_CONFIGURED)
    try:
        p = 22 if port in (None, "") else int(port)
    except (TypeError, ValueError) as exc:
        raise SSHNotConfiguredError("ssh_port must be an integer 1–65535.") from exc
    if p < 1 or p > 65535:
        raise SSHNotConfiguredError("ssh_port must be an integer 1–65535.")
    ident = _as_env_name(identity_env)
    if ident and looks_like_key_material(ident):
        raise SSHNotConfiguredError(SSH_IDENTITY_IS_KEY)
    return SSHTarget(
        host=h,
        user=u,
        port=p,
        identity_env=ident,
        use_agent=bool(use_agent),
    )


def _default_runner(
    argv: list[str],
    *,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    return execute_command_safe(argv, timeout=timeout, capture_output=True, text=True, check=False)


class SSHTransport:
    """Run argv on the Herdr host via OpenSSH. Inject ``runner`` in tests."""

    def __init__(
        self,
        target: SSHTarget,
        *,
        runner: Runner | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        self.target = target
        self._runner = runner or _default_runner
        self._environ = environ

    def build_ssh_argv(self, remote_command: list[str]) -> list[str]:
        """``ssh [opts] user@host -- <remote_command>``. Never embeds a key."""
        if not remote_command:
            raise SSHError("remote command is required")
        target = self.target
        if not target.host or not target.user:
            raise SSHNotConfiguredError(SSH_NOT_CONFIGURED)
        argv: list[str] = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
        ]
        if target.port and target.port != 22:
            argv.extend(["-p", str(int(target.port))])
        identity_path = resolve_identity_path(target.identity_env, self._environ)
        if identity_path:
            argv.extend(["-i", identity_path, "-o", "IdentitiesOnly=yes"])
        elif not target.use_agent:
            raise SSHNotConfiguredError(
                "Remote Herdr SSH needs ssh_identity_env (env-var name for a "
                "key path) or ssh_agent=true. Never paste a private key. "
                "Refusing to guess a host."
            )
        argv.append(target.destination())
        argv.append("--")
        argv.extend(list(remote_command))
        return argv

    def run(
        self,
        argv: list[str],
        *,
        timeout: int | None = _DEFAULT_PROCESS_TIMEOUT,
    ) -> subprocess.CompletedProcess:
        ssh_argv = self.build_ssh_argv(argv)
        try:
            return self._runner(ssh_argv, timeout=timeout)
        except FileNotFoundError as exc:
            raise SSHError(
                "ssh is not on PATH. Install OpenSSH or stub SSHTransport "
                "in tests (no live LAN / no guessed hosts)."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SSHError(f"ssh timed out: {ssh_argv}") from exc


def remote_command_from_ssh_argv(argv: list[str]) -> list[str]:
    """Slice the command after ``--`` from a stubbed ssh argv (tests)."""
    try:
        idx = list(argv).index("--")
    except ValueError:
        return []
    return list(argv[idx + 1 :])


def stub_ssh_transport(
    handler: Callable[[list[str]], subprocess.CompletedProcess],
    target: SSHTarget | None = None,
) -> SSHTransport:
    """Test helper: ``handler`` receives the full ssh argv."""

    def runner(argv: list[str], *, timeout: int | None = None, **_kwargs: Any) -> subprocess.CompletedProcess:  # noqa: ARG001
        del timeout, _kwargs
        return handler(argv)

    dest = target or SSHTarget(host="herdr.example.test", user="herdr")
    return SSHTransport(dest, runner=runner)


def parse_ssh_target(raw: str, default_user: str = "") -> SSHTarget:
    """Parse a flexible remote-target string into an :class:`SSHTarget` (#849).

    Accepted shapes:

    * plain host — ``192.0.2.10``, ``host.example.lan`` (port 22; user falls back
      to *default_user*, then the current user)
    * ``user@host`` and ``user@host:port`` — ``operator@192.0.2.10:2222``
    * ``ssh://`` URIs — ``ssh://host:22``, ``ssh://user@host:2222``

    The identity/agent fields stay at their defaults; callers override them
    via the advanced SSH options in the settings card. Raises
    :class:`SSHNotConfiguredError` on empty input or a non-integer port so
    the UI can surface a clear message.
    """
    text = (raw or "").strip()
    if not text:
        raise SSHNotConfiguredError(SSH_NOT_CONFIGURED)

    user = ""
    host = text
    port: int | str | None = 22

    if "://" in text:
        try:
            parts = urlsplit(text)
        except ValueError as exc:
            raise SSHNotConfiguredError(f"Invalid SSH URI '{text}'.") from exc
        if parts.scheme.lower() != "ssh":
            raise SSHNotConfiguredError(
                f"Unsupported scheme '{parts.scheme}:' — use ssh://host[:port][/path]."
            )
        user = parts.username or ""
        host = parts.hostname or ""
        port = parts.port if parts.port else 22
    elif "@" in text:
        user, _, hostpart = text.partition("@")
        # user@host:port — one colon after the user is a port, not IPv6.
        if ":" in hostpart and hostpart.count(":") == 1:
            host, _, raw_port = hostpart.partition(":")
            port = raw_port
        else:
            host = hostpart
    elif ":" in text and text.count(":") == 1:
        host, _, raw_port = text.partition(":")
        port = raw_port

    host = (host or "").strip().strip("/")
    user = (user or "").strip() or (default_user or "").strip()
    if not user:
        try:
            user = getpass.getuser()
        except Exception:  # pragma: no cover - exotic platforms
            user = ""
    return require_ssh_target(host=host, user=user, port=port)

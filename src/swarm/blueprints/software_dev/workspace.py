"""software_dev workspace backends — local FS or SSH remote.

File tools historically resolved ``params.workdir`` on the **API-host
filesystem**. A control plane on dev-worker-max (:8002) therefore cannot see a
tree that only exists on dev-worker-gpu (for example ``~/chatty-commander``)
unless an SSH remote workdir is configured.

Remote hop reuses the Herdr SSH argv builder (BatchMode, identity = env-var
*name* for a key *path*, never a private key). Tests stub the runner and
must not open a live SSH session or guess a host.

Local path tools still refuse ``..`` / absolute escapes out of the
workspace root. That sandbox is unchanged.
"""

from __future__ import annotations

import logging
import os
import posixpath
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlparse

from swarm.herdr.ssh import (
    SSHNotConfiguredError,
    SSHTarget,
    SSHTransport,
    looks_like_key_material,
    require_ssh_target,
)

logger = logging.getLogger(__name__)

ENV_WORKDIR = "SWARM_SOFTWARE_DEV_WORKDIR"
ENV_REMOTE_WORKDIR = "SWARM_SOFTWARE_DEV_REMOTE_WORKDIR"
ENV_SSH_HOST = "SWARM_SOFTWARE_DEV_SSH_HOST"
ENV_SSH_USER = "SWARM_SOFTWARE_DEV_SSH_USER"
ENV_SSH_PORT = "SWARM_SOFTWARE_DEV_SSH_PORT"
ENV_SSH_IDENTITY = "SWARM_SOFTWARE_DEV_SSH_IDENTITY"

WORKDIR_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "workdir",
        "cwd",
        "remote_workdir",
        "ssh_host",
        "ssh_user",
        "ssh_port",
        "ssh_identity_env",
        "ssh_agent",
    }
)

REMOTE_NOT_CONFIGURED = (
    "software_dev remote workdir is SSH-shaped and needs ssh_host + ssh_user "
    "(optional ssh_port, ssh_identity_env, ssh_agent). "
    "A local params.workdir is the API-host filesystem and cannot see a path "
    "on another host. Refusing to guess a host. Set remote_workdir="
    "user@host:path or ssh://user@host/path, or set ssh_host + ssh_user with "
    "a remote path. Identity is an env-var name for a key path — never a "
    "private key."
)

FS_LOCALITY_LOCAL = (
    "fs-locality: file tools read/write the API-host filesystem; a path on "
    "another host is invisible unless remote_workdir / SSH is configured"
)

FS_LOCALITY_SSH = (
    "fs-locality: file tools hop via SSH to that host path "
    "(not the API-host disk)"
)

# Self-contained remote helper. The SSH host does not have this package.
# Ops: read | list | write. Argv: python3 -c HELPER <op> <root> <rel>
# write reads stdin. Exit 2 = escape, 3 = not a file, 4 = not a directory.
# Each element must be shell-quoted before ssh (OpenSSH space-joins).
REMOTE_HELPER = r"""
import os, sys, pathlib
op, root, rel = sys.argv[1], sys.argv[2], sys.argv[3]
root_n = os.path.normpath(os.path.expanduser(root))
rel = (rel or ".").strip() or "."
if rel in (".",):
    target = root_n
elif rel.startswith(("/", "~")):
    target = os.path.normpath(os.path.expanduser(rel))
else:
    target = os.path.normpath(os.path.join(root_n, rel))
try:
    parent_r = os.path.realpath(root_n) if os.path.exists(root_n) else root_n
    child_r = os.path.realpath(target)
except OSError:
    parent_r, child_r = root_n, target
sep = os.sep
if not (child_r == parent_r or child_r.startswith(parent_r + sep)):
    sys.stderr.write("ESCAPE\n")
    sys.exit(2)
p = pathlib.Path(target)
if op == "read":
    if not p.is_file():
        sys.stderr.write("NOTFILE\n")
        sys.exit(3)
    sys.stdout.write(p.read_text(encoding="utf-8"))
elif op == "list":
    if not p.is_dir():
        sys.stderr.write("NOTDIR\n")
        sys.exit(4)
    sys.stdout.write("\n".join(sorted(x.name for x in p.iterdir())))
elif op == "write":
    p.parent.mkdir(parents=True, exist_ok=True)
    data = sys.stdin.read()
    p.write_text(data, encoding="utf-8")
    sys.stdout.write(str(len(data.encode("utf-8"))))
else:
    sys.stderr.write("BADOP\n")
    sys.exit(1)
"""

_DEFAULT_SSH_TIMEOUT = 30

SshRunner = Callable[..., subprocess.CompletedProcess]


def quote_remote_ssh_argv(remote: list[str]) -> list[str]:
    """Quote each argv so OpenSSH space-join survives a remote login shell.

    OpenSSH concatenates the remote command with spaces; the remote shell
    then parses that string. A multiline ``python3 -c`` helper without
    quotes becomes ``python3 -c import os, sys…`` and fails with
    ``Argument expected for the -c option``. Stub runners that exec the
    argv list after ``--`` hide this (Issue #148 / fleet pattern #157).
    """
    return [shlex.quote(part) for part in remote]


class WorkspaceBackend(Protocol):
    kind: str

    def read_file(self, path: str) -> str: ...

    def list_files(self, directory: str = ".") -> str: ...

    def write_file(self, path: str, content: str) -> str: ...

    def label(self) -> str: ...

    def locality_note(self) -> str: ...


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def looks_like_remote_workdir(raw: str | None) -> bool:
    """True for ``ssh://…`` or ``user@host:path`` (not a Windows drive)."""
    text = (raw or "").strip()
    if not text:
        return False
    if text.startswith("ssh://"):
        return True
    if "@" not in text:
        return False
    user, rest = text.split("@", 1)
    if not user or len(user) == 1 or "://" in user:
        return False
    if ":" not in rest:
        return False
    host, _path = rest.split(":", 1)
    return bool(host.strip())


def confine_posix(root: str, rel: str) -> str | None:
    """String-level POSIX confinement. Does not touch the local filesystem."""
    root_n = posixpath.normpath((root or "").strip() or ".")
    rel_n = (rel or ".").strip() or "."
    if rel_n in (".",):
        candidate = root_n
    elif rel_n.startswith("/"):
        candidate = posixpath.normpath(rel_n)
    elif rel_n.startswith("~"):
        candidate = posixpath.normpath(rel_n)
    else:
        candidate = posixpath.normpath(posixpath.join(root_n, rel_n))
    if candidate == root_n or candidate.startswith(root_n + "/"):
        return candidate
    return None


def confine_local(root: Path, rel: str) -> Path | None:
    """Resolve *rel* under *root*; None when it escapes (incl. ``/tmp/ws`` vs ``/tmp/ws-evil``)."""
    try:
        root_r = root.expanduser().resolve()
    except OSError:
        return None
    text = (rel or ".").strip() or "."
    rel_p = Path(text)
    try:
        target = rel_p.resolve() if rel_p.is_absolute() else (root_r / rel_p).resolve()
    except OSError:
        return None
    try:
        if target == root_r or target.is_relative_to(root_r):
            return target
    except (OSError, ValueError):
        return None
    return None


def _parse_ssh_url(text: str) -> tuple[str, str, int, str] | None:
    parsed = urlparse(text)
    if parsed.scheme != "ssh":
        return None
    user = parsed.username or ""
    host = parsed.hostname or ""
    port = parsed.port or 22
    path = parsed.path or "/"
    if path.startswith("//"):
        path = path[1:]
    return user, host, port, path or "/"


def _parse_user_at_host(text: str) -> tuple[str, str, str] | None:
    if "@" not in text or ":" not in text.split("@", 1)[-1]:
        return None
    user, rest = text.split("@", 1)
    host, path = rest.split(":", 1)
    user, host, path = user.strip(), host.strip(), path.strip()
    if not user or not host or not path:
        return None
    return user, host, path


@dataclass(frozen=True)
class RemoteWorkdirSpec:
    """Public SSH target + remote path. No private keys."""

    host: str
    user: str
    path: str
    port: int = 22
    identity_env: str = ""
    use_agent: bool = True
    source: str = "remote_workdir"

    def public_label(self) -> str:
        port = f":{self.port}" if self.port and self.port != 22 else ""
        return f"{self.user}@{self.host}{port}:{self.path}"

    def ssh_target(self) -> SSHTarget:
        return require_ssh_target(
            host=self.host,
            user=self.user,
            port=self.port,
            identity_env=self.identity_env,
            use_agent=self.use_agent,
        )


def parse_remote_workdir(
    params: dict[str, Any] | None,
    cfg: dict[str, Any] | None = None,
    *,
    environ: dict[str, str] | None = None,
) -> RemoteWorkdirSpec | None:
    """Build a remote spec or None when the request is local-FS.

    Precedence: ``params.remote_workdir`` → config → env → remote-shaped
    ``params.workdir`` / ``cwd``. ``ssh_host`` + ``ssh_user`` can pair with
    a bare remote path. Missing host/user raises ``SSHNotConfiguredError``.
    """
    blob = params or {}
    block = cfg or {}
    env = environ if environ is not None else os.environ

    explicit = _first_text(
        blob.get("remote_workdir"),
        block.get("remote_workdir"),
        env.get(ENV_REMOTE_WORKDIR),
    )
    workdir = _first_text(
        blob.get("workdir"),
        blob.get("cwd"),
        block.get("workdir"),
        block.get("cwd"),
        env.get(ENV_WORKDIR),
    )
    host = _first_text(blob.get("ssh_host"), block.get("ssh_host"), env.get(ENV_SSH_HOST))
    user = _first_text(blob.get("ssh_user"), block.get("ssh_user"), env.get(ENV_SSH_USER))
    port_raw = _first_text(blob.get("ssh_port"), block.get("ssh_port"), env.get(ENV_SSH_PORT))
    identity = _first_text(
        blob.get("ssh_identity_env"),
        block.get("ssh_identity_env"),
        ENV_SSH_IDENTITY if env.get(ENV_SSH_IDENTITY) else "",
    )
    if looks_like_key_material(identity):
        raise SSHNotConfiguredError(
            "ssh_identity_env must be an environment variable name for a key "
            "path, not key material. Never paste a private key."
        )
    agent_raw = blob.get("ssh_agent", block.get("ssh_agent", True))
    if isinstance(agent_raw, str):
        use_agent = agent_raw.strip().lower() not in ("0", "false", "no", "off")
    else:
        use_agent = bool(agent_raw)

    port = 22
    if port_raw:
        try:
            port = int(port_raw)
        except (TypeError, ValueError) as exc:
            raise SSHNotConfiguredError("ssh_port must be an integer 1–65535.") from exc

    source = "remote_workdir"
    raw = explicit
    if not raw and looks_like_remote_workdir(workdir):
        raw = workdir
        source = "workdir"
    if not raw and host and user and workdir:
        raw = workdir
        source = "ssh_host+workdir"
    if not raw:
        if host or user:
            raise SSHNotConfiguredError(REMOTE_NOT_CONFIGURED)
        return None

    path = raw
    parsed_user = user
    parsed_host = host
    parsed_port = port
    if raw.startswith("ssh://"):
        parsed = _parse_ssh_url(raw)
        if parsed is None:
            raise SSHNotConfiguredError(REMOTE_NOT_CONFIGURED)
        parsed_user = parsed_user or parsed[0]
        parsed_host = parsed_host or parsed[1]
        if not port_raw:
            parsed_port = parsed[2]
        path = parsed[3]
        source = "ssh_url"
    elif looks_like_remote_workdir(raw):
        trip = _parse_user_at_host(raw)
        if trip is None:
            raise SSHNotConfiguredError(REMOTE_NOT_CONFIGURED)
        parsed_user = parsed_user or trip[0]
        parsed_host = parsed_host or trip[1]
        path = trip[2]

    if not parsed_host or not parsed_user or not path:
        raise SSHNotConfiguredError(REMOTE_NOT_CONFIGURED)

    return RemoteWorkdirSpec(
        host=parsed_host,
        user=parsed_user,
        path=path,
        port=parsed_port,
        identity_env=identity,
        use_agent=use_agent,
        source=source,
    )


class LocalWorkspaceBackend:
    """API-host filesystem. Default software_dev workdir."""

    kind = "local"

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def label(self) -> str:
        return f"local {self.root}"

    def locality_note(self) -> str:
        return FS_LOCALITY_LOCAL

    def read_file(self, path: str) -> str:
        rel = path.strip() or "."
        target = confine_local(self.root, rel)
        if target is None:
            return f"ERROR: path escapes workspace: {path}"
        if not target.is_file():
            return f"ERROR: not a file: {path}"
        return target.read_text(encoding="utf-8")

    def list_files(self, directory: str = ".") -> str:
        target = confine_local(self.root, directory)
        if target is None:
            return f"ERROR: path escapes workspace: {directory}"
        if not target.is_dir():
            return f"ERROR: not a directory: {directory}"
        return "\n".join(sorted(p.name for p in target.iterdir()))

    def write_file(self, path: str, content: str) -> str:
        rel = path.strip()
        target = confine_local(self.root, rel)
        if target is None:
            return f"ERROR: path escapes workspace: {path}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"OK: wrote {rel} ({len(content)} bytes)"


class UnconfiguredRemoteBackend:
    """Honest error backend when SSH remote was requested but not configured."""

    kind = "ssh-unconfigured"

    def __init__(self, detail: str) -> None:
        self.detail = detail

    def label(self) -> str:
        return "ssh (not configured)"

    def locality_note(self) -> str:
        return FS_LOCALITY_LOCAL

    def read_file(self, path: str) -> str:
        return f"ERROR: {self.detail}"

    def list_files(self, directory: str = ".") -> str:
        return f"ERROR: {self.detail}"

    def write_file(self, path: str, content: str) -> str:
        del path, content
        return f"ERROR: {self.detail}"


class SSHWorkspaceBackend:
    """Read/write a remote tree over SSH. Tests inject ``runner``."""

    kind = "ssh"

    def __init__(
        self,
        spec: RemoteWorkdirSpec,
        *,
        transport: SSHTransport | None = None,
        runner: SshRunner | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        self.spec = spec
        self.target = spec.ssh_target()
        self._transport = transport or SSHTransport(self.target, environ=environ)
        self._runner = runner

    def label(self) -> str:
        return f"ssh {self.spec.public_label()}"

    def locality_note(self) -> str:
        return FS_LOCALITY_SSH

    def _exec(self, op: str, rel: str, content: str | None = None) -> subprocess.CompletedProcess:
        confined = confine_posix(self.spec.path, rel)
        if confined is None:
            return subprocess.CompletedProcess(
                args=["ssh"],
                returncode=2,
                stdout="",
                stderr="ESCAPE\n",
            )
        remote = quote_remote_ssh_argv(
            ["python3", "-c", REMOTE_HELPER, op, self.spec.path, rel]
        )
        ssh_argv = self._transport.build_ssh_argv(remote)
        if self._runner is not None:
            return self._runner(ssh_argv, timeout=_DEFAULT_SSH_TIMEOUT, input=content)
        return subprocess.run(
            ssh_argv,
            shell=False,
            capture_output=True,
            text=True,
            input=content,
            timeout=_DEFAULT_SSH_TIMEOUT,
            check=False,
        )

    def _translate(self, proc: subprocess.CompletedProcess, path: str, *, not_kind: str) -> str:
        if proc.returncode == 0:
            return proc.stdout
        err = (proc.stderr or "").strip()
        if proc.returncode == 2 or err == "ESCAPE":
            return f"ERROR: path escapes workspace: {path}"
        if proc.returncode == 3:
            return f"ERROR: not a file: {path}"
        if proc.returncode == 4:
            return f"ERROR: not a directory: {path}"
        detail = err or (proc.stdout or "").strip() or f"exit {proc.returncode}"
        if looks_like_key_material(detail):
            detail = "ssh failed (redacted)"
        return f"ERROR: remote {not_kind} failed: {detail}"

    def read_file(self, path: str) -> str:
        rel = path.strip() or "."
        return self._translate(self._exec("read", rel), path, not_kind="read")

    def list_files(self, directory: str = ".") -> str:
        return self._translate(self._exec("list", directory), directory, not_kind="list")

    def write_file(self, path: str, content: str) -> str:
        rel = path.strip()
        proc = self._exec("write", rel, content=content)
        if proc.returncode == 0:
            return f"OK: wrote {rel} ({len(content)} bytes)"
        return self._translate(proc, path, not_kind="write")


def resolve_local_root(
    params: dict[str, Any] | None,
    cfg: dict[str, Any] | None = None,
    *,
    environ: dict[str, str] | None = None,
) -> Path:
    blob = params or {}
    block = cfg or {}
    env = environ if environ is not None else os.environ
    raw = _first_text(
        blob.get("workdir"),
        blob.get("cwd"),
        block.get("workdir"),
        block.get("cwd"),
        env.get(ENV_WORKDIR),
    )
    if raw:
        return Path(raw)
    return Path.cwd() / ".software_dev_ws"


def resolve_workspace(
    params: dict[str, Any] | None,
    cfg: dict[str, Any] | None = None,
    *,
    environ: dict[str, str] | None = None,
    runner: SshRunner | None = None,
    transport: SSHTransport | None = None,
) -> WorkspaceBackend:
    """Pick local vs SSH backend. Never guesses a host."""
    try:
        spec = parse_remote_workdir(params, cfg, environ=environ)
    except SSHNotConfiguredError as exc:
        logger.info("software_dev remote workdir not configured: %s", exc)
        return UnconfiguredRemoteBackend(str(exc))
    if spec is None:
        return LocalWorkspaceBackend(resolve_local_root(params, cfg, environ=environ))
    try:
        return SSHWorkspaceBackend(spec, transport=transport, runner=runner, environ=environ)
    except SSHNotConfiguredError as exc:
        logger.info("software_dev SSH target refused: %s", exc)
        return UnconfiguredRemoteBackend(str(exc))


def stub_remote_helper_runner(
    *,
    python: str | None = None,
) -> SshRunner:
    """Test double: run ``REMOTE_HELPER`` locally. No live SSH.

    Replays OpenSSH's space-join + a POSIX shell parse before exec so a
    list-only stub cannot hide an unquoted multiline ``-c`` helper.
    """
    import sys

    exe = python or sys.executable

    def runner(
        argv: list[str],
        *,
        timeout: int | None = None,
        input: str | None = None,
        **_kwargs: Any,
    ) -> subprocess.CompletedProcess:
        from swarm.herdr.ssh import remote_command_from_ssh_argv

        del _kwargs
        remote = remote_command_from_ssh_argv(argv)
        try:
            parsed = shlex.split(" ".join(remote))
        except ValueError as exc:
            return subprocess.CompletedProcess(argv, 1, "", f"remote-shell parse: {exc}\n")
        if len(parsed) < 4 or parsed[0] != "python3" or parsed[1] != "-c":
            return subprocess.CompletedProcess(argv, 1, "", "unexpected remote argv\n")
        return subprocess.run(
            [exe, "-c", parsed[2], *parsed[3:]],
            input=input,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    return runner

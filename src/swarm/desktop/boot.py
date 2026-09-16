"""Loopback desktop boot contracts for Operating Swarm (REQ-883 / #280).

Pure helpers: no Django import, no pywebview, no freeze. The window, onedir
bundle, and installers are follow-up REQs. Tests and ``swarm-desktop
--print-plan`` exercise this module on Linux CI.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

LOOPBACK_HOST = "127.0.0.1"
PREFERRED_PORT = 8000
PRODUCT_NAME = "Operating Swarm"
WINDOWS_PROFILE_DIRNAME = "OperatingSwarm"
MACOS_PROFILE_DIRNAME = "Operating Swarm"
LINUX_PROFILE_DIRNAME = "operating-swarm"

# Host-native CLIs stay on the machine. Desktop must discover them via PATH
# merge — never vendor the binaries into the freeze.
HOST_CLI_NAMES = ("agy", "qwen", "grok", "claude", "opencode")


def loopback_url(port: int) -> str:
    """Navigate the pane-of-glass window here. IPv4, never bare ``localhost``."""
    if port <= 0 or port > 65535:
        raise ValueError(f"invalid loopback port: {port}")
    return f"http://{LOOPBACK_HOST}:{port}/"


def _can_bind(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((LOOPBACK_HOST, port))
        except OSError:
            return False
    return True


def pick_free_loopback_port(preferred: int = PREFERRED_PORT) -> int:
    """Prefer ``preferred`` (default :8000) but yield an ephemeral port if taken."""
    if preferred > 0 and _can_bind(preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOOPBACK_HOST, 0))
        return int(sock.getsockname()[1])


def desktop_profile_dir(
    environ: Mapping[str, str] | None = None,
    *,
    platform: str | None = None,
) -> Path:
    """User-profile home for sqlite, config, and the first-run secret.

    ``SWARM_USER_DATA_DIR`` always wins so tests and ADR-002 helpers share one
    folder. Platform defaults use the Operating Swarm product name — they do
    not rewrite ``swarm.core.paths.APP_AUTHOR`` (that is REQ-862).
    """
    env = os.environ if environ is None else environ
    override = (env.get("SWARM_USER_DATA_DIR") or "").strip()
    if override:
        return Path(override)
    plat = sys.platform if platform is None else platform
    if plat == "win32":
        root = env.get("LOCALAPPDATA") or env.get("APPDATA") or str(Path.home())
        return Path(root) / WINDOWS_PROFILE_DIRNAME
    if plat == "darwin":
        return Path.home() / "Library" / "Application Support" / MACOS_PROFILE_DIRNAME
    xdg = (env.get("XDG_DATA_HOME") or "").strip()
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / LINUX_PROFILE_DIRNAME


def materialize_secret_key(profile: Path) -> str:
    """Create a user-only ``DJANGO_SECRET_KEY`` file on first run.

    Never writes into the git tree. Returns the key; callers export it into
    process env. ``--print-plan`` must not echo the value.
    """
    path = profile / "config" / "django_secret_key"
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(48)
    path.write_text(key + "\n", encoding="utf-8")
    with suppress(OSError):
        os.chmod(path, 0o600)
    return key


def desktop_process_env(
    *,
    port: int,
    profile: Path,
    secret_key: str,
) -> dict[str, str]:
    """Env the frozen ASGI process must run with. Bind loopback only."""
    origin = loopback_url(port).rstrip("/")
    sqlite = profile / "data" / "db.sqlite3"
    return {
        "HOST": LOOPBACK_HOST,
        "PORT": str(port),
        "DJANGO_SETTINGS_MODULE": "swarm.settings",
        "DJANGO_DEBUG": "false",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "DJANGO_CSRF_TRUSTED_ORIGINS": f"{origin},http://localhost:{port}",
        "SWARM_SECURE_COOKIES": "false",
        "DJANGO_SECRET_KEY": secret_key,
        "DJANGO_DB_NAME": str(sqlite),
        "SQLITE_DB_PATH": str(sqlite),
        "SWARM_USER_DATA_DIR": str(profile),
        "SWARM_CONFIG_PATH": str(profile / "config" / "swarm_config.json"),
        "SWARM_CHAT_DIR": str(profile / "data" / "chats"),
        "SWARM_ATTACHMENTS_DIR": str(profile / "data" / "attachments"),
    }


def _probe_login_shell_path(*, timeout: float = 2.0) -> str | None:
    """macOS / Linux: GUI apps do not source ``.zprofile`` / ``.bashrc``."""
    shell = os.environ.get("SHELL") or "/bin/sh"
    try:
        completed = subprocess.run(
            [shell, "-ilc", 'printf %s "$PATH"'],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _probe_windows_user_path() -> str | None:
    try:
        import winreg
    except ImportError:
        return None
    chunks: list[str] = []
    keys = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    )
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as handle:
                value, _ = winreg.QueryValueEx(handle, "Path")
        except OSError:
            continue
        if value:
            chunks.append(str(value))
    return os.pathsep.join(chunks) if chunks else None


def probe_interactive_path() -> str | None:
    if sys.platform == "win32":
        return _probe_windows_user_path()
    return _probe_login_shell_path()


def merge_interactive_path(
    current: str | None = None,
    extra: str | None = None,
) -> str:
    """Deduped PATH: probed interactive dirs first, then the process PATH."""
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in (extra, current):
        if not chunk:
            continue
        for part in chunk.split(os.pathsep):
            if part and part not in seen:
                seen.add(part)
                parts.append(part)
    return os.pathsep.join(parts)


def print_plan(
    *,
    profile: Path | None = None,
    port: int | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Machine-readable boot plan for CI. Never includes secret material."""
    env = os.environ if environ is None else environ
    resolved_profile = profile or desktop_profile_dir(env)
    resolved_port = pick_free_loopback_port() if port is None else port
    url = loopback_url(resolved_port)
    sqlite = resolved_profile / "data" / "db.sqlite3"
    return {
        "object": "desktop.plan",
        "product": PRODUCT_NAME,
        "req": "REQ-883",
        "issue": 280,
        "shell": "pywebview",
        "freeze": "PyInstaller onedir",
        "host": LOOPBACK_HOST,
        "port": resolved_port,
        "url": url,
        "profile": str(resolved_profile),
        "sqlite": str(sqlite),
        "window": False,
        "phase": "REQ-883A-scaffold",
        "vendored_clis": False,
        "host_clis": list(HOST_CLI_NAMES),
        "secret_key_file": str(resolved_profile / "config" / "django_secret_key"),
    }

"""Behaviour tests for the REQ-883 swarm-desktop boot scaffold."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from swarm.desktop.boot import (
    HOST_CLI_NAMES,
    LOOPBACK_HOST,
    PRODUCT_NAME,
    desktop_process_env,
    desktop_profile_dir,
    loopback_url,
    materialize_secret_key,
    merge_interactive_path,
    pick_free_loopback_port,
    print_plan,
)
from swarm.desktop.packaging import (
    ASGI_APP,
    PRIMARY_FREEZE,
    PRIMARY_SHELL,
    PYINSTALLER_HIDDENIMPORTS,
    REJECTED_SHELLS,
)


def test_loopback_url_is_ipv4_with_trailing_slash():
    assert loopback_url(8765) == "http://127.0.0.1:8765/"
    with pytest.raises(ValueError):
        loopback_url(0)


def test_pick_free_port_falls_back_when_preferred_is_taken():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupied.bind((LOOPBACK_HOST, 0))
        taken = int(occupied.getsockname()[1])
        chosen = pick_free_loopback_port(preferred=taken)
    assert chosen != taken
    assert 0 < chosen <= 65535


def test_profile_dir_override_and_platform_defaults(tmp_path: Path):
    override = tmp_path / "profile"
    assert desktop_profile_dir({"SWARM_USER_DATA_DIR": str(override)}) == override
    win = desktop_profile_dir(
        {"LOCALAPPDATA": r"C:\Users\os\AppData\Local"},
        platform="win32",
    )
    assert win == Path(r"C:\Users\os\AppData\Local") / "OperatingSwarm"
    mac = desktop_profile_dir({}, platform="darwin")
    assert mac.as_posix().endswith("Library/Application Support/Operating Swarm")


def test_secret_key_materializes_once_outside_the_repo(tmp_path: Path):
    profile = tmp_path / "OperatingSwarm"
    first = materialize_secret_key(profile)
    second = materialize_secret_key(profile)
    assert first == second
    assert len(first) >= 32
    path = profile / "config" / "django_secret_key"
    assert path.is_file()
    assert "sk-" not in first
    # Never lands in the git tree.
    repo = Path(__file__).resolve().parents[2]
    assert repo not in path.resolve().parents


def test_desktop_env_binds_loopback_and_durable_sqlite(tmp_path: Path):
    profile = tmp_path / "OperatingSwarm"
    env = desktop_process_env(port=8123, profile=profile, secret_key="test-key")
    assert env["HOST"] == "127.0.0.1"
    assert env["HOST"] != "0.0.0.0"
    assert env["SWARM_SECURE_COOKIES"] == "false"
    assert env["DJANGO_DEBUG"] == "false"
    assert "/tmp/db.sqlite3" not in env["DJANGO_DB_NAME"]
    assert env["DJANGO_DB_NAME"].endswith("data/db.sqlite3") or env[
        "DJANGO_DB_NAME"
    ].endswith("data\\db.sqlite3")
    assert "http://127.0.0.1:8123" in env["DJANGO_CSRF_TRUSTED_ORIGINS"]
    assert env["SWARM_USER_DATA_DIR"] == str(profile)


def test_path_merge_puts_interactive_dirs_first_and_does_not_vendor_clis():
    merged = merge_interactive_path(
        current="/usr/bin:/bin",
        extra="/home/os/.local/bin:/usr/bin",
    )
    parts = merged.split(os.pathsep)
    assert parts[0] == "/home/os/.local/bin"
    assert parts.count("/usr/bin") == 1
    for name in HOST_CLI_NAMES:
        assert name not in merged


def test_print_plan_omits_secret_material(tmp_path: Path):
    plan = print_plan(profile=tmp_path / "p", port=9001)
    assert plan["object"] == "desktop.plan"
    assert plan["product"] == PRODUCT_NAME
    assert plan["host"] == "127.0.0.1"
    assert plan["url"] == "http://127.0.0.1:9001/"
    assert plan["window"] is False
    assert plan["vendored_clis"] is False
    dumped = str(plan)
    assert "sk-" not in dumped
    assert "test-key" not in dumped
    assert "token_urlsafe" not in dumped


def test_packaging_constants_name_asgi_and_reject_electron():
    assert ASGI_APP == "swarm.asgi:application"
    assert PRIMARY_SHELL == "pywebview"
    assert PRIMARY_FREEZE == "PyInstaller onedir"
    assert "Electron" in REJECTED_SHELLS
    assert "channels" in PYINSTALLER_HIDDENIMPORTS
    assert "uvicorn" in PYINSTALLER_HIDDENIMPORTS
    assert "swarm.asgi" in PYINSTALLER_HIDDENIMPORTS

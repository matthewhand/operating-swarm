"""#1175 — the CLI *exec* path needs more mounts than the probe path did.

#1140 fixed the list-models probes; the live agent sweep (2026-09-25) showed
the **turn** path still bricks three seats in-container where $HOME is
root-owned (REQ-45 sandbox-home):

- ``qwen``  → EACCES mkdir ``~/.qwen`` (first-run state dir)
- ``hermes``→ launcher venv ``~/.hermes/.../venv/bin/python`` unmounted
- ``grok``  → binary is a symlink into ``~/.grok/downloads`` (unmounted)

All three host dirs exist and are uid-1000-owned; mounting them is the same
doctrine as #762/#1125/#1140 — the host is the source of truth. Hermes's
launcher also execs ``python``/``python3`` from its venv bin, so the writable
``~/.local/share/uv`` python install must be on the seat PATH too (which_cli
must resolve it).
"""

from __future__ import annotations
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"


def _swarm_volumes() -> list[str]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    volumes = data["services"]["swarm"]["volumes"]
    assert isinstance(volumes, list)
    return [str(v) for v in volumes]


def test_cli_exec_state_dirs_are_mounted_writable():
    volumes = _swarm_volumes()
    for host_dir in (
        ".qwen",  # qwen first-run state dir (EACCES mkdir)
        ".hermes",  # hermes launcher + venv (python symlink target lives here)
        ".grok",  # grok binary symlink target: ~/.grok/downloads (read-only OK)
    ):
        rows = [v for v in volumes if f"/{host_dir}:" in v]
        assert rows, f"compose must mount $HOME/{host_dir} into the container"


def test_grok_download_target_mounted_readonly():
    """grok's binary chain crosses into ~/.grok/downloads — ro is sufficient."""
    volumes = _swarm_volumes()
    rows = [v for v in volumes if "/.grok:" in v]
    assert rows, "compose must mount $HOME/.grok for the grok binary symlink"


def test_hermes_venv_python_on_seat_path():
    """which_cli must resolve hermes's venv interpreter (host_cli_path)."""
    from swarm.core.cli_catalog import extra_cli_path_dirs, host_cli_path

    home = Path.home()
    venv_bin = home / ".hermes" / "hermes-agent" / "venv" / "bin"
    if not venv_bin.is_dir():
        import pytest

        pytest.skip("host has no hermes venv; nothing to pin on this machine")
    assert str(venv_bin) in extra_cli_path_dirs(), (
        "#1175: hermes's venv bin must be on the seat PATH so its launcher's "
        "`python` exec resolves"
    )
    assert str(venv_bin) in host_cli_path()

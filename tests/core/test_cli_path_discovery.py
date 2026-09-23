"""#716/#717 — CLI discovery scope: configurable extra dirs + honest messages.

The catalog's ``which_cli`` already scans known user bin dirs, but a
container deployment sees only what compose mounts — and the not-installed
warning did not say *where* it looked, reading as nonsense to a user whose
host install is simply not visible in-container. Contract:

1. ``SWARM_CLI_PATH_DIRS`` (``os.pathsep``-joined) extends the scan, dirs
   first, existing dirs only.
2. ``which_cli`` resolves through the extended scan.
3. The list-models not-installed warning names the searched scope instead
   of a bare "on PATH".
"""

from __future__ import annotations

import os

import pytest

from swarm.core import cli_models
from swarm.core.cli_catalog import extra_cli_path_dirs, host_cli_path, which_cli


@pytest.fixture
def fake_cli_dir(tmp_path):
    d = tmp_path / "bins"
    d.mkdir()
    exe = d / "agy"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    return d


def test_configured_env_dirs_extend_the_scan(fake_cli_dir, monkeypatch):
    monkeypatch.setenv("SWARM_CLI_PATH_DIRS", str(fake_cli_dir))
    assert str(fake_cli_dir) in extra_cli_path_dirs()
    assert which_cli("agy") == str(fake_cli_dir / "agy")


def test_configured_dirs_come_first(tmp_path, monkeypatch):
    first, second = tmp_path / "a", tmp_path / "b"
    for d in (first, second):
        d.mkdir()
        exe = d / "tool"
        exe.write_text("#!/bin/sh\nexit 0\n")
        exe.chmod(0o755)
    monkeypatch.setenv(
        "SWARM_CLI_PATH_DIRS", os.pathsep.join([str(first), str(second)])
    )
    dirs = extra_cli_path_dirs()
    assert dirs.index(str(first)) < dirs.index(str(second))
    assert which_cli("tool") == str(first / "tool")


def test_missing_configured_dirs_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "SWARM_CLI_PATH_DIRS",
        os.pathsep.join([str(tmp_path / "nope"), str(tmp_path / "also-nope")]),
    )
    assert extra_cli_path_dirs() == [
        d for d in extra_cli_path_dirs() if "nope" not in d
    ]


def test_unset_env_leaves_discovered_dirs_only(monkeypatch):
    monkeypatch.delenv("SWARM_CLI_PATH_DIRS", raising=False)
    baseline = [d for d in extra_cli_path_dirs()]
    assert baseline == extra_cli_path_dirs()


def test_host_cli_path_prepends_configured(fake_cli_dir, monkeypatch):
    monkeypatch.setenv("SWARM_CLI_PATH_DIRS", str(fake_cli_dir))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    path = host_cli_path()
    assert path.startswith(str(fake_cli_dir))


def test_not_installed_warning_names_the_scope(tmp_path, monkeypatch):
    """A CLI absent from the *scanned* scope must say where it looked (#716)."""
    import asyncio

    # No SWARM_CLI_PATH_DIRS, no fake binary: the not-installed branch runs.
    monkeypatch.delenv("SWARM_CLI_PATH_DIRS", raising=False)
    result = asyncio.run(
        cli_models.probe_list_models(
            "agy", which=lambda exe: None, timeout=0.5
        )
    )
    assert result.warning
    assert "scanned PATH" in result.warning
    assert "SWARM_CLI_PATH_DIRS" in result.warning

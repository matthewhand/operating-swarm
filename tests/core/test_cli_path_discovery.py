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
from swarm.utils.cli_path import (
    in_linux_container,
    is_foreign_windows_binary,
    is_runnable_cli_binary,
)


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


def test_newest_nvm_bin_wins_over_stale_npm_global(tmp_path, monkeypatch):
    """A Node CLI installed twice must resolve the current nvm release.

    Regression: ``~/.npm-global/bin/pi`` (old 0.74.2, no ``--approve``) was
    scanned before the newest nvm bin, so the adapter resolved the stale copy
    and every pi one-shot failed ``Unknown options: --approve``.
    """
    home = tmp_path / "home"
    npm_global = home / ".npm-global" / "bin"
    npm_global.mkdir(parents=True)
    (npm_global / "pi").write_text("#!/bin/sh\necho old\n")
    (npm_global / "pi").chmod(0o755)

    nvm = home / ".nvm" / "versions" / "node"
    for ver, marker in (("v22.22.3", "older"), ("v22.23.2", "newest")):
        bin_dir = nvm / ver / "bin"
        bin_dir.mkdir(parents=True)
        exe = bin_dir / "pi"
        exe.write_text(f"#!/bin/sh\necho {marker}\n")
        exe.chmod(0o755)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("SWARM_CLI_PATH_DIRS", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    newest = nvm / "v22.23.2" / "bin" / "pi"
    assert which_cli("pi") == str(newest)
    dirs = extra_cli_path_dirs()
    assert dirs.index(str(nvm / "v22.23.2" / "bin")) < dirs.index(str(npm_global))


def test_configured_dirs_still_outrank_nvm(tmp_path, monkeypatch):
    """SWARM_CLI_PATH_DIRS stays the top-priority deployment override."""
    home = tmp_path / "home"
    nvm_bin = home / ".nvm" / "versions" / "node" / "v22.23.2" / "bin"
    nvm_bin.mkdir(parents=True)
    (nvm_bin / "pi").write_text("#!/bin/sh\necho nvm\n")
    (nvm_bin / "pi").chmod(0o755)

    configured = tmp_path / "configured"
    configured.mkdir()
    (configured / "pi").write_text("#!/bin/sh\necho configured\n")
    (configured / "pi").chmod(0o755)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SWARM_CLI_PATH_DIRS", str(configured))
    assert which_cli("pi") == str(configured / "pi")
    dirs = extra_cli_path_dirs()
    assert dirs.index(str(configured)) < dirs.index(str(nvm_bin))


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


def test_foreign_windows_pe_rejected_on_linux(tmp_path, monkeypatch):
    """#1718: PE (MZ) host mounts must not count as runnable on Linux."""
    pe = tmp_path / "opencode"
    pe.write_bytes(b"MZ" + b"\x00" * 32)
    pe.chmod(0o755)
    monkeypatch.setattr("swarm.utils.cli_path.os.name", "posix")
    assert is_foreign_windows_binary(str(pe)) is True
    assert is_runnable_cli_binary(str(pe)) is False


def test_shell_script_still_runnable_on_linux(tmp_path, monkeypatch):
    script = tmp_path / "opencode"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    monkeypatch.setattr("swarm.utils.cli_path.os.name", "posix")
    assert is_foreign_windows_binary(str(script)) is False
    assert is_runnable_cli_binary(str(script)) is True


def test_container_prefers_usr_local_bin_over_home(tmp_path, monkeypatch):
    """#1718: in-container image bins beat host-mounted $HOME shims."""
    home = tmp_path / "home"
    home_bin = home / ".local" / "bin"
    home_bin.mkdir(parents=True)
    shim = home_bin / "opencode"
    shim.write_text(
        "#!/bin/sh\n"
        "echo opencode: Windows host binary not executable >&2\n"
        "exit 126\n"
    )
    shim.chmod(0o755)

    image_bin = tmp_path / "usr" / "local" / "bin"
    image_bin.mkdir(parents=True)
    baked = image_bin / "opencode"
    baked.write_text("#!/bin/sh\necho baked-linux\n")
    baked.chmod(0o755)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("SWARM_CLI_PATH_DIRS", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(
        "swarm.utils.cli_path.in_linux_container", lambda: True
    )
    monkeypatch.setattr(
        "swarm.utils.cli_path._IMAGE_BIN_DIRS", (str(image_bin),)
    )

    dirs = extra_cli_path_dirs()
    assert dirs.index(str(image_bin)) < dirs.index(str(home_bin))
    assert which_cli("opencode") == str(baked)


def test_which_cli_skips_pe_for_next_elf(tmp_path, monkeypatch):
    """#1718: when PATH leads with a PE, discovery walks to a Linux binary."""
    pe_dir = tmp_path / "pe"
    ok_dir = tmp_path / "ok"
    pe_dir.mkdir()
    ok_dir.mkdir()
    pe = pe_dir / "opencode"
    pe.write_bytes(b"MZ" + b"\x00" * 16)
    pe.chmod(0o755)
    ok = ok_dir / "opencode"
    ok.write_text("#!/bin/sh\nexit 0\n")
    ok.chmod(0o755)

    monkeypatch.setattr("swarm.utils.cli_path.os.name", "posix")
    monkeypatch.setattr(
        "swarm.utils.cli_path.in_linux_container", lambda: False
    )
    monkeypatch.setenv("SWARM_CLI_PATH_DIRS", os.pathsep.join([str(pe_dir), str(ok_dir)]))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    assert which_cli("opencode") == str(ok)


def test_annotate_exit_126_windows_host_binary():
    from swarm.blueprints.common.cli_fusion_support import annotate_cli_failure

    raw = (
        "exited 126: opencode: Windows host binary not executable "
        "inside Linux container; use host PATH / CLI seat via gateway"
    )
    out = annotate_cli_failure(raw)
    assert "rebuild" in out.lower() or "/usr/local/bin" in out
    assert raw in out or "exited 126" in out

"""REQ-871 — blueprint lifecycle: compile, launch fallback, delete scope.

Behaviour spec of record for the "CLI blueprint lifecycle (gaps in
``swarm-cli``)" items in TODO.md. Plan: docs/qa/REQ-871-cli-blueprint-lifecycle.md
Source lock: tests/unit/test_req871_cli_blueprint_lifecycle.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from swarm.core import swarm_cli

runner = CliRunner()


@pytest.fixture
def xdg(tmp_path, mocker):
    """Temp XDG roots so these tests never touch the real ~/.local or ~/.cache.

    ``swarm_cli`` resolves paths through ``swarm.core.paths`` at call time, so
    patching the module attributes is enough.
    """
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    blueprints = data / "blueprints"
    bin_dir = tmp_path / "bin"
    for path in (data, cache, blueprints, bin_dir):
        path.mkdir(parents=True, exist_ok=True)
    mocker.patch("swarm.core.paths.get_user_data_dir_for_swarm", return_value=data)
    mocker.patch("swarm.core.paths.get_user_blueprints_dir", return_value=blueprints)
    mocker.patch("swarm.core.paths.get_user_bin_dir", return_value=bin_dir)
    mocker.patch("swarm.core.paths.get_user_cache_dir_for_swarm", return_value=cache)
    return {"data": data, "cache": cache, "blueprints": blueprints, "bin": bin_dir}


def _write_blueprint(root: Path, name: str) -> Path:
    """Source dir with the highest-priority entry point (``{name}_cli.py``)."""
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    entry = directory / f"{name}_cli.py"
    entry.write_text("print('hi')\n", encoding="utf-8")
    return entry


def _write_executable(path: Path, content: bytes = b"\x7fELF not-a-shim") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o755)
    return path


def _ok_process() -> MagicMock:
    process = MagicMock()
    process.returncode = 0
    process.stdout = "ok"
    process.stderr = ""
    return process


# --- Workstream A: compile ---------------------------------------------------


@patch("subprocess.run")
def test_compile_and_both_aliases_build_identical_argv(mock_run, xdg):
    _write_blueprint(xdg["blueprints"], "alias_bp")
    mock_run.return_value = _ok_process()

    for command in ("compile", "install-executable", "install"):
        result = runner.invoke(swarm_cli.app, [command, "alias_bp"])
        assert result.exit_code == 0, f"{command}: {result.stdout}"

    assert mock_run.call_count == 3
    argvs = [call.args[0] for call in mock_run.call_args_list]
    assert argvs[0] == argvs[1] == argvs[2]
    assert argvs[0][0] == "pyinstaller"
    assert argvs[0][argvs[0].index("--name") + 1] == "alias_bp"


@patch("subprocess.run")
def test_compile_test_mode_installs_stub_and_skips_pyinstaller(mock_run, xdg, monkeypatch):
    _write_blueprint(xdg["blueprints"], "stub_bp")
    monkeypatch.setenv("SWARM_TEST_MODE", "1")

    result = runner.invoke(swarm_cli.app, ["compile", "stub_bp"])

    assert result.exit_code == 0, result.stdout
    stub = xdg["bin"] / "stub_bp"
    assert stub.is_file()
    assert os.access(stub, os.X_OK)
    assert "Installed stub executable" in result.stdout
    mock_run.assert_not_called()


@patch("subprocess.run")
def test_compile_rejects_unsafe_name_before_building(mock_run, xdg):
    result = runner.invoke(swarm_cli.app, ["compile", "../escape"])

    assert result.exit_code == 1
    mock_run.assert_not_called()


def test_compile_missing_blueprint_exits_1(xdg):
    result = runner.invoke(swarm_cli.app, ["compile", "ghost_bp_xyz"])

    assert result.exit_code == 1
    assert "not found" in result.stdout


# --- Workstream B: launch fallback ------------------------------------------


@patch("subprocess.run")
def test_launch_falls_back_to_installed_source(mock_run, xdg):
    entry = _write_blueprint(xdg["blueprints"], "src_bp")
    mock_run.return_value = _ok_process()

    result = runner.invoke(swarm_cli.app, ["launch", "src_bp"])

    assert result.exit_code == 0, result.stdout
    assert "installed source" in result.stdout
    mock_run.assert_called_once_with(
        [sys.executable, str(entry)], capture_output=True, text=True, check=False
    )


@patch("subprocess.run")
def test_launch_prefers_compiled_binary_over_source(mock_run, xdg):
    _write_blueprint(xdg["blueprints"], "both_bp")
    binary = _write_executable(xdg["bin"] / "both_bp")
    mock_run.return_value = _ok_process()

    result = runner.invoke(swarm_cli.app, ["launch", "both_bp"])

    assert result.exit_code == 0, result.stdout
    assert "installed source" not in result.stdout
    mock_run.assert_called_once_with(
        [str(binary)], capture_output=True, text=True, check=False
    )


@patch("subprocess.run")
def test_launch_falls_back_to_bundled_source(mock_run, xdg):
    mock_run.return_value = _ok_process()

    result = runner.invoke(swarm_cli.app, ["launch", "codey"])

    assert result.exit_code == 0, result.stdout
    assert "bundled source" in result.stdout
    cmd = mock_run.call_args.args[0]
    assert cmd[0] == sys.executable
    assert cmd[1].endswith(os.path.join("blueprints", "codey", "codey_cli.py"))


def test_launch_missing_all_tiers_exits_1(xdg):
    result = runner.invoke(swarm_cli.app, ["launch", "no_such_bp_xyz"])

    assert result.exit_code == 1
    assert "not found or not executable" in result.stdout
    assert "os-cli compile" in result.stdout


@patch("subprocess.run")
def test_launch_source_fallback_is_not_interactive(mock_run, xdg, monkeypatch):
    """A prompt would hang hook-driven runs, so the fallback must never ask."""
    entry = _write_blueprint(xdg["blueprints"], "quiet_bp")
    mock_run.return_value = _ok_process()
    monkeypatch.setattr("builtins.input", lambda *a, **k: pytest.fail("launch prompted"))

    result = runner.invoke(swarm_cli.app, ["launch", "quiet_bp", "--message", "hello"])

    assert result.exit_code == 0, result.stdout
    mock_run.assert_called_once_with(
        [sys.executable, str(entry), "--message", "hello"],
        capture_output=True,
        text=True,
        check=False,
    )


# --- Workstream C: delete / uninstall scope ---------------------------------


def test_delete_default_removes_source_and_binary(xdg):
    _write_blueprint(xdg["blueprints"], "both_del")
    binary = _write_executable(xdg["bin"] / "both_del")

    result = runner.invoke(swarm_cli.app, ["delete", "both_del"])

    assert result.exit_code == 0, result.stdout
    assert not (xdg["blueprints"] / "both_del").exists()
    assert not binary.exists()
    assert "Removed blueprint source" in result.stdout
    assert "Removed executable" in result.stdout


def test_delete_source_flag_leaves_binary(xdg):
    _write_blueprint(xdg["blueprints"], "src_del")
    binary = _write_executable(xdg["bin"] / "src_del")

    result = runner.invoke(swarm_cli.app, ["delete", "src_del", "--source"])

    assert result.exit_code == 0, result.stdout
    assert not (xdg["blueprints"] / "src_del").exists()
    assert binary.is_file()
    assert "Removed executable" not in result.stdout


def test_delete_binary_flag_leaves_source(xdg):
    _write_blueprint(xdg["blueprints"], "bin_del")
    binary = _write_executable(xdg["bin"] / "bin_del")

    result = runner.invoke(swarm_cli.app, ["delete", "bin_del", "--binary"])

    assert result.exit_code == 0, result.stdout
    assert (xdg["blueprints"] / "bin_del").is_dir()
    assert not binary.exists()
    assert "Removed blueprint source" not in result.stdout


def test_delete_all_flag_matches_default(xdg):
    _write_blueprint(xdg["blueprints"], "all_del")
    binary = _write_executable(xdg["bin"] / "all_del")

    result = runner.invoke(swarm_cli.app, ["delete", "all_del", "--all"])

    assert result.exit_code == 0, result.stdout
    assert not (xdg["blueprints"] / "all_del").exists()
    assert not binary.exists()


def test_delete_nothing_present_exits_1(xdg):
    result = runner.invoke(swarm_cli.app, ["delete", "absent_bp"])

    assert result.exit_code == 1
    # click >=8.2 splits stderr from stdout in CliRunner results; the
    # "Nothing to remove" summary is written to stderr.
    assert "Nothing to remove" in result.output


def test_uninstall_removes_binary_only(xdg):
    _write_blueprint(xdg["blueprints"], "uninst_bp")
    binary = _write_executable(xdg["bin"] / "uninst_bp")

    result = runner.invoke(swarm_cli.app, ["uninstall", "uninst_bp"])

    assert result.exit_code == 0, result.stdout
    assert not binary.exists()
    assert (xdg["blueprints"] / "uninst_bp").is_dir()


def test_delete_refuses_to_unlink_a_directory_in_bin_dir(xdg):
    directory = xdg["bin"] / "dir_bp"
    directory.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(swarm_cli.app, ["delete", "dir_bp", "--binary"])

    assert result.exit_code == 1
    assert directory.is_dir()


def test_list_installed_distinguishes_shim_from_executable(xdg):
    _write_executable(xdg["bin"] / "compiled_bp")
    shim = xdg["bin"] / "shim_bp"
    shim.write_text("#!/bin/sh\nexec python3 thing.py\n", encoding="utf-8")
    shim.chmod(0o755)

    result = runner.invoke(swarm_cli.app, ["list", "--installed"])

    assert result.exit_code == 0, result.stdout
    assert "- compiled_bp (executable)" in result.stdout
    assert "- shim_bp (shim)" in result.stdout

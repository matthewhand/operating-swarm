import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from swarm.core import (
    swarm_cli,  # This is the Typer app instance
)

runner = CliRunner()

EXPECTED_EXE_NAME = "test_blueprint" # Used in launch tests

@pytest.fixture
def mock_dirs(tmp_path):
    """
    Creates temporary directories for testing XDG paths.
    Returns a dictionary of paths.
    """
    # These will be the values our patched path functions return
    mock_user_data_dir = tmp_path / "user_data_for_swarm"
    mock_user_config_dir = tmp_path / "user_config_for_swarm"
    mock_user_cache_dir = tmp_path / "user_cache_for_swarm"

    # Derived paths based on the new structure in paths.py
    mock_user_blueprints_dir = mock_user_data_dir / "blueprints"
    # For non-Windows, get_user_bin_dir() returns Path.home() / ".local" / "bin"
    # For testing, we want a predictable, temporary location.
    # So, we'll mock get_user_bin_dir to return a subdir of tmp_path.
    mock_user_bin_dir_test = tmp_path / "user_bin_test"

    # Ensure these base directories for mocking are created if paths.py functions are called by mistake
    # before patching, though ideally patching happens first.
    mock_user_data_dir.mkdir(parents=True, exist_ok=True)
    mock_user_config_dir.mkdir(parents=True, exist_ok=True)
    mock_user_cache_dir.mkdir(parents=True, exist_ok=True)
    mock_user_blueprints_dir.mkdir(parents=True, exist_ok=True)
    mock_user_bin_dir_test.mkdir(parents=True, exist_ok=True)

    return {
        "data_dir": mock_user_data_dir,
        "config_dir": mock_user_config_dir,
        "cache_dir": mock_user_cache_dir,
        "blueprints_dir": mock_user_blueprints_dir,
        "bin_dir": mock_user_bin_dir_test, # This is what get_user_bin_dir will be mocked to return
    }

@pytest.fixture(autouse=True)
def patch_xdg_paths(mocker, mock_dirs):
    """
    Automatically patches all relevant functions in swarm.core.paths
    to use the temporary directories from mock_dirs.
    """
    mocker.patch("swarm.core.paths.get_user_data_dir_for_swarm", return_value=mock_dirs["data_dir"])
    mocker.patch("swarm.core.paths.get_user_config_dir_for_swarm", return_value=mock_dirs["config_dir"])
    mocker.patch("swarm.core.paths.get_user_cache_dir_for_swarm", return_value=mock_dirs["cache_dir"])
    mocker.patch("swarm.core.paths.get_user_blueprints_dir", return_value=mock_dirs["blueprints_dir"])
    mocker.patch("swarm.core.paths.get_user_bin_dir", return_value=mock_dirs["bin_dir"])
    # ensure_swarm_directories_exist is called at import time in swarm_cli.py.
    # We need to ensure it can run without error, or mock it if it causes issues
    # during test collection/setup before these patches are fully applied.
    # For now, the individual getters are patched. If ensure_swarm_directories_exist itself
    # needs more complex mocking (e.g. if it's called before this fixture), that can be added.
    # It's generally better if such functions are idempotent or designed to be test-friendly.
    # Since ensure_swarm_directories_exist calls the getters, patching the getters should suffice.


def test_swarm_cli_entrypoint():
    result = runner.invoke(swarm_cli.app, ["--help"])
    if result.exit_code != 0:  # surface the underlying exception, not just the code
        raise AssertionError(f"exit={result.exit_code} exc={result.exception!r} out={result.output[:500]}")
    assert result.exit_code == 0
    assert "[OPTIONS] COMMAND [ARGS]..." in result.stdout
    assert "Operating Swarm CLI (OS CLI)" in result.stdout


@patch("subprocess.run")
def test_swarm_cli_install_executable_creates_executable(mock_pyinstaller_run, mock_dirs, mocker, monkeypatch):
    # mock_dirs are already applied via the patch_xdg_paths autouse fixture
    install_bin_dir = mock_dirs["bin_dir"] # This is where executables should go
    blueprints_src_dir = mock_dirs["blueprints_dir"] # This is where source blueprints are found
    # cache_dir will be used by pyinstaller for workpath/specpath, patched via get_user_cache_dir_for_swarm

    blueprint_name = "test_blueprint"
    target_path = install_bin_dir / blueprint_name # Expected executable path

    # Create a dummy blueprint source
    source_dir = blueprints_src_dir / blueprint_name
    source_dir.mkdir(parents=True, exist_ok=True)
    entry_point_name = "main.py"
    entry_point_path = source_dir / entry_point_name
    entry_point_path.write_text("print('hello from blueprint')")

    # Mock find_entry_point if its logic is complex or external
    mocker.patch("swarm.core.swarm_cli.find_entry_point", return_value=entry_point_name)

    # Test mode (shim creation)
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    # Invoke the renamed command "install-executable"
    result_test_mode = runner.invoke(swarm_cli.app, ["install-executable", blueprint_name])
    if result_test_mode.exit_code != 0:
        print(f"CLI Output (Test Mode):\n{result_test_mode.stdout}")
    assert result_test_mode.exit_code == 0, result_test_mode.stdout
    assert f"Installing blueprint '{blueprint_name}' as executable..." in result_test_mode.stdout
    # Message text is either the historical "Test-mode shim" or current "Installed stub".
    out = result_test_mode.stdout
    assert (
        f"Test-mode shim installed at: {target_path}" in out
        or f"Installed stub executable: {target_path}" in out
    ), out
    assert target_path.exists()
    assert os.access(target_path, os.X_OK)
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)

    # Production mode (PyInstaller call)
    mock_pyinstaller_process = MagicMock()
    mock_pyinstaller_process.returncode = 0
    mock_pyinstaller_process.stdout = f"PyInstaller finished successfully. Executable at {target_path}"
    mock_pyinstaller_process.stderr = ""
    mock_pyinstaller_run.return_value = mock_pyinstaller_process

    result_prod_mode = runner.invoke(swarm_cli.app, ["install-executable", blueprint_name])
    if result_prod_mode.exit_code != 0:
        print(f"CLI Output (Prod Mode):\n{result_prod_mode.stdout}")
    assert result_prod_mode.exit_code == 0, result_prod_mode.stdout
    assert f"Installing blueprint '{blueprint_name}' as executable..." in result_prod_mode.stdout
    assert f"Successfully installed '{blueprint_name}' to {target_path}" in result_prod_mode.stdout

    mock_pyinstaller_run.assert_called_once()
    args, kwargs = mock_pyinstaller_run.call_args
    cmd_list = args[0]
    assert "pyinstaller" in cmd_list[0] # Check if pyinstaller is the command
    assert str(entry_point_path) in cmd_list
    assert "--name" in cmd_list
    assert cmd_list[cmd_list.index("--name") + 1] == blueprint_name
    assert "--distpath" in cmd_list
    assert cmd_list[cmd_list.index("--distpath") + 1] == str(install_bin_dir)
    # Check workpath and specpath use the mocked cache dir
    expected_workpath = mock_dirs["cache_dir"] / "build" / blueprint_name
    expected_specpath = mock_dirs["cache_dir"] / "specs"
    assert "--workpath" in cmd_list
    assert cmd_list[cmd_list.index("--workpath") + 1] == str(expected_workpath)
    assert "--specpath" in cmd_list
    assert cmd_list[cmd_list.index("--specpath") + 1] == str(expected_specpath)


@patch("subprocess.run")
def test_swarm_install_executable_failure(mock_run, mock_dirs, mocker, monkeypatch):
    # mock_dirs are applied via patch_xdg_paths
    blueprints_src_dir = mock_dirs["blueprints_dir"]
    blueprint_name = "fail_blueprint"

    # Create dummy blueprint source
    source_dir = blueprints_src_dir / blueprint_name
    source_dir.mkdir(parents=True, exist_ok=True)
    entry_point_name = "fail_main.py"
    entry_point_path = source_dir / entry_point_name
    entry_point_path.write_text("print('fail')")

    mocker.patch("swarm.core.swarm_cli.find_entry_point", return_value=entry_point_name)

    error_stderr = "PyInstaller error: Build failed!"
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["pyinstaller", "..."], stderr=error_stderr
    )

    monkeypatch.delenv("SWARM_TEST_MODE", raising=False) # Ensure not in test mode

    result = runner.invoke(swarm_cli.app, ["install-executable", blueprint_name])

    assert result.exit_code == 1, result.stdout
    assert "Error during PyInstaller execution" in result.stdout
    assert error_stderr in result.stdout


@patch("subprocess.run")
def test_swarm_launch_runs_executable(mock_run, mock_dirs, mocker):
    # mock_dirs applied via patch_xdg_paths
    install_bin_dir = mock_dirs["bin_dir"] # This is where executables are looked for
    blueprint_name = EXPECTED_EXE_NAME
    exe_path = install_bin_dir / blueprint_name

    # Create a dummy executable
    exe_path.touch(exist_ok=True)
    os.chmod(exe_path, 0o755) # Make it executable

    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.stdout = "Blueprint output"
    mock_process.stderr = ""
    mock_run.return_value = mock_process

    # No need to patch INSTALLED_BIN_DIR on swarm_cli, as it uses paths.get_user_bin_dir()
    # which is already patched by patch_xdg_paths.

    result = runner.invoke(
        swarm_cli.app,
        ["launch", blueprint_name],
        catch_exceptions=False, # So Pytest handles it
    )

    assert result.exit_code == 0, f"CLI failed unexpectedly. Output:\n{result.stdout}"
    assert f"Launching '{blueprint_name}' with: {exe_path}" in result.stdout
    mock_run.assert_called_once_with([str(exe_path)], capture_output=True, text=True, check=False)


def test_swarm_launch_failure_not_found(mock_dirs, mocker):
    # mock_dirs applied via patch_xdg_paths
    install_bin_dir = mock_dirs["bin_dir"]
    blueprint_name = "nonexistent_blueprint"
    expected_path = install_bin_dir / blueprint_name # Path where it would be if it existed

    # Ensure it doesn't exist
    if expected_path.exists():
        expected_path.unlink()

    # No need to patch INSTALLED_BIN_DIR on swarm_cli

    result = runner.invoke(swarm_cli.app, ["launch", blueprint_name])

    assert result.exit_code == 1, result.stdout
    # The error message in swarm_cli.py uses paths.get_user_bin_dir() to construct the message
    # and our patch_xdg_paths fixture ensures this returns mock_dirs["bin_dir"].
    expected_error_msg_path = mock_dirs["bin_dir"] / blueprint_name
    assert f"Error: Blueprint executable not found or not executable: {expected_error_msg_path}" in result.stdout.strip()

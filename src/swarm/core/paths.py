import os
import sys  # Import sys module for platform checking
from pathlib import Path

import platformdirs

APP_NAME = "swarm"
APP_AUTHOR = "OpenSwarm"  # Using OpenSwarm as author for platformdirs


def get_user_data_dir_for_swarm() -> Path:
    """
    Returns the user-specific data directory for swarm.
    Example: ~/.local/share/OpenSwarm/swarm/ (or similar based on APP_AUTHOR)
    """
    # Allow override for testing/sandboxes
    override = os.environ.get("SWARM_USER_DATA_DIR")
    if override:
        return Path(override)
    return Path(platformdirs.user_data_dir(appname=APP_NAME, appauthor=APP_AUTHOR))


def get_user_blueprints_dir() -> Path:
    """
    Returns the directory where user-installed blueprint sources are stored.
    Example: ~/.local/share/OpenSwarm/swarm/blueprints/
    """
    return get_user_data_dir_for_swarm() / "blueprints"


def get_user_bin_dir() -> Path:
    """
    Returns the user-specific directory for Swarm's managed executables/launchers.
    This will be a 'bin' subdirectory within the application's user data directory.
    Example: ~/.local/share/OpenSwarm/swarm/bin/ on Linux
             %APPDATA%\\OpenSwarm\\swarm\\bin on Windows
    Users may need to add this location to their PATH if they wish to run these
    executables directly from any terminal location.
    """
    return get_user_data_dir_for_swarm() / "bin"


def get_user_cache_dir_for_swarm() -> Path:
    """
    Returns the user-specific cache directory for swarm.
    Example: ~/.cache/OpenSwarm/swarm/ on Linux.
    """
    return Path(platformdirs.user_cache_dir(appname=APP_NAME, appauthor=APP_AUTHOR))


def get_user_config_dir_for_swarm() -> Path:
    """
    Returns the user-specific config directory for swarm.
    Example: ~/.config/OpenSwarm/swarm/ on Linux.
    """
    return Path(platformdirs.user_config_dir(appname=APP_NAME, appauthor=APP_AUTHOR))


def get_swarm_config_file(config_filename: str = "swarm_config.json") -> Path:
    """
    Returns the full path to the swarm configuration file.

    Defaults to ``swarm_config.json`` within the user config directory — the name
    every reader and writer uses (``config_loader.DEFAULT_CONFIG_FILENAME``,
    ``_xdg_config_path``, ``swarm_config.example.json``). It previously claimed
    ``config.yaml``, which nothing writes and the JSON loader could not read.
    Uses basename only to prevent path traversal.
    """
    config_dir = get_user_config_dir_for_swarm()
    safe_filename = Path(config_filename).name  # Strip any path components
    return config_dir / safe_filename


def get_project_root_dir() -> Path:
    """
    Returns the project root directory.
    This assumes the script is located at <project_root>/src/swarm/core/paths.py.
    Useful for development, testing, or accessing project-relative resources.
    """
    return Path(__file__).resolve().parent.parent.parent.parent


def _safe_mkdir(path: Path) -> bool:
    """Create ``path`` (and parents). Return False on OSError (e.g. broken XDG symlink).

    Import-time callers must not crash the whole CLI when one XDG root is unusable
    (broken ``~/.cache`` symlink is common on multi-disk home layouts).
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def ensure_swarm_directories_exist():
    """
    Ensures all standard Swarm XDG directories and the user bin directory exist.
    Call this early in application startup.

    Best-effort: failures for individual roots are ignored so a broken cache
    path does not block config/data setup or CLI import.
    """
    _safe_mkdir(get_user_data_dir_for_swarm())
    _safe_mkdir(get_user_blueprints_dir())
    _safe_mkdir(get_user_bin_dir())
    _safe_mkdir(get_user_cache_dir_for_swarm())
    _safe_mkdir(get_user_config_dir_for_swarm())
    try:
        from swarm.core.workdir import get_workspaces_dir

        _safe_mkdir(get_workspaces_dir())
    except Exception:
        pass


if __name__ == "__main__":
    print(f"Current sys.platform: {sys.platform}")
    print(f"Project Root Dir:   {get_project_root_dir()}")
    print(f"User Data Dir:      {get_user_data_dir_for_swarm()}")
    print(f"User Blueprints Dir: {get_user_blueprints_dir()}")
    print(f"User Bin Dir:       {get_user_bin_dir()}")
    print(f"User Cache Dir:     {get_user_cache_dir_for_swarm()}")
    print(f"User Config Dir:    {get_user_config_dir_for_swarm()}")
    print(f"Swarm Config File:  {get_swarm_config_file()}")
    print("\nEnsuring directories exist...")
    ensure_swarm_directories_exist()
    print("All listed directories should now exist.")
    print("Done.")

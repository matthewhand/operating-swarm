import logging
import os
import shutil
import sys  # Import sys module for platform checking
import tempfile
from pathlib import Path

import platformdirs

logger = logging.getLogger(__name__)

APP_NAME = "swarm"
APP_AUTHOR = "OpenSwarm"  # Using OpenSwarm as author for platformdirs

# Directory override for the one config root. File-level names below are
# overlays: they point at one file or a data directory, not a second root.
CONFIG_DIR_ENV = "SWARM_CONFIG_DIR"
CONFIG_FILE_OVERLAYS: tuple[str, ...] = (
    "SWARM_CONFIG_PATH",
    "SWARM_ROUTER_DESIGNS",
    "SWARM_AGENT_SETTINGS_PATH",
    "SWARM_CHAT_DIR",
    "SWARM_USER_DATA_DIR",
    "SWARM_RESPONSES_DIR",
)


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


class ConfigRootConflict(RuntimeError):
    """Legacy and canonical config roots both contain a file that differs.

    Startup must refuse. Picking either tree would hide the other half.
    """

    def __init__(
        self,
        legacy: Path,
        canonical: Path,
        relative: Path,
        other: Path | None = None,
    ):
        self.legacy = legacy
        self.canonical = canonical
        self.relative = relative
        self.other = other
        right = other if other is not None else canonical / relative
        super().__init__(
            f"Config root conflict: {legacy / relative} differs from "
            f"{right}. Refusing to pick one silently. "
            "Keep the tree you want, remove or merge the other, or set "
            f"{CONFIG_DIR_ENV} to the directory that should win."
        )


def _xdg_style_config_root() -> Path:
    """XDG config root: ``$XDG_CONFIG_HOME/<app>`` or the home config dir."""
    xdg = (os.environ.get("XDG_CONFIG_HOME") or "").strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / APP_NAME


def _windows_style_config_root() -> Path:
    """Windows config root: ``%APPDATA%\\OpenSwarm\\swarm``."""
    appdata = (os.environ.get("APPDATA") or "").strip()
    base = Path(appdata).expanduser() if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_AUTHOR / APP_NAME


def config_root() -> Path:
    """One resolver for every Swarm config file.

    ``SWARM_CONFIG_DIR`` wins when set. Otherwise Windows uses
    ``%APPDATA%/OpenSwarm/swarm`` and every other platform uses the XDG
    config directory (``$XDG_CONFIG_HOME/swarm`` or ``~/.config/swarm``).

    Per-file env vars in ``CONFIG_FILE_OVERLAYS`` name one file or a data
    directory. They are overlays on top of this root, not a second root.
    Chat JSON stays on the data directory (#1435).
    """
    override = (os.environ.get(CONFIG_DIR_ENV) or "").strip()
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        return _windows_style_config_root()
    return _xdg_style_config_root()


def get_user_config_dir_for_swarm() -> Path:
    """Canonical user config directory. Alias of :func:`config_root`."""
    return config_root()


def _dir_key(path: Path) -> str:
    try:
        return os.path.normcase(str(path.expanduser().resolve()))
    except OSError:
        return os.path.normcase(str(path.expanduser()))


def _same_dir(left: Path, right: Path) -> bool:
    if _dir_key(left) == _dir_key(right):
        return True
    try:
        if left.exists() and right.exists():
            return os.path.samefile(left, right)
    except OSError:
        return False
    return False


def _platformdirs_config_dir() -> Path | None:
    """Live library path, when it differs from the formulas above.

    Always ask platformdirs. On Windows the formula and the library usually
    match and the duplicate is dropped; when they do not, the library path
    is still a legacy root that must be copied.
    """
    try:
        return Path(platformdirs.user_config_dir(appname=APP_NAME, appauthor=APP_AUTHOR))
    except Exception:
        logger.debug("platformdirs config dir unavailable", exc_info=True)
        return None


def legacy_config_roots() -> list[Path]:
    """Directories that used to hold config before :func:`config_root`.

    Includes the author-scoped XDG folder (``OpenSwarm/swarm``), macOS
    Application Support, the Windows roaming folder, and the XDG folder
    when the canonical root is somewhere else (``SWARM_CONFIG_DIR`` or
    Windows). The canonical root itself is never listed.
    """
    canonical = config_root()
    xdg = _xdg_style_config_root()
    candidates = [
        xdg.parent / APP_AUTHOR / APP_NAME,
        Path.home() / "Library" / "Application Support" / APP_AUTHOR / APP_NAME,
        Path.home() / "Library" / "Application Support" / APP_NAME,
        _windows_style_config_root(),
        xdg,
    ]
    live = _platformdirs_config_dir()
    if live is not None:
        candidates.append(live)
    seen: set[str] = set()
    out: list[Path] = []
    for cand in candidates:
        if _same_dir(cand, canonical):
            continue
        key = _dir_key(cand)
        if key in seen:
            continue
        seen.add(key)
        out.append(cand)
    return out


def _iter_legacy_files(root: Path):
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]
        for name in filenames:
            path = current / name
            if path.is_symlink():
                # A symlinked config file (often ``.env``) must move with the
                # tree. Copy the referent's bytes later; do not walk a
                # directory symlink (those names were already dropped).
                if path.is_file():
                    yield path
                continue
            if not path.is_file():
                continue
            yield path


def startup_should_migrate_config() -> bool:
    """Whether process startup may copy a legacy config tree.

    Pytest imports Django and the CLI while collecting tests, before the
    XDG isolation fixture runs. A migrate at that moment would copy or
    refuse against the operator's real config directory (#1335). Direct
    calls to :func:`migrate_legacy_config_root` are unchanged so unit tests
    can still exercise the copy. Set ``SWARM_ALLOW_CONFIG_MIGRATE_IN_TESTS=1``
    to opt back in, or ``SWARM_SKIP_CONFIG_MIGRATE=1`` to force it off.
    """
    skip = (os.environ.get("SWARM_SKIP_CONFIG_MIGRATE") or "").strip().lower()
    if skip in {"1", "true", "yes", "on"}:
        return False
    under_pytest = "pytest" in sys.modules or bool(os.environ.get("PYTEST_VERSION"))
    if not under_pytest:
        return True
    allow = (os.environ.get("SWARM_ALLOW_CONFIG_MIGRATE_IN_TESTS") or "").strip().lower()
    return allow in {"1", "true", "yes", "on"}


def _same_file_bytes(left: Path, right: Path) -> bool:
    """True when both paths are regular files (symlink targets count) with equal bytes.

    ``OSError`` propagates. A permission or I/O failure is not a content mismatch,
    and treating it as one would refuse startup with the wrong instruction.
    """
    if not (left.is_file() and right.is_file()):
        return False
    return left.read_bytes() == right.read_bytes()


def _copy_legacy_file(src: Path, dest: Path) -> None:
    """Copy ``src`` onto ``dest`` as a regular file.

    A legacy symlink is followed so the new root does not keep the old link.
    Bytes land on a temp name in the destination directory, then replace
    ``dest``. A failed copy removes that temp name so the next boot does not
    see a short file and report a false conflict.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dest.name}.",
        suffix=".migrate",
        dir=dest.parent,
    )
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp, follow_symlinks=True)
        os.replace(tmp, dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def migrate_legacy_config_root() -> list[Path]:
    """Copy legacy config trees onto :func:`config_root`.

    Identical files are left alone, including when the canonical path is a
    symlink to the same bytes. A file symlink in a legacy tree is copied as
    a regular file so the new root does not depend on the old link.
    A same-named file with different bytes raises :class:`ConfigRootConflict`
    before any copy, including when two legacy trees disagree with each
    other. Missing legacy directories are a no-op. Process startup must call
    :func:`startup_should_migrate_config` first; unit tests call this directly.
    """
    canonical = config_root()
    planned: list[tuple[Path, Path, Path]] = []
    claimed: dict[str, Path] = {}
    for legacy in legacy_config_roots():
        if not legacy.is_dir() or _same_dir(legacy, canonical):
            continue
        for src in _iter_legacy_files(legacy):
            relative = src.relative_to(legacy)
            dest = canonical / relative
            key = _dir_key(dest)
            if dest.exists() or dest.is_symlink():
                if not _same_file_bytes(dest, src):
                    raise ConfigRootConflict(legacy, canonical, relative)
                continue
            prior = claimed.get(key)
            if prior is not None:
                if not _same_file_bytes(prior, src):
                    raise ConfigRootConflict(legacy, canonical, relative, other=prior)
                continue
            claimed[key] = src
            planned.append((legacy, src, dest))
    copied: list[Path] = []
    for _legacy, src, dest in planned:
        _copy_legacy_file(src, dest)
        copied.append(dest)
    if copied:
        sources = ", ".join(str(path) for path in dict.fromkeys(item[0] for item in planned))
        logger.warning(
            "Migrated %s file(s) from legacy config root(s) %s to %s. "
            "The legacy tree was left in place.",
            len(copied),
            sources,
            canonical,
        )
    return copied


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

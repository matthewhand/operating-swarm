"""#1434 — one config root, legacy migrate-or-refuse, Windows and XDG.

ADR-002 §2.2 / §7.3: ``config_root()`` is the only resolver.
``SWARM_CONFIG_DIR`` overrides it. Windows uses
``%APPDATA%/OpenSwarm/swarm``; other platforms use the XDG config
directory. Startup copies a legacy tree or refuses on conflict.
``_xdg_config_path()`` and ``get_user_config_dir_for_swarm()`` share
that directory. Compose mounts ``~/.config/swarm``; CLI init writes
there. No syncer. Data/cache stay on platformdirs (#1435).
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

import pytest

from swarm.core.config_loader import DEFAULT_CONFIG_FILENAME, _xdg_config_path
from swarm.core.paths import (
    APP_AUTHOR,
    APP_NAME,
    CONFIG_DIR_ENV,
    CONFIG_FILE_OVERLAYS,
    ConfigRootConflict,
    config_root,
    get_swarm_config_file,
    get_user_config_dir_for_swarm,
    migrate_legacy_config_root,
    startup_should_migrate_config,
)
from swarm.core.remotes import resolve_config_path
from swarm.utils.dotenv_load import xdg_swarm_env_path


def _pin_unix_config_root(monkeypatch) -> None:
    """XDG assertions assume a non-Windows host.

    Windows ignores ``XDG_CONFIG_HOME``. The roaming formula reads
    ``%APPDATA%``. ``platformdirs.user_config_dir`` stays on the Windows
    class bound at import, and that helper defaults to ``roaming=False``,
    so it reads ``%LOCALAPPDATA%`` (``WIN_PD_OVERRIDE_LOCAL_APPDATA``), not
    ``WIN_PD_OVERRIDE_APPDATA``. Patching ``sys.platform`` does not retarget
    the class. Point every one of those variables at a directory that is
    never created, and replace ``user_config_dir`` so a stub or an
    already-imported Windows class cannot still return the operator tree.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    absent = str(
        Path(tempfile.gettempdir()) / f"swarm-pin-absent-appdata-{id(monkeypatch)}"
    )
    monkeypatch.setenv("APPDATA", absent)
    monkeypatch.setenv("LOCALAPPDATA", absent)
    # Roaming override is not what user_config_dir reads. Set it anyway so a
    # roaming=True call cannot fall through to the operator profile.
    monkeypatch.setenv("WIN_PD_OVERRIDE_APPDATA", absent)
    monkeypatch.setenv("WIN_PD_OVERRIDE_LOCAL_APPDATA", absent)
    monkeypatch.setattr(
        "swarm.core.paths.platformdirs.user_config_dir",
        lambda *_args, **_kwargs: str(Path(absent) / APP_AUTHOR / APP_NAME),
    )


def test_helpers_share_one_directory_when_xdg_config_home_set(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    root = get_user_config_dir_for_swarm()
    assert root == tmp_path / "xdg" / APP_NAME
    assert _xdg_config_path() == root / DEFAULT_CONFIG_FILENAME
    assert get_swarm_config_file() == _xdg_config_path()
    assert xdg_swarm_env_path() == root / ".env"


def test_helpers_share_home_config_swarm_when_xdg_unset(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("SWARM_CONFIG_DIR", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    root = get_user_config_dir_for_swarm()
    assert root == tmp_path / "home" / ".config" / APP_NAME
    assert _xdg_config_path().parent == root
    assert get_swarm_config_file() == root / DEFAULT_CONFIG_FILENAME


def test_config_dir_env_overrides_xdg_and_windows(tmp_path, monkeypatch):
    custom = tmp_path / "custom-root"
    monkeypatch.setenv(CONFIG_DIR_ENV, str(custom))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert config_root() == custom
    assert get_user_config_dir_for_swarm() == custom
    assert get_swarm_config_file() == custom / DEFAULT_CONFIG_FILENAME


def test_windows_style_root_uses_appdata_not_xdg(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    appdata = tmp_path / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))
    assert config_root() == appdata / APP_AUTHOR / APP_NAME


def test_file_overlays_are_documented_and_not_a_second_root():
    assert "SWARM_CONFIG_PATH" in CONFIG_FILE_OVERLAYS
    assert "SWARM_ROUTER_DESIGNS" in CONFIG_FILE_OVERLAYS
    assert "SWARM_AGENT_SETTINGS_PATH" in CONFIG_FILE_OVERLAYS
    assert CONFIG_DIR_ENV not in CONFIG_FILE_OVERLAYS


def test_legacy_author_tree_migrates_with_warning(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    legacy = tmp_path / "xdg" / APP_AUTHOR / APP_NAME
    legacy.mkdir(parents=True)
    (legacy / "router_designs.json").write_text('{"ok": true}', encoding="utf-8")
    (legacy / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    nested = legacy / "notes"
    nested.mkdir()
    (nested / "readme.txt").write_text("keep", encoding="utf-8")

    records: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _Handler()
    log = logging.getLogger("swarm.core.paths")
    log.addHandler(handler)
    try:
        copied = migrate_legacy_config_root()
    finally:
        log.removeHandler(handler)

    canonical = config_root()
    assert canonical == tmp_path / "xdg" / APP_NAME
    assert (canonical / "router_designs.json").read_text(encoding="utf-8") == '{"ok": true}'
    assert (canonical / ".env").read_text(encoding="utf-8").startswith("OPENAI_API_KEY=")
    assert (canonical / "notes" / "readme.txt").read_text(encoding="utf-8") == "keep"
    assert (legacy / "router_designs.json").is_file()
    assert len(copied) == 3
    assert any("Migrated" in message for message in records)


def test_legacy_conflict_refuses_without_copying(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    legacy = tmp_path / "xdg" / APP_AUTHOR / APP_NAME
    canonical = tmp_path / "xdg" / APP_NAME
    legacy.mkdir(parents=True)
    canonical.mkdir(parents=True)
    (legacy / "swarm_config.json").write_text('{"from": "legacy"}', encoding="utf-8")
    (canonical / "swarm_config.json").write_text('{"from": "canonical"}', encoding="utf-8")
    (legacy / "agent_settings.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ConfigRootConflict, match="SWARM_CONFIG_DIR"):
        migrate_legacy_config_root()

    assert (canonical / "swarm_config.json").read_text(encoding="utf-8") == '{"from": "canonical"}'
    assert not (canonical / "agent_settings.json").exists()


def test_windows_legacy_xdg_tree_migrates(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: home)
    appdata = tmp_path / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata))
    # platformdirs binds Windows at import. user_config_dir defaults to
    # roaming=False, so it reads %LOCALAPPDATA% through the shell API, not
    # this APPDATA value. The override that call honors is
    # WIN_PD_OVERRIDE_LOCAL_APPDATA. Replace the helper too: Unix ignores
    # that variable, and a pre-bound stub would ignore it as well.
    monkeypatch.setenv("WIN_PD_OVERRIDE_LOCAL_APPDATA", str(appdata))
    monkeypatch.setattr(
        "swarm.core.paths.platformdirs.user_config_dir",
        lambda *_args, **_kwargs: str(appdata / APP_AUTHOR / APP_NAME),
    )
    legacy = home / ".config" / APP_NAME
    legacy.mkdir(parents=True)
    (legacy / "agent_settings.json").write_text('{"agents": {}}', encoding="utf-8")

    copied = migrate_legacy_config_root()

    dest = appdata / APP_AUTHOR / APP_NAME / "agent_settings.json"
    assert dest.read_text(encoding="utf-8") == '{"agents": {}}'
    assert dest in copied


def test_src_mentions_platformdirs_and_config_swarm_only_in_paths_py():
    """Acceptance: a grep of those literals under src hits only paths.py."""
    repo = Path(__file__).resolve().parents[2]
    src = repo / "src"
    needles = ("platformdirs", ".config/swarm")
    hits: list[str] = []
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".md", ".yml", ".yaml", ".json", ".toml", ".txt", ".sh"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(needle in text for needle in needles):
            hits.append(path.relative_to(repo).as_posix())
    assert hits == ["src/swarm/core/paths.py"]


def test_cli_create_if_missing_target_is_xdg_path(tmp_path, monkeypatch):
    """swarm-cli config init fallback must write the file discovery reads."""
    _pin_unix_config_root(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("SWARM_CONFIG_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    from swarm.core.config_loader import find_config_file

    found = find_config_file()
    dest = found if found else (get_user_config_dir_for_swarm() / DEFAULT_CONFIG_FILENAME)
    assert dest == _xdg_config_path()
    assert dest.parent == tmp_path / "xdg" / APP_NAME


def test_resolve_config_path_create_fallback_is_xdg(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("SWARM_CONFIG_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path() == _xdg_config_path()


def test_blank_xdg_config_home_falls_back_to_home_config(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", "   ")
    monkeypatch.delenv("SWARM_CONFIG_DIR", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    assert get_user_config_dir_for_swarm() == tmp_path / "home" / ".config" / APP_NAME


def test_discovery_and_writers_delegate_to_paths_helper():
    """No second hardcoded ``~/.config/swarm`` formula in the live writers."""
    repo = Path(__file__).resolve().parents[2]
    loader = (repo / "src" / "swarm" / "core" / "config_loader.py").read_text(
        encoding="utf-8"
    )
    remotes = (repo / "src" / "swarm" / "core" / "remote_teams.py").read_text(
        encoding="utf-8"
    )
    dotenv = (repo / "src" / "swarm" / "utils" / "dotenv_load.py").read_text(
        encoding="utf-8"
    )
    blueprint_base = (repo / "src" / "swarm" / "core" / "blueprint_base.py").read_text(
        encoding="utf-8"
    )
    assert "return get_swarm_config_file(DEFAULT_CONFIG_FILENAME)" in loader
    assert 'Path.home() / ".config"' not in remotes
    assert "get_user_config_dir_for_swarm()" in dotenv
    assert 'base / "swarm" / ".env"' not in dotenv
    assert "get_swarm_config_file()" in blueprint_base
    assert "Path.home() / '.config/swarm/swarm_config.json'" not in blueprint_base


def test_blueprint_profile_fallback_honors_xdg_config_home(tmp_path, monkeypatch):
    """Profile fallback must read ``$XDG_CONFIG_HOME/swarm``, not ``~/.config/swarm``."""
    import json

    from swarm.core.blueprint_base import BlueprintBase

    class _Probe(BlueprintBase):
        async def run(self, messages, **kwargs):
            if False:
                yield {}

    _pin_unix_config_root(monkeypatch)
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: home)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.delenv("DEFAULT_LLM", raising=False)
    monkeypatch.delenv("SWARM_CONFIG_PATH", raising=False)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    home_cfg = home / ".config" / APP_NAME
    home_cfg.mkdir(parents=True)
    (home_cfg / "swarm_config.json").write_text(
        json.dumps({"settings": {"default_llm_profile": "from_home"}}),
        encoding="utf-8",
    )
    xdg_cfg = xdg / APP_NAME
    xdg_cfg.mkdir(parents=True)
    (xdg_cfg / "swarm_config.json").write_text(
        json.dumps({"settings": {"default_llm_profile": "from_xdg"}}),
        encoding="utf-8",
    )

    bp = _Probe(
        "probe",
        config={
            "llm": {
                "from_xdg": {"provider": "mock"},
                "from_home": {"provider": "mock"},
            },
            "settings": {},
            "blueprints": {},
        },
    )
    assert bp._resolve_llm_profile() == "from_xdg"


def test_startup_migration_is_off_under_pytest(monkeypatch):
    """Collecting tests must not copy the operator's real config tree."""
    monkeypatch.delenv("SWARM_ALLOW_CONFIG_MIGRATE_IN_TESTS", raising=False)
    monkeypatch.delenv("SWARM_SKIP_CONFIG_MIGRATE", raising=False)
    assert startup_should_migrate_config() is False


def test_startup_migration_opt_in_and_force_off(monkeypatch):
    monkeypatch.setenv("SWARM_ALLOW_CONFIG_MIGRATE_IN_TESTS", "1")
    monkeypatch.delenv("SWARM_SKIP_CONFIG_MIGRATE", raising=False)
    assert startup_should_migrate_config() is True
    monkeypatch.setenv("SWARM_SKIP_CONFIG_MIGRATE", "1")
    assert startup_should_migrate_config() is False


def test_startup_hooks_ask_before_migrating():
    repo = Path(__file__).resolve().parents[2]
    for rel in (
        "src/swarm/apps.py",
        "src/swarm/core/swarm_cli.py",
        "src/swarm/utils/dotenv_load.py",
        "manage.py",
        "src/manage.py",
    ):
        text = (repo / rel).read_text(encoding="utf-8")
        assert "startup_should_migrate_config()" in text
        if rel.endswith("manage.py"):
            head = text.split("try:", 1)[0]
            assert "migrate_legacy_config_root()" in head


def test_unix_pin_does_not_copy_a_host_appdata_tree(tmp_path, monkeypatch):
    """Roaming APPDATA and the Local platformdirs path must not ride along.

    ``test_legacy_file_symlink_is_copied_as_regular_file`` still passed while
    copying ``%APPDATA%/OpenSwarm/swarm`` into the temp XDG root.
    ``user_config_dir`` defaults to ``roaming=False``, so it follows
    ``%LOCALAPPDATA%`` / ``WIN_PD_OVERRIDE_LOCAL_APPDATA``, not
    ``WIN_PD_OVERRIDE_APPDATA``. A stub installed first stands in for the
    Windows class bound at import.
    """
    roaming = tmp_path / "host-roaming"
    local = tmp_path / "host-local"
    roaming_tree = roaming / APP_AUTHOR / APP_NAME
    local_tree = local / APP_AUTHOR / APP_NAME
    roaming_tree.mkdir(parents=True)
    local_tree.mkdir(parents=True)
    (roaming_tree / "host_only.txt").write_text("HOST=1\n", encoding="utf-8")
    (local_tree / "local_only.txt").write_text("LOCAL=1\n", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(
        "swarm.core.paths.platformdirs.user_config_dir",
        lambda *_args, **_kwargs: str(local_tree),
    )

    _pin_unix_config_root(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")

    assert migrate_legacy_config_root() == []
    canonical = tmp_path / "xdg" / APP_NAME
    assert not (canonical / "host_only.txt").exists()
    assert not (canonical / "local_only.txt").exists()
    assert os.environ["WIN_PD_OVERRIDE_LOCAL_APPDATA"] != str(local)
    assert "host-local" not in os.environ["WIN_PD_OVERRIDE_LOCAL_APPDATA"]
    assert "host-roaming" not in os.environ["APPDATA"]


def test_legacy_file_symlink_is_copied_as_regular_file(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    legacy = tmp_path / "xdg" / APP_AUTHOR / APP_NAME
    legacy.mkdir(parents=True)
    target = tmp_path / "secret.env"
    target.write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")
    (legacy / ".env").symlink_to(target)

    copied = migrate_legacy_config_root()

    dest = tmp_path / "xdg" / APP_NAME / ".env"
    assert dest.read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-test\n"
    assert not dest.is_symlink()
    assert dest in copied
    assert (legacy / ".env").is_symlink()


def test_canonical_symlink_with_same_bytes_is_not_a_conflict(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    legacy = tmp_path / "xdg" / APP_AUTHOR / APP_NAME
    canonical = tmp_path / "xdg" / APP_NAME
    legacy.mkdir(parents=True)
    canonical.mkdir(parents=True)
    body = '{"from": "same"}\n'
    (legacy / "swarm_config.json").write_text(body, encoding="utf-8")
    kept = tmp_path / "kept.json"
    kept.write_text(body, encoding="utf-8")
    dest = canonical / "swarm_config.json"
    dest.symlink_to(kept)

    assert migrate_legacy_config_root() == []
    assert dest.is_symlink()
    assert dest.read_text(encoding="utf-8") == body


def test_two_legacy_trees_that_disagree_name_both_files(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: home)
    author = tmp_path / "xdg" / APP_AUTHOR / APP_NAME
    mac = home / "Library" / "Application Support" / APP_AUTHOR / APP_NAME
    author.mkdir(parents=True)
    mac.mkdir(parents=True)
    (author / "swarm_config.json").write_text('{"from": "author"}', encoding="utf-8")
    (mac / "swarm_config.json").write_text('{"from": "mac"}', encoding="utf-8")

    with pytest.raises(ConfigRootConflict, match="swarm_config.json") as exc:
        migrate_legacy_config_root()

    message = str(exc.value)
    assert str(author / "swarm_config.json") in message
    assert str(mac / "swarm_config.json") in message
    assert not (tmp_path / "xdg" / APP_NAME).exists()


def test_live_platformdirs_dir_migrates_when_it_differs(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    live = tmp_path / "from-platformdirs"
    live.mkdir()
    (live / "router_designs.json").write_text("{}", encoding="utf-8")

    def _live(*_args, **_kwargs):
        return str(live)

    monkeypatch.setattr("swarm.core.paths.platformdirs.user_config_dir", _live)
    copied = migrate_legacy_config_root()
    dest = tmp_path / "xdg" / APP_NAME / "router_designs.json"
    assert dest.read_text(encoding="utf-8") == "{}"
    assert dest in copied


def test_dotenv_load_reads_legacy_env_on_first_call(tmp_path, monkeypatch):
    """The first dotenv load must see secrets that still live in the legacy tree."""
    monkeypatch.setenv("SWARM_ALLOW_DOTENV_IN_TESTS", "1")
    monkeypatch.setenv("SWARM_ALLOW_CONFIG_MIGRATE_IN_TESTS", "1")
    monkeypatch.delenv("SWARM_SKIP_DOTENV", raising=False)
    monkeypatch.delenv("SWARM_SKIP_CONFIG_MIGRATE", raising=False)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("LEGACY_ONLY_KEY", raising=False)
    _pin_unix_config_root(monkeypatch)
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    legacy = xdg / APP_AUTHOR / APP_NAME
    legacy.mkdir(parents=True)
    (legacy / ".env").write_text("LEGACY_ONLY_KEY=from-legacy\n", encoding="utf-8")

    from swarm.utils.dotenv_load import load_swarm_dotenv

    try:
        load_swarm_dotenv(project_root=tmp_path / "project")
        assert os.environ["LEGACY_ONLY_KEY"] == "from-legacy"
    finally:
        os.environ.pop("LEGACY_ONLY_KEY", None)
    assert (xdg / APP_NAME / ".env").read_text(encoding="utf-8").startswith("LEGACY_ONLY_KEY=")


def test_failed_copy_does_not_leave_a_partial_canonical_file(tmp_path, monkeypatch):
    """A mid-copy OSError must not leave bytes that the next boot calls a conflict."""
    _pin_unix_config_root(monkeypatch)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    legacy = tmp_path / "xdg" / APP_AUTHOR / APP_NAME
    legacy.mkdir(parents=True)
    (legacy / "swarm_config.json").write_text('{"from": "legacy"}', encoding="utf-8")
    seen: list[Path] = []

    def _fail(_src, dst, **_kwargs):
        seen.append(Path(dst))
        Path(dst).write_text("PARTIAL", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr("swarm.core.paths.shutil.copy2", _fail)
    with pytest.raises(OSError, match="disk full"):
        migrate_legacy_config_root()

    canonical = tmp_path / "xdg" / APP_NAME
    dest = canonical / "swarm_config.json"
    assert seen
    assert all(path != dest for path in seen)
    assert not dest.exists()
    assert list(canonical.iterdir()) == []


def test_unreadable_compare_is_not_a_content_conflict(tmp_path, monkeypatch):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", lambda *_args, **_kwargs: tmp_path / "home")
    legacy = tmp_path / "xdg" / APP_AUTHOR / APP_NAME
    canonical = tmp_path / "xdg" / APP_NAME
    legacy.mkdir(parents=True)
    canonical.mkdir(parents=True)
    (legacy / "swarm_config.json").write_text("same", encoding="utf-8")
    (canonical / "swarm_config.json").write_text("same", encoding="utf-8")

    def _boom(_self):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_bytes", _boom)
    with pytest.raises(OSError, match="permission denied"):
        migrate_legacy_config_root()


@pytest.mark.parametrize("failure", ["conflict", "oserror"])
def test_manage_entry_points_do_not_swallow_migration_failure(monkeypatch, tmp_path, failure):
    """Root manage.py is what Docker and `python manage.py` run.

    A swallowed migration error falls through to the checkout .env. That file
    can set SWARM_CONFIG_DIR or SWARM_SKIP_CONFIG_MIGRATE, and AppConfig then
    skips the refusal this migration exists to enforce.
    """
    import importlib.util

    import django.core.management as mgmt
    import dotenv

    called: dict[str, bool] = {}
    monkeypatch.setattr(
        dotenv,
        "load_dotenv",
        lambda *_a, **_k: called.__setitem__("dotenv", True),
    )
    monkeypatch.setattr(
        mgmt,
        "execute_from_command_line",
        lambda _argv: called.__setitem__("django", True),
    )
    monkeypatch.setattr("swarm.core.paths.startup_should_migrate_config", lambda: True)

    def _boom():
        if failure == "conflict":
            raise ConfigRootConflict(
                tmp_path / "legacy",
                tmp_path / "canonical",
                Path("swarm_config.json"),
            )
        raise OSError("disk full")

    monkeypatch.setattr("swarm.core.paths.migrate_legacy_config_root", _boom)

    repo = Path(__file__).resolve().parents[2]
    for rel in ("manage.py", "src/manage.py"):
        called.clear()
        spec = importlib.util.spec_from_file_location(
            f"manage_under_test_{rel.replace('/', '_')}_{failure}",
            repo / rel,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        with pytest.raises((ConfigRootConflict, OSError)):
            module.main()
        assert called == {}, rel


@pytest.mark.django_db
def test_health_url_reports_resolved_config_root(tmp_path, monkeypatch):
    """GET /health through URL routing, including the SWARM_CONFIG_DIR override.

    Calling ``HealthCheckView.get`` directly does not prove the mounted route.
    """
    from rest_framework.test import APIClient

    root = tmp_path / "live-config-root"
    monkeypatch.setenv(CONFIG_DIR_ENV, str(root))
    client = APIClient()
    for path in ("/health", "/health/"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.data == {"status": "ok", "config_root": str(root)}

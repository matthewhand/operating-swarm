"""XDG-first dotenv loading (unit/shell env wins, then XDG, then checkout)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from swarm.utils.dotenv_load import (
    load_swarm_dotenv,
    upsert_swarm_env_secret,
    xdg_swarm_env_path,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_xdg_wins_over_project_env(tmp_path: Path):
    project = tmp_path / "project"
    xdg = tmp_path / "xdg"
    _write(project / ".env", "SHARED=from-project\nONLY_PROJECT=p\n")
    _write(xdg / "swarm" / ".env", "SHARED=from-xdg\nONLY_XDG=x\n")

    with patch("sys.platform", "linux"), patch.dict(
        os.environ,
                # #1335: load_swarm_dotenv() is a no-op under pytest so the suite
        # never loads the operator's ~/.config/swarm/.env. Opt back in --
        # clear=True would otherwise wipe the opt-in itself.
        {"SWARM_ALLOW_DOTENV_IN_TESTS": "1", "XDG_CONFIG_HOME": str(xdg), "PREEXISTING": "keep-me"},
        clear=True,
    ):
        loaded = load_swarm_dotenv(project_root=project)
        assert os.environ["PREEXISTING"] == "keep-me"
        assert os.environ["SHARED"] == "from-xdg"
        assert os.environ["ONLY_PROJECT"] == "p"
        assert os.environ["ONLY_XDG"] == "x"
        assert any("swarm" in item and "+2 keys" in item for item in loaded)


def test_process_env_not_overwritten_by_xdg(tmp_path: Path):
    project = tmp_path / "project"
    xdg = tmp_path / "xdg"
    _write(project / ".env", "TOKEN=from-project\n")
    _write(xdg / "swarm" / ".env", "TOKEN=from-xdg\n")

    with patch("sys.platform", "linux"), patch.dict(
        os.environ,
                # #1335: load_swarm_dotenv() is a no-op under pytest so the suite
        # never loads the operator's ~/.config/swarm/.env. Opt back in --
        # clear=True would otherwise wipe the opt-in itself.
        {"SWARM_ALLOW_DOTENV_IN_TESTS": "1", "XDG_CONFIG_HOME": str(xdg), "TOKEN": "from-systemd"},
        clear=True,
    ):
        load_swarm_dotenv(project_root=project)
        assert os.environ["TOKEN"] == "from-systemd"


def test_xdg_swarm_env_path_uses_xdg_config_home(tmp_path: Path):
    with (
        patch("sys.platform", "linux"),
        patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(tmp_path), "SWARM_CONFIG_DIR": ""},
            clear=False,
        ),
    ):
        assert xdg_swarm_env_path() == tmp_path / "swarm" / ".env"


# --- #1273: upsert_swarm_env_secret -----------------------------------------


def test_upsert_appends_new_secret_and_sets_process_env(tmp_path: Path):
    with (
        patch("sys.platform", "linux"),
        patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(tmp_path), "SWARM_CONFIG_DIR": ""},
            clear=False,
        ),
    ):
        path = upsert_swarm_env_secret("MY_COOKIE", "sid=abc123")
        assert path == tmp_path / "swarm" / ".env"
        text = path.read_text(encoding="utf-8")
        assert 'MY_COOKIE="sid=abc123"' in text
        assert os.environ["MY_COOKIE"] == "sid=abc123"


def test_upsert_replaces_only_its_own_key(tmp_path: Path):
    xdg = tmp_path / "swarm"
    xdg.mkdir(parents=True)
    env = xdg / ".env"
    env.write_text(
        "# operator comment\nKEEP=1  # inline comment stays\nOLD_COOKIE=\"stale\"\n",
        encoding="utf-8",
    )
    with (
        patch("sys.platform", "linux"),
        patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(tmp_path), "SWARM_CONFIG_DIR": ""},
            clear=False,
        ),
    ):
        upsert_swarm_env_secret("OLD_COOKIE", "fresh=2")
    text = env.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# operator comment"
    assert "KEEP=1" in lines[1] and "inline comment stays" in lines[1]
    assert lines[2] == 'OLD_COOKIE="fresh=2"'
    assert "stale" not in text
    # position preserved — no key was appended
    assert len(lines) == 3


def test_upsert_dollar_without_brace_stores_verbatim(tmp_path: Path):
    """Bare ``$`` (no ``{``) does not interpolate — stored and read back as-is.

    A literal ``${NAME}`` inside a value has no escape form in the loader's
    grammar; opaque machine-generated tokens (cookies, keys) never contain
    that sequence, which is the only input this store accepts.
    """
    with (
        patch("sys.platform", "linux"),
        patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(tmp_path), "SWARM_CONFIG_DIR": ""},
            clear=False,
        ),
    ):
        upsert_swarm_env_secret("SID", "mausbot_session=st-$123; Path=/")
        from dotenv import dotenv_values

        read_back = dotenv_values(xdg_swarm_env_path())
        assert read_back["SID"] == "mausbot_session=st-$123; Path=/"


def test_upsert_rejects_bad_names_and_multiline_values(tmp_path: Path):
    with (
        patch("sys.platform", "linux"),
        patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(tmp_path), "SWARM_CONFIG_DIR": ""},
            clear=False,
        ),
    ):
        import pytest

        with pytest.raises(ValueError):
            upsert_swarm_env_secret("HAS=EQ", "v")
        with pytest.raises(ValueError):
            upsert_swarm_env_secret("MULTI", "a\nb")

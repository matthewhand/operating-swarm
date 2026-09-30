import os
import sys
import tempfile
from pathlib import Path

from swarm.core import config_loader


def _pin_unix_config_root(monkeypatch) -> None:
    """These tests assert the XDG root. Windows uses %APPDATA% instead."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("SWARM_CONFIG_DIR", raising=False)


def test_xdg_config_discovery(monkeypatch):
    _pin_unix_config_root(monkeypatch)
    # Create a temp XDG config file
    with tempfile.TemporaryDirectory() as tmpdir:
        xdg_config_dir = Path(tmpdir) / "swarm"
        xdg_config_dir.mkdir(parents=True, exist_ok=True)
        config_path = xdg_config_dir / config_loader.DEFAULT_CONFIG_FILENAME
        config_path.write_text('{"llm": {"gpt-4o": {"provider": "openai", "model": "gpt-4o"}}}')
        monkeypatch.setenv("XDG_CONFIG_HOME", tmpdir)
        found = config_loader.find_config_file()
        assert found is not None
        assert found.samefile(config_path)

def test_config_fallback_to_cwd(monkeypatch):
    _pin_unix_config_root(monkeypatch)
    # Patch XDG_CONFIG_HOME to a temp dir with NO config file present
    with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as fake_xdg:
        monkeypatch.setenv("XDG_CONFIG_HOME", fake_xdg)
        cwd = Path(tmpdir)
        config_path = cwd / config_loader.DEFAULT_CONFIG_FILENAME
        config_path.write_text('{"llm": {"gpt-4o": {"provider": "openai", "model": "gpt-4o"}}}')
        old_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            found = config_loader.find_config_file()
            assert found is not None
            assert found.samefile(config_path)
        finally:
            os.chdir(old_cwd)

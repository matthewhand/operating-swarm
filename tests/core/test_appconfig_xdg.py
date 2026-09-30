"""Tests for XDG-aware config loading on the Django AppConfig.

``SwarmConfig._load_swarm_config`` is what makes the *server* honor
``~/.config/swarm/swarm_config.json`` (like ``swarm-cli`` already does). It
never raises, and resolves with precedence SWARM_CONFIG_PATH > XDG > cwd.
"""

from __future__ import annotations

import json
import sys

from swarm.apps import SwarmConfig


def _pin_unix_config_root(monkeypatch) -> None:
    """These tests assert the XDG root. Windows uses %APPDATA% instead."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("SWARM_CONFIG_DIR", raising=False)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def test_loads_from_xdg_when_present(monkeypatch, tmp_path):
    _pin_unix_config_root(monkeypatch)
    xdg = tmp_path / "xdg"
    _write(xdg / "swarm" / "swarm_config.json", {"settings": {"from": "xdg"}})
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.delenv("SWARM_CONFIG_PATH", raising=False)
    # cwd has no swarm_config.json under tmp, so XDG must win.
    monkeypatch.chdir(tmp_path)

    cfg = SwarmConfig._load_swarm_config()
    assert cfg.get("settings", {}).get("from") == "xdg"


def test_swarm_config_path_overrides_xdg(monkeypatch, tmp_path):
    xdg = tmp_path / "xdg"
    _write(xdg / "swarm" / "swarm_config.json", {"settings": {"from": "xdg"}})
    explicit = _write(tmp_path / "explicit.json", {"settings": {"from": "env"}})
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("SWARM_CONFIG_PATH", str(explicit))

    cfg = SwarmConfig._load_swarm_config()
    assert cfg.get("settings", {}).get("from") == "env"  # explicit beats XDG


def test_env_vars_are_substituted(monkeypatch, tmp_path):
    explicit = _write(tmp_path / "c.json", {"llm": {"default": {"api_key": "${MY_KEY}"}}})
    monkeypatch.setenv("SWARM_CONFIG_PATH", str(explicit))
    monkeypatch.setenv("MY_KEY", "secret-123")

    cfg = SwarmConfig._load_swarm_config()
    assert cfg["llm"]["default"]["api_key"] == "secret-123"


def test_missing_config_returns_empty_never_raises(monkeypatch, tmp_path):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-xdg"))
    monkeypatch.delenv("SWARM_CONFIG_PATH", raising=False)
    monkeypatch.chdir(tmp_path)  # no swarm_config.json anywhere reachable

    assert SwarmConfig._load_swarm_config() == {}


def test_bad_path_in_env_falls_back(monkeypatch, tmp_path):
    _pin_unix_config_root(monkeypatch)
    monkeypatch.setenv("SWARM_CONFIG_PATH", str(tmp_path / "does-not-exist.json"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-xdg"))
    monkeypatch.chdir(tmp_path)
    # Non-existent SWARM_CONFIG_PATH must not raise; falls through to discovery → empty.
    assert SwarmConfig._load_swarm_config() == {}

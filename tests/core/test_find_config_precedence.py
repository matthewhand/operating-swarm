"""find_config_file precedence — an explicit path must beat the XDG default.

Regression: previously XDG was checked before the user-specified path, so
`swarm-cli --config /some/file` was silently overridden whenever an
`~/.config/swarm/swarm_config.json` existed.
"""

from __future__ import annotations

import json
import sys

from swarm.core.config_loader import find_config_file


def _pin_unix_config_root(monkeypatch) -> None:
    """These tests assert the XDG root. Windows uses %APPDATA% instead."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("SWARM_CONFIG_DIR", raising=False)


def _write(path, data=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data or {"settings": {}}))
    return path


def test_explicit_path_beats_xdg(monkeypatch, tmp_path):
    xdg = _write(tmp_path / "cfg" / "swarm" / "swarm_config.json", {"src": "xdg"})
    explicit = _write(tmp_path / "explicit.json", {"src": "explicit"})
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))

    found = find_config_file(specific_path=str(explicit))
    assert found == explicit.resolve()
    assert found != xdg.resolve()


def test_falls_back_to_xdg_when_no_explicit(monkeypatch, tmp_path):
    _pin_unix_config_root(monkeypatch)
    xdg = _write(tmp_path / "cfg" / "swarm" / "swarm_config.json", {"src": "xdg"})
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))

    assert find_config_file() == xdg.resolve()


def test_nonexistent_explicit_falls_through_to_xdg(monkeypatch, tmp_path):
    _pin_unix_config_root(monkeypatch)
    xdg = _write(tmp_path / "cfg" / "swarm" / "swarm_config.json", {"src": "xdg"})
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))

    # A bad --config path should warn and fall through, not crash, landing on XDG.
    assert find_config_file(specific_path=str(tmp_path / "nope.json")) == xdg.resolve()

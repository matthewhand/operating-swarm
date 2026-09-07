"""REQ-167 — CLI agent Folder resolve / persist / session cwd."""

from __future__ import annotations

import pytest

from swarm.core import agent_settings as store
from swarm.core.agent_folder import (
    AgentFolderError,
    folder_from_blueprint_code,
    resolve_agent_folder,
    resolve_session_cwd,
    lookup_agent_folder,
)


def test_blank_folder_keeps_existing_default():
    assert resolve_agent_folder(None) is None
    assert resolve_agent_folder("") is None
    assert resolve_agent_folder("   ") is None
    assert resolve_session_cwd(agent_id="cli_agent", raw="") is None


def test_existing_directory_resolves(tmp_path):
    folder = tmp_path / "project"
    folder.mkdir()
    assert resolve_agent_folder(str(folder)) == str(folder.resolve())


def test_missing_path_is_visible_error(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(AgentFolderError, match="does not exist"):
        resolve_agent_folder(str(missing))


def test_file_is_not_a_directory(tmp_path):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("x\n", encoding="utf-8")
    with pytest.raises(AgentFolderError, match="not a directory"):
        resolve_agent_folder(str(file_path))


def test_invalid_format_is_visible_error():
    with pytest.raises(AgentFolderError, match="not a valid directory path"):
        resolve_agent_folder("/bad/*/path")


def test_folder_comment_parse():
    code = "# CLI agent: Tool\n# Command: my-cli\n# Folder: /tmp/ws\n"
    assert folder_from_blueprint_code(code) == "/tmp/ws"
    assert folder_from_blueprint_code("") == ""


def test_settings_folder_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    store.reset_agent_settings_cache()
    updated = store.update_settings("cli_agent", {"folder": "  /home/dev/tool  "})
    assert updated["folder"] == "/home/dev/tool"
    store.reset_agent_settings_cache()
    assert store.stored_folder("cli_agent") == "/home/dev/tool"
    store.update_settings("cli_agent", {"folder": ""})
    assert store.stored_folder("cli_agent") is None
    store.reset_agent_settings_cache()


def test_lookup_uses_settings_when_params_blank(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    store.reset_agent_settings_cache()
    folder = tmp_path / "bound"
    folder.mkdir()
    store.update_settings("my_cli", {"folder": str(folder)})
    assert resolve_session_cwd(agent_id="my_cli") == str(folder.resolve())
    store.reset_agent_settings_cache()

def test_lookup_agent_folder_handles_import_error(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "swarm.core.agent_settings", None)
    # Should not raise exception
    assert lookup_agent_folder("non_existent_agent") == ""


"""
Unit tests for src/swarm/core/config_manager.py
==============================================

Tests configuration CRUD, placeholder resolution, and backup/restore behaviors.
"""

import json
import os
import shutil

import pytest

# Import the module under test
from swarm.core.config_manager import (
    CONFIG_BACKUP_SUFFIX,
    backup_configuration,
    load_config,
    resolve_placeholders,
    save_config,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_config():
    """Return a sample configuration dictionary."""
    return {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4",
                "api_key": "${OPENAI_API_KEY}",
                "base_url": "",
                "temperature": 0.7
            },
            "ollama_local": {
                "provider": "ollama",
                "model": "llama3",
                "api_key": "",
                "base_url": "http://localhost:11434"
            }
        },
        "mcpServers": {
            "memory": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "env": {}
            }
        },
        "settings": {
            "default_markdown_output": True
        }
    }


@pytest.fixture
def config_file(tmp_path, sample_config):
    """Create a temporary config file and return its path."""
    config_path = tmp_path / "swarm_config.json"
    with open(config_path, "w") as f:
        json.dump(sample_config, f)
    return str(config_path)


# =============================================================================
# Tests for resolve_placeholders
# =============================================================================

class TestResolvePlaceholders:
    """Test placeholder resolution functionality."""

    def test_resolve_placeholders_env_var_present(self, monkeypatch):
        """Test that ${ENV_VAR} is resolved when env var exists."""
        monkeypatch.setenv("TEST_API_KEY", "secret123")

        config = {"api_key": "${TEST_API_KEY}"}
        result = resolve_placeholders(config)

        assert result["api_key"] == "secret123"

    def test_resolve_placeholders_env_var_missing(self, monkeypatch):
        """Test that ${ENV_VAR} is left unchanged when env var is missing."""
        monkeypatch.delenv("MISSING_VAR", raising=False)

        config = {"api_key": "${MISSING_VAR}"}
        result = resolve_placeholders(config)

        # Should leave the placeholder unchanged
        assert result["api_key"] == "${MISSING_VAR}"

    def test_resolve_placeholders_nested_dict(self, monkeypatch):
        """Test placeholder resolution in nested dictionaries."""
        monkeypatch.setenv("NESTED_KEY", "nested_value")

        config = {
            "level1": {
                "level2": {
                    "value": "${NESTED_KEY}"
                }
            }
        }
        result = resolve_placeholders(config)

        assert result["level1"]["level2"]["value"] == "nested_value"

    def test_resolve_placeholders_list(self, monkeypatch):
        """Test placeholder resolution in lists."""
        monkeypatch.setenv("LIST_VAR", "list_value")

        config = {
            "items": ["${LIST_VAR}", "static_value", "${MISSING_VAR}"]
        }
        result = resolve_placeholders(config)

        assert result["items"][0] == "list_value"
        assert result["items"][1] == "static_value"
        assert result["items"][2] == "${MISSING_VAR}"

    def test_resolve_placeholders_mixed_content(self, monkeypatch):
        """Test placeholder resolution with mixed content types."""
        monkeypatch.setenv("API_KEY", "my_key")

        config = {
            "string_val": "${API_KEY}",
            "int_val": 42,
            "float_val": 3.14,
            "bool_val": True,
            "none_val": None,
            "list_val": ["${API_KEY}", 123],
            "dict_val": {"nested": "${API_KEY}"}
        }
        result = resolve_placeholders(config)

        assert result["string_val"] == "my_key"
        assert result["int_val"] == 42
        assert result["float_val"] == 3.14
        assert result["bool_val"] is True
        assert result["none_val"] is None
        assert result["list_val"] == ["my_key", 123]
        assert result["dict_val"] == {"nested": "my_key"}

    def test_resolve_placeholders_multiple_vars_in_string(self, monkeypatch):
        """Test multiple placeholders in a single string."""
        monkeypatch.setenv("VAR1", "value1")
        monkeypatch.setenv("VAR2", "value2")

        config = {
            "connection_string": "${VAR1}:${VAR2}@localhost"
        }
        result = resolve_placeholders(config)

        assert result["connection_string"] == "value1:value2@localhost"

    def test_resolve_placeholders_empty_config(self):
        """Test placeholder resolution with empty config."""
        result = resolve_placeholders({})
        assert result == {}

    def test_resolve_placeholders_no_placeholders(self):
        """Test config without any placeholders passes through unchanged."""
        config = {
            "llm": {
                "default": {
                    "provider": "ollama",
                    "model": "llama3"
                }
            }
        }
        result = resolve_placeholders(config)
        assert result == config


# =============================================================================
# Tests for backup_configuration
# =============================================================================

class TestBackupConfiguration:
    """Test backup configuration functionality."""

    def test_backup_creates_file(self, config_file):
        """Test that backup file is created."""
        backup_configuration(config_file)

        backup_path = config_file + CONFIG_BACKUP_SUFFIX
        assert os.path.exists(backup_path)

    def test_backup_content_matches(self, config_file, sample_config):
        """Test that backup content matches original."""
        backup_configuration(config_file)

        backup_path = config_file + CONFIG_BACKUP_SUFFIX
        with open(backup_path) as f:
            backup_content = json.load(f)

        assert backup_content == sample_config

    def test_backup_overwrites_existing(self, config_file):
        """Test that existing backup is overwritten."""
        # Create initial backup
        backup_configuration(config_file)
        backup_path = config_file + CONFIG_BACKUP_SUFFIX

        # Modify original config
        modified_config = {"llm": {"new": "profile"}}
        with open(config_file, "w") as f:
            json.dump(modified_config, f)

        # Create new backup
        backup_configuration(config_file)

        # Verify backup has new content
        with open(backup_path) as f:
            backup_content = json.load(f)
        assert backup_content == modified_config

    def test_backup_missing_file_exits(self, tmp_path, capsys):
        """Test that backup of missing file causes system exit."""
        missing_path = str(tmp_path / "nonexistent.json")

        with pytest.raises(SystemExit) as exc_info:
            backup_configuration(missing_path)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Failed to create backup" in captured.out


# =============================================================================
# Tests for load_config
# =============================================================================

class TestLoadConfig:
    """Test configuration loading functionality."""

    def test_load_config_valid_file(self, config_file, sample_config):
        """Test loading a valid configuration file."""
        result = load_config(config_file)

        # Config should be loaded (placeholders resolved)
        assert "llm" in result
        assert result["llm"]["default"]["provider"] == "openai"

    def test_load_config_resolves_placeholders(self, config_file, monkeypatch):
        """Test that load_config resolves environment placeholders."""
        monkeypatch.setenv("OPENAI_API_KEY", "test_key_12345")

        result = load_config(config_file)

        assert result["llm"]["default"]["api_key"] == "test_key_12345"

    def test_load_config_does_not_log_api_keys(self, config_file, monkeypatch, caplog):
        """Resolved secrets must not appear in DEBUG logs (#326)."""
        import logging

        secret = "sk-live-secret-value-12345"
        monkeypatch.setenv("OPENAI_API_KEY", secret)
        with caplog.at_level(logging.DEBUG, logger="swarm.core.config_manager"):
            load_config(config_file)
        blob = caplog.text
        assert secret not in blob
        assert "sk-live-secret-value" not in blob

    def test_load_config_missing_file_exits(self, tmp_path, capsys):
        """Test that missing config file causes system exit."""
        missing_path = str(tmp_path / "missing_config.json")

        with pytest.raises(SystemExit) as exc_info:
            load_config(missing_path)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Configuration file not found" in captured.out

    def test_load_config_invalid_json_exits(self, tmp_path, capsys):
        """Test that invalid JSON causes system exit."""
        invalid_json_path = str(tmp_path / "invalid.json")
        with open(invalid_json_path, "w") as f:
            f.write("{ invalid json content }")

        with pytest.raises(SystemExit) as exc_info:
            load_config(invalid_json_path)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid JSON" in captured.out

    def test_load_config_empty_file_exits(self, tmp_path, capsys):
        """Test that empty file causes system exit (invalid JSON)."""
        empty_path = str(tmp_path / "empty.json")
        with open(empty_path, "w") as f:
            f.write("")

        with pytest.raises(SystemExit) as exc_info:
            load_config(empty_path)

        assert exc_info.value.code == 1


# =============================================================================
# Tests for save_config
# =============================================================================

class TestSaveConfig:
    """Test configuration saving functionality."""

    def test_save_config_creates_file(self, tmp_path, sample_config):
        """Test that save_config creates a file."""
        config_path = str(tmp_path / "new_config.json")

        save_config(config_path, sample_config)

        assert os.path.exists(config_path)

    def test_save_config_content_correct(self, tmp_path, sample_config):
        """Test that saved content matches input."""
        config_path = str(tmp_path / "new_config.json")

        save_config(config_path, sample_config)

        with open(config_path) as f:
            loaded = json.load(f)

        assert loaded == sample_config

    def test_save_config_overwrites_existing(self, tmp_path, sample_config):
        """Test that save_config overwrites existing file."""
        config_path = str(tmp_path / "existing_config.json")

        # Create initial file
        with open(config_path, "w") as f:
            json.dump({"old": "data"}, f)

        # Save new config
        save_config(config_path, sample_config)

        with open(config_path) as f:
            loaded = json.load(f)

        assert loaded == sample_config
        assert "old" not in loaded

    def test_save_config_missing_parent_dir_exits(self, tmp_path, sample_config, capsys):
        """Test that save_config exits when parent directory doesn't exist."""
        config_path = str(tmp_path / "subdir" / "deep" / "config.json")

        with pytest.raises(SystemExit) as exc_info:
            save_config(config_path, sample_config)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Failed to save configuration" in captured.out

    def test_save_config_formatted_json(self, tmp_path, sample_config):
        """Test that saved JSON is properly formatted (indented)."""
        config_path = str(tmp_path / "formatted.json")

        save_config(config_path, sample_config)

        with open(config_path) as f:
            content = f.read()

        # Check for indentation (formatted JSON has newlines and spaces)
        assert "\n" in content
        assert "    " in content  # 4-space indent


# =============================================================================
# Tests for LLM Profile CRUD (add_llm, remove_llm)
# =============================================================================

class TestLLMProfileCRUD:
    """Test LLM profile add/remove operations."""

    def test_remove_llm_existing(self, config_file, monkeypatch):
        """Test removing an existing LLM profile."""
        # Mock prompt_user to confirm removal
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: "yes"
        )

        from swarm.core.config_manager import remove_llm

        remove_llm(config_file, "default")

        # Verify profile was removed
        config = load_config(config_file)
        assert "default" not in config["llm"]
        assert "ollama_local" in config["llm"]  # Other profile still exists

    def test_remove_llm_nonexistent(self, config_file, capsys):
        """Test removing a non-existent LLM profile."""
        from swarm.core.config_manager import remove_llm

        remove_llm(config_file, "nonexistent_profile")

        captured = capsys.readouterr()
        assert "does not exist" in captured.out

    def test_remove_llm_cancelled(self, config_file, monkeypatch, sample_config):
        """Test cancelling LLM removal."""
        # Mock prompt_user to cancel
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: "no"
        )

        from swarm.core.config_manager import remove_llm

        remove_llm(config_file, "default")

        # Verify profile still exists
        with open(config_file) as f:
            config = json.load(f)
        assert "default" in config["llm"]

    def test_remove_llm_creates_backup(self, config_file, monkeypatch):
        """Test that removing LLM creates a backup."""
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: "yes"
        )

        from swarm.core.config_manager import remove_llm

        remove_llm(config_file, "default")

        backup_path = config_file + CONFIG_BACKUP_SUFFIX
        assert os.path.exists(backup_path)

        # Backup should still have the removed profile
        with open(backup_path) as f:
            backup_config = json.load(f)
        assert "default" in backup_config["llm"]

    def test_add_llm_single_profile(self, config_file, monkeypatch):
        """Test adding a single LLM profile."""
        # Mock prompt_user to add one profile then finish
        responses = iter([
            "test_profile",  # LLM name
            "openai",        # provider
            "gpt-4o",        # model
            "https://api.openai.com",  # base_url
            "TEST_API_KEY",  # api_key env var
            "0.5",           # temperature
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_llm

        add_llm(config_file)

        # Verify profile was added
        config = load_config(config_file)
        assert "test_profile" in config["llm"]
        assert config["llm"]["test_profile"]["provider"] == "openai"
        assert config["llm"]["test_profile"]["model"] == "gpt-4o"
        assert config["llm"]["test_profile"]["api_key"] == "${TEST_API_KEY}"
        assert config["llm"]["test_profile"]["temperature"] == 0.5

    def test_add_llm_empty_name_rejected(self, config_file, monkeypatch):
        """Test that empty LLM name is rejected."""
        responses = iter([
            "",              # empty name - should be rejected
            "valid_name",    # valid name
            "ollama",        # provider
            "llama3",        # model
            "http://localhost:11434",  # base_url
            "",              # no api key
            "0.7",           # temperature
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_llm

        add_llm(config_file)

        # Verify only valid profile was added
        config = load_config(config_file)
        assert "valid_name" in config["llm"]

    def test_add_llm_duplicate_name_rejected(self, config_file, monkeypatch):
        """Test that duplicate LLM name is rejected."""
        responses = iter([
            "default",       # duplicate name - should be rejected
            "new_profile",   # valid new name
            "ollama",        # provider
            "llama3",        # model
            "http://localhost:11434",  # base_url
            "",              # no api key
            "0.7",           # temperature
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_llm

        add_llm(config_file)

        # Verify new profile was added, default unchanged
        config = load_config(config_file)
        assert "new_profile" in config["llm"]
        assert "default" in config["llm"]
        assert config["llm"]["default"]["provider"] == "openai"  # unchanged

    def test_add_llm_invalid_temperature_uses_default(self, config_file, monkeypatch):
        """Test that invalid temperature uses default value."""
        responses = iter([
            "test_profile",  # LLM name
            "openai",        # provider
            "gpt-4o",        # model
            "https://api.openai.com",  # base_url
            "TEST_API_KEY",  # api_key env var
            "invalid",       # invalid temperature
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_llm

        add_llm(config_file)

        # Verify default temperature was used
        config = load_config(config_file)
        assert config["llm"]["test_profile"]["temperature"] == 0.7

    def test_add_llm_creates_backup(self, config_file, monkeypatch):
        """Test that adding LLM creates a backup."""
        responses = iter([
            "new_profile",   # LLM name
            "ollama",        # provider
            "llama3",        # model
            "http://localhost:11434",  # base_url
            "",              # no api key
            "0.7",           # temperature
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_llm

        add_llm(config_file)

        backup_path = config_file + CONFIG_BACKUP_SUFFIX
        assert os.path.exists(backup_path)

        # Backup should NOT have the new profile
        with open(backup_path) as f:
            backup_config = json.load(f)
        assert "new_profile" not in backup_config["llm"]


# =============================================================================
# Tests for MCP Server CRUD (add_mcp_server, remove_mcp_server)
# =============================================================================

class TestMCPServerCRUD:
    """Test MCP server add/remove operations."""

    def test_remove_mcp_server_existing(self, config_file, monkeypatch):
        """Test removing an existing MCP server."""
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: "yes"
        )

        from swarm.core.config_manager import remove_mcp_server

        remove_mcp_server(config_file, "memory")

        config = load_config(config_file)
        assert "memory" not in config.get("mcpServers", {})

    def test_remove_mcp_server_nonexistent(self, config_file, capsys):
        """Test removing a non-existent MCP server."""
        from swarm.core.config_manager import remove_mcp_server

        remove_mcp_server(config_file, "nonexistent_server")

        captured = capsys.readouterr()
        assert "does not exist" in captured.out

    def test_remove_mcp_server_cancelled(self, config_file, monkeypatch):
        """Test cancelling MCP server removal."""
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: "no"
        )

        from swarm.core.config_manager import remove_mcp_server

        remove_mcp_server(config_file, "memory")

        # Verify server still exists
        with open(config_file) as f:
            config = json.load(f)
        assert "memory" in config.get("mcpServers", {})

    def test_remove_mcp_server_creates_backup(self, config_file, monkeypatch):
        """Test that removing MCP server creates a backup."""
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: "yes"
        )

        from swarm.core.config_manager import remove_mcp_server

        remove_mcp_server(config_file, "memory")

        backup_path = config_file + CONFIG_BACKUP_SUFFIX
        assert os.path.exists(backup_path)

        # Backup should still have the removed server
        with open(backup_path) as f:
            backup_config = json.load(f)
        assert "memory" in backup_config.get("mcpServers", {})

    def test_add_mcp_server_single(self, config_file, monkeypatch):
        """Test adding a single MCP server."""
        responses = iter([
            "test_server",   # server name
            "npx",           # command
            '["-y", "test-server"]',  # args as JSON
            "no",            # no env vars
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_mcp_server

        add_mcp_server(config_file)

        # Verify server was added
        config = load_config(config_file)
        assert "test_server" in config.get("mcpServers", {})
        assert config["mcpServers"]["test_server"]["command"] == "npx"
        assert config["mcpServers"]["test_server"]["args"] == ["-y", "test-server"]

    def test_add_mcp_server_with_env_vars(self, config_file, monkeypatch):
        """Test adding MCP server with environment variables."""
        responses = iter([
            "test_server",   # server name
            "npx",           # command
            '["-y", "test-server"]',  # args as JSON
            "yes",           # add env vars
            "API_KEY",       # env var name
            "${API_KEY}",    # env var value
            "no",            # no more env vars
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_mcp_server

        add_mcp_server(config_file)

        # Verify server was added with env vars
        config = load_config(config_file)
        assert "test_server" in config.get("mcpServers", {})
        assert config["mcpServers"]["test_server"]["env"] == {"API_KEY": "${API_KEY}"}

    def test_add_mcp_server_invalid_args_uses_empty_list(self, config_file, monkeypatch):
        """Test that invalid JSON args uses empty list."""
        responses = iter([
            "test_server",   # server name
            "npx",           # command
            'invalid json',  # invalid args
            "no",            # no env vars
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_mcp_server

        add_mcp_server(config_file)

        # Verify server was added with empty args
        config = load_config(config_file)
        assert config["mcpServers"]["test_server"]["args"] == []

    def test_add_mcp_server_args_not_list_uses_empty_list(self, config_file, monkeypatch):
        """Test that args that are valid JSON but not a list uses empty list."""
        responses = iter([
            "test_server",   # server name
            "npx",           # command
            '{"not": "a list"}',  # valid JSON but not a list
            "no",            # no env vars
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_mcp_server

        add_mcp_server(config_file)

        # Verify server was added with empty args
        config = load_config(config_file)
        assert config["mcpServers"]["test_server"]["args"] == []

    def test_add_mcp_server_empty_name_rejected(self, config_file, monkeypatch):
        """Test that empty server name is rejected."""
        responses = iter([
            "",              # empty name - rejected
            "valid_server",  # valid name
            "npx",           # command
            '["-y", "test"]',  # args
            "no",            # no env vars
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_mcp_server

        add_mcp_server(config_file)

        # Verify only valid server was added
        config = load_config(config_file)
        assert "valid_server" in config.get("mcpServers", {})

    def test_add_mcp_server_duplicate_name_rejected(self, config_file, monkeypatch):
        """Test that duplicate server name is rejected."""
        responses = iter([
            "memory",        # duplicate name - rejected
            "new_server",    # valid new name
            "npx",           # command
            '["-y", "test"]',  # args
            "no",            # no env vars
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_mcp_server

        add_mcp_server(config_file)

        # Verify new server was added, memory unchanged
        config = load_config(config_file)
        assert "new_server" in config.get("mcpServers", {})
        assert "memory" in config.get("mcpServers", {})

    def test_add_mcp_server_creates_backup(self, config_file, monkeypatch):
        """Test that adding MCP server creates a backup."""
        responses = iter([
            "new_server",    # server name
            "npx",           # command
            '["-y", "test"]',  # args
            "no",            # no env vars
            "done"           # finish
        ])
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: next(responses)
        )

        from swarm.core.config_manager import add_mcp_server

        add_mcp_server(config_file)

        backup_path = config_file + CONFIG_BACKUP_SUFFIX
        assert os.path.exists(backup_path)

        # Backup should NOT have the new server
        with open(backup_path) as f:
            backup_config = json.load(f)
        assert "new_server" not in backup_config.get("mcpServers", {})


# =============================================================================
# Integration Tests
# =============================================================================

class TestConfigManagerIntegration:
    """Integration tests for config manager workflows."""

    def test_save_and_load_roundtrip(self, tmp_path, sample_config):
        """Test that save followed by load preserves data."""
        config_path = str(tmp_path / "roundtrip.json")

        save_config(config_path, sample_config)
        loaded = load_config(config_path)

        # Compare structures (ignoring placeholder resolution differences)
        assert loaded["llm"].keys() == sample_config["llm"].keys()
        assert loaded["mcpServers"].keys() == sample_config["mcpServers"].keys()

    def test_backup_restore_workflow(self, config_file, sample_config, monkeypatch):
        """Test backup and restore workflow."""
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: "yes"
        )

        from swarm.core.config_manager import remove_llm

        # Remove an LLM (creates backup)
        remove_llm(config_file, "default")

        # Verify current config is modified
        current_config = load_config(config_file)
        assert "default" not in current_config["llm"]

        # Restore from backup
        backup_path = config_file + CONFIG_BACKUP_SUFFIX
        shutil.copy(backup_path, config_file)

        # Verify restored config
        restored_config = load_config(config_file)
        assert "default" in restored_config["llm"]

    def test_multiple_operations_preserve_integrity(self, config_file, monkeypatch):
        """Test that multiple CRUD operations maintain config integrity."""
        monkeypatch.setattr(
            "swarm.core.config_manager.prompt_user",
            lambda msg: "yes"
        )

        from swarm.core.config_manager import remove_llm, remove_mcp_server

        # Remove LLM profile
        remove_llm(config_file, "default")

        # Remove MCP server
        remove_mcp_server(config_file, "memory")

        # Load and verify
        config = load_config(config_file)

        assert "default" not in config["llm"]
        assert "ollama_local" in config["llm"]  # Other LLM preserved
        assert "memory" not in config.get("mcpServers", {})
        assert "settings" in config  # Other sections preserved

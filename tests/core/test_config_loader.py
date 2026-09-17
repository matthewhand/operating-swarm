"""
Comprehensive tests for config_loader module
===========================================

Tests configuration loading, environment variable substitution,
and complex merging scenarios.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured

from src.swarm.core.config_loader import (
    _substitute_env_vars,
    load_environment,
    load_full_configuration,
)


class TestEnvironmentVariableSubstitution:
    """Test environment variable substitution functionality."""

    def test_substitute_env_vars_string(self):
        """Test env var substitution in strings."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = _substitute_env_vars("$TEST_VAR")
            assert result == "test_value"

    def test_substitute_env_vars_string_braces(self):
        """Test env var substitution with braces."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = _substitute_env_vars("${TEST_VAR}")
            assert result == "test_value"

    def test_substitute_env_vars_multiple_vars(self):
        """Test multiple env vars in one string."""
        with patch.dict(os.environ, {"VAR1": "value1", "VAR2": "value2"}):
            result = _substitute_env_vars("$VAR1 and $VAR2")
            assert result == "value1 and value2"

    def test_substitute_env_vars_missing_var(self):
        """Test handling of missing env vars."""
        result = _substitute_env_vars("$MISSING_VAR")
        assert result == "$MISSING_VAR"  # Should leave unsubstituted

    def test_substitute_env_vars_list(self):
        """Test env var substitution in lists."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = _substitute_env_vars(["$TEST_VAR", "static", {"key": "$TEST_VAR"}])
            expected = ["test_value", "static", {"key": "test_value"}]
            assert result == expected

    def test_substitute_env_vars_dict(self):
        """Test env var substitution in dicts."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = _substitute_env_vars({
                "key1": "$TEST_VAR",
                "key2": {"nested": "$TEST_VAR"},
                "key3": ["$TEST_VAR"]
            })
            expected = {
                "key1": "test_value",
                "key2": {"nested": "test_value"},
                "key3": ["test_value"]
            }
            assert result == expected

    def test_substitute_env_vars_non_string_types(self):
        """Test that non-string types pass through unchanged."""
        result = _substitute_env_vars(42)
        assert result == 42

        result = _substitute_env_vars(True)
        assert result == True

        result = _substitute_env_vars(None)
        assert result == None


class TestLoadEnvironment:
    """Test environment loading functionality."""

    def test_load_environment_with_dotenv_file(self):
        """Test loading environment from .env file."""
        env_content = "TEST_KEY=test_value\nANOTHER_KEY=another_value\n"

        # Create a temporary directory and a .env file inside it
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dotenv_path = temp_path / ".env"
            with open(dotenv_path, 'w') as f:
                f.write(env_content)

            with patch('src.swarm.core.config_loader.get_project_root_dir', return_value=temp_path):
                xdg = temp_path / "xdg"
                xdg.mkdir()
                with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(xdg)}, clear=True):
                    load_environment()

                    # Should have loaded the variables
                    assert os.environ.get("TEST_KEY") == "test_value"
                    assert os.environ.get("ANOTHER_KEY") == "another_value"

    def test_load_environment_no_dotenv_file(self):
        """Test loading environment when no .env file exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            xdg = Path(temp_dir) / "xdg"
            xdg.mkdir()
            with patch('src.swarm.core.config_loader.get_project_root_dir', return_value=Path('/nonexistent')):
                with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(xdg)}, clear=False):
                    # Should not raise an exception
                    load_environment()

    def test_load_environment_invalid_dotenv_file(self):
        """Test loading environment with invalid .env file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("INVALID LINE WITHOUT EQUALS\n")
            dotenv_path = Path(f.name)

        try:
            with patch('src.swarm.core.config_loader.get_project_root_dir', return_value=dotenv_path.parent):
                with patch.dict(
                    os.environ,
                    {"XDG_CONFIG_HOME": str(dotenv_path.parent / "xdg-empty")},
                    clear=False,
                ):
                    # Should handle invalid lines gracefully
                    load_environment()
        finally:
            os.unlink(dotenv_path)


class TestLoadFullConfiguration:
    """Test full configuration loading functionality."""

    def test_load_full_configuration_basic(self):
        """Test basic configuration loading."""
        config_data = {
            "defaults": {"setting1": "value1"},
            "llm": {"provider": "openai"},
            "mcpServers": {"memory": True}
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            result = load_full_configuration(
                blueprint_class_name="TestBlueprint",
                default_config_path_for_tests=config_path
            )

            assert result["setting1"] == "value1"
            assert result["llm"]["provider"] == "openai"
            assert result["mcpServers"]["memory"] is True
        finally:
            os.unlink(config_path)

    def test_load_full_configuration_blueprint_specific(self):
        """Test blueprint-specific configuration merging."""
        config_data = {
            "defaults": {"global_setting": "global_value"},
            "blueprints": {
                "TestBlueprint": {
                    "blueprint_setting": "blueprint_value",
                    "override_setting": "blueprint_override"
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            result = load_full_configuration(
                blueprint_class_name="TestBlueprint",
                default_config_path_for_tests=config_path
            )

            assert result["global_setting"] == "global_value"
            assert result["blueprint_setting"] == "blueprint_value"
            assert result["override_setting"] == "blueprint_override"
        finally:
            os.unlink(config_path)

    def test_load_full_configuration_profile_merging(self):
        """Test profile-based configuration merging."""
        config_data = {
            "defaults": {"default_profile": "production"},
            "profiles": {
                "production": {"env": "prod", "debug": False},
                "development": {"env": "dev", "debug": True}
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            # Test default profile
            result = load_full_configuration(
                blueprint_class_name="TestBlueprint",
                default_config_path_for_tests=config_path
            )
            assert result["env"] == "prod"
            assert result["debug"] is False

            # Test explicit profile override
            result = load_full_configuration(
                blueprint_class_name="TestBlueprint",
                profile_override="development",
                default_config_path_for_tests=config_path
            )
            assert result["env"] == "dev"
            assert result["debug"] is True
        finally:
            os.unlink(config_path)

    def test_load_full_configuration_cli_overrides(self):
        """Test CLI configuration overrides."""
        config_data = {
            "defaults": {"setting": "base_value"}
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            cli_overrides = {"setting": "cli_override", "new_setting": "new_value"}

            result = load_full_configuration(
                blueprint_class_name="TestBlueprint",
                cli_config_overrides=cli_overrides,
                default_config_path_for_tests=config_path
            )

            assert result["setting"] == "cli_override"  # CLI override wins
            assert result["new_setting"] == "new_value"
        finally:
            os.unlink(config_path)

    def test_load_full_configuration_env_var_substitution(self):
        """Test environment variable substitution in configuration."""
        config_data = {
            "defaults": {
                "api_key": "$TEST_API_KEY",
                "database_url": "${TEST_DB_URL}",
                "nested": {
                    "path": "$TEST_PATH"
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            with patch.dict(os.environ, {
                "TEST_API_KEY": "secret123",
                "TEST_DB_URL": "postgresql://localhost",
                "TEST_PATH": "/usr/local/bin"
            }):
                result = load_full_configuration(
                    blueprint_class_name="TestBlueprint",
                    default_config_path_for_tests=config_path
                )

                assert result["api_key"] == "secret123"
                assert result["database_url"] == "postgresql://localhost"
                assert result["nested"]["path"] == "/usr/local/bin"
        finally:
            os.unlink(config_path)

    def test_load_full_configuration_missing_config_file(self):
        """Test loading configuration when file doesn't exist."""
        result = load_full_configuration(
            blueprint_class_name="TestBlueprint",
            default_config_path_for_tests=Path("/nonexistent/config.json")
        )

        # Should return minimal config with defaults
        assert isinstance(result, dict)
        assert "llm" in result
        assert "mcpServers" in result

    def test_load_full_configuration_invalid_json(self):
        """Test loading configuration with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"invalid": json syntax}')
            config_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Failed to parse JSON"):
                load_full_configuration(
                    blueprint_class_name="TestBlueprint",
                    default_config_path_for_tests=config_path
                )
        finally:
            os.unlink(config_path)

    def test_load_full_configuration_cli_path_override(self):
        """Test configuration loading with CLI path override."""
        # The config loader expects specific top-level keys like 'defaults', 'llm', etc.
        # Place the test data under 'defaults' so it gets loaded into the final config.
        config_data = {
            "defaults": {
                "cli_override": True
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            config_path = Path(f.name)

        try:
            result = load_full_configuration(
                blueprint_class_name="TestBlueprint",
                config_path_override=str(config_path)
            )

            assert result["cli_override"] is True
        finally:
            os.unlink(config_path)

    def test_load_full_configuration_missing_cli_path(self):
        """Test error when CLI path override doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Specified config file not found"):
            load_full_configuration(
                blueprint_class_name="TestBlueprint",
                config_path_override="/nonexistent/config.json"
            )


def test_django_secret_key_prod_requires_env(monkeypatch):
    """Test prod (non-debug) requires DJANGO_SECRET_KEY (drives real shipped function)."""
    from swarm.utils.env_utils import get_django_secret_key
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    with pytest.raises(ImproperlyConfigured) as exc:
        get_django_secret_key()
    assert "DJANGO_SECRET_KEY" in str(exc.value)


def test_django_secret_key_debug_fallback(monkeypatch):
    """Test debug allows fallback."""
    from swarm.utils.env_utils import get_django_secret_key
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    key = get_django_secret_key()
    assert "insecure-fallback" in key


def test_load_full_configuration_complex_merging():
    """Test complex configuration merging with all layers (top level)."""
    import json
    import os
    import tempfile
    from pathlib import Path

    from swarm.core.config_loader import load_full_configuration
    config_data = {
        "defaults": {
            "global_setting": "global",
            "profile_setting": "default_profile",
            "blueprint_setting": "default_blueprint"
        },
        "profiles": {
            "test_profile": {
                "profile_setting": "profile_override",
                "profile_only": "profile_value"
            }
        },
        "blueprints": {
            "TestBlueprint": {
                "blueprint_setting": "blueprint_override",
                "blueprint_only": "blueprint_value"
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        config_path = Path(f.name)

    try:
        cli_overrides = {
            "cli_setting": "cli_value",
            "profile_setting": "cli_profile_override"
        }

        result = load_full_configuration(
            blueprint_class_name="TestBlueprint",
            profile_override="test_profile",
            cli_config_overrides=cli_overrides,
            default_config_path_for_tests=config_path
        )

        # Verify merging priority (CLI > Profile > Blueprint > Defaults)
        assert result["global_setting"] == "global"
        assert result["profile_setting"] == "cli_profile_override"
        assert result["blueprint_setting"] == "blueprint_override"
        assert result["profile_only"] == "profile_value"
        assert result["blueprint_only"] == "blueprint_value"
        assert result["cli_setting"] == "cli_value"
    finally:
        os.unlink(config_path)


class TestDefaultConfigDiscovery:
    """A no-override caller must load the real config, not an empty base one.

    The default used to resolve through ``paths.get_swarm_config_file()``, which
    named ``config.yaml`` — a file nothing writes, loaded with ``json.load``. So
    every caller without an override (``requirements.load_active_config``, and the
    MCP provider's ``mcpServers`` behind it) silently merged against ``{}``.
    """

    def test_no_override_discovers_swarm_config_json(self, tmp_path, monkeypatch):
        config_file = tmp_path / "swarm_config.json"
        config_file.write_text(
            json.dumps(
                {
                    "llm": {
                        "default": {
                            "provider": "openai",
                            "model": "gpt-4o-mini",
                            "api_key": "sk-test",
                        }
                    },
                    "settings": {"default_llm_profile": "default"},
                    "mcpServers": {"filesystem": {"command": "npx"}},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("SWARM_CONFIG_PATH", str(config_file))

        result = load_full_configuration("TestBlueprint")

        assert result["llm"]["default"]["model"] == "gpt-4o-mini"
        assert result["mcpServers"]["filesystem"]["command"] == "npx"

    def test_nothing_found_still_returns_the_shape(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SWARM_CONFIG_PATH", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        monkeypatch.chdir(tmp_path)

        result = load_full_configuration("TestBlueprint")

        assert isinstance(result, dict)
        for key in ("llm", "mcpServers", "remotes"):
            assert key in result

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import TestCase

from swarm.core.blueprint_base import BlueprintBase


class ConcreteBlueprint(BlueprintBase):
    """Concrete implementation of BlueprintBase for testing"""
    async def run(self, messages, **kwargs):
        yield {"messages": [{"role": "assistant", "content": "test response"}]}

    @property
    def metadata(self):
        """Mock metadata property for testing"""
        return getattr(self, '_test_metadata', {'title': 'Test Blueprint', 'description': 'A test blueprint'})


class TestBlueprintBase(TestCase):
    def setUp(self):
        self.blueprint_id = 'test_blueprint'
        self.test_config = {
            'llm': {
                'default': {
                    'provider': 'openai',
                    'model': 'gpt-3.5-turbo',
                    'api_key': 'test-key'
                }
            },
            'settings': {
                'default_llm_profile': 'default',
                'default_markdown_output': True
            },
            'blueprints': {}
        }

    def test_init_basic(self):
        """Test basic initialization of BlueprintBase"""
        blueprint = ConcreteBlueprint(self.blueprint_id)
        assert blueprint.blueprint_id == self.blueprint_id
        assert blueprint.config_path is None
        # Config will be loaded by _load_configuration, so it won't be empty
        assert blueprint._config is not None

    def test_init_with_config(self):
        """Test initialization with provided config"""
        blueprint = ConcreteBlueprint(self.blueprint_id, config=self.test_config)
        assert blueprint.blueprint_id == self.blueprint_id
        assert blueprint._config == self.test_config

    def test_init_with_config_path(self):
        """Test initialization with config path"""
        config_path = '/path/to/config.json'
        blueprint = ConcreteBlueprint(self.blueprint_id, config_path=config_path)
        assert str(blueprint.config_path) == config_path

    @patch('swarm.core.blueprint_base.Path.cwd')
    @patch('swarm.core.blueprint_base.Path.home')
    @patch.dict(os.environ, {}, clear=True)
    def test_config_loading_no_config_files(self, mock_home, mock_cwd):
        """Test config loading when no config files exist"""
        from django.apps import apps

        mock_cwd.return_value = Path('/fake/cwd')
        mock_home.return_value = Path('/fake/home')

        # Force the AppConfig.config (loaded once at startup, XDG-aware) empty so
        # this test is hermetic — it must not depend on whether the dev's machine
        # happens to have a ~/.config/swarm/swarm_config.json.
        # Mock paths to not exist.
        with patch.object(apps.get_app_config('swarm'), 'config', {}), \
             patch.object(Path, 'exists', return_value=False):
            blueprint = ConcreteBlueprint(self.blueprint_id)
            assert blueprint._config == {}

    def test_config_property_access(self):
        """Test accessing config property"""
        blueprint = ConcreteBlueprint(self.blueprint_id, config=self.test_config)
        assert blueprint.config == self.test_config

    def test_config_property_access_before_init(self):
        """Test config property raises error when accessed before initialization"""
        blueprint = ConcreteBlueprint(self.blueprint_id)
        blueprint._config = None
        with pytest.raises(RuntimeError, match="Configuration accessed before initialization"):
            _ = blueprint.config

    def test_llm_profile_resolution_default(self):
        """Test LLM profile resolution with default config"""
        blueprint = ConcreteBlueprint(self.blueprint_id, config=self.test_config)
        profile_name = blueprint._resolve_llm_profile()
        assert profile_name == 'default'

    def test_llm_profile_resolution_explicit(self):
        """Test LLM profile resolution with explicit profile"""
        config = {
            'llm': {
                'default': self.test_config['llm']['default'],
                'custom': {'provider': 'openai', 'model': 'gpt-4', 'api_key': 'k'},
            },
            'settings': self.test_config['settings'],
            'blueprints': {},
            'llm_profile': 'custom',
        }
        blueprint = ConcreteBlueprint(self.blueprint_id, config=config)
        profile_name = blueprint._resolve_llm_profile()
        assert profile_name == 'custom'

    def test_llm_profile_resolution_programmatic_override(self):
        """Test LLM profile resolution with programmatic override"""
        config = {
            'llm': {
                'default': self.test_config['llm']['default'],
                'override': {'provider': 'openai', 'model': 'gpt-4', 'api_key': 'k'},
            },
            'settings': self.test_config['settings'],
            'blueprints': {},
        }
        blueprint = ConcreteBlueprint(self.blueprint_id, config=config)
        blueprint.llm_profile_name = 'override'
        profile_name = blueprint._resolve_llm_profile()
        assert profile_name == 'override'

    def test_llm_profile_property(self):
        """Test llm_profile property returns correct profile data"""
        blueprint = ConcreteBlueprint(self.blueprint_id, config=self.test_config)
        profile = blueprint.llm_profile
        assert profile == self.test_config['llm']['default']

    def test_llm_profile_property_missing_profile(self):
        """Test llm_profile property raises error for missing profile"""
        config = {'llm': {}}
        blueprint = ConcreteBlueprint(self.blueprint_id, config=config)
        with pytest.raises(ValueError, match="LLM profile 'default' not found"):
            _ = blueprint.llm_profile

    def test_llm_profile_property_missing_provider(self):
        """Test llm_profile property raises error for missing provider"""
        config = {'llm': {'default': {'model': 'gpt-3.5-turbo'}}}
        blueprint = ConcreteBlueprint(self.blueprint_id, config=config)
        with pytest.raises(ValueError, match="'provider' missing in LLM profile"):
            _ = blueprint.llm_profile

    def test_llm_profile_name_property(self):
        """Test llm_profile_name property"""
        blueprint = ConcreteBlueprint(self.blueprint_id, config=self.test_config)
        assert blueprint.llm_profile_name == 'default'

    def test_llm_profile_name_setter(self):
        """Test llm_profile_name setter"""
        blueprint = ConcreteBlueprint(self.blueprint_id, config=self.test_config)
        blueprint.llm_profile_name = 'new_profile'
        assert blueprint._llm_profile_name == 'new_profile'
        # Should clear resolved cache
        assert not hasattr(blueprint, '_resolved_llm_profile')

    def test_get_llm_profile_with_profiles_section(self):
        """Test get_llm_profile with profiles section"""
        config = {
            'llm': {
                'profiles': {
                    'test_profile': {'provider': 'openai', 'model': 'gpt-4'}
                }
            }
        }
        blueprint = ConcreteBlueprint(self.blueprint_id, config=config)
        profile = blueprint.get_llm_profile('test_profile')
        assert profile == {'provider': 'openai', 'model': 'gpt-4'}

    def test_get_llm_profile_without_profiles_section(self):
        """Test get_llm_profile without profiles section"""
        blueprint = ConcreteBlueprint(self.blueprint_id, config=self.test_config)
        profile = blueprint.get_llm_profile('default')
        assert profile == self.test_config['llm']['default']

    def test_get_llm_profile_not_found(self):
        """Test get_llm_profile returns empty dict for non-existent profile"""
        blueprint = ConcreteBlueprint(self.blueprint_id, config=self.test_config)
        profile = blueprint.get_llm_profile('nonexistent')
        assert profile == {}

    def test_get_llm_profile_missing_name_warns(self):
        """Named miss must warn (CONFIGURATION.md); still returns {} for optional lookup."""
        import logging

        blueprint = ConcreteBlueprint(self.blueprint_id, config=self.test_config)
        warned: list[str] = []
        original = logging.Logger.warning

        def _capture(self, msg, *args, **kwargs):
            warned.append(msg % args if args else str(msg))
            return original(self, msg, *args, **kwargs)

        with patch.object(logging.Logger, "warning", _capture):
            profile = blueprint.get_llm_profile("typo-profile")
        assert profile == {}
        assert any("typo-profile" in w and "not found" in w.lower() for w in warned)

    def test_should_output_markdown_blueprint_specific(self):
        """Test should_output_markdown with blueprint-specific setting"""
        config = {
            'settings': {'default_markdown_output': False},
            'blueprints': {
                self.blueprint_id: {'output_markdown': True}
            }
        }
        blueprint = ConcreteBlueprint(self.blueprint_id, config=config)
        assert blueprint.should_output_markdown is True

    def test_should_output_markdown_global_setting(self):
        """Test should_output_markdown with global setting"""
        config = {'settings': {'default_markdown_output': True}}
        blueprint = ConcreteBlueprint(self.blueprint_id, config=config)
        assert blueprint.should_output_markdown is True

    def test_should_output_markdown_default_false(self):
        """Test should_output_markdown defaults to False"""
        blueprint = ConcreteBlueprint(self.blueprint_id, config={})
        assert blueprint.should_output_markdown is False

    def test_splash_property(self):
        """Test splash property"""
        blueprint = ConcreteBlueprint(self.blueprint_id)
        # The metadata property returns default test values
        splash = blueprint.splash
        assert 'Test Blueprint' in splash
        assert 'A test blueprint' in splash

    def test_splash_property_defaults(self):
        """Test splash property with default values"""
        blueprint = ConcreteBlueprint(self.blueprint_id)
        # Test with empty metadata
        blueprint._test_metadata = {}
        splash = blueprint.splash
        assert 'Blueprint' in splash

    @patch('swarm.core.blueprint_base.logger')
    def test_config_error_handling(self, mock_logger):
        """Test configuration error handling"""
        # Mock the config loading to raise an exception
        with patch.object(Path, 'exists', return_value=True):
            with patch('builtins.open'):
                with patch('swarm.core.blueprint_base.json.load', side_effect=ValueError("Invalid JSON")):
                    blueprint = ConcreteBlueprint(self.blueprint_id)
                    # Should handle the error gracefully
                    assert blueprint._config is not None  # Should fallback to empty config

    def test_metadata_property(self):
        """Test metadata property"""
        blueprint = ConcreteBlueprint(self.blueprint_id)
        # Test the default metadata
        metadata = blueprint.metadata
        assert 'title' in metadata
        assert 'description' in metadata

    def test_enable_terminal_commands_default(self):
        """Test enable_terminal_commands default value"""
        blueprint = ConcreteBlueprint(self.blueprint_id)
        assert blueprint.enable_terminal_commands is False

    def test_approval_required_default(self):
        """Test approval_required default value"""
        blueprint = ConcreteBlueprint(self.blueprint_id)
        assert blueprint.approval_required is False

    def test_get_navbar_items_default(self):
        """Test get_navbar_items default value on BlueprintBase and instance"""
        blueprint = ConcreteBlueprint(self.blueprint_id)
        assert blueprint.get_navbar_items() == []
        assert BlueprintBase.get_navbar_items() == []

    def test_get_navbar_items_subclass_override(self):
        """Test that subclasses can override get_navbar_items"""
        class CustomNavbarBlueprint(BlueprintBase):
            async def run(self, messages, **kwargs):
                yield {}

            def get_navbar_items(self=None):
                return [{"id": "custom_item", "kind": "custom", "label": "Custom"}]

        bp = CustomNavbarBlueprint("custom")
        assert bp.get_navbar_items() == [{"id": "custom_item", "kind": "custom", "label": "Custom"}]
        assert CustomNavbarBlueprint.get_navbar_items() == [{"id": "custom_item", "kind": "custom", "label": "Custom"}]

    def test_api_kind_base_get_navbar_items(self):
        """Test that ApiKindBase provides token counter navbar item"""
        from swarm.core.kind_bases import ApiKindBase
        assert ApiKindBase.get_navbar_items() == [
            {"id": "token_counter", "kind": "token_counter", "label": "Tokens"}
        ]

    def test_chatbot_blueprint_navbar_items(self):
        """Test that ChatbotBlueprint provides token counter navbar item and metadata"""
        from swarm.blueprints.chatbot.blueprint_chatbot import ChatbotBlueprint
        assert ChatbotBlueprint.get_navbar_items() == [
            {"id": "token_counter", "kind": "token_counter", "label": "Tokens"}
        ]
        assert ChatbotBlueprint.metadata.get("navbar_items") == [
            {"id": "token_counter", "kind": "token_counter", "label": "Tokens"}
        ]


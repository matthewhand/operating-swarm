"""
Basic functional tests for Codey blueprint (SWARM_TEST_MODE / keyless).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from swarm.blueprints.codey.blueprint_codey import CodeyBlueprint, CodeySpinner


@pytest.fixture(autouse=True)
def _test_mode(monkeypatch):
    monkeypatch.setenv("SWARM_TEST_MODE", "1")


class TestCodeyBasicFunctionality:
    """Test basic functionality of Codey blueprint"""

    @pytest.fixture
    def codey_blueprint(self):
        """Fixture for Codey blueprint instance"""
        return CodeyBlueprint(blueprint_id="test_codey")

    def test_blueprint_initialization(self, codey_blueprint):
        """Test that Codey blueprint initializes correctly"""
        assert codey_blueprint is not None
        assert codey_blueprint.blueprint_id == "test_codey"
        assert hasattr(codey_blueprint, 'metadata')
        assert 'name' in codey_blueprint.metadata
        assert codey_blueprint.metadata['name'] == 'codey'

    def test_blueprint_metadata(self, codey_blueprint):
        """Test that Codey blueprint has correct metadata"""
        metadata = codey_blueprint.metadata
        assert 'name' in metadata
        assert 'emoji' in metadata
        assert 'description' in metadata
        assert 'examples' in metadata
        assert isinstance(metadata['examples'], list)
        assert len(metadata['examples']) > 0

    @pytest.mark.asyncio
    async def test_run_with_empty_messages(self, codey_blueprint):
        """Test that Codey handles empty messages gracefully in test mode"""
        result = []
        async for chunk in codey_blueprint.run([]):
            result.append(chunk)

        assert len(result) > 0
        content = str(result[-1]).lower()
        assert "test-mode" in content or "search" in content or "message" in content

    @pytest.mark.asyncio
    async def test_run_with_valid_message(self, codey_blueprint):
        """Test that Codey processes valid messages in test mode"""
        test_message = "Search for recursion examples"
        messages = [{"role": "user", "content": test_message}]

        result = []
        async for chunk in codey_blueprint.run(messages):
            result.append(chunk)

        assert len(result) > 0
        response_content = str(result[-1]).lower()
        assert (
            "test-mode" in response_content
            or "codey" in response_content
            or "search" in response_content
            or test_message.lower() in response_content
        )

    @pytest.mark.asyncio
    async def test_run_with_multiple_messages(self, codey_blueprint):
        """Test that Codey handles conversation history"""
        messages = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Response to first message"},
            {"role": "user", "content": "Second message"},
        ]

        result = []
        async for chunk in codey_blueprint.run(messages):
            result.append(chunk)

        assert len(result) > 0

    def test_spinner_functionality(self):
        """Test that CodeySpinner advances and reports state"""
        spinner = CodeySpinner()
        spinner.start()
        initial_state = spinner.current_spinner_state()
        assert initial_state is not None
        assert isinstance(initial_state, str)

        spinner._spin()
        new_state = spinner.current_spinner_state()
        assert new_state is not None
        assert new_state != initial_state or len(CodeySpinner.SPINNER_STATES) == 1

    @pytest.mark.asyncio
    async def test_run_in_test_mode(self, codey_blueprint):
        """Test that Codey works in test mode"""
        with patch.dict('os.environ', {'SWARM_TEST_MODE': '1'}):
            messages = [{"role": "user", "content": "test command"}]

            result = []
            async for chunk in codey_blueprint.run(messages):
                result.append(chunk)

            assert len(result) > 0
            if isinstance(result[0], dict):
                assert 'messages' in result[0] or 'progress' in result[0] or 'spinner_state' in result[0]

    def test_render_prompt_method(self, codey_blueprint):
        """Test that prompt rendering works"""
        context = {
            "user_request": "test request",
            "history": [],
            "available_tools": ["code"]
        }

        rendered = codey_blueprint.render_prompt("codey_prompt.j2", context)
        assert rendered is not None
        assert isinstance(rendered, str)
        assert len(rendered) > 0

    def test_blueprint_config_access(self, codey_blueprint):
        """Test that config can be accessed"""
        assert hasattr(codey_blueprint, 'config')
        config = codey_blueprint.config
        assert config is not None
        assert isinstance(config, dict)

    @pytest.mark.asyncio
    async def test_run_with_special_characters(self, codey_blueprint):
        """Test that Codey handles special characters in input"""
        special_message = "Test with special chars: ¡™£¢∞§¶•ªº–≠\n\t\r"
        messages = [{"role": "user", "content": special_message}]

        result = []
        async for chunk in codey_blueprint.run(messages):
            result.append(chunk)

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_run_with_very_long_message(self, codey_blueprint):
        """Test that Codey handles long messages"""
        long_message = "A" * 1000
        messages = [{"role": "user", "content": long_message}]

        result = []
        async for chunk in codey_blueprint.run(messages):
            result.append(chunk)

        assert len(result) > 0


class TestCodeyConfiguration:
    """Test configuration handling in Codey blueprint"""

    @pytest.fixture
    def codey_blueprint(self):
        """Fixture for Codey blueprint instance"""
        return CodeyBlueprint(blueprint_id="test_codey_config")

    def test_default_configuration(self, codey_blueprint):
        """Test that default configuration is loaded"""
        config = codey_blueprint.config
        assert config is not None
        assert isinstance(config, dict)

    def test_llm_profile_access(self, tmp_path, monkeypatch):
        """LLM profile comes from a fixture SoT — not a committed live file."""
        import json

        cfg = {
            "llm": {
                "default": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "api_key": "${OPENAI_API_KEY}",
                }
            },
            "settings": {"default_llm_profile": "default"},
        }
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        monkeypatch.setenv("SWARM_CONFIG_PATH", str(path))
        # AppConfig.config (discovery step 1) is cached at ready() from the
        # developer's real XDG config and would shadow the SWARM_CONFIG_PATH
        # fixture above — blank it for the construction (same hermetic idiom
        # as tests/core/test_blueprint_base.py).
        from django.apps import apps

        with patch.object(apps.get_app_config("swarm"), "config", {}):
            codey_blueprint = CodeyBlueprint(blueprint_id="test_codey_config")
        assert hasattr(codey_blueprint, "llm_profile")
        profile = codey_blueprint.llm_profile
        assert profile is not None
        assert profile.get("model") == "gpt-4o-mini"

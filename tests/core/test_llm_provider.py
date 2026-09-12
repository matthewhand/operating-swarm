from swarm.core.config_loader import named_profile_model, get_resolved_llm_profile
from swarm.core.llm_provider import (
    is_openai_chat_provider,
    normalize_chat_provider,
    openai_sdk_provider,
)


def test_litellm_is_openai_chat_compatible():
    assert is_openai_chat_provider("litellm") is True
    assert is_openai_chat_provider("openai") is True
    assert is_openai_chat_provider(None) is True
    assert is_openai_chat_provider("anthropic") is False


def test_litellm_aliases_and_prefixes():
    assert normalize_chat_provider("  LiteLLM  ") == "litellm"
    assert normalize_chat_provider("litellm/openai") == "litellm"
    assert normalize_chat_provider("lite-llm") == "litellm"
    assert is_openai_chat_provider("litellm/openai") is True
    assert is_openai_chat_provider("lite-llm") is True
    assert is_openai_chat_provider("LiteLLM") is True
    assert openai_sdk_provider("litellm") == "openai"
    assert openai_sdk_provider("litellm/openai") == "openai"


def test_named_profile_model_ignores_env_steal(monkeypatch):
    monkeypatch.setenv("LITELLM_MODEL", "auxiliary")
    monkeypatch.setenv("DEFAULT_LLM", "auxiliary")
    cfg = {
        "llm": {
            "orchestration": {"provider": "litellm", "model": "orchestration"},
            "default": {"provider": "litellm", "model": "auxiliary"},
        }
    }
    resolved = get_resolved_llm_profile(cfg, "orchestration")
    assert resolved["provider"] == "litellm"
    assert resolved["model"] == "auxiliary"  # env steal on the resolved copy
    assert named_profile_model(cfg, "orchestration", resolved) == "orchestration"

import json

import pytest

from swarm.core.config_loader import get_resolved_llm_profile, named_profile_model
from swarm.core.llm_provider import (
    CATEGORIZER_PROVIDERS,
    MODEL_TYPE_CATEGORIZER,
    MODEL_TYPE_CHAT,
    MODEL_TYPES,
    OPENAI_CHAT_PROVIDERS,
    PROVIDER_DEFAULTS,
    apply_provider_defaults,
    is_categorizer_model_type,
    is_categorizer_provider,
    is_openai_chat_provider,
    model_type_for_provider,
    normalize_chat_provider,
    normalize_model_type,
    openai_sdk_provider,
    provider_owns_endpoint,
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


def test_mistral_is_openai_chat_compatible():
    # Mistral speaks OpenAI Chat Completions (https://api.mistral.ai/v1); it is
    # a first-class allow-list entry, not a parallel adapter.
    assert is_openai_chat_provider("mistral") is True
    assert is_openai_chat_provider("Mistral") is True
    assert normalize_chat_provider("  Mistral  ") == "mistral"
    assert openai_sdk_provider("mistral") == "openai"


def test_mistral_aliases_and_prefixes():
    for alias in ("mistralai", "mistral-ai", "mistral_ai", "MistralAI", "MISTRAL-AI"):
        assert normalize_chat_provider(alias) == "mistral"
        assert is_openai_chat_provider(alias) is True
    # A profile may carry a provider/model prefix; the provider part decides.
    assert normalize_chat_provider("mistral/mistral-large-latest") == "mistral"
    assert is_openai_chat_provider("mistral/mistral-large-latest") is True


def test_unknown_vendors_stay_rejected():
    # The allow-list must not widen: non-OpenAI-compatible brands still fail.
    assert is_openai_chat_provider("anthropic") is False
    assert is_openai_chat_provider("cohere") is False
    assert is_openai_chat_provider("mistral-unknown") is False


def test_mistral_provider_defaults_prefill_base_url_and_key_env(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    filled = apply_provider_defaults({"provider": "mistralai", "model": "mistral-large-latest"})
    assert filled["base_url"] == "https://api.mistral.ai/v1"
    assert filled["api_key"] == "${MISTRAL_API_KEY}"
    monkeypatch.setenv("MISTRAL_API_KEY", "from-env")
    filled_env = apply_provider_defaults({"provider": "mistral", "model": "mistral-small-latest"})
    assert filled_env["api_key"] == "from-env"
    kept = apply_provider_defaults(
        {
            "provider": "mistral",
            "base_url": "https://custom.example/v1",
            "api_key": "already-set",
        }
    )
    assert kept["base_url"] == "https://custom.example/v1"
    assert kept["api_key"] == "already-set"
    monkeypatch.setenv("MISTRAL_API_KEY", "from-env")
    replaced = apply_provider_defaults(
        {"provider": "mistral", "api_key": "${MISTRAL_API_KEY}"}
    )
    assert replaced["api_key"] == "from-env"


def test_mistral_resolver_ignores_litellm_gateway_env(monkeypatch):
    """A set LITELLM_* / OPENAI_* must not redirect a first-class Mistral profile."""
    monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-gateway")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("LITELLM_MODEL", "auxiliary")
    monkeypatch.setenv("DEFAULT_LLM", "auxiliary")
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-mistral")
    config = {
        "llm": {
            "mistral-chat": {
                "provider": "mistralai",
                "model": "mistral-large-latest",
                "api_key": "${MISTRAL_API_KEY}",
            }
        }
    }
    resolved = get_resolved_llm_profile(config, "mistral-chat")
    assert provider_owns_endpoint("mistralai") is True
    assert resolved["base_url"] == "https://api.mistral.ai/v1"
    assert resolved["api_key"] == "sk-mistral"
    assert resolved["model"] == "mistral-large-latest"


def _mistral_profile() -> dict:
    return {
        "provider": "mistral",
        "model": "mistral-large-latest",
        "base_url": "https://api.mistral.ai/v1",
        "api_key": "sk-test",
    }


def test_chatbot_accepts_mistral_profile(monkeypatch):
    """A ``mistral`` API profile instantiates via the OpenAI SDK path (#1325)."""
    from swarm.blueprints.chatbot import blueprint_chatbot as bc

    bp = bc.ChatbotBlueprint(blueprint_id="chatbot")
    # Class-level caches are shared across instances; clear for this profile.
    bp._model_instance_cache = {}
    bp._openai_client_cache = {}
    monkeypatch.setattr(bp, "get_llm_profile", lambda _name: dict(_mistral_profile()))
    monkeypatch.setattr(
        "swarm.core.config_loader.named_profile_model",
        lambda *_a, **_k: "mistral-large-latest",
    )
    captured: dict = {}

    class _Client:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    class _Model:
        def __init__(self, model, openai_client):
            captured["model"] = model
            captured["client"] = openai_client

    # Patch the owning module object the blueprint's method resolves globals
    # from, so a re-imported module can never leave the real SDK in place.
    monkeypatch.setattr(bc, "AsyncOpenAI", _Client)
    monkeypatch.setattr(bc, "OpenAIChatCompletionsModel", _Model)

    inst = bp._get_model_instance("mistral-profile")
    assert captured["model"] == "mistral-large-latest"
    assert captured["kwargs"]["base_url"] == "https://api.mistral.ai/v1"
    assert captured["kwargs"]["api_key"] == "sk-test"
    assert isinstance(inst, _Model)


def test_chatbot_rejects_unsupported_provider(monkeypatch):
    """An out-of-allow-list vendor still raises the honest error (no regression)."""
    from swarm.blueprints.chatbot import blueprint_chatbot as bc

    bp = bc.ChatbotBlueprint(blueprint_id="chatbot")
    bp._model_instance_cache = {}
    bp._openai_client_cache = {}
    monkeypatch.setattr(
        bp,
        "get_llm_profile",
        lambda _name: {"provider": "cohere", "model": "command-r", "api_key": "k"},
    )
    monkeypatch.setattr(
        "swarm.core.config_loader.named_profile_model", lambda *_a, **_k: "command-r"
    )
    with pytest.raises(ValueError, match="Unsupported provider"):
        bp._get_model_instance("cohere-profile")


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


# --- #1745 — System1 is a model type, not a hidden OpenAI-compat base URL ---


def test_model_types_and_normalizer():
    assert MODEL_TYPES == (MODEL_TYPE_CHAT, MODEL_TYPE_CATEGORIZER)
    # Missing / unknown values collapse to chat so an unrecognised key can
    # never hide a model from every chat surface.
    assert normalize_model_type(None) == MODEL_TYPE_CHAT
    assert normalize_model_type("") == MODEL_TYPE_CHAT
    assert normalize_model_type("chat") == MODEL_TYPE_CHAT
    assert normalize_model_type("  CHAT ") == MODEL_TYPE_CHAT
    assert normalize_model_type("llm") == MODEL_TYPE_CHAT
    assert normalize_model_type("nonsense") == MODEL_TYPE_CHAT
    assert normalize_model_type(MODEL_TYPE_CATEGORIZER) == MODEL_TYPE_CATEGORIZER
    # The System1 brand spellings are first-class aliases, not custom URLs.
    for alias in ("system1", "System1", "system-1", "system_1", "  SYSTEM1  "):
        assert normalize_model_type(alias) == MODEL_TYPE_CATEGORIZER
    for alias in ("classifier", "classify", "gate", "gating", "filter"):
        assert is_categorizer_model_type(alias) is True
    assert is_categorizer_model_type("chat") is False
    assert is_categorizer_model_type(None) is False


def test_system1_is_registered_but_never_a_chat_provider():
    """The whole point of #1745: a typed System1 vendor, not a chat provider."""
    assert "system1" in CATEGORIZER_PROVIDERS
    assert "system1" in PROVIDER_DEFAULTS
    # Chat resolution must never select a categorizer.
    assert "system1" not in OPENAI_CHAT_PROVIDERS
    assert is_openai_chat_provider("system1") is False
    assert is_openai_chat_provider("System1") is False
    assert is_openai_chat_provider("system-1") is False
    assert is_openai_chat_provider("system1/system1-categorizer") is False
    assert openai_sdk_provider("system1") == "system1"
    assert is_categorizer_provider("system1") is True
    assert is_categorizer_provider("openai") is False
    assert provider_owns_endpoint("system1") is True


def test_system1_defaults_use_env_placeholders_only(monkeypatch):
    monkeypatch.delenv("SYSTEM1_API_KEY", raising=False)
    monkeypatch.delenv("SYSTEM1_BASE_URL", raising=False)
    defaults = PROVIDER_DEFAULTS["system1"]
    # Env *names* only — the module can never write a credential.
    assert defaults["api_key_env"] == "SYSTEM1_API_KEY"
    assert defaults["base_url"] == "${SYSTEM1_BASE_URL}"
    assert defaults["base_url_env"] == "SYSTEM1_BASE_URL"

    filled = apply_provider_defaults({"provider": "system1", "model": "system1-categorizer"})
    assert filled["base_url"] == "${SYSTEM1_BASE_URL}"
    assert filled["api_key"] == "${SYSTEM1_API_KEY}"

    monkeypatch.setenv("SYSTEM1_API_KEY", "from-env")
    monkeypatch.setenv("SYSTEM1_BASE_URL", "http://127.0.0.1:8900")
    resolved = apply_provider_defaults({"provider": "system-1"})
    assert resolved["api_key"] == "from-env"
    # The provider's own endpoint placeholder resolves from its env var too.
    assert resolved["base_url"] == "http://127.0.0.1:8900"

    kept = apply_provider_defaults(
        {
            "provider": "system1",
            "base_url": "http://127.0.0.1:8900/v1",
            "api_key": "already-set",
        }
    )
    assert kept["base_url"] == "http://127.0.0.1:8900/v1"
    assert kept["api_key"] == "already-set"


def test_system1_resolver_ignores_litellm_gateway_env(monkeypatch):
    """A set LITELLM_* / OPENAI_* must not redirect a System1 profile."""
    monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-gateway")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("DEFAULT_LLM", "auxiliary")
    monkeypatch.setenv("SYSTEM1_API_KEY", "system1-from-env")
    monkeypatch.setenv("SYSTEM1_BASE_URL", "http://127.0.0.1:8900")
    config = {
        "llm": {
            "system1-filter": {
                "provider": "system1",
                "model": "system1-categorizer",
                "api_key": "${SYSTEM1_API_KEY}",
            }
        }
    }
    resolved = get_resolved_llm_profile(config, "system1-filter")
    assert provider_owns_endpoint("system1") is True
    assert resolved["base_url"] == "http://127.0.0.1:8900"
    assert resolved["api_key"] == "system1-from-env"


def test_system1_base_url_placeholder_is_dropped_when_env_is_unset(monkeypatch):
    """An unresolved ``${SYSTEM1_BASE_URL}`` must not reach a client."""
    monkeypatch.delenv("SYSTEM1_BASE_URL", raising=False)
    monkeypatch.delenv("SYSTEM1_API_KEY", raising=False)
    config = {
        "llm": {
            "system1-filter": {
                "provider": "system1",
                "model": "system1-categorizer",
            }
        }
    }
    resolved = get_resolved_llm_profile(config, "system1-filter")
    assert "${SYSTEM1_BASE_URL}" not in json.dumps(resolved)
    assert "${SYSTEM1_API_KEY}" not in json.dumps(resolved)


def test_model_type_for_provider_prefers_explicit_type():
    # An explicit type always wins over the vendor default.
    assert model_type_for_provider("openai") == MODEL_TYPE_CHAT
    assert model_type_for_provider("openai", "categorizer") == MODEL_TYPE_CATEGORIZER
    assert model_type_for_provider("openai", "System1") == MODEL_TYPE_CATEGORIZER
    assert model_type_for_provider("system1") == MODEL_TYPE_CATEGORIZER
    # …and a chat type on a System1 vendor is honoured too, so a profile can be
    # corrected without a hand edit of swarm_config.json.
    assert model_type_for_provider("system1", "chat") == MODEL_TYPE_CHAT
    assert model_type_for_provider("system1", "") == MODEL_TYPE_CATEGORIZER
    assert model_type_for_provider(None, None) == MODEL_TYPE_CHAT

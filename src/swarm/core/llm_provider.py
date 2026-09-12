"""OpenAI-compatible chat providers (LiteLLM gateway, Groq OpenAI mode, …)."""

from __future__ import annotations

OPENAI_CHAT_PROVIDERS = frozenset(
    {
        "openai",
        "litellm",
        "azure",
        "azure_openai",
        "groq",
        "together",
        "openrouter",
        "xai",
        "ollama",
        "deepseek",
        "fireworks",
    }
)

# Tip swarm_config keeps provider: "litellm" on orchestration/default.
# Adapters and curl clients also send lite-llm, litellm/openai, etc.
_PROVIDER_ALIASES = {
    "lite_llm": "litellm",
    "lite-llm": "litellm",
    "openai_compatible": "litellm",
    "openai-compatible": "litellm",
    "openai_compat": "litellm",
}


def normalize_chat_provider(provider: str | None) -> str:
    """Strip / lower / alias a profile provider string (``litellm`` stays ``litellm``)."""
    key = (provider or "openai").strip().lower()
    for sep in ("/", ":", "|"):
        if sep in key:
            key = key.split(sep, 1)[0].strip()
    return _PROVIDER_ALIASES.get(key, key)


def is_openai_chat_provider(provider: str | None) -> bool:
    """True when Chat Completions can be spoken via the OpenAI SDK + base_url."""
    return normalize_chat_provider(provider) in OPENAI_CHAT_PROVIDERS


def openai_sdk_provider(provider: str | None) -> str:
    """Client cache key: OpenAI-compatible gateways all use the OpenAI SDK."""
    return "openai" if is_openai_chat_provider(provider) else normalize_chat_provider(provider)

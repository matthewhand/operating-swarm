"""OpenAI-compatible chat providers (LiteLLM gateway, Groq, Mistral, …).

#1745 adds the *model type* axis alongside the vendor axis. ``provider`` says
who serves a model; ``model_type`` says what the model emits. A System1
categorizer answers a gate question (allow / deny) instead of chat tokens, so
it is a first-class type here — never a "hidden OpenAI-compat base URL hack" —
and it is deliberately **absent** from :data:`OPENAI_CHAT_PROVIDERS` so chat
resolution can never select one.
"""

from __future__ import annotations

import os

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
        # Mistral exposes an OpenAI-compatible Chat Completions API at
        # https://api.mistral.ai/v1 — reuse the OpenAI SDK path, no new adapter.
        "mistral",
    }
)

#: Model types (#1745). ``chat`` emits tokens; ``categorizer`` answers a gate.
MODEL_TYPE_CHAT = "chat"
MODEL_TYPE_CATEGORIZER = "categorizer"
MODEL_TYPES: tuple[str, ...] = (MODEL_TYPE_CHAT, MODEL_TYPE_CATEGORIZER)

#: Vendors that only ever serve categorizer models. Registering one of these
#: as a profile's provider implies ``model_type: categorizer`` even when the
#: stored profile omits the key.
CATEGORIZER_PROVIDERS = frozenset({"system1"})

_MODEL_TYPE_ALIASES = {
    "system1": MODEL_TYPE_CATEGORIZER,
    "system-1": MODEL_TYPE_CATEGORIZER,
    "system_1": MODEL_TYPE_CATEGORIZER,
    "categoriser": MODEL_TYPE_CATEGORIZER,
    "classifier": MODEL_TYPE_CATEGORIZER,
    "classify": MODEL_TYPE_CATEGORIZER,
    "gate": MODEL_TYPE_CATEGORIZER,
    "gating": MODEL_TYPE_CATEGORIZER,
    "filter": MODEL_TYPE_CATEGORIZER,
    "text": MODEL_TYPE_CHAT,
    "llm": MODEL_TYPE_CHAT,
}

# Tip swarm_config keeps provider: "litellm" on orchestration/default.
# Adapters and curl clients also send lite-llm, litellm/openai, etc.
_PROVIDER_ALIASES = {
    "lite_llm": "litellm",
    "lite-llm": "litellm",
    "openai_compatible": "litellm",
    "openai-compatible": "litellm",
    "openai_compat": "litellm",
    # Mistral brand spellings → the canonical OpenAI-compatible id.
    "mistralai": "mistral",
    "mistral-ai": "mistral",
    "mistral_ai": "mistral",
    # System1 brand spellings → the canonical OpenRig categorizer id.
    "system-1": "system1",
    "system_1": "system1",
    "system1-service": "system1",
}

# Shared OpenAI-compat engine defaults. Env *names* only — never secrets.
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
    },
    # #1745 — the System1 Service owns reachability; Open Swarm only records the
    # type and the env *names*. The endpoint/key stay `${VAR}` placeholders so
    # no credential can land in swarm_config.json from this module.
    "system1": {
        "base_url": "${SYSTEM1_BASE_URL}",
        "base_url_env": "SYSTEM1_BASE_URL",
        "api_key_env": "SYSTEM1_API_KEY",
    },
}


def normalize_model_type(value: object) -> str:
    """Normalize a stored/typed model type to one of :data:`MODEL_TYPES`.

    Unknown or missing values collapse to ``chat`` so an unrecognised key can
    never silently exclude a model from every chat surface.
    """
    key = str(value or "").strip().lower()
    if not key:
        return MODEL_TYPE_CHAT
    key = _MODEL_TYPE_ALIASES.get(key, key)
    return key if key in MODEL_TYPES else MODEL_TYPE_CHAT


def is_categorizer_model_type(value: object) -> bool:
    """True for System1-style categorizer / gate models."""
    return normalize_model_type(value) == MODEL_TYPE_CATEGORIZER


def is_categorizer_provider(provider: str | None) -> bool:
    """True when this vendor only serves categorizer models."""
    return normalize_chat_provider(provider) in CATEGORIZER_PROVIDERS


def model_type_for_provider(
    provider: str | None,
    model_type: object | None = None,
) -> str:
    """Resolve a profile's model type: an explicit type wins over the vendor."""
    if model_type is not None and str(model_type).strip():
        return normalize_model_type(model_type)
    if is_categorizer_provider(provider):
        return MODEL_TYPE_CATEGORIZER
    return MODEL_TYPE_CHAT


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


def provider_owns_endpoint(provider: str | None) -> bool:
    """True when this provider has its own URL and key, not the LiteLLM gateway.

    Gateway env (``LITELLM_BASE_URL`` / ``OPENAI_API_KEY`` / ``LITELLM_MODEL``)
    must not redirect these profiles. An explicit ``base_url`` on the profile
    still wins inside :func:`apply_provider_defaults`.
    """
    return normalize_chat_provider(provider) in PROVIDER_DEFAULTS


def _credential_unset(value: object, env_name: str) -> bool:
    """True when ``api_key`` is missing or still the provider's own ``${ENV}``."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return True
    return bool(env_name) and text == f"${{{env_name}}}"


def apply_provider_defaults(profile: dict | None) -> dict:
    """Fill missing ``base_url`` / ``api_key`` from :data:`PROVIDER_DEFAULTS`.

    Does not overwrite an explicit URL or a key that is already a concrete
    secret. A still-unresolved ``${ENV}`` for this provider's own env var is
    replaced when that variable is set; otherwise the placeholder is left so
    ``drop_unresolved_env_values`` can remove it before a client sees it.
    """
    out = dict(profile or {})
    defaults = PROVIDER_DEFAULTS.get(normalize_chat_provider(out.get("provider")))
    if not defaults:
        return out
    base_env = defaults.get("base_url_env") or ""
    base = out.get("base_url")
    if not (isinstance(base, str) and base.strip()):
        base = defaults.get("base_url") or ""
    # The provider's own endpoint placeholder resolves from its env var, exactly
    # like the credential. An operator-typed URL is never touched.
    if base_env and base.strip() == f"${{{base_env}}}":
        resolved = (os.getenv(base_env) or "").strip()
        if resolved:
            base = resolved
    if base:
        out["base_url"] = base
    env_name = defaults.get("api_key_env") or ""
    if env_name and _credential_unset(out.get("api_key"), env_name):
        out["api_key"] = os.getenv(env_name) or f"${{{env_name}}}"
    return out

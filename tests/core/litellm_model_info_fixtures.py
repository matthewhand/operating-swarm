"""Recorded LiteLLM ``/v1/model/info`` payloads from this project's own gateway.

Trimmed to the four fields the route resolver actually reads
(``model_name``, ``custom_llm_provider``, ``model``, ``weight``, ``api_base``)
and to the four aliases that matter, but otherwise byte-faithful to the live
2026-09-28 response (449 rows, ~2.4 MB). Trimming is safe precisely because the
resolver only ever reads those fields — a test that pinned the other ~200
``model_info`` cost keys would be asserting on a vendor's pricing table, not on
this module's behaviour.

The point of recording real payloads rather than hand-written ones: a
hand-written ``orchestration`` fixture would have two vendors and would happily
have "passed" a label function that names a vendor for a multi-vendor pool. The
real one has four, and a nested gateway, and a duplicate-alias trap
(``qwen3.8-27b`` is a byte-for-byte copy of ``orchestration``).
"""

from __future__ import annotations

# --- the four aliases under test -----------------------------------------

ORCHESTRATION_ROWS: list[dict] = [
    # weight 0 (parked): a local llama.cpp on :8088
    {
        "model_name": "orchestration",
        "litellm_params": {
            "api_base": "http://203.0.113.30:8088/v1",
            "custom_llm_provider": "custom_openai",
            "model": "custom_openai//home/matthewh/dev/bonsai2/models/Ternary-Bonsai-2-27B-PQ2_0.gguf",
            "weight": 0,
        },
    },
    {
        "model_name": "orchestration",
        "litellm_params": {
            "api_base": "https://tokenharbor.ai/v1",
            "custom_llm_provider": "custom_openai",
            "model": "custom_openai/deepseek-v4.1-flash:free",
            "weight": 0,
        },
    },
    # weight 100: a NESTED gateway, same alias name, different host
    {
        "model_name": "orchestration",
        "litellm_params": {
            "api_base": "https://open-litellm.fly.dev/v1",
            "custom_llm_provider": "custom_openai",
            "model": "custom_openai/orchestration",
            "weight": 100,
        },
    },
    {
        "model_name": "orchestration",
        "litellm_params": {
            "api_base": "https://api.pgsrove.com/v1",
            "custom_llm_provider": "custom_openai",
            "model": "custom_openai/glm-5.3-flash",
            "weight": 0,
        },
    },
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "groq",
        "model": "groq/openai/gpt-oss-120b", "weight": 1}},
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/deepseek-ai/deepseek-v4.1-flash", "weight": 120}},
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/z-ai/glm-5.3-flash", "weight": 120}},
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/z-ai/glm-5.3", "weight": 100}},
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/poolside/laguna-xs-2.1", "weight": 20}},
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/meta/muse-glimmer-30b", "weight": 1}},
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b", "weight": 20}},
    # the same model twice at two weights: LiteLLM rows are not unique
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "openai",
        "model": "openai/gpt-5.6-luna", "weight": 1}},
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "openai",
        "model": "openai/gpt-5.6-luna", "weight": 20}},
    {"model_name": "orchestration", "litellm_params": {
        "api_base": None, "custom_llm_provider": "openai",
        "model": "openai/gpt-5.6-terra", "weight": 0}},
]

AUXILIARY_ROWS: list[dict] = [
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": "http://127.0.0.1:8087/v1", "custom_llm_provider": "custom_openai",
        "model": "custom_openai//home/matthewh/dev/minicpm5/models/MiniCPM5-2B-Q4_K_M.gguf",
        "weight": 100}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/meta/muse-glimmer-30b", "weight": 20}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/google/diffusiongemma-26b-a4b-it", "weight": 40}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/openai/gpt-oss-20b", "weight": 50}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/meta/llama-3.2-11b-vision-instruct", "weight": 50}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "nvidia_nim",
        "model": "nvidia_nim/nvidia/nemotron-3.5-lightning-30b-a3b", "weight": 20}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "groq",
        "model": "groq/openai/gpt-oss-120b", "weight": 50}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "gemini",
        "model": "gemini/gemini-3-flash-preview", "weight": 1}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "gemini",
        "model": "gemini/gemini-3.1-flash-lite", "weight": 1}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "gemini",
        "model": "gemini/gemini-3.5-flash", "weight": 1}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "gemini",
        "model": "gemini/gemini-3.5-flash-lite", "weight": 1}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "gemini",
        "model": "gemini/gemini-3.6-flash", "weight": 1}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "gemini",
        "model": "gemini/gemini-3.7-flash", "weight": 1}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "gemini",
        "model": "gemini/gemini-3.8-flash", "weight": 1}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "gemini",
        "model": "gemini/gemma-4-26b-a4b-it", "weight": 5}},
    {"model_name": "auxiliary", "litellm_params": {
        "api_base": None, "custom_llm_provider": "gemini",
        "model": "gemini/gemma-4-31b-it", "weight": 5}},
]

#: The only deterministic alias in use: one deployment, no weight key at all.
QWEN_CF_ROWS: list[dict] = [
    {"model_name": "qwen3.8-27b-cf", "litellm_params": {
        "api_base": None, "custom_llm_provider": "cloudflare",
        "model": "cloudflare/@cf/qwen/qwen3.8-27b", "weight": None}},
]

#: The rename trap. ``qwen3.8-27b`` (no ``-cf``) is a 14-row duplicate of
#: ``orchestration``: nvidia_nim deepseek, glm, laguna, nemotron, muse, a
#: nested gateway, groq, openai. A seat labelled "Qwen" here is served DeepSeek.
QWEN_DUPLICATE_ROWS: list[dict] = [
    {**row, "model_name": "qwen3.8-27b"} for row in ORCHESTRATION_ROWS
]

#: The bigger trap, found by running the resolver against the live gateway.
#: ``gpt-4o-mini`` is not an OpenAI model here — it is a 16-row copy of the
#: ``auxiliary`` pool: a local MiniCPM5, six nvidia_nim models (Gemma, Nemotron,
#: Muse, Llama, gpt-oss), Groq, and seven Google/Gemini models. Measured from the
#: live gateway, not inferred: every one of its 16 rows is byte-identical to
#: ``auxiliary``'s. A seat labelled "gpt-4o-mini" is served Gemma and Nemotron.
#: The live config wires this alias into four profiles (``testprof``,
#: ``realprof``, ``verif_prof``, ``spot_prof``), which is why it matters.
GPT_4O_MINI_ROWS: list[dict] = [
    {**row, "model_name": "gpt-4o-mini"} for row in AUXILIARY_ROWS
]

MODEL_INFO_PAYLOAD: dict = {
    "object": "list",
    "data": (
        ORCHESTRATION_ROWS
        + AUXILIARY_ROWS
        + QWEN_CF_ROWS
        + QWEN_DUPLICATE_ROWS
        + GPT_4O_MINI_ROWS
    ),
}

#: The LAN gateway host the payloads above were fetched from.
GATEWAY_BASE = "http://203.0.113.30:8000/v1"
GATEWAY_HOST = "203.0.113.30:8000"

#: The live shape of the config these aliases are wired into, reduced to the
#: routing keys the resolver reads.
OPERATOR_CONFIG: dict = {
    "llm": {
        "orchestration": {
            "provider": "litellm",
            "model": "orchestration",
            "base_url": "${LITELLM_BASE_URL}",
            "api_key": "${LITELLM_API_KEY}",
        },
        "auxiliary": {
            "provider": "litellm",
            "model": "auxiliary",
            "base_url": "${LITELLM_BASE_URL}",
            "api_key": "${LITELLM_API_KEY}",
        },
        "delegation": {
            "provider": "litellm",
            "model": "delegation",
            "base_url": "${LITELLM_BASE_URL}",
            "api_key": "${LITELLM_API_KEY}",
        },
        # The deterministic alias, wrapped in a profile the way the composer
        # picker would. Not in the live config (the `qwen` CLI reaches it
        # directly), but it is the one alias a seat CAN be attributed to, so
        # the dispatcher needs a case for it.
        "qwen_cf": {
            "provider": "litellm",
            "model": "qwen3.8-27b-cf",
            "base_url": "${LITELLM_BASE_URL}",
            "api_key": "${LITELLM_API_KEY}",
        },
        "testprof": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "${OPENAI_API_KEY}",
        },
    },
    "settings": {
        "default_llm_profile": "orchestration",
        "override_per_task": True,
        "task_llm_profiles": {
            "auxiliary": "auxiliary",
            "delegation": "delegation",
            "orchestration": "orchestration",
        },
    },
}

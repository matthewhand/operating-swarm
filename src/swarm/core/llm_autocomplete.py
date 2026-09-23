"""#860: Low-latency prompt autocompletion engine."""

from __future__ import annotations

import os
import time
from typing import Any

from swarm.core.model_text import sanitize_model_text


AUTOCOMPLETE_SYSTEM_PROMPT = (
    "You are a fast, low-latency inline prompt and code autocompleter. "
    "Output ONLY the continuation text that immediately follows the prefix at the cursor. "
    "Do NOT repeat any text from the prefix. Keep completion concise and short (1-2 sentences or short code fragment max). "
    "Do not include quotes, explanations, markdown fences, or preamble."
)


def generate_autocomplete(
    prefix: str,
    suffix: str = "",
    agent_id: str = "",
    conversation_id: str = "",
    max_tokens: int = 32,
    timeout: float = 3.0,
) -> tuple[str, float]:
    """Generate inline ghost text completion for prefix using the resolved autocomplete model.

    Returns:
        (completion_text, duration_ms)
    """
    start_time = time.perf_counter()
    trimmed_prefix = prefix or ""
    if not trimmed_prefix.strip():
        return "", 0.0

    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("SWARM_LLM_ASSIST") != "1":
        # Predictable fallback in test runs
        duration = (time.perf_counter() - start_time) * 1000
        return " and continue", round(duration, 2)

    from openai import OpenAI

    from swarm.core.llm_task_routing import (
        get_profile_dict,
        load_swarm_config,
        model_id_for_profile,
        resolve_autocomplete_model,
    )
    from swarm.utils.env_utils import get_llm_base_url

    config = None
    try:
        config = load_swarm_config()
    except Exception:
        pass

    route = resolve_autocomplete_model(config)
    profile = get_profile_dict(route.profile, config) if config else None
    model = model_id_for_profile(route.profile, config) if config else route.profile

    base_url = ""
    api_key = ""
    if profile and isinstance(profile, dict):
        base_url = str(profile.get("base_url") or "").strip()
        api_key = str(profile.get("api_key") or "").strip()

    if not base_url:
        base_url = get_llm_base_url() or os.getenv("OPENAI_BASE_URL") or ""
    if not api_key:
        api_key = (
            os.getenv("LITELLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "ollama"
        )

    kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)

    user_content = (
        f"Prefix: {trimmed_prefix}\nSuffix: {suffix}\nCompletion:"
        if suffix
        else f"Prefix: {trimmed_prefix}\nCompletion:"
    )

    try:
        resp = client.chat.completions.create(
            model=model or "autocomplete",
            messages=[
                {"role": "system", "content": AUTOCOMPLETE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=min(64, max(8, max_tokens)),
            temperature=0.0,
        )
        content = (resp.choices[0].message.content or "") if resp.choices else ""
        cleaned = sanitize_model_text(content).strip()
        # If the model repeated the prefix, strip it
        if cleaned.startswith(trimmed_prefix):
            cleaned = cleaned[len(trimmed_prefix) :].strip()
        duration = (time.perf_counter() - start_time) * 1000
        return cleaned, round(duration, 2)
    except Exception:
        duration = (time.perf_counter() - start_time) * 1000
        return "", round(duration, 2)

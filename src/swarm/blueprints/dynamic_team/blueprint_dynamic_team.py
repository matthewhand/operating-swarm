import logging
import os
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from swarm.core.blueprint_base import BlueprintBase

logger = logging.getLogger(__name__)


class DynamicTeamBlueprint(BlueprintBase):
    """
    Minimal dynamic team blueprint that proxies user messages to the configured
    LLM profile via OpenAI-compatible Chat Completions and yields a single final
    assistant message.

    The blueprint_id is the team name/slug and is used as the `model` value in
    external OpenAI API clients when calling our `/v1/chat/completions`.
    """

    metadata = {
        "name": "dynamic-team",
        "description": "A dynamically-registered team using a configured LLM profile",
        "abbreviation": None,
    }

    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        profile_name = self.llm_profile_name
        profile = self.get_llm_profile(profile_name)

        base_url = profile.get("base_url")
        api_key = profile.get("api_key") or "ollama"  # Ollama usually doesn't require a key
        # No hardcoded model fallback: the profile's model is authoritative, with
        # env overrides as the only escape hatch (consistent with BlueprintBase).
        model_name = profile.get("model") or os.getenv("LITELLM_MODEL") or os.getenv("DEFAULT_LLM")

        if not base_url or not model_name:
            missing = "base_url" if not base_url else "model"
            logger.error("DynamicTeamBlueprint missing %s in llm profile '%s'", missing, profile_name)
            content = (f"Configuration error: {missing} missing for LLM profile '{profile_name}'.\n"
                       "Please configure the profile (e.g. an 'ollama' profile) in swarm_config.json.")
            yield {"messages": [{"role": "assistant", "content": content}]}
            return

        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        stream = bool(kwargs.get("stream"))
        try:
            if stream:
                # Stream tokens; yield incremental content chunks
                async with client.chat.completions.stream(model=model_name, messages=messages) as s:
                    async for event in s:
                        try:
                            # openai v1 stream yields chunks with .choices[0].delta.content
                            delta = getattr(event, "choices", [None])[0]
                            content = getattr(getattr(delta, "delta", None), "content", None)
                            if content:
                                yield {"messages": [{"role": "assistant", "content": content}]}
                        except Exception:
                            # Ignore malformed chunks; continue
                            continue
                # No explicit final aggregation here; ChatCompletionsView handles [DONE]
                return
            else:
                # Non-streaming single-shot
                resp = await client.chat.completions.create(model=model_name, messages=messages, stream=False)
                text = (resp.choices[0].message.content or "").strip()
                if not text:
                    text = (
                        f"[DynamicTeam] empty completion from model={model_name!r} "
                        f"profile={profile_name!r}. Check Settings → LLM profiles / gateway."
                    )
                yield {"messages": [{"role": "assistant", "content": text}]}
        except Exception as e:
            logger.exception("Dynamic team LLM call failed: %s", e)
            yield {"messages": [{"role": "assistant", "content": f"[DynamicTeam Error] {e}"}]}

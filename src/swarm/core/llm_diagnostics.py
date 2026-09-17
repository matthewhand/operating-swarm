"""Name the configuration that stops an LLM client from authenticating.

Provider failures say what went wrong technically — ``The api_key client option
must be set``, a 401 from a gateway, an invalid URL — but not what to change. The
observed case (REQ-884) was a ``swarm_config.json`` whose ``api_key`` /
``base_url`` were ``${LITELLM_API_KEY}`` / ``${LITELLM_BASE_URL}`` placeholders
with both variables unset, which reached the SPA as a bare provider error.

This module answers one question for an error path: which configuration knob is
missing? It is deliberately conservative — it only speaks up for the two cases it
can prove from configuration, and stays silent otherwise so a caller never blames
credentials it cannot see.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV_FILE_HINT = "in the environment (.env or ~/.config/swarm/.env)"


def _and_list(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def active_config() -> dict[str, Any] | None:
    """The raw (unsubstituted) active ``swarm_config.json``, or None.

    Raw on purpose: an unsubstituted ``${NAME}`` is the evidence this module is
    looking for, and ``load_raw_config`` discovers the same file the app uses.
    """
    try:
        from swarm.core.llm_task_routing import load_swarm_config

        config = load_swarm_config()
    except Exception:
        logger.debug("llm_diagnostics: could not load swarm config", exc_info=True)
        return None
    return config if isinstance(config, dict) else None


def active_chat_profile_name(config: dict[str, Any] | None = None) -> str:
    """Profile name the chat path would use (``orchestration`` under override)."""
    try:
        from swarm.core.llm_task_routing import resolve_chat_model

        return resolve_chat_model(config).profile or "default"
    except Exception:
        logger.debug("llm_diagnostics: could not resolve the chat profile", exc_info=True)
        return "default"


def llm_credential_hint(
    config: dict[str, Any] | None = None,
    profile_name: str | None = None,
) -> str:
    """One sentence naming what to set, or ``""`` when nothing looks missing.

    Covers (a) a ``${NAME}`` the profile points at that is not set, and (b) a
    profile with no key at all while the environment the SDK would fall back to
    has none either. Anything else returns ``""``.
    """
    from swarm.core.config_loader import raw_llm_profile, unresolved_env_placeholders

    cfg = config if isinstance(config, dict) else active_config()
    if not isinstance(cfg, dict):
        return ""
    name = profile_name or active_chat_profile_name(cfg)
    profile = raw_llm_profile(cfg, name)
    if not profile:
        # An absent or empty profile is its own, louder problem (the resolver
        # already says so); do not blame credentials for it.
        return ""

    # A surviving ``${NAME}`` means substitution found nothing; the env check
    # covers the same reference when the variable *is* set (the raw profile keeps
    # the placeholder either way).
    unset = [
        var
        for var in unresolved_env_placeholders(
            {key: profile.get(key) for key in ("api_key", "base_url")}
        )
        if not os.environ.get(var)
    ]
    if unset:
        return f"Set {_and_list(unset)} {_ENV_FILE_HINT}."

    from swarm.utils.env_utils import get_llm_api_key

    if not (profile.get("api_key") or get_llm_api_key()):
        return (
            f"Set LITELLM_API_KEY (or OPENAI_API_KEY) {_ENV_FILE_HINT}, "
            "or add an api_key to this LLM profile in swarm_config.json."
        )
    return ""

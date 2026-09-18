"""Classify fatal CLI/config session failures and decide whether to persist them.

A first-turn configuration or CLI-session failure must not become a history
thread the UI rehydrates on every refresh. Transient model errors still persist.
"""

from __future__ import annotations

from typing import Any, Mapping

from swarm.core.cli_sessions import is_resume_failure_text

FATAL_CONFIG_ERROR_KEY = "fatal_config_error"

# Terminal environment/config copy. Transient provider faults are not listed.
_FATAL_CONFIG_NEEDLES = (
    "no cli agents are configured",
    "no cli is configured",
    "no cli backend is configured",
    "unconfigured harness",
    "endpoint not configured",
)

# #499: needle → Settings section that can actually resolve the failure. The
# banner's primary action deep-links there; session actions stay secondary.
_FATAL_CONFIG_TARGETS: dict[str, dict[str, str]] = {
    "no cli agents are configured": {"section": "cli-agents"},
    "no cli is configured": {"section": "cli-agents"},
    "no cli backend is configured": {"section": "cli-agents"},
    "unconfigured harness": {"section": "remotes"},
    "endpoint not configured": {"section": "remotes"},
}

CONFIG_TARGET_KEY = "config_target"


def _blob(content: Any) -> str:
    if isinstance(content, Mapping):
        return str(content.get("content") or "")
    return str(content or "")


def is_fatal_config_error(content: Any, meta: Mapping[str, Any] | None = None) -> bool:
    """True for fatal CLI/config failures (not transient model errors)."""
    if isinstance(meta, Mapping) and meta.get(FATAL_CONFIG_ERROR_KEY) is True:
        return True
    if isinstance(content, Mapping) and content.get(FATAL_CONFIG_ERROR_KEY) is True:
        return True
    blob = _blob(content).lower()
    if not blob:
        return False
    if any(needle in blob for needle in _FATAL_CONFIG_NEEDLES):
        return True
    if is_resume_failure_text(blob):
        return True
    if "not configured" in blob and ("cli" in blob or "harness" in blob):
        return True
    return False


def is_fatal_config_turn(message: Any) -> bool:
    """True when a stored assistant turn is a terminal CLI/config failure."""
    if not isinstance(message, Mapping):
        return False
    if message.get("role") != "assistant":
        return False
    return is_fatal_config_error(message, message)


def fatal_config_error_extra(content: Any, meta: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Kwargs for ``append_turn`` when the reply is a fatal config/CLI failure.

    #499: when the matching needle maps to a Settings section, the target
    rides along as ``config_target`` — the banner's primary action deep-links
    there instead of dead-ending on session reshuffles. The bare boolean is
    kept for compatibility: a flag without a target must keep rendering
    today's banner.
    """
    if not is_fatal_config_error(content, meta):
        return {}
    extra: dict[str, Any] = {FATAL_CONFIG_ERROR_KEY: True}
    if isinstance(meta, Mapping) and meta.get(FATAL_CONFIG_ERROR_KEY) is True:
        return extra  # explicit flag carries no inferred target
    blob = _blob(content).lower()
    for needle, target in _FATAL_CONFIG_TARGETS.items():
        if needle in blob:
            extra[CONFIG_TARGET_KEY] = dict(target)
            break
    return extra


def is_uncontinued_fatal_init(messages: Any) -> bool:
    """True when the only assistant replies are fatal and the user has not continued.

    One user turn + fatal assistant (and no successful assistant) is an
    initialization failure — do not persist it as chat history.
    """
    turns = [
        item
        for item in (messages or [])
        if isinstance(item, Mapping) and item.get("role") in ("user", "assistant")
    ]
    users = [item for item in turns if item.get("role") == "user"]
    assistants = [item for item in turns if item.get("role") == "assistant"]
    if len(users) > 1:
        return False
    if not assistants:
        return False
    if any(not is_fatal_config_turn(item) for item in assistants):
        return False
    return True

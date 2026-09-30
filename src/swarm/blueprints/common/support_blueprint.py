"""Support session-ownership helpers (REQ-50).

Applies ``skills/support-session-ownership`` via the same ``skill=`` attach
as ``cli_agent``. Used by the discoverable Support blueprint every turn.
"""

from __future__ import annotations

import logging
from typing import Any

from swarm.blueprints.common import cli_fusion_support as fusion
from swarm.core.support_journey import SUPPORT_JOURNEY_FIXTURE

logger = logging.getLogger(__name__)

SUPPORT_SKILL_NAME = "support-session-ownership"
SUPPORT_SKILL_FIXTURE = "SESSION_OWNERSHIP_API_CLI_REMOTE"
SUPPORT_JOURNEY_SKILL_FIXTURE = SUPPORT_JOURNEY_FIXTURE
CLICK_BUBBLE_TO_EDIT = "click the bubble to edit"

SESSION_KINDS = ("api", "cli", "remote")
PARAM_SESSION_KIND = "session_kind"


def is_support_id(blueprint_id: str | None) -> bool:
    return (blueprint_id or "").strip().lower() == "support"


def normalize_session_kind(value: Any) -> str:
    kind = str(value or "").strip().lower()
    return kind if kind in SESSION_KINDS else "api"


def resolve_session_kind(
    params: dict[str, Any] | None,
    messages: list[dict[str, Any]] | None = None,
) -> str:
    """Resolve api/cli/remote for this Support turn.

    Explicit ``session_kind`` wins. Otherwise a coarse heuristic on the latest
    user text (so "my grok/cli session" is treated as external).
    """
    params = params or {}
    explicit = params.get(PARAM_SESSION_KIND)
    if explicit:
        return normalize_session_kind(explicit)

    text = ""
    for msg in reversed(messages or []):
        if (msg.get("role") or "user") == "user" and msg.get("content"):
            text = str(msg["content"]).lower()
            break
    if any(token in text for token in (" remote ", "remote agent", "remote session")):
        return "remote"
    if any(
        token in text
        for token in (
            "cli ",
            "cli.",
            "cli?",
            "cli agent",
            "cli session",
            "grok",
            "claude",
            "gemini",
            "codex",
            "opencode",
        )
    ):
        return "cli"
    return "api"


def support_turn_context(session_kind: str = "api", task: str = "") -> str:
    """System/prompt Support sees this turn (skill attach + session kind)."""
    kind = normalize_session_kind(session_kind)
    note = (
        "Current session kind: API. Operating Swarm owns this thread; bubbles are editable."
        if kind == "api"
        else (
            f"Current session kind: {kind}. The live session is outside Operating Swarm. "
            "Do not tell the user to click the bubble to edit."
        )
    )
    body = f"{note}\n{task}".strip() if task else note
    prompt, applied = fusion.apply_skill_to_prompt(
        body, {fusion.PARAM_SKILL: SUPPORT_SKILL_NAME}
    )
    if applied != SUPPORT_SKILL_NAME:
        logger.warning("Support skill %s was not applied", SUPPORT_SKILL_NAME)
    return prompt


def support_turn_reply(
    _messages: list[dict[str, Any]] | None,
    session_kind: str = "api",
) -> str:
    """Laconic Socratic reply used in tests and when no LLM is available.

    CLI/remote must never claim the user can click the bubble to edit.
    """
    kind = normalize_session_kind(session_kind)
    if kind in ("cli", "remote"):
        return (
            "That session lives outside Operating Swarm — I cannot edit those bubbles. "
            "What are you trying to change?"
        )
    return (
        "This thread is owned here, so you can edit a user or assistant bubble. "
        "Which message needs a rewrite?"
    )

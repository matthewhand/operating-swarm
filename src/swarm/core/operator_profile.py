"""#1323 — operator About me profile (persist + model-context injection).

The operator writes a short identity card (name, timezone, notes). It lives
in ``UserPreference.values['operator_profile']`` and is prepended as a
system message on API chat turns. Empty cards inject nothing. Secret-shaped
keys are rejected the same way as the rest of the preferences bag.
"""

from __future__ import annotations

from typing import Any

from swarm.core.user_preferences import (
    ABOUT_ME_KEY,
    OPERATOR_PROFILE_KEY,
    is_secret_key,
    normalize_about_me,
    normalize_operator_profile,
    operator_profile_has_content,
    primary_operator_principal,
)

OPERATOR_PROFILE_PREFIX = "About the operator:"
OPERATOR_PROFILE_HEADER = "[Operator profile]"
OPERATOR_PROFILE_FOOTER = "[/Operator profile]"


def empty_operator_profile() -> dict[str, str]:
    return normalize_operator_profile(None)


def format_operator_profile(profile: dict[str, Any] | None) -> str:
    """Render the system-message body, or ``\"\"`` when there is nothing to say."""
    card = normalize_operator_profile(profile)
    if not operator_profile_has_content(card):
        return ""
    lines = [OPERATOR_PROFILE_PREFIX]
    if card["name"]:
        lines.append(f"- Name: {card['name']}")
    if card["timezone"]:
        lines.append(f"- Timezone: {card['timezone']}")
    if card["about"]:
        lines.append(f"- Notes: {card['about']}")
    return "\n".join(lines)


def _already_injected(messages: list[dict[str, Any]]) -> bool:
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        if role not in {"system", "developer"}:
            continue
        content = msg.get("content")
        text = content if isinstance(content, str) else ""
        if text.startswith(OPERATOR_PROFILE_PREFIX):
            return True
    return False


def messages_with_operator_profile(
    messages: list[dict[str, Any]] | None,
    profile: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Prepend the About me card when it has content and is not already present."""
    out = list(messages or [])
    body = format_operator_profile(profile)
    if not body or _already_injected(out):
        return out
    return [{"role": "system", "content": body}, *out]


def operator_profile_text_from_messages(messages: list[dict[str, Any]] | None) -> str:
    """Return the injected About me card, or ``\"\"`` when this turn has none."""
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        if role not in {"system", "developer"}:
            continue
        content = msg.get("content")
        text = content if isinstance(content, str) else ""
        if text.startswith(OPERATOR_PROFILE_PREFIX):
            return text
    return ""


def apply_operator_profile_to_agent(agent: Any, messages: list[dict[str, Any]] | None) -> None:
    """Copy this turn's About me card onto ``agent.instructions``.

    API runners (``ApiKindBase``, chatbot, agent_router) hand ``Runner.run``
    only the latest user turn, so a system message prepended to the list is
    discarded. The card has to live on the agent instructions for that call.
    Missing instructions are treated as empty. Callable instructions are left
    alone. No-op when the card is absent or already present.
    """
    body = operator_profile_text_from_messages(messages)
    if not body or agent is None:
        return
    current = getattr(agent, "instructions", None)
    if callable(current):
        return
    if current is None:
        current = ""
    elif not isinstance(current, str):
        return
    if body in current:
        return
    agent.instructions = f"{body}\n\n{current}" if current.strip() else body


def load_operator_profile(*, user: Any = None, principal: str | None = None) -> dict[str, str]:
    """Read the persisted card for this caller. Never raises; empty on miss."""
    try:
        from swarm.models.preferences import UserPreference
    except Exception:
        return empty_operator_profile()

    row = None
    try:
        username = ""
        if user is not None and getattr(user, "is_authenticated", False):
            getter = getattr(user, "get_username", None)
            username = str(getter() if callable(getter) else "").strip()
            if getattr(user, "pk", None) is not None:
                row = UserPreference.objects.filter(user=user).first()
            if row is None and username:
                row = UserPreference.objects.filter(principal=f"user:{username}").first()
        if row is None:
            key = (principal or "").strip() or (
                f"user:{username}" if username else primary_operator_principal()
            )
            row = UserPreference.objects.filter(principal=key).first()
    except Exception:
        return empty_operator_profile()

    values = getattr(row, "values", None) if row is not None else None
    raw = values.get(OPERATOR_PROFILE_KEY) if isinstance(values, dict) else None
    return normalize_operator_profile(raw)


def messages_with_operator_profile_for_user(
    user: Any,
    messages: list[dict[str, Any]] | None,
    *,
    principal: str | None = None,
) -> list[dict[str, Any]]:
    return messages_with_operator_profile(
        messages, load_operator_profile(user=user, principal=principal)
    )


def format_about_me_block(about_me: str | None) -> str:
    """Delimited ``[Operator profile]`` block, or ``\"\"`` when unset."""
    text = normalize_about_me(about_me)
    if not text:
        return ""
    return f"{OPERATOR_PROFILE_HEADER}\n{text}\n{OPERATOR_PROFILE_FOOTER}"


def load_about_me(*, user: Any = None, principal: str | None = None) -> str:
    """Read the persisted ``about_me`` string. Never raises; empty on miss."""
    try:
        from swarm.models.preferences import UserPreference
    except Exception:
        return ""

    row = None
    try:
        username = ""
        if user is not None and getattr(user, "is_authenticated", False):
            getter = getattr(user, "get_username", None)
            username = str(getter() if callable(getter) else "").strip()
            if getattr(user, "pk", None) is not None:
                row = UserPreference.objects.filter(user=user).first()
            if row is None and username:
                row = UserPreference.objects.filter(principal=f"user:{username}").first()
        if row is None:
            key = (principal or "").strip() or (
                f"user:{username}" if username else primary_operator_principal()
            )
            row = UserPreference.objects.filter(principal=key).first()
    except Exception:
        return ""

    values = getattr(row, "values", None) if row is not None else None
    raw = values.get(ABOUT_ME_KEY) if isinstance(values, dict) else None
    return normalize_about_me(raw)


def instructions_with_about_me(
    instructions: str | None,
    about_me: str | None = None,
    *,
    user: Any = None,
    principal: str | None = None,
) -> str:
    """Append the delimited profile block to composed instructions.

    Empty ``about_me`` leaves ``instructions`` unchanged. A block already
    present is not repeated. Non-string instructions (callables) pass through.
    """
    if instructions is not None and not isinstance(instructions, str):
        return instructions  # type: ignore[return-value]
    base = instructions or ""
    if OPERATOR_PROFILE_HEADER in base:
        return base
    if about_me is None:
        about_me = load_about_me(user=user, principal=principal)
    block = format_about_me_block(about_me)
    if not block:
        return base
    if not base.strip():
        return block
    return f"{base.rstrip()}\n\n{block}"


def messages_with_operator_profile_for_request(
    request: Any,
    messages: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    from swarm.core.user_preferences import preference_identity

    try:
        user, principal, _guest = preference_identity(request)
    except Exception:
        user, principal = getattr(request, "user", None), None
    return messages_with_operator_profile_for_user(user, messages, principal=principal)


# Re-export so callers can import the registry key from one module.
__all__ = [
    "OPERATOR_PROFILE_FOOTER",
    "OPERATOR_PROFILE_HEADER",
    "OPERATOR_PROFILE_KEY",
    "OPERATOR_PROFILE_PREFIX",
    "apply_operator_profile_to_agent",
    "empty_operator_profile",
    "format_about_me_block",
    "format_operator_profile",
    "instructions_with_about_me",
    "is_secret_key",
    "load_about_me",
    "load_operator_profile",
    "operator_profile_text_from_messages",
    "messages_with_operator_profile",
    "messages_with_operator_profile_for_request",
    "messages_with_operator_profile_for_user",
    "normalize_operator_profile",
    "operator_profile_has_content",
]

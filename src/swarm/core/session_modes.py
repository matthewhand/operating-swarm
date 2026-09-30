"""Operator session modes for Agent Router (Shift+Tab).

Always-approve is not a cycle stop: Operating Swarm already injects the host CLI
auto-approve flags (``--always-approve``, ``--yolo``, …) in ``cli_catalog``.
"""

from __future__ import annotations

SESSION_MODES = ("default", "plan", "auto-edit")

PLAN_PREFIX = (
    "[Operating Swarm session mode: plan]\n"
    "Explore and write an implementation plan. Do not edit files or run "
    "mutating commands. Ask if the approach is ambiguous.\n\n"
)

AUTO_EDIT_PREFIX = (
    "[Operating Swarm session mode: auto-edit]\n"
    "You may edit project files without asking. Still ask before destructive "
    "shell, secrets, or paths outside the project. Host CLIs already run "
    "always-approve via Operating Swarm catalog flags.\n\n"
)

_ALIASES = {
    "default": "default",
    "ask": "default",
    "normal": "default",
    "plan": "plan",
    "auto-edit": "auto-edit",
    "autoedit": "auto-edit",
    "auto_edit": "auto-edit",
    "accept-edits": "auto-edit",
    "acceptedits": "auto-edit",
}


def normalize_session_mode(value: str | None) -> str:
    raw = (value or "default").strip().lower().replace(" ", "-")
    return _ALIASES.get(raw, "default")


def cycle_session_mode(current: str | None) -> str:
    mode = normalize_session_mode(current)
    idx = SESSION_MODES.index(mode) if mode in SESSION_MODES else 0
    return SESSION_MODES[(idx + 1) % len(SESSION_MODES)]


def apply_session_mode(message: str, mode: str | None) -> str:
    """Prefix a user message. Empty text is unchanged."""
    text = message or ""
    if not text.strip():
        return text
    resolved = normalize_session_mode(mode)
    if resolved == "plan":
        return PLAN_PREFIX + text
    if resolved == "auto-edit":
        return AUTO_EDIT_PREFIX + text
    return text

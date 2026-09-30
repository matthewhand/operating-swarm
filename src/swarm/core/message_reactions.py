"""Chat message emoji reactions + the agent ``add_reaction`` tool (#1411).

Operators toggle a small palette from the message action row. Agents call
``add_reaction`` to write the same store. Reactions live on the JSON
transcript (like ``edited``) and never enter model context.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from swarm.core.safety import CHANNEL_API, uses_swarm_approval

logger = logging.getLogger(__name__)

TOOL_NAME = "add_reaction"
EVENT_TYPE = "reaction"
ACTOR_USER = "user"
ACTOR_AGENT_PREFIX = "agent:"

# Theme-defined reaction sets (#1411). Speech owns the full palette; Simple
# and IRC define smaller sets. Keep in sync with
# webui/frontend/src/lib/bubbleThemes/reactions.ts.
THEME_REACTION_EMOJIS: dict[str, tuple[str, ...]] = {
    "speech": ("👍", "👎", "❤️", "😂", "🎉", "👀", "🚀", "✅"),
    "simple": ("👍", "👎", "❤️", "😂", "✅"),
    "irc": ("👍", "👎", "👀", "🎉"),
}
DEFAULT_BUBBLE_THEME = "speech"
REACTION_EMOJIS: tuple[str, ...] = THEME_REACTION_EMOJIS[DEFAULT_BUBBLE_THEME]
REACTION_EMOJI_SET = frozenset(
    emoji for emojis in THEME_REACTION_EMOJIS.values() for emoji in emojis
)
RESPOND_TOOL_NAME = "respond_with_reaction"

ERROR_NO_SESSION = "add_reaction is not available on this seat"
ERROR_CHANNEL = "add_reaction is only available on API chat"
ERROR_EMOJI = "add_reaction: emoji must be one of " + " ".join(REACTION_EMOJIS)
ERROR_INDEX = "add_reaction: message_index is out of range"
ERROR_NO_TARGET = "add_reaction: no user message to react to"

EmitFn = Callable[[dict[str, Any]], Awaitable[None] | None]
PersistFn = Callable[[], Awaitable[None] | None]


def actor_for_agent(agent_id: str | None) -> str:
    slug = str(agent_id or "agent").strip() or "agent"
    return f"{ACTOR_AGENT_PREFIX}{slug[:64]}"


# Emoji presentation selector. Models often emit ❤ (U+2764) for ❤️.
_EMOJI_VARIATION_SELECTOR = "\ufe0f"


def _without_variation_selector(text: str) -> str:
    return text.replace(_EMOJI_VARIATION_SELECTOR, "")


def resolve_bubble_theme(raw: Any) -> str:
    """Known bubble theme id, or speech when the value is missing/unknown."""
    text = str(raw or "").strip().lower()
    return text if text in THEME_REACTION_EMOJIS else DEFAULT_BUBBLE_THEME


def reactions_for_theme(theme: Any = None) -> tuple[str, ...]:
    return THEME_REACTION_EMOJIS[resolve_bubble_theme(theme)]


def is_allowed_emoji(emoji: Any) -> bool:
    return normalize_emoji(emoji) is not None


def normalize_emoji(emoji: Any) -> str | None:
    """Return the palette form, or None.

    Unqualified hearts (``❤``) map to the palette ``❤️``. Other characters
    stay rejected.
    """
    text = str(emoji or "").strip()
    if text in REACTION_EMOJI_SET:
        return text
    folded = _without_variation_selector(text)
    if not folded:
        return None
    for candidate in REACTION_EMOJIS:
        if _without_variation_selector(candidate) == folded:
            return candidate
    return None


def emoji_allowed_for_theme(emoji: Any, theme: Any = None) -> str | None:
    text = normalize_emoji(emoji)
    if text is None or text not in reactions_for_theme(theme):
        return None
    return text


def emoji_error(theme: Any = None, tool: str = TOOL_NAME) -> str:
    allowed = reactions_for_theme(theme)
    if tool == TOOL_NAME and allowed == REACTION_EMOJIS:
        return ERROR_EMOJI
    return f"{tool}: emoji must be one of " + " ".join(allowed)


def _as_actor(raw: Any) -> str | None:
    text = str(raw or "").strip()
    if not text or len(text) > 80:
        return None
    if text == ACTOR_USER or text.startswith(ACTOR_AGENT_PREFIX):
        return text
    return None


def normalize_reactions(raw: Any) -> list[dict[str, Any]]:
    """Keep only palette emojis with unique actors. Empty list when none."""
    if not isinstance(raw, list):
        return []
    by_emoji: dict[str, list[str]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        emoji = normalize_emoji(item.get("emoji"))
        if emoji is None:
            continue
        actors: list[str] = []
        seen: set[str] = set()
        for actor in item.get("actors") or []:
            cleaned = _as_actor(actor)
            if cleaned is None or cleaned in seen:
                continue
            seen.add(cleaned)
            actors.append(cleaned)
        if actors:
            by_emoji[emoji] = actors
    return [{"emoji": emoji, "actors": by_emoji[emoji]} for emoji in REACTION_EMOJIS if emoji in by_emoji]


def public_reactions(raw: Any, *, viewer: str = ACTOR_USER) -> list[dict[str, Any]]:
    """Aggregate counts + whether the viewer / any agent reacted."""
    out: list[dict[str, Any]] = []
    for row in normalize_reactions(raw):
        actors = list(row["actors"])
        out.append(
            {
                "emoji": row["emoji"],
                "count": len(actors),
                "userReacted": ACTOR_USER in actors,
                "agentReacted": any(actor.startswith(ACTOR_AGENT_PREFIX) for actor in actors),
                "viewerReacted": viewer in actors,
            }
        )
    return out


def toggle_reaction(message: dict[str, Any], emoji: str, actor: str) -> list[dict[str, Any]] | None:
    """Toggle ``actor`` on ``emoji``. Returns the new list, or None if invalid."""
    cleaned = normalize_emoji(emoji)
    who = _as_actor(actor)
    if cleaned is None or who is None or not isinstance(message, dict):
        return None
    current = normalize_reactions(message.get("reactions"))
    found = False
    next_rows: list[dict[str, Any]] = []
    for row in current:
        actors = list(row["actors"])
        if row["emoji"] != cleaned:
            next_rows.append({"emoji": row["emoji"], "actors": actors})
            continue
        found = True
        if who in actors:
            actors = [item for item in actors if item != who]
        else:
            actors.append(who)
        if actors:
            next_rows.append({"emoji": cleaned, "actors": actors})
    if not found:
        next_rows.append({"emoji": cleaned, "actors": [who]})
    if next_rows:
        message["reactions"] = next_rows
    else:
        message.pop("reactions", None)
    return normalize_reactions(message.get("reactions"))


def ensure_reaction(message: dict[str, Any], emoji: str, actor: str) -> list[dict[str, Any]] | None:
    """Add ``actor`` on ``emoji`` if missing. Does not remove. None if invalid."""
    cleaned = normalize_emoji(emoji)
    who = _as_actor(actor)
    if cleaned is None or who is None or not isinstance(message, dict):
        return None
    current = normalize_reactions(message.get("reactions"))
    found = False
    next_rows: list[dict[str, Any]] = []
    for row in current:
        actors = list(row["actors"])
        if row["emoji"] != cleaned:
            next_rows.append({"emoji": row["emoji"], "actors": actors})
            continue
        found = True
        if who not in actors:
            actors.append(who)
        next_rows.append({"emoji": cleaned, "actors": actors})
    if not found:
        next_rows.append({"emoji": cleaned, "actors": [who]})
    stored = normalize_reactions(next_rows)
    if stored:
        message["reactions"] = stored
    else:
        message.pop("reactions", None)
    return stored


def resolve_target_index(messages: list[Any], message_index: Any) -> int | None:
    """Resolve a tool index. ``-1`` / omitted → last user turn."""
    if not isinstance(messages, list) or not messages:
        return None
    if message_index is None or message_index == "" or message_index == -1:
        for idx in range(len(messages) - 1, -1, -1):
            row = messages[idx]
            if isinstance(row, dict) and str(row.get("role") or "") == "user":
                return idx
        return None
    try:
        idx = int(message_index)
    except (TypeError, ValueError):
        return None
    if 0 <= idx < len(messages) and isinstance(messages[idx], dict):
        return idx
    return None


def reaction_event(
    *,
    index: int,
    emoji: str,
    actor: str,
    reactions: list[dict[str, Any]],
    agent_id: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": EVENT_TYPE,
        "index": index,
        "emoji": emoji,
        "actor": actor,
        "reactions": public_reactions(reactions, viewer=ACTOR_USER),
    }
    if agent_id:
        payload["agent_id"] = agent_id
    return payload


@dataclass
class ReactionSession:
    """Per-turn handle so ``add_reaction`` can mutate the live transcript."""

    messages: list[dict[str, Any]]
    agent_id: str
    channel: str = CHANNEL_API
    bubble_theme: str = DEFAULT_BUBBLE_THEME
    persist_fn: PersistFn | None = None
    emit_fn: EmitFn | None = None
    reaction_only: dict[str, str] | None = None

    async def react(self, emoji: str, message_index: Any = -1) -> str:
        if not uses_swarm_approval(self.channel):
            return ERROR_CHANNEL
        cleaned = emoji_allowed_for_theme(emoji, self.bubble_theme)
        if cleaned is None:
            return emoji_error(self.bubble_theme, TOOL_NAME)
        idx = resolve_target_index(self.messages, message_index)
        if idx is None:
            return ERROR_NO_TARGET if message_index in (None, "", -1) else ERROR_INDEX
        actor = actor_for_agent(self.agent_id)
        rows = ensure_reaction(self.messages[idx], cleaned, actor)
        if rows is None:
            return ERROR_EMOJI
        event = reaction_event(
            index=idx,
            emoji=cleaned,
            actor=actor,
            reactions=rows,
            agent_id=self.agent_id,
        )
        if self.persist_fn is not None:
            result = self.persist_fn()
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]
        if self.emit_fn is not None:
            result = self.emit_fn(event)
            if hasattr(result, "__await__"):
                await result  # type: ignore[misc]
        return json.dumps({"ok": True, "action": "added", "emoji": cleaned, "index": idx})

    async def respond_only(self, emoji: str) -> str:
        """Record a reaction-only turn: the emoji is the whole reply, no text."""
        if not uses_swarm_approval(self.channel):
            return ERROR_CHANNEL
        cleaned = emoji_allowed_for_theme(emoji, self.bubble_theme)
        if cleaned is None:
            return emoji_error(self.bubble_theme, RESPOND_TOOL_NAME)
        self.reaction_only = {
            "emoji": cleaned,
            "actor": actor_for_agent(self.agent_id),
        }
        return json.dumps(
            {
                "ok": True,
                "reaction_only": True,
                "emoji": cleaned,
                "text": "",
            }
        )


_CURRENT_SESSION: ContextVar[ReactionSession | None] = ContextVar(
    "swarm_reaction_session",
    default=None,
)


def current_reaction_session() -> ReactionSession | None:
    return _CURRENT_SESSION.get()


def install_reaction_session(session: ReactionSession | None):
    return _CURRENT_SESSION.set(session)


def reset_reaction_session(token) -> None:
    _CURRENT_SESSION.reset(token)


async def add_reaction(emoji: str, message_index: int = -1) -> str:
    """Add an emoji reaction to a chat message.

    Use this to acknowledge the operator without writing a full reply
    (thumbs-up when a task is done, eyes when you are looking). Calling
    again with the same emoji keeps the reaction; it does not remove it.
    Omit ``message_index`` (or pass -1) to react to the latest user message.
    An explicit index is a position in the stored transcript, not in the
    compacted context window.

    Args:
        emoji: One of 👍 👎 ❤️ 😂 🎉 👀 🚀 ✅. Unqualified ❤ is accepted.
        message_index: Stored-transcript index. -1 = last user message.
    """
    session = current_reaction_session()
    if session is None:
        return ERROR_NO_SESSION
    return await session.react(emoji, message_index)


async def respond_with_reaction(emoji: str) -> str:
    """End this turn with only an emoji reaction and no text reply.

    Use when a reaction from the active bubble theme (for example a
    thumbs-up) is the whole response. Do not also write a text reply.

    Args:
        emoji: One reaction emoji defined by the active bubble theme.
    """
    session = current_reaction_session()
    if session is None:
        return ERROR_NO_SESSION
    return await session.respond_only(emoji)


def reaction_only_record(*, emoji: str, actor: str) -> dict[str, Any]:
    """Assistant turn whose display is the emoji and whose content is empty."""
    return {
        "role": "assistant",
        "content": "",
        "reaction_only": True,
        "reactions": [{"emoji": emoji, "actors": [actor]}],
    }


def reaction_turn_event(
    *,
    message_id: str,
    emoji: str,
    reactions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": "reaction_turn",
        "id": message_id,
        "emoji": emoji,
        "reaction_only": True,
        "reactions": public_reactions(reactions, viewer=ACTOR_USER),
    }


def reaction_tool_schema(theme: Any = None) -> dict[str, Any]:
    """JSON schema the agent sees for a reaction-only turn."""
    emojis = list(reactions_for_theme(theme))
    return {
        "name": RESPOND_TOOL_NAME,
        "description": (
            "End this turn with only an emoji reaction and no text reply. "
            "Pick one emoji from the active bubble theme."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "emoji": {
                    "type": "string",
                    "enum": emojis,
                    "description": "Reaction emoji defined by the active bubble theme.",
                }
            },
            "required": ["emoji"],
            "additionalProperties": False,
        },
    }


def _apply_emoji_enum(tool: Any, theme: str) -> None:
    schema = getattr(tool, "params_json_schema", None)
    if not isinstance(schema, dict):
        return
    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    emoji = props.get("emoji")
    if not isinstance(emoji, dict):
        return
    emoji["enum"] = list(reactions_for_theme(theme))


def _tool_names(current: Any) -> set[str]:
    names: set[str] = set()
    for fn in current or []:
        name = getattr(fn, "name", None) or getattr(fn, "__name__", None)
        if name:
            names.add(str(name))
    return names


def _iter_agents(blueprint: Any) -> list[Any]:
    agents: list[Any] = []
    raw = getattr(blueprint, "agents", None)
    if isinstance(raw, dict):
        agents.extend(raw.values())
    elif isinstance(raw, list):
        agents.extend(raw)
    starting = getattr(blueprint, "starting_agent", None)
    if starting is not None and not callable(starting) and starting not in agents:
        agents.append(starting)
    return agents


def _wrap_function_tool(fn: Any, name: str) -> Any:
    from agents import function_tool

    try:
        return function_tool(fn, name_override=name)
    except TypeError:
        wrapped = function_tool(fn)
        try:
            wrapped.name = name
        except Exception:
            pass
        return wrapped


def as_function_tools(theme: Any = None) -> list[Any]:
    """openai-agents function_tool wrappers, or [] if the SDK is missing."""
    try:
        from agents import function_tool  # noqa: F401
    except Exception:
        logger.debug("agents SDK not available; reaction tools unavailable")
        return []
    resolved = resolve_bubble_theme(theme)
    tools = [
        _wrap_function_tool(add_reaction, TOOL_NAME),
        _wrap_function_tool(respond_with_reaction, RESPOND_TOOL_NAME),
    ]
    for tool in tools:
        _apply_emoji_enum(tool, resolved)
    return tools


def attach_reaction_to_agent(agent: Any, theme: Any = None) -> list[str]:
    extras = as_function_tools(theme)
    if not extras:
        extras = [add_reaction, respond_with_reaction]

    attached: list[str] = []
    for attr in ("tools", "functions"):
        current = getattr(agent, attr, None)
        if current is None:
            try:
                setattr(agent, attr, [])
                current = getattr(agent, attr)
            except Exception:
                continue
        if isinstance(current, tuple):
            current = list(current)
            try:
                setattr(agent, attr, current)
            except Exception:
                continue
        if not isinstance(current, list):
            continue
        have = _tool_names(current)
        for tool in extras:
            name = str(getattr(tool, "name", None) or getattr(tool, "__name__", "") or "")
            if not name or name in have:
                continue
            current.append(tool)
            have.add(name)
            attached.append(name)
    return attached


def install_reaction_on_blueprint(blueprint: Any) -> list[str]:
    original = getattr(blueprint, "create_starting_agent", None)
    if callable(original) and not getattr(blueprint, "_reaction_tool_wrapped", False):

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            agent = original(*args, **kwargs)
            attach_reaction_to_agent(agent, getattr(blueprint, "_reaction_theme", None))
            return agent

        blueprint.create_starting_agent = wrapped
        blueprint._reaction_tool_wrapped = True

    attached: list[str] = []
    for agent in _iter_agents(blueprint):
        attached.extend(attach_reaction_to_agent(agent))
    return attached


def _refresh_reaction_schemas(blueprint: Any, theme: str) -> None:
    for agent in _iter_agents(blueprint):
        for attr in ("tools", "functions"):
            current = getattr(agent, attr, None)
            if not isinstance(current, list):
                continue
            for tool in current:
                name = str(getattr(tool, "name", None) or getattr(tool, "__name__", "") or "")
                if name in (TOOL_NAME, RESPOND_TOOL_NAME):
                    _apply_emoji_enum(tool, theme)


def install_reaction_for_runtime(
    blueprint: Any,
    *,
    channel: str = CHANNEL_API,
    theme: Any = None,
) -> list[str]:
    """Attach reaction tools on API-owned seats. No-op for CLI/remote.

    theme selects the bubble theme emoji enum on the tool schema.
    """
    if not uses_swarm_approval(channel):
        return []
    resolved = resolve_bubble_theme(theme)
    try:
        blueprint._reaction_theme = resolved
    except Exception:
        pass
    attached = install_reaction_on_blueprint(blueprint)
    _refresh_reaction_schemas(blueprint, resolved)
    return attached


__all__ = [
    "ACTOR_AGENT_PREFIX",
    "ACTOR_USER",
    "ERROR_CHANNEL",
    "ERROR_EMOJI",
    "ERROR_INDEX",
    "ERROR_NO_SESSION",
    "ERROR_NO_TARGET",
    "EVENT_TYPE",
    "DEFAULT_BUBBLE_THEME",
    "REACTION_EMOJIS",
    "RESPOND_TOOL_NAME",
    "THEME_REACTION_EMOJIS",
    "TOOL_NAME",
    "ReactionSession",
    "actor_for_agent",
    "add_reaction",
    "emoji_allowed_for_theme",
    "emoji_error",
    "reaction_only_record",
    "reaction_tool_schema",
    "reaction_turn_event",
    "reactions_for_theme",
    "resolve_bubble_theme",
    "respond_with_reaction",
    "attach_reaction_to_agent",
    "current_reaction_session",
    "ensure_reaction",
    "install_reaction_for_runtime",
    "install_reaction_on_blueprint",
    "install_reaction_session",
    "is_allowed_emoji",
    "normalize_emoji",
    "normalize_reactions",
    "public_reactions",
    "reaction_event",
    "reset_reaction_session",
    "resolve_target_index",
    "toggle_reaction",
]

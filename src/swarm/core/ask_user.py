"""Agent-initiated questions to the human (issue #221).

Cheapest honest path: an ``ask_user`` function_tool that reuses the
gate-approval elicit pattern (in-memory Future + WS frame). The openai-agents
run loop waits on the tool result — no engine change.

Opt-in via params ``elicit_questions`` (default off). At most one outstanding
question per turn. Ask/choices/answer pass :func:`sanitize_model_text`.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from swarm.core.model_text import sanitize_model_text
from swarm.core.safety import CHANNEL_API, uses_swarm_approval

logger = logging.getLogger(__name__)

TOOL_NAME = "ask_user"
EVENT_TYPE = "user_question"
ANSWER_TYPE = "question_answer"

MAX_OUTSTANDING_PER_TURN = 1
MAX_CHOICES = 8
ASK_MAX = 280
CHOICE_MAX = 80
OTHER_MAX = 80
ANSWER_MAX = 500
TIMEOUT_SEC = 300

ERROR_DISABLED = "ask_user is not enabled on this seat (elicit_questions is off)"
ERROR_CHANNEL = "ask_user is only available on API chat"
ERROR_CAP = "ask_user: a question is already pending this turn"
ERROR_INVALID = "ask_user: ask and at least one choice are required"
TIMEOUT_RESULT = "timed out; user did not answer"
INTERRUPTED_RESULT = "interrupted"

DEMO_ASK = "Which profile should I deploy?"
DEMO_CHOICES = ["staging", "canary", "prod"]
DEMO_OTHER = "Custom profile"
DEMO_QUESTION_ID = "deploy-profile"

ElicitQuestionFn = Callable[[dict[str, Any]], Awaitable[str] | str]


def coerce_enabled(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, (int, float)) and value == 1:
        return True
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def elicit_questions_enabled(
    params: dict[str, Any] | None,
    *,
    channel: str = CHANNEL_API,
) -> bool:
    """Opt-in per seat. Default off. API chat only (CLI/remote keep their own UIs)."""
    if not uses_swarm_approval(channel):
        return False
    if not isinstance(params, dict):
        return False
    return coerce_enabled(params.get("elicit_questions"))


def _clip(text: str, limit: int) -> str:
    cleaned = sanitize_model_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip()


def _as_choices(raw: Any) -> list[str]:
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            raw = parsed
        else:
            raw = [part.strip() for part in stripped.split(",") if part.strip()]
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        label = _clip(str(item or ""), CHOICE_MAX)
        key = label.lower()
        if not label or key in seen:
            continue
        seen.add(key)
        out.append(label)
        if len(out) >= MAX_CHOICES:
            break
    return out


def normalize_question(
    *,
    ask: str,
    choices: Any,
    other: str = "Other",
    question_id: str = "q",
) -> dict[str, Any] | None:
    """Sanitize and validate a question payload, or None when unusable."""
    cleaned_ask = _clip(str(ask or ""), ASK_MAX)
    cleaned_choices = _as_choices(choices)
    if not cleaned_ask or not cleaned_choices:
        return None
    qid = _clip(str(question_id or "q"), 64) or "q"
    cleaned_other = _clip(str(other or "Other"), OTHER_MAX) or "Other"
    return {
        "id": qid,
        "ask": cleaned_ask,
        "choices": cleaned_choices,
        "other": cleaned_other,
    }


def demo_profile_question() -> dict[str, Any]:
    """Spike demo: deploy-profile card (3 choices + custom)."""
    payload = normalize_question(
        ask=DEMO_ASK,
        choices=DEMO_CHOICES,
        other=DEMO_OTHER,
        question_id=DEMO_QUESTION_ID,
    )
    assert payload is not None
    return payload


def question_event(question: dict[str, Any], *, agent_id: str = "") -> dict[str, Any]:
    event = {
        "type": EVENT_TYPE,
        "id": question["id"],
        "ask": question["ask"],
        "choices": list(question["choices"]),
        "other": question.get("other") or "Other",
    }
    if agent_id:
        event["agent_id"] = str(agent_id)
    return event


def normalize_answer(raw: Any) -> str:
    return _clip(str(raw or ""), ANSWER_MAX)


@dataclass
class AskUserSession:
    """Per-run hook installed by the API chat consumer when opt-in."""

    agent_id: str = ""
    channel: str = CHANNEL_API
    elicit_fn: ElicitQuestionFn | None = None
    outstanding: int = 0
    asked_ids: list[str] = field(default_factory=list)

    def enabled(self) -> bool:
        return uses_swarm_approval(self.channel) and self.elicit_fn is not None

    async def ask(self, ask: str, choices: Any, other: str = "Other") -> str:
        if not self.enabled():
            return ERROR_DISABLED if self.elicit_fn is None else ERROR_CHANNEL
        if self.outstanding >= MAX_OUTSTANDING_PER_TURN:
            return ERROR_CAP
        question = normalize_question(
            ask=ask,
            choices=choices,
            other=other,
            question_id=f"q{len(self.asked_ids) + 1}",
        )
        if question is None:
            return ERROR_INVALID
        self.outstanding += 1
        self.asked_ids.append(str(question["id"]))
        try:
            result = self.elicit_fn(question)
            if hasattr(result, "__await__"):
                answer = await result  # type: ignore[misc]
            else:
                answer = result
        except Exception:
            logger.debug("ask_user elicit failed", exc_info=True)
            return ERROR_INVALID
        finally:
            self.outstanding = max(0, self.outstanding - 1)
        cleaned = normalize_answer(answer)
        return cleaned or TIMEOUT_RESULT


_CURRENT_SESSION: ContextVar[AskUserSession | None] = ContextVar(
    "swarm_ask_user_session",
    default=None,
)


def current_ask_user_session() -> AskUserSession | None:
    return _CURRENT_SESSION.get()


def install_ask_user_session(session: AskUserSession | None):
    return _CURRENT_SESSION.set(session)


def reset_ask_user_session(token) -> None:
    _CURRENT_SESSION.reset(token)


async def ask_user(ask: str, choices: str = "", other: str = "Other") -> str:
    """Ask the human operator a multiple-choice question and wait for their answer.

    Use this when you must know the operator's pick before continuing (deploy
    target, which agent to configure, confirm a destructive plan). Do not use
    it for chit-chat. The last option is always a custom free-text field.

    Args:
        ask: Short question shown to the operator.
        choices: JSON array of strings, or a comma-separated list.
        other: Placeholder for the custom free-text last option.
    """
    session = current_ask_user_session()
    if session is None:
        return ERROR_DISABLED
    return await session.ask(ask, choices, other)


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


def as_function_tools() -> list[Any]:
    """openai-agents ``function_tool`` wrappers, or ``[]`` if the SDK is missing."""
    try:
        from agents import function_tool
    except Exception:
        logger.debug("agents SDK not available; ask_user as_function_tools() -> []")
        return []
    try:
        return [function_tool(ask_user, name_override=TOOL_NAME)]
    except TypeError:
        wrapped = function_tool(ask_user)
        try:
            wrapped.name = TOOL_NAME
        except Exception:
            pass
        return [wrapped]


def attach_ask_user_to_agent(agent: Any) -> list[str]:
    """Append ``ask_user`` onto one Agent-like object."""
    extras = as_function_tools()
    if not extras:
        extras = [ask_user]
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


def install_ask_user_on_blueprint(blueprint: Any) -> list[str]:
    """Wrap ``create_starting_agent`` and attach to existing agents."""
    original = getattr(blueprint, "create_starting_agent", None)
    if callable(original) and not getattr(blueprint, "_ask_user_wrapped", False):

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            agent = original(*args, **kwargs)
            attach_ask_user_to_agent(agent)
            return agent

        blueprint.create_starting_agent = wrapped
        blueprint._ask_user_wrapped = True

    attached: list[str] = []
    for agent in _iter_agents(blueprint):
        attached.extend(attach_ask_user_to_agent(agent))
    return attached


def install_ask_user_for_runtime(
    blueprint: Any,
    *,
    params: dict[str, Any] | None = None,
    channel: str = CHANNEL_API,
) -> list[str]:
    """Attach ``ask_user`` when the seat opted in. No-op otherwise."""
    if not elicit_questions_enabled(params, channel=channel):
        return []
    return install_ask_user_on_blueprint(blueprint)


__all__ = [
    "ANSWER_TYPE",
    "ASK_MAX",
    "DEMO_ASK",
    "DEMO_CHOICES",
    "DEMO_OTHER",
    "DEMO_QUESTION_ID",
    "ERROR_CAP",
    "ERROR_CHANNEL",
    "ERROR_DISABLED",
    "ERROR_INVALID",
    "EVENT_TYPE",
    "INTERRUPTED_RESULT",
    "MAX_OUTSTANDING_PER_TURN",
    "TIMEOUT_RESULT",
    "TIMEOUT_SEC",
    "TOOL_NAME",
    "AskUserSession",
    "ask_user",
    "attach_ask_user_to_agent",
    "coerce_enabled",
    "current_ask_user_session",
    "demo_profile_question",
    "elicit_questions_enabled",
    "install_ask_user_for_runtime",
    "install_ask_user_on_blueprint",
    "install_ask_user_session",
    "normalize_answer",
    "normalize_question",
    "question_event",
    "reset_ask_user_session",
]

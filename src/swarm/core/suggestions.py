"""REQ-85: ``suggestions`` role — short quick-select prompts after a turn.

A *consumer* agent with **Use suggestions** on invokes a ``suggestions``-role
specialist (openai-agents ``as_tool`` / handoff) and the chat UI renders the
returned strings as chips. Chips are chrome: they are never appended to the
transcript and never sent as extra LLM context (#407).

Fail-soft: a bad, empty, or failed list is an honest omission — no crash,
no toast dump.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from swarm.core.agent_roles import (
    ROLE_SUGGESTIONS,
    attach_role,
    find_role_agent,
    normalize_agent_role,
)
from swarm.core.async_utils import run_coro_sync
from swarm.core.support_journey import (
    is_support_consumer,
    support_kickstart,
)

logger = logging.getLogger(__name__)

SUGGESTIONS_ROLE = ROLE_SUGGESTIONS
MIN_SUGGESTIONS = 1
MAX_SUGGESTIONS = 5
# #532: the role presents a fixed trio of chips unless the caller narrows it.
SUGGESTIONS_COUNT = 3
MAX_CHIP_CHARS = 80

SUGGESTIONS_INSTRUCTIONS = (
    "You prepare short quick-select prompts for the operator. "
    "Return a JSON object with a single key 'suggestions' whose value is "
    "a list of exactly "
    f"{SUGGESTIONS_COUNT} concise strings the user might send next. "
    "No numbering, no quotes in the strings, no explanation."
)

KICKSTART_CANNED = (
    "What should we explore first?",
    "Show me how this agent is set up",
    "Give me a short status",
)

CONTINUE_CANNED = (
    "Can you expand on that?",
    "What are the main risks or trade-offs?",
    "What would a minimal next step look like?",
)

SuggestFn = Callable[[str, str], Any]


class SuggestionsSpecialist:
    """Role-stamped specialist used when the consumer has no roster seat.

    CLI / API / remote consumers still get chips when **Use suggestions** is on
    (Success-5). Team rosters with a ``suggestions`` member take precedence.
    """

    name = "suggestions"
    instructions = SUGGESTIONS_INSTRUCTIONS

    def __init__(self) -> None:
        attach_role(self, ROLE_SUGGESTIONS)


def parse_suggestions(raw: Any) -> list[str]:
    """Normalize a suggestions payload into 1–5 short unique strings.

    Accepts a list, a ``{"suggestions": [...]}`` dict, a JSON string, or
    newline-separated text. Anything unusable becomes ``[]``.
    """
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    elif isinstance(raw, dict):
        items = raw.get("suggestions")
        if items is None:
            items = raw.get("prompts") or raw.get("chips") or raw.get("options")
        if not isinstance(items, (list, tuple)):
            return []
        items = list(items)
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            items = [line.strip(" -*\t") for line in text.splitlines() if line.strip()]
        else:
            return parse_suggestions(parsed)
    else:
        return []

    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item is None:
            continue
        chip = str(item).strip()
        if not chip:
            continue
        chip = " ".join(chip.split())
        if len(chip) > MAX_CHIP_CHARS:
            chip = chip[: MAX_CHIP_CHARS - 1].rstrip() + "…"
        key = chip.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(chip)
        if len(out) >= MAX_SUGGESTIONS:
            break
    return out if len(out) >= MIN_SUGGESTIONS else []


def canned_kickstart(consumer_id: str | None = None) -> list[str]:
    """Generic kickstart, or Support journey chips for the first-run seat."""
    if is_support_consumer(consumer_id):
        return support_kickstart()
    return list(KICKSTART_CANNED)


def canned_continue(messages: list[dict[str, Any]] | None = None) -> list[str]:
    last_user = ""
    if messages:
        for row in reversed(messages):
            if isinstance(row, dict) and row.get("role") == "user":
                last_user = str(row.get("content") or "").strip()
                break
    if last_user:
        snippet = last_user[:48].rstrip()
        extra = f"Go deeper on: {snippet}" if snippet else ""
        chips = list(CONTINUE_CANNED)
        if extra:
            chips = [extra, *chips[:2]]
        return parse_suggestions(chips)
    return list(CONTINUE_CANNED)


def _stringify_output(result: Any) -> Any:
    if result is None:
        return ""
    final = getattr(result, "final_output", None)
    if final is not None:
        return final
    return result


def _invoke_suggestions(
    agent: Any,
    prompt: str,
    *,
    suggest_fn: SuggestFn | None = None,
) -> list[str]:
    if suggest_fn is not None:
        return parse_suggestions(suggest_fn(agent, prompt))
    suggest = getattr(agent, "suggest", None)
    if callable(suggest):
        return parse_suggestions(suggest(prompt))
    respond = getattr(agent, "respond", None)
    if callable(respond):
        return parse_suggestions(respond(prompt))
    as_tool = getattr(agent, "as_tool", None)
    if callable(as_tool):
        try:
            tool = as_tool(
                tool_name=getattr(agent, "name", None) or "suggestions",
                tool_description=(
                    f"Prepare exactly {SUGGESTIONS_COUNT} short quick-select prompts."
                ),
            )
            on_invoke = getattr(tool, "on_invoke_tool", None)
            if callable(on_invoke):
                result = on_invoke(None, prompt)
                if hasattr(result, "__await__"):
                    result = run_coro_sync(result)
                return parse_suggestions(result)
        except Exception as exc:
            logger.debug("suggestions as_tool invoke skipped: %s", exc)
    try:
        from agents import Runner

        async def _run() -> Any:
            result = await Runner.run(agent, prompt, max_turns=1)
            return _stringify_output(result)

        return parse_suggestions(run_coro_sync(_run()))
    except Exception as exc:
        logger.info("suggestions Runner unavailable (%s)", exc)
        return []


def _mode_prompt(
    mode: str,
    messages: list[dict[str, Any]] | None,
    consumer_id: str | None = None,
) -> str:
    if mode == "kickstart":
        if is_support_consumer(consumer_id):
            return (
                "The thread is empty on Support, the first-run onboarder. "
                "Suggest exactly "
                f"{SUGGESTIONS_COUNT} short first messages that start the "
                "open-swarm "
                "journey — create a team, add a remote, wire a CLI, or how "
                "CLI / API / remotes differ. No Settings maze. "
                "Return JSON {\"suggestions\": [...]}."
            )
        return (
            "The thread is empty. Suggest exactly "
            f"{SUGGESTIONS_COUNT} short first messages the operator "
            "might send to start usefully. Return JSON {\"suggestions\": [...]}."
        )
    last_user = ""
    last_assistant = ""
    if messages:
        for row in reversed(messages):
            if not isinstance(row, dict):
                continue
            role = row.get("role")
            content = str(row.get("content") or "").strip()
            if role == "assistant" and not last_assistant:
                last_assistant = content
            elif role == "user" and not last_user:
                last_user = content
            if last_user and last_assistant:
                break
    return (
        "Suggest exactly "
        f"{SUGGESTIONS_COUNT} short follow-up messages the operator might send "
        "next.\n\n"
        f"Last user message:\n{last_user or '(none)'}\n\n"
        f"Last assistant output:\n{last_assistant or '(none)'}\n\n"
        "Return JSON {\"suggestions\": [...]}."
    )


def _as_agent_list(agents: Any) -> list[Any]:
    if agents is None:
        return []
    if isinstance(agents, dict):
        return [item for item in agents.values() if item is not None]
    try:
        return [item for item in agents if item is not None]
    except TypeError:
        return [agents]


def live_agents_from_blueprint(blueprint: Any) -> list[Any]:
    """Pull a live roster off a blueprint instance (``_agents`` / ``_build_agents``)."""
    if blueprint is None:
        return []
    for attr in ("_agents", "agents"):
        live = getattr(blueprint, attr, None)
        if live:
            return _as_agent_list(live)
    build = getattr(blueprint, "_build_agents", None)
    if callable(build):
        try:
            return _as_agent_list(build())
        except Exception:
            logger.debug("suggestions roster build skipped", exc_info=True)
    meta = getattr(blueprint, "metadata", None)
    meta_role = normalize_agent_role(meta.get("role")) if isinstance(meta, dict) else ""
    start = getattr(blueprint, "create_starting_agent", None)
    if callable(start) and meta_role == ROLE_SUGGESTIONS:
        try:
            agent = start([])
            if agent is not None:
                attach_role(agent, ROLE_SUGGESTIONS)
                return [agent]
        except Exception:
            logger.debug("suggestions starting agent skipped", exc_info=True)
    if isinstance(meta, dict) and normalize_agent_role(meta.get("role")) == ROLE_SUGGESTIONS:
        return [SuggestionsSpecialist()]
    return []


def _specialist_from_catalog(catalog: Any, consumer_id: str | None) -> Any | None:
    if not isinstance(catalog, dict):
        return None
    wanted_name = ""
    consumer = (consumer_id or "").strip()
    if consumer and consumer in catalog:
        row = catalog[consumer]
        meta = row.get("metadata") if isinstance(row, dict) else {}
        if isinstance(meta, dict):
            wanted_name = str(meta.get("suggestions_agent") or "").strip()
            if normalize_agent_role(meta.get("role")) == ROLE_SUGGESTIONS:
                return _specialist_from_catalog_row(row)
            roster = meta.get("agents")
            named = find_role_agent(roster, ROLE_SUGGESTIONS)
            if named is not None:
                attach_role(named, ROLE_SUGGESTIONS)
                return named
    for key, row in catalog.items():
        if key in {"suggestion", "suggestions"} or key == wanted_name:
            agent = _specialist_from_catalog_row(row)
            if agent is not None:
                return agent
        meta = row.get("metadata") if isinstance(row, dict) else {}
        if isinstance(meta, dict) and normalize_agent_role(meta.get("role")) == ROLE_SUGGESTIONS:
            agent = _specialist_from_catalog_row(row)
            if agent is not None:
                return agent
    return None


def _specialist_from_catalog_row(row: Any) -> Any | None:
    if not isinstance(row, dict):
        return None
    cls = row.get("class_type")
    if cls is None:
        return None
    try:
        instance = cls(blueprint_id=str(row.get("id") or "suggestion"))
        live = live_agents_from_blueprint(instance)
        return live[0] if live else None
    except Exception:
        logger.debug("catalog suggestions specialist skipped", exc_info=True)
        return None


def resolve_suggestions_agents(
    consumer_id: str | None,
    *,
    blueprint: Any = None,
    catalog: Any = None,
    extra_agents: Any = None,
) -> list[Any]:
    """Roster that includes the suggestions-role agent for this consumer.

    Never returns ``None``. Call sites must pass this into ``run_suggestions``
    / ``suggestions_payload_for_turn`` — do not substitute ``agents=None``.
    """
    roster = _as_agent_list(extra_agents) + live_agents_from_blueprint(blueprint)
    if find_role_agent(roster, ROLE_SUGGESTIONS) is not None:
        return roster
    specialist = _specialist_from_catalog(catalog, consumer_id)
    if specialist is not None:
        roster.append(specialist)
        return roster
    roster.append(SuggestionsSpecialist())
    return roster


def load_continue_messages(
    user: Any,
    agent_id: str,
    conversation_id: str = "",
) -> list[dict[str, Any]]:
    """Transcript turns for continue chips. Empty list when none are readable."""
    try:
        from swarm.core.chat_store import load, user_key_for

        pk = getattr(user, "pk", None)
        if pk is None:
            pk = getattr(user, "id", None)
        if pk is None:
            return []
        record = load(
            user_key_for(user),
            agent_id,
            conversation_id=(conversation_id or "").strip(),
        )
        rows = (record or {}).get("messages") or []
        return [row for row in rows if isinstance(row, dict)]
    except Exception:
        logger.debug("continue messages omitted", exc_info=True)
        return []


def run_suggestions(
    *,
    mode: str = "kickstart",
    messages: list[dict[str, Any]] | None = None,
    agents: Any = None,
    suggest_fn: SuggestFn | None = None,
    consumer_id: str | None = None,
) -> list[str]:
    """Return chips for kickstart or continue. Empty list on any failure."""
    kind = "kickstart" if str(mode).strip().lower() != "continue" else "continue"
    try:
        if suggest_fn is not None:
            agent = find_role_agent(agents, ROLE_SUGGESTIONS)
            return _invoke_suggestions(
                agent,
                _mode_prompt(kind, messages, consumer_id),
                suggest_fn=suggest_fn,
            )
        if os.environ.get("SWARM_TEST_MODE"):
            return (
                canned_kickstart(consumer_id)
                if kind == "kickstart"
                else canned_continue(messages)
            )
        agent = find_role_agent(agents, ROLE_SUGGESTIONS)
        if agent is None:
            return []
        return _invoke_suggestions(agent, _mode_prompt(kind, messages, consumer_id))
    except Exception:
        logger.debug("suggestions run omitted", exc_info=True)
        return []


def suggestions_payload_for_turn(
    agent_id: str | None,
    messages: list[dict[str, Any]] | None = None,
    *,
    agents: Any = None,
    blueprint: Any = None,
    catalog: Any = None,
) -> dict[str, Any] | None:
    """WS/API payload after a finished turn, or ``None`` when chips should hide."""
    from swarm.core.agent_settings import is_use_suggestions

    if not is_use_suggestions(agent_id):
        return None
    has_assistant = any(
        isinstance(row, dict) and row.get("role") == "assistant"
        for row in (messages or [])
    )
    roster = agents
    if roster is None:
        roster = resolve_suggestions_agents(
            agent_id,
            blueprint=blueprint,
            catalog=catalog,
        )
    chips = run_suggestions(
        mode="continue" if has_assistant else "kickstart",
        messages=messages,
        agents=roster,
        consumer_id=agent_id,
    )
    if not chips:
        return None
    return {"type": "suggestions", "suggestions": chips}


def attach_suggestions_as_tool(coordinator: Any, suggestions: Any) -> Any:
    """Expose the suggestions specialist on the coordinator via ``as_tool``."""
    if coordinator is None or suggestions is None:
        return coordinator
    attach_role(suggestions, ROLE_SUGGESTIONS)
    as_tool = getattr(suggestions, "as_tool", None)
    if not callable(as_tool):
        return coordinator
    try:
        tool = as_tool(
            tool_name=getattr(suggestions, "name", None) or "suggestions",
            tool_description=(
                f"Prepare exactly {SUGGESTIONS_COUNT} short quick-select prompts "
                "for the operator."
            ),
        )
        tools = list(getattr(coordinator, "tools", None) or [])
        tools.append(tool)
        coordinator.tools = tools
    except Exception as exc:
        logger.debug("suggestions as_tool wiring skipped: %s", exc)
    return coordinator


def suggestions_from_team(agents: Any) -> Any | None:
    return find_role_agent(agents, ROLE_SUGGESTIONS)


def is_suggestions_role(role: Any) -> bool:
    return normalize_agent_role(role) == ROLE_SUGGESTIONS

"""#862 — live background instruction runner for GitHub-event routines.

Replaces the passive record-only default with a real dispatch path:

1. Resolve the target agent's blueprint via ``get_blueprint_instance``
   (the same resolution the chat surface uses — CLI/remote seats resolve
   their own way; API seats run the openai-agents graph).
2. Execute one full turn with ``stream=False`` and collect the text
   chunks (webhook runs have no socket to stream to).
3. Append the assistant reply to the webhook conversation so the run is
   reviewable in chat.
4. Record status/duration into the live-job log for the routine history.

Failures are deliberately loud: the exception propagates so
``fire_routine`` records ``status=error`` with the cause. A routine that
"ran" without an agent or silently swallowed the traceback would be a
lie in the history.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

GITHUB_WEBHOOK_USER_KEY = "github-webhook"


def get_blueprint_instance(agent_id: str, params: dict[str, Any] | None = None) -> Any:
    """Resolve an agent id to a blueprint instance (module-level test seam)."""
    from swarm.views.utils import get_blueprint_instance as _resolve

    return _resolve(agent_id, params=params or {})

DEFAULT_MAX_TURNS = 3


async def run_routine_agent_job(
    agent_id: str,
    instruction: str,
    *,
    conversation_id: str,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> str:
    """Execute one live agent turn for a routine firing and persist the reply.

    Args:
        agent_id: Agent (blueprint id) the routine is assigned to.
        instruction: The full prompt (event briefing + routine instruction).
        conversation_id: Stable webhook conversation id to append to.
        max_turns: Upper bound on automated turns for this conversation.

    Returns:
        The collected assistant reply text.

    Raises:
        Exception: Blueprint resolution or execution failures propagate so
            ``fire_routine`` records an error history row.
    """
    import swarm.core.routine_jobs as _jobs_mod

    # Imported through the source module so tests can monkeypatch the seam.
    get_blueprint_instance = _jobs_mod.get_blueprint_instance

    started = time.monotonic()
    status = "ok"
    detail = ""
    reply = ""
    try:
        blueprint = await get_blueprint_instance(agent_id, params={})
        if blueprint is None:
            raise RuntimeError(f"Agent '{agent_id}' could not be resolved to a blueprint instance.")
        messages = _conversation_messages(agent_id, conversation_id)
        messages.append({"role": "user", "content": instruction})
        # max_turns caps automated follow-on turns per conversation; this
        # entry point executes exactly one turn and returns.
        del max_turns
        reply = await _collect_turn(blueprint, messages)
        _persist_turn(agent_id, conversation_id, messages, reply)
        detail = f"{len(reply)} chars"
        return reply
    except Exception as exc:
        status = "error"
        detail = str(exc) or type(exc).__name__
        raise
    finally:
        duration_ms = int((time.monotonic() - started) * 1000)
        from swarm.core import routines

        routines.record_live_job_status(agent_id, status, duration_ms=duration_ms, detail=detail)


def _conversation_messages(agent_id: str, conversation_id: str) -> list[dict[str, Any]]:
    """Load the webhook conversation's model-turn list (empty when fresh)."""
    from swarm.core.chat_store import load as load_chat

    record = load_chat(
        GITHUB_WEBHOOK_USER_KEY,
        agent_id,
        conversation_id=conversation_id,
    )
    if not isinstance(record, dict):
        return []
    messages = record.get("messages")
    return [dict(m) for m in messages] if isinstance(messages, list) else []


async def _collect_turn(blueprint: Any, messages: list[dict[str, Any]]) -> str:
    """Run one blueprint turn (non-streaming) and join the text chunks."""
    parts: list[str] = []
    async_generator = blueprint.run(messages, stream=False, user_id=GITHUB_WEBHOOK_USER_KEY)
    async for chunk in async_generator:
        text = _chunk_text(chunk)
        if text:
            parts.append(text)
    return "".join(parts).strip()


def _chunk_text(chunk: Any) -> str:
    """Best-effort text extraction across chunk shapes (str/dict/objects)."""
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        for key in ("content", "text", "delta", "output_text"):
            value = chunk.get(key)
            if isinstance(value, str):
                return value
        return ""
    for attr in ("content", "text", "delta"):
        value = getattr(chunk, attr, None)
        if isinstance(value, str):
            return value
    return ""


def _persist_turn(
    agent_id: str,
    conversation_id: str,
    messages: list[dict[str, Any]],
    reply: str,
) -> None:
    """Append the assistant reply to the webhook conversation. Never raises."""
    from swarm.core.chat_store import save as save_chat

    turn = list(messages)
    if reply:
        turn.append({"role": "assistant", "content": reply})
    try:
        save_chat(
            GITHUB_WEBHOOK_USER_KEY,
            agent_id,
            turn,
            conversation_id=conversation_id,
            session_id=conversation_id,
        )
    except Exception:
        logger.exception("Could not persist routine job turn for %s (%s)", agent_id, conversation_id)

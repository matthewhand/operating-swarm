"""Process-local FIFO of inbound inter-agent messages keyed by target agent (#1255).

An API agent that is mid-turn cannot accept a new user turn without
interleaving. While a target agent's turn is live, the peer mailbox
(``agent_mailbox``) enqueues inbound messages here in FIFO order; the turn
runner drains the queue when the turn ends, so each queued message lands in
the target's transcript with explicit sender attribution.

Single-process by design — ``concurrency.py`` pins
``SWARM_UVICORN_WORKERS=1`` so inflight/queue accounting stays accurate.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: Cap per target so a runaway broadcaster cannot exhaust memory.
MAX_PENDING_PER_AGENT = 200

_lock = threading.Lock()
_live_turns: dict[str, int] = {}
_pending: dict[str, deque[QueuedMessage]] = {}
_current_agent: ContextVar[str | None] = ContextVar(
    "mailbox_current_agent", default=None
)


@dataclass
class QueuedMessage:
    """One inbound message held until the target's live turn finishes."""

    sender_id: str
    content: str
    user_key: str = ""
    chat_base_dir: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "content": self.content,
            "user_key": self.user_key,
            "chat_base_dir": self.chat_base_dir,
            "meta": dict(self.meta),
        }


def _norm(agent_id: Any) -> str:
    return str(agent_id or "").strip()


def is_agent_busy(agent_id: Any) -> bool:
    """True while at least one live turn is registered for ``agent_id``."""
    ident = _norm(agent_id)
    if not ident:
        return False
    with _lock:
        return _live_turns.get(ident, 0) > 0


def begin_agent_turn(agent_id: Any) -> bool:
    """Mark a live turn. Returns True when the agent was idle before."""
    ident = _norm(agent_id)
    if not ident:
        return False
    with _lock:
        was_idle = _live_turns.get(ident, 0) == 0
        _live_turns[ident] = _live_turns.get(ident, 0) + 1
    _current_agent.set(ident)
    return was_idle


def end_agent_turn(agent_id: Any) -> bool:
    """Release one live turn. Returns True when the agent is now idle."""
    ident = _norm(agent_id)
    if not ident:
        return False
    with _lock:
        remaining = _live_turns.get(ident, 0) - 1
        if remaining > 0:
            _live_turns[ident] = remaining
            return False
        _live_turns.pop(ident, None)
    if _current_agent.get() == ident:
        _current_agent.set(None)
    return True


def current_agent() -> str | None:
    """The agent whose turn is running on this task, if any."""
    return _current_agent.get()


@contextmanager
def agent_turn(agent_id: Any) -> Iterator[None]:
    """Scope a live turn; balances ``begin_agent_turn`` / ``end_agent_turn``."""
    begin_agent_turn(agent_id)
    try:
        yield
    finally:
        end_agent_turn(agent_id)


def enqueue(agent_id: Any, message: QueuedMessage) -> int:
    """Append one message to ``agent_id``'s FIFO. Returns new depth."""
    ident = _norm(agent_id)
    if not ident:
        return 0
    with _lock:
        bucket = _pending.setdefault(ident, deque())
        if len(bucket) >= MAX_PENDING_PER_AGENT:
            dropped = bucket.popleft()
            logger.warning(
                "agent turn queue full for %s; dropped oldest from %s",
                ident,
                dropped.sender_id,
            )
        bucket.append(message)
        return len(bucket)


def pending_count(agent_id: Any) -> int:
    ident = _norm(agent_id)
    if not ident:
        return 0
    with _lock:
        return len(_pending.get(ident) or ())


def pending_messages(agent_id: Any) -> list[QueuedMessage]:
    """Snapshot of queued messages (FIFO), without draining."""
    ident = _norm(agent_id)
    if not ident:
        return []
    with _lock:
        return list(_pending.get(ident) or ())


def drain(agent_id: Any) -> list[QueuedMessage]:
    """Pop and return all queued messages for ``agent_id`` in FIFO order."""
    ident = _norm(agent_id)
    if not ident:
        return []
    with _lock:
        bucket = _pending.pop(ident, None)
        return list(bucket) if bucket else []


def reset_agent_turn_queue() -> None:
    """Drop all live turns and pending messages (tests)."""
    with _lock:
        _live_turns.clear()
        _pending.clear()
    _current_agent.set(None)


def forget_agent(agent_id: Any) -> None:
    """Drop live-turn + pending state for one agent (tests / teardown)."""
    ident = _norm(agent_id)
    if not ident:
        return
    with _lock:
        _live_turns.pop(ident, None)
        _pending.pop(ident, None)


__all__ = [
    "MAX_PENDING_PER_AGENT",
    "QueuedMessage",
    "agent_turn",
    "begin_agent_turn",
    "current_agent",
    "drain",
    "end_agent_turn",
    "enqueue",
    "forget_agent",
    "is_agent_busy",
    "pending_count",
    "pending_messages",
    "reset_agent_turn_queue",
]

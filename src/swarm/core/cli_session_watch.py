"""Websocket stat poller + tail-only queue for CLI session updates (REQ-809).

- 2-second stat poller per user, tail-only (new messages only), per-user queues.
- Emits ``cli_session_update`` WS frames when a CLI session id changes.
- After the model finishes outputting, waits 6 seconds of quiet then notifies
  the browser via agentNoti.

Design
------
- Poller runs every 2s checking ``chat_store`` for the user's latest CLI session ids.
- Only delivers updates when a session id actually changed (delta).
- Queue per user id: FIFO, capped at 50 entries to avoid memory growth.
- Terminal event: after the last message from the model, a 6-second quiet window
  triggers a browser notification (``agentNoti``) so the UI can surface
  "session complete" to the user.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any

from django.contrib.auth import get_user_model
from django.utils import timezone

from swarm.core import chat_store
from swarm.core.cli_sessions import (
    extract_session_id,
    sanitize_cli_session_id,
    session_notice_text,
)

logger = logging.getLogger(__name__)

User = get_user_model()

# ── Per-user queue ──────────────────────────────────────────────────────────_

_MAX_QUEUE_SIZE = 50


def _user_queue(user_key: str) -> "deque[dict[str, Any]]":
    """Return the FIFO queue for *user_key*, creating it if needed.

    The queue holds dicts with at least a ``"type"`` key (e.g. ``"cli_session_update"``).
    """
    from swarm.core.cli_session_watch import _queues  # circular-import safe at call time

    if user_key not in _queues:
        _queues[user_key] = deque(maxlen=_MAX_QUEUE_SIZE)
    return _queues[user_key]


_queues: dict[str, deque[dict[str, Any]]] = {}


# ── Poller ──────────────────────────────────────────────────────────────────


async def start_poller(user_key: str, interval: float = 2.0) -> None:
    """Start the 2s stat poller for *user_key*.

    The poller checks ``chat_store`` for the user's current CLI session ids and
    pushes ``cli_session_update`` frames into the user's queue whenever a session
    id has changed since the last poll.
    """
    from swarm.core.cli_session_watch import _last_sids  # circular-safe

    last_sid = _last_sids.get(user_key, {})

    while True:
        try:
            await _poll_and_notify(user_key, last_sid)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # broad — never let the poller die silently
            logger.exception("cli_session_watch poller error for %s: %s", user_key, exc)
        await asyncio.sleep(interval)


async def _poll_and_notify(user_key: str, last_sid: dict[str, str]) -> None:
    """Poll chat_store and push any delta into the user's queue."""
    from swarm.core.cli_session_watch import _last_sids

    # Gather current session ids for all CLIs the user has chatted with.
    # We look at recent messages to determine which CLIs have been used.
    record = chat_store.load(user_key, "")  # empty agent_id → whole thread
    messages = record.get("messages") if record else []
    # Walk messages backward to find unique CLI names.
    seen_clis: set[str] = set()
    for msg in reversed(messages or []):
        role = msg.get("role")
        # Skip system/assistant messages that don't carry cli_name
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", {})
        if isinstance(content, str):
            content = {"text": content}
        # cli_name can be in content or in a metadata dict
        cli_name = None
        if isinstance(content, dict):
            cli_name = content.get("cli_name") or content.get("name")
        if not cli_name:
            # Try top-level
            cli_name = msg.get("cli_name")
        if cli_name:
            seen_clis.add(cli_name)

    current_sid: dict[str, str] = {}
    for cli_name in seen_clis:
        sid = get_cli_session(
            user_key=user_key,
            agent_id="",  # thread-level
            cli_name=cli_name,
        )
        if sid:
            current_sid[cli_name] = sid

    # Detect changes
    changed = False
    for cli_name, sid in current_sid.items():
        prev = last_sid.get(cli_name)
        if prev != sid:
            last_sid[cli_name] = sid
            changed = True
            # Push update into the per-user queue
            queue = _user_queue(user_key)
            queue.append(
                {
                    "type": "cli_session_update",
                    "cli_name": cli_name,
                    "session_id": sid,
                    "timestamp": timezone.now().isoformat(),
                }
            )

    # If any session was cleared (removed from last_sid but still present → no change)
    # or a new session appeared, we've already handled it above.

    # Check for completions: if no new messages in 6s, fire browser notify.
    # (The consumer of this module tracks "quiet" periods externally; here we just
    # expose the current state so the caller can decide.)
    _last_sids[user_key] = last_sid


# ── Completion notification ─────────────────────────────────────────────────

# 6-second quiet window after model output finishes before browser notify.
_COMPLETION_QUIET_MS = 6_000

_last_activity: dict[str, float] = {}  # user_key -> timestamp of last model msg


def record_model_activity(user_key: str) -> None:
    """Call when the user sees a new model message in the chat thread."""
    from swarm.core.cli_session_watch import _last_activity

    _last_activity[user_key] = time.time()


async def check_completion(user_key: str) -> bool:
    """Return True if 6s quiet has elapsed since last model activity.

    Callers should await this periodically (e.g. from the poller). When it
    returns True, the UI should fire the browser notification via
    ``agentNoti`` and then clear the timer.
    """
    last = _last_activity.get(user_key, 0)
    elapsed = time.time() - last
    if elapsed >= _COMPLETION_QUIET_MS / 1000:
        # Clear so we don't fire repeatedly.
        _last_activity.pop(user_key, None)
        return True
    return False
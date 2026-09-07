"""In-memory registry of swarm-spawned CLI chat subprocesses (REQ-114).

``CliAdapter.stream_run`` registers the child after ``start_new_session=True``
so a rail **Terminate** can kill that process *group* (SIGTERM, then SIGKILL)
without deleting the agent, wiping the session id, or clearing the transcript.

Only pids/pgids this process registered are signalled — never pid/pgid <= 1
and never an unrelated host process.
"""

from __future__ import annotations

import contextvars
import logging
import os
import signal
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from swarm.core.cli_adapter import TERM_GRACE

logger = logging.getLogger(__name__)

# Bound for the duration of a CLI blueprint turn so nested adapter.run /
# consensus panelists register under the same rail agent.
_current_owner: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "cli_run_owner", default=None
)

_lock = threading.Lock()
_runs: dict[str, CliRun] = {}


@dataclass
class CliRun:
    """One tracked CLI subprocess group."""

    token: str
    user_key: str
    agent_id: str
    conversation_id: str
    pid: int
    pgid: int
    started_at: float = field(default_factory=time.monotonic)
    terminated: bool = False


def reset_cli_run_registry() -> None:
    """Drop all tracked runs (tests). Does not signal processes."""
    with _lock:
        _runs.clear()


def run_owner_from_params(params: dict[str, Any] | None) -> dict[str, str]:
    """Build a registry owner from chat/blueprint request params."""
    raw = params if isinstance(params, dict) else {}
    user_key = str(raw.get("user_key") or "u0").strip() or "u0"
    agent_id = str(raw.get("agent_id") or raw.get("agent") or "cli_agent").strip() or "cli_agent"
    conversation_id = str(raw.get("conversation_id") or "").strip()
    return {
        "user_key": user_key,
        "agent_id": agent_id,
        "conversation_id": conversation_id,
    }


def bind_run_owner(owner: dict[str, str] | None) -> contextvars.Token:
    """Bind owner for nested ``stream_run`` calls on this task."""
    return _current_owner.set(owner)


def reset_run_owner(token: contextvars.Token) -> None:
    _current_owner.reset(token)


def current_run_owner() -> dict[str, str] | None:
    return _current_owner.get()


def register_cli_run(
    *,
    user_key: str,
    agent_id: str,
    conversation_id: str = "",
    pid: int,
    pgid: int | None = None,
) -> str | None:
    """Track a swarm-spawned CLI child. Returns a token, or None if unsafe."""
    if not pid or pid <= 1:
        return None
    try:
        resolved = os.getpgid(pid) if pgid is None else int(pgid)
    except (ProcessLookupError, OSError, TypeError, ValueError):
        return None
    if resolved <= 1:
        return None
    token = uuid.uuid4().hex
    run = CliRun(
        token=token,
        user_key=str(user_key or "u0"),
        agent_id=str(agent_id or "cli_agent"),
        conversation_id=str(conversation_id or ""),
        pid=int(pid),
        pgid=resolved,
    )
    with _lock:
        _runs[token] = run
    return token


def unregister_cli_run(token: str | None) -> bool:
    """Remove a tracked run. Returns True if it had been marked user-terminated."""
    if not token:
        return False
    with _lock:
        run = _runs.pop(token, None)
    return bool(run and run.terminated)


def was_user_terminated(token: str | None) -> bool:
    if not token:
        return False
    with _lock:
        run = _runs.get(token)
        return bool(run and run.terminated)


def _process_alive(pid: int) -> bool:
    if not pid or pid <= 1:
        return False
    # Reap our own zombies so kill(pid, 0) is not a false positive.
    try:
        waited, _status = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            return False
    except ChildProcessError:
        pass
    except OSError:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _pgid_still_ours(run: CliRun) -> bool:
    try:
        return os.getpgid(run.pid) == run.pgid
    except (ProcessLookupError, OSError):
        return False


def _matches(
    run: CliRun,
    *,
    user_key: str,
    agent_id: str,
    conversation_id: str | None,
) -> bool:
    if run.user_key != user_key or run.agent_id != agent_id:
        return False
    if conversation_id:
        return run.conversation_id == conversation_id
    return True


def list_cli_runs(
    user_key: str,
    agent_id: str,
    *,
    conversation_id: str | None = None,
) -> list[CliRun]:
    """Alive registered runs for this user/agent (optional conversation)."""
    with _lock:
        candidates = [
            run
            for run in _runs.values()
            if _matches(run, user_key=user_key, agent_id=agent_id, conversation_id=conversation_id)
        ]
    return [run for run in candidates if _process_alive(run.pid) and _pgid_still_ours(run)]


def is_cli_run_running(
    user_key: str,
    agent_id: str,
    *,
    conversation_id: str | None = None,
) -> bool:
    return bool(list_cli_runs(user_key, agent_id, conversation_id=conversation_id))


def terminate_process_group(pid: int, pgid: int) -> bool:
    """SIGTERM then SIGKILL a registered process group. Never signals <= 1.

    Escalation: ``os.killpg(pgid, SIGTERM)``, wait up to ``TERM_GRACE`` (5s)
    for the leader to exit, then ``SIGKILL`` if it is still alive.
    """
    if not pid or pid <= 1 or not pgid or pgid <= 1:
        return False
    try:
        if os.getpgid(pid) != pgid:
            return False
    except (ProcessLookupError, OSError):
        return False
    sent = False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
            sent = True
        except (ProcessLookupError, OSError):
            return sent
        deadline = time.monotonic() + TERM_GRACE
        while time.monotonic() < deadline:
            if not _process_alive(pid):
                return True
            time.sleep(0.05)
    return sent


def terminate_cli_runs(
    user_key: str,
    agent_id: str,
    *,
    conversation_id: str | None = None,
) -> str:
    """Kill registered CLI group(s). Returns ``terminated`` or ``not_running``."""
    runs = list_cli_runs(user_key, agent_id, conversation_id=conversation_id)
    if not runs:
        return "not_running"
    killed = False
    for run in runs:
        with _lock:
            tracked = _runs.get(run.token)
            if tracked is not None:
                tracked.terminated = True
        if terminate_process_group(run.pid, run.pgid):
            killed = True
    return "terminated" if killed else "not_running"

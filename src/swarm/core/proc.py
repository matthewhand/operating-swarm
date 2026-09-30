"""Spawn and kill-tree for CLI children (#1438).

One module owns process-group semantics so call sites never touch POSIX-only
``os.getpgid`` / ``os.killpg`` / ``os.setsid``:

* POSIX — ``start_new_session=True`` (setsid) at spawn, ``os.killpg`` at kill
  (SIGTERM, then SIGKILL).
* Windows — ``CREATE_NEW_PROCESS_GROUP`` at spawn, ``taskkill /T /F`` at kill
  (the pid and every child it spawned).
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from typing import Any

# Win32 CREATE_NEW_PROCESS_GROUP. The stdlib exposes this only on Windows;
# keep the numeric value so tests can assert it on any host.
CREATE_NEW_PROCESS_GROUP = 0x00000200

# Force-kill *pid* and every process it spawned. Order matches `taskkill /T /F`.
TASKKILL_TREE = ("taskkill", "/T", "/F", "/PID")
# A stuck taskkill must not wedge rail Terminate. The process may still be dying.
TASKKILL_TIMEOUT_S = 10

# Already-exited races and taskkill/signal failures. Missing POSIX attributes
# are not swallowed — Windows takes the taskkill branch instead.
PROCESS_GROUP_ERRORS = (ProcessLookupError, OSError)


def on_windows() -> bool:
    """True on native Windows. Tests monkeypatch ``sys.platform``."""
    return sys.platform == "win32"


def spawn_kwargs() -> dict[str, Any]:
    """kwargs for ``asyncio.create_subprocess_exec`` / ``subprocess.Popen``.

    POSIX detaches a new session so a later process-group signal reaches the
    child and its descendants. Windows rejects ``start_new_session`` (CPython
    raises ``ValueError``). A new process group keeps the parent's console
    Ctrl+C off this child. ``taskkill /T`` walks the parent-pid tree; that
    walk, not the process group, is the Windows tree boundary.
    """
    if on_windows():
        flag = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", CREATE_NEW_PROCESS_GROUP))
        return {"creationflags": flag}
    return {"start_new_session": True}


def group_id(pid: int) -> int:
    """Process-group id for *pid*.

    POSIX: the session set up at spawn. Windows has no POSIX process groups;
    the spawn pid is the root ``taskkill /T`` walks.
    """
    pid_i = int(pid)
    if on_windows():
        return pid_i
    return int(os.getpgid(pid_i))


def kill_tree(pid: int, sig: int | None = None) -> None:
    """Kill *pid* and its descendants.

    POSIX signals the process group (``os.killpg``) with *sig* (default
    SIGTERM). Windows ignores *sig* and runs ``taskkill /T /F /PID``.
    Refuses pid <= 1.
    """
    pid_i = int(pid)
    if pid_i <= 1:
        raise ProcessLookupError(f"refusing to signal pid {pid_i}")
    if on_windows():
        _taskkill_tree(pid_i)
        return
    sig_i = int(signal.SIGTERM if sig is None else sig)
    pgid = int(os.getpgid(pid_i))
    if pgid <= 1:
        raise ProcessLookupError(f"refusing to signal pgid {pgid}")
    os.killpg(pgid, sig_i)


def _taskkill_tree(pid: int) -> None:
    try:
        completed = subprocess.run(
            [*TASKKILL_TREE, str(pid)],
            check=False,
            capture_output=True,
            timeout=TASKKILL_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        raise OSError(f"taskkill timed out for pid {pid}") from exc
    # 0 = killed. 128 = already gone. Anything else is a real failure.
    code = int(getattr(completed, "returncode", 1))
    if code in (0, 128):
        return
    err = getattr(completed, "stderr", b"") or b""
    if isinstance(err, bytes):
        err = err.decode("utf-8", "replace")
    raise OSError(code, str(err).strip() or f"taskkill failed for pid {pid}")


def termination_signals() -> tuple[int, ...]:
    """Signals for a POSIX escalate. Windows is a single taskkill, so one entry.

    SIGKILL is omitted when the host does not define it, or when it aliases
    SIGTERM.
    """
    term = int(signal.SIGTERM)
    if on_windows():
        return (term,)
    kill = getattr(signal, "SIGKILL", None)
    if kill is None or int(kill) == term:
        return (term,)
    return (term, int(kill))


async def terminate_subprocess(proc: Any, *, grace: float) -> None:
    """Stop a CLI child and its tree.

    POSIX: process-group SIGTERM, wait up to *grace*, then SIGKILL.
    Windows: ``taskkill /T /F`` once, then wait up to *grace* for the pipe
    to close.
    """
    if getattr(proc, "returncode", None) is not None:
        return
    pid = int(getattr(proc, "pid", 0) or 0)
    if pid <= 1:
        return
    try:
        pgid = group_id(pid)
    except PROCESS_GROUP_ERRORS:
        return
    if pgid <= 1:
        return
    for sig in termination_signals():
        try:
            kill_tree(pid, sig)
        except PROCESS_GROUP_ERRORS:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=grace)
            return
        except TimeoutError:
            continue

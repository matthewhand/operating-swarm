"""#720 — process-wide registry of live sandbox backends.

The sandbox-display endpoint runs in a different request (and therefore a
different ``SandboxManager`` instance) than the agent turn that created a
Daytona microVM. This registry lets the display resolve the *already-live*
sandbox without re-creating one — a GET must never touch the cloud API or
spin up a VM.

Only backends that already hold a live remote sandbox are registered;
``unregister`` is called from ``cleanup()`` so a stopped VM disappears from
the display immediately. All access is lock-guarded so concurrent agent
turns and display polls cannot race.
"""

from __future__ import annotations

import threading
from typing import Any

DEFAULT_SANDBOX_KEY = "daytona"

_LOCK = threading.Lock()
_LIVE: dict[str, Any] = {}


def register_live_sandbox(backend: Any, key: str = DEFAULT_SANDBOX_KEY) -> None:
    """Record *backend* as the live sandbox for *key* (no-op when None)."""
    if backend is None:
        return
    with _LOCK:
        _LIVE[key or DEFAULT_SANDBOX_KEY] = backend


def get_live_sandbox(key: str = DEFAULT_SANDBOX_KEY) -> Any | None:
    """Return the live backend for *key*, or None."""
    with _LOCK:
        return _LIVE.get(key or DEFAULT_SANDBOX_KEY)


def unregister_live_sandbox(key: str = DEFAULT_SANDBOX_KEY) -> None:
    """Drop the live backend for *key* (idempotent)."""
    with _LOCK:
        _LIVE.pop(key or DEFAULT_SANDBOX_KEY, None)


def live_sandbox_keys() -> list[str]:
    """Sorted snapshot of registered keys."""
    with _LOCK:
        return sorted(_LIVE)


def clear_live_sandboxes() -> None:
    """Drop every registration (test isolation / provider switch)."""
    with _LOCK:
        _LIVE.clear()

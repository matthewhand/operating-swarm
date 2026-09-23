"""#818 — the auxiliary-task registry.

Background/auxiliary LLM work (context compaction, advisor notes, session
naming…) used to run invisibly: a runaway loop burned tokens with no surface
to see or stop it. The registry is the single source of truth the WS layer
broadcasts from: register on start, finish on completion, cancel from the
navbar's activity dialog.

Pure and synchronous — the WS layer owns all I/O. Clock is injectable so
durations are deterministic in tests.
"""

from __future__ import annotations

import time
from typing import Any, Callable


class AuxiliaryTaskRegistry:
    """Active/finished auxiliary tasks for one consumer connection."""

    DECAY_SECONDS = 4.0

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.monotonic
        self._tasks: dict[str, dict[str, Any]] = {}
        self._seq = 0

    def register(self, label: str, model: str | None = None, task_id: str | None = None, *, cancellable: Any = None) -> str:
        """Start tracking a task. `cancellable` is any object with .cancel()
        (e.g. an asyncio.Task); None marks the task as not interruptible."""
        self._seq += 1
        tid = task_id or f"aux-{self._seq}"
        self._tasks[tid] = {
            "task_id": tid,
            "label": label,
            "model": model,
            "started_at": self._clock(),
            "state": "running",
            "cancellable": cancellable,
        }
        return tid

    def finish(self, task_id: str, status: str = "done") -> dict[str, Any] | None:
        """Mark a task complete; returns the finished payload (for the WS
        frame) or None when the id is unknown. Finished tasks linger for the
        decay window so the user can see what just ran."""
        task = self._tasks.get(task_id)
        if not task or task["state"] != "running":
            return None
        task["state"] = status
        task["ended_at"] = self._clock()
        task["duration_s"] = round(task["ended_at"] - task["started_at"], 2)
        return self.payload(task)

    def cancel(self, task_id: str) -> bool:
        """Abort one task. Returns False when the id is unknown or the task
        cannot be interrupted (inline awaits have no cancellable handle)."""
        task = self._tasks.get(task_id)
        if not task or task["state"] != "running":
            return False
        handle = task.get("cancellable")
        cancelled = False
        if handle is not None and hasattr(handle, "cancel"):
            try:
                handle.cancel()
                cancelled = True
            except Exception:
                cancelled = False
        if cancelled:
            self.finish(task_id, status="cancelled")
        return cancelled

    def _sweep(self) -> None:
        now = self._clock()
        for tid in list(self._tasks):
            task = self._tasks[tid]
            if task["state"] != "running":
                if now - task["ended_at"] > self.DECAY_SECONDS:
                    del self._tasks[tid]

    def active(self) -> list[dict[str, Any]]:
        self._sweep()
        return [self.payload(t) for t in self._tasks.values() if t["state"] == "running"]

    def snapshot(self) -> list[dict[str, Any]]:
        """Active first (longest-running first), then finished by recency."""
        self._sweep()
        rows = [self.payload(t) for t in self._tasks.values()]
        rows.sort(key=lambda t: (t["state"] != "running", -t["started_at"]))
        return rows

    def payload(self, task: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": task["task_id"],
            "label": task["label"],
            "model": task.get("model"),
            "state": task["state"],
            "duration_s": task.get("duration_s")
            if task["state"] != "running"
            else round(self._clock() - task["started_at"], 1),
            "started_at": task["started_at"],
        }

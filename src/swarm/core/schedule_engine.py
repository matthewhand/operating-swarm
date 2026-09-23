"""In-process scheduler loop for Routines + Test schedules (#222).

Lives with the Django process. A daemon thread ticks due interval / cron /
one-shot rows. Not a distributed scheduler — one process, one loop. Tests
call ``tick()`` directly and never start the thread.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

ENV_DISABLE = "SWARM_DISABLE_SCHEDULE_ENGINE"
DEFAULT_INTERVAL_SECONDS = 30

_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None
_interval_seconds = DEFAULT_INTERVAL_SECONDS


def tick(now: datetime | None = None) -> dict[str, Any]:
    """Fire due routines and test schedules once. Safe to call from tests."""
    routines_fired: list[Any] = []
    schedules_fired: list[Any] = []
    try:
        from swarm.core.routines import tick_due_routines

        routines_fired = tick_due_routines(now)
    except Exception:
        logger.exception("Routine schedule tick failed")
    try:
        from swarm.core.test_schedules import tick_due_schedules

        schedules_fired = tick_due_schedules(now)
    except Exception:
        logger.exception("Test-schedule tick failed")
    return {
        "routines": len(routines_fired),
        "schedules": len(schedules_fired),
        "routine_rows": routines_fired,
        "schedule_rows": schedules_fired,
    }


def _loop() -> None:
    logger.info(
        "Schedule engine started (interval=%ss, single-process; no distributed claims).",
        _interval_seconds,
    )
    while not _stop.wait(_interval_seconds):
        try:
            tick()
        except Exception:
            logger.exception("Schedule engine tick crashed")
    logger.info("Schedule engine stopped.")


def start_loop(interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> bool:
    """Start the daemon ticker if this process is serving. Idempotent."""
    global _thread, _interval_seconds
    if os.environ.get(ENV_DISABLE) or os.environ.get("SWARM_TEST_MODE"):
        return False
    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _interval_seconds = max(1, int(interval_seconds))
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="swarm-schedule-engine", daemon=True)
        _thread.start()
        return True


def stop_loop() -> None:
    global _thread
    _stop.set()
    with _lock:
        thread = _thread
        _thread = None
    if thread is not None:
        thread.join(timeout=1.0)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()

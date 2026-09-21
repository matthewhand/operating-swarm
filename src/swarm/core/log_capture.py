"""#903 — in-memory log capture for the diagnostics surface.

A thread-safe ring buffer of recent ``swarm.*`` log lines. Volatile by
design: no file I/O, no shipping, no persistence. The diagnostics payload
(#904) composes :meth:`LogCapture.recent` output and owns masking; this
module records formatted messages as-is.

Never raises: a failing formatter must not take down the app (the failure
is reported to stderr and the record is dropped).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import deque
from typing import Any

#: Default ring-buffer depth; overridable via ``SWARM_DIAG_LOG_LINES``.
DEFAULT_LOG_LINES = 200

_LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

#: Loggers the capture attaches to (the swarm namespace plus hot sub-loggers).
_SWARM_LOGGER_NAMES = ("swarm", "swarm.auth", "swarm.views", "swarm.extensions")


def _buffer_capacity() -> int:
    raw = os.environ.get("SWARM_DIAG_LOG_LINES", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LOG_LINES
    return value if value > 0 else DEFAULT_LOG_LINES


class LogCapture(logging.Handler):
    """Ring-buffer handler collecting structured recent log records.

    ``install()`` registers a capture on the swarm loggers and the read API
    (``recent()`` / ``level_counts()``) works class-wide over every installed
    capture — the diagnostics payload composes it without holding handles.
    """

    _installed: list["LogCapture"] = []

    def __init__(self, capacity: int | None = None) -> None:
        super().__init__(level=logging.DEBUG)
        self._capacity = capacity or _buffer_capacity()
        self._lock = threading.Lock()
        self._buffer: deque[dict[str, Any]] = deque(maxlen=self._capacity)

    # -- logging.Handler ---------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover - depends on broken formatters
            try:
                sys.stderr.write(
                    f"[log_capture] failed to format record from {record.name!r}\n"
                )
            except Exception:
                pass
            return
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        with self._lock:
            self._buffer.append(entry)

    # -- public surface ----------------------------------------------------

    @classmethod
    def recent(
        cls,
        level: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Most recent lines across installed captures, chronological.

        Optionally filtered by level name; ``limit`` keeps the tail.
        """
        rows: list[dict[str, Any]] = []
        for capture in list(cls._installed):
            with capture._lock:
                rows.extend(capture._buffer)
        if level:
            wanted = level.upper()
            rows = [row for row in rows if row["level"] == wanted]
        if limit is not None and limit >= 0:
            rows = rows[-limit:] if limit else []
        return rows

    @classmethod
    def level_counts(cls) -> dict[str, int]:
        """Per-level counts over the buffered window (unknown levels → OTHER)."""
        counts: dict[str, int] = {name: 0 for name in _LEVEL_NAMES}
        counts["OTHER"] = 0
        for capture in list(cls._installed):
            with capture._lock:
                rows = list(capture._buffer)
            for row in rows:
                level = row["level"]
                counts[level if level in counts else "OTHER"] += 1
        return counts

    @classmethod
    def install(cls) -> "LogCapture":
        """Attach a capture to the swarm loggers; returns the handle.

        The returned object doubles as the uninstall handle (``h.uninstall()``).
        """
        handle = cls()
        for name in _SWARM_LOGGER_NAMES:
            logging.getLogger(name).addHandler(handle)
        cls._installed.append(handle)
        return handle

    def uninstall(self) -> None:
        """Remove this capture from every logger and the class registry."""
        for name in _SWARM_LOGGER_NAMES:
            logger = logging.getLogger(name)
            try:
                logger.removeHandler(self)
            except Exception:  # pragma: no cover - removal cannot realistically fail
                pass
        type(self)._installed = [
            c for c in type(self)._installed if c is not self
        ]

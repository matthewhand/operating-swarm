"""Logging integration for request telemetry — one line per request, one
report per rate-limit bucket.

``swarm.core.request_telemetry`` owns the *state* (what happened); this module
owns what the journal sees. Two jobs:

1. ``ThrottleLogDedupFilter`` sits on the ``swarm.throttle`` logger. The 429
   handler logs its full forensic report on **every** rejected request, so a
   burst of N rejections produced N identical multi-line reports — the logger,
   not the client, was the flood. The filter counts each rejection into its
   ``(client, endpoint)`` window bucket and lets exactly the first one through;
   the rest are dropped, and the count is published once per bucket per window
   as a ``[RATE_LIMIT_WINDOW]`` line by the telemetry module.

   It is a ``logging.Filter`` rather than a change to the handler because the
   handler builds ``logger.warning(...)`` with the report already formatted by
   the time a record exists — the only lever that dedups without the handler
   knowing. The extraction of (client, method, path, wait) from the record is
   deliberately *tolerant*: anything it cannot recognise is passed through
   unchanged. Losing a log line would be worse than logging one twice, so every
   unrecognised shape fails open.

2. ``install()`` wires the filter up once, from ``SwarmConfig.ready()``, and
   registers an ``atexit`` flush so a bucket's final count is not lost when the
   traffic simply stops rather than rolling over.

The filter also *sanitises* the record on its way through: the handler
interpolates ``request.path`` raw, and a path can carry a token. Normalising
it here closes that hole without touching the handler.
"""

from __future__ import annotations

import atexit
import logging
import threading
from typing import Any, Tuple

from swarm.core.request_telemetry import (
    RequestTelemetry,
    default_telemetry,
    normalize_path,
    sanitize_field,
)

THROTTLE_LOGGER_NAME = "swarm.throttle"

#: The one report prefix the 429 handler emits. Anything else is not ours.
REPORT_PREFIX = "[RATE_LIMIT_EXCEEDED]"

#: Indented continuation lines are the report's own body (built by the
#: telemetry formatters, which sanitise every field they interpolate), so they
#: are left alone; every other string argument is scrubbed here.
_REPORT_BODY_PREFIX = "    "

_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"}
)


def _first_string(args: Tuple[Any, ...]) -> str:
    for arg in args:
        if isinstance(arg, str) and arg:
            return arg
    return ""


def _find_endpoint(args: Tuple[Any, ...]) -> Tuple[str, str]:
    """Locate ``(method, path)`` among the record's arguments."""
    method = ""
    path = ""
    for arg in args:
        if not isinstance(arg, str):
            continue
        if not method and arg.upper() in _HTTP_METHODS:
            method = arg.upper()
            continue
        if not path and arg.startswith("/"):
            path = arg
    return method, path


def _find_number(args: Tuple[Any, ...]) -> float | None:
    """Best-effort ``wait`` from the record's arguments.

    The 429 report's numeric argument is its ``wait``; when the caller is
    authenticated a user pk precedes it, so the *last* number is the one that
    belongs to the throttle. Informational only — nothing decides on it.
    """
    found: float | None = None
    for arg in args:
        if isinstance(arg, (int, float)) and not isinstance(arg, bool):
            found = float(arg)
    return found


def _scrub_arg(value: str) -> str:
    """Sanitise one interpolated argument of the throttle report."""
    if "\n" in value and value.startswith(_REPORT_BODY_PREFIX):
        return value  # the report's own indented body — already sanitised
    if value.startswith("/"):
        return normalize_path(value)
    return sanitize_field(value, limit=120) or "-"


class ThrottleLogDedupFilter(logging.Filter):
    """Emit the detailed 429 report once per (client, endpoint) per window."""

    def __init__(self, telemetry: RequestTelemetry | None = None) -> None:
        super().__init__()
        self._telemetry = telemetry
        self._lock = threading.Lock()
        self.seen = 0
        self.suppressed = 0

    def telemetry(self) -> RequestTelemetry:
        if self._telemetry is None:
            with self._lock:
                if self._telemetry is None:
                    self._telemetry = default_telemetry()
        return self._telemetry

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        message = record.msg
        if not isinstance(message, str) or not message.startswith(REPORT_PREFIX):
            return True  # not a throttle report — never swallow it
        args = record.args if isinstance(record.args, tuple) else ()
        client_ip = _first_string(args)
        method, path = _find_endpoint(args)
        try:
            event = self.telemetry().note_throttle(
                client_ip=client_ip,
                method=method or "?",
                path=path or "/",
                wait=_find_number(args),
            )
        except Exception:  # pragma: no cover - observability must not break a 429
            return True
        self._rewrite(record, args)
        self.seen += 1
        if event.first:
            return True
        self.suppressed += 1
        return False

    @staticmethod
    def _rewrite(record: logging.LogRecord, args: Tuple[Any, ...]) -> None:
        """Replace interpolated strings with their log-safe form."""
        if not args:
            return
        record.args = tuple(_scrub_arg(arg) if isinstance(arg, str) else arg for arg in args)

    def reset(self) -> None:
        self.seen = 0
        self.suppressed = 0


_INSTALLED: dict[str, ThrottleLogDedupFilter] = {}
_INSTALL_LOCK = threading.Lock()
_ATEXIT_REGISTERED = False


def install(logger_name: str = THROTTLE_LOGGER_NAME) -> ThrottleLogDedupFilter:
    """Attach the dedup filter to the throttle logger. Idempotent."""
    global _ATEXIT_REGISTERED
    with _INSTALL_LOCK:
        existing = _INSTALLED.get(logger_name)
        if existing is not None and existing in logging.getLogger(logger_name).filters:
            return existing
        log_filter = ThrottleLogDedupFilter()
        logging.getLogger(logger_name).addFilter(log_filter)
        _INSTALLED[logger_name] = log_filter
        if not _ATEXIT_REGISTERED:
            atexit.register(_flush_at_exit)
            _ATEXIT_REGISTERED = True
        return log_filter


def installed(logger_name: str = THROTTLE_LOGGER_NAME) -> ThrottleLogDedupFilter | None:
    return _INSTALLED.get(logger_name)


def uninstall(logger_name: str = THROTTLE_LOGGER_NAME) -> None:
    with _INSTALL_LOCK:
        log_filter = _INSTALLED.pop(logger_name, None)
        if log_filter is not None:
            logging.getLogger(logger_name).removeFilter(log_filter)


def _flush_at_exit() -> None:
    """Publish the last window's counts when the process stops mid-window."""
    # At interpreter shutdown pytest (and anything else holding captured
    # streams) may already have closed the handlers' files. logging's
    # ``raiseExceptions`` prints a traceback in that case; the flush is
    # best-effort by definition, so silence it rather than emit noise on exit.
    previous = logging.raiseExceptions
    logging.raiseExceptions = False
    try:
        default_telemetry().flush()
    except Exception:  # pragma: no cover - interpreter shutdown
        pass
    finally:
        logging.raiseExceptions = previous
#!/usr/bin/env python
"""Measure throttle log volume for N rejected requests from one client.

The operator's number to beat: 119,925 rate-limit lines in 24h, because the
429 handler logged its whole forensic report on every rejected request. This
script drives the real DRF ``Throttled`` path (the exception a throttle
raises, through the real ``swarm_exception_handler``, against the real
telemetry module) with the throttle logger captured, and reports how many
journal lines N rejections cost.

No database, no cache server: the throttle's own budget arithmetic is not what
is being measured, so the exception is constructed directly. Nothing here
performs a query -- ``Throttled``/``exception_handler`` never touch the ORM,
and the rate-limit incident ring is an in-memory deque.

    # after (this tree)
    .venv/bin/python scripts/measure_throttle_log_volume.py --requests 300

    # before (pristine HEAD copy of src/, no working-tree writes)
    git archive HEAD src | tar -x -C /tmp/opencode/before
    PYTHONPATH=/tmp/opencode/before/src \\
        .venv/bin/python scripts/measure_throttle_log_volume.py --requests 300
"""

from __future__ import annotations

import argparse
import inspect
import logging
import os
import sys
import time

os.environ.setdefault("SWARM_SKIP_DOTENV", "1")
os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")


class _LineCounter(logging.Handler):
    """Capture the journal as an operator would see it: formatted lines."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[tuple[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append((record.name, record.getMessage()))

    @property
    def lines(self) -> int:
        return sum(len(msg.splitlines()) or 1 for _name, msg in self.records)

    def dump(self, limit: int = 12) -> None:
        for name, msg in self.records[:limit]:
            for line in msg.splitlines():
                print(f"  {name}: {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--client", default="192.0.2.44")
    parser.add_argument("--path", default="/v1/seat-health/")
    parser.add_argument("--method", default="GET")
    parser.add_argument("--wait", type=float, default=60.0)
    parser.add_argument("--history", type=int, default=25)
    parser.add_argument("--show", type=int, default=6)
    args = parser.parse_args()

    import django

    django.setup()

    import swarm  # noqa: F401  (report which tree answered)
    from rest_framework import exceptions
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    from swarm.core.request_telemetry import default_telemetry
    from swarm.views import exception_handlers

    print(f"tree: {os.path.dirname(os.path.dirname(swarm.__file__))}")

    # The filter is installed by SwarmConfig.ready(); make the measurement
    # independent of whether django.setup() reached it. Absent on a pre-fix
    # tree, which is the point of running this against one.
    try:
        from swarm.core import request_logging

        log_filter = request_logging.install()
    except ImportError:
        log_filter = None

    # Own the journal output so the counts below are not interleaved with the
    # console handler's echo.
    for name in ("swarm", "swarm.throttle", "swarm.requests", "swarm.throttle_summary"):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        logger.propagate = False
        logger.setLevel(logging.DEBUG)

    throttle_log = _LineCounter()
    throttle_logger = logging.getLogger("swarm.throttle")
    throttle_logger.addHandler(throttle_log)
    throttle_logger.propagate = False

    summary_log = _LineCounter()
    logging.getLogger("swarm.throttle_summary").addHandler(summary_log)
    logging.getLogger("swarm.requests").addHandler(_LineCounter())
    request_log = logging.getLogger("swarm.requests").handlers[-1]

    telemetry = default_telemetry()
    if hasattr(telemetry, "reset"):
        telemetry.reset()

    # A prior burst, so the report has real top-endpoint content to print.
    base = time.monotonic()
    # response_bytes is a later addition; the same script must run against a
    # pre-fix tree to produce the "before" number.
    extra = (
        {"response_bytes": 88}
        if "response_bytes" in inspect.signature(telemetry.record).parameters
        else {}
    )
    for i in range(args.history):
        telemetry.record(
            client_ip=args.client,
            method=args.method,
            path=args.path,
            status_code=429,
            user_key="42",
            source="seatHealthPoll",
            duration_ms=1.0,
            now=base + i * 0.0001,
            **extra,
        )

    factory = APIRequestFactory()
    for i in range(args.requests):
        django_request = factory.get(
            args.path, REMOTE_ADDR=args.client, HTTP_X_SWARM_CLIENT_SOURCE="seatHealthPoll"
        )
        django_request.user = None
        exception_handlers.swarm_exception_handler(
            exceptions.Throttled(wait=args.wait),
            {"request": Request(django_request)},
        )

    rollup = telemetry.flush() if hasattr(telemetry, "flush") else []

    n = args.requests
    print(f"\n{n} rejected requests from {args.client} on {args.method} {args.path}")
    print(f"  throttle logger records : {len(throttle_log.records)}")
    print(f"  throttle journal lines  : {throttle_log.lines}")
    print(f"  rollup journal lines    : {summary_log.lines}")
    print(
        "  dedup filter            : "
        + (f"seen={log_filter.seen} suppressed={log_filter.suppressed}" if log_filter else "not installed")
    )
    print(f"  request lines (seeded)  : {request_log.lines}")
    print(f"  lines per rejection     : {throttle_log.lines / max(1, n):.2f}")
    if rollup:
        print("  window rollup (emitted when the bucket's window closes):")
        for line in rollup:
            print(f"  {line}")
    print("\n  first records:")
    throttle_log.dump(args.show)
    return 0


if __name__ == "__main__":
    sys.exit(main())
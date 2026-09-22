"""#800 — DRF exception handler with 429 burst forensics.

On a ``Throttled`` exception the client's telemetry window is logged as a
structured warning: who flooded, which endpoint, at what cadence, and (when
the client sends ``X-Swarm-Client-Source``) which frontend caller. Every
other exception falls through to DRF's default handler unchanged.
"""

from __future__ import annotations

import logging
import time

from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("swarm.throttle")


def swarm_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if isinstance(exc, exceptions.Throttled):
        request = context.get("request")
        try:
            from swarm.core.request_telemetry import default_telemetry

            client_ip = (
                (getattr(request, "META", {}) or {}).get("REMOTE_ADDR") or "unknown"
            )
            wait = getattr(exc, "wait", None)
            user = getattr(getattr(request, "user", None), "pk", None)
            source = ""
            if request is not None:
                source = request.headers.get("X-Swarm-Client-Source", "")
            telemetry = default_telemetry()
            try:
                from swarm.views.telemetry_api import record_throttle_incident

                record_throttle_incident(
                    {
                        "ts": time.time(),
                        "client_ip": client_ip,
                        "user": user,
                        "method": getattr(request, "method", "?"),
                        "path": getattr(request, "path", "?"),
                        "wait": wait,
                        "source": source,
                        "top_paths": telemetry.client_summary(client_ip)["top_paths"][:8],
                    }
                )
            except Exception:
                pass
            logger.warning(
                "[RATE_LIMIT_EXCEEDED] 429 Too Many Requests\n"
                "  Client: %s (user: %s)\n"
                "  Triggered on: %s %s (wait: %ss)\n"
                "  Declared source: %s\n"
                "  Top endpoints in last window:\n%s\n"
                "  Sources: %s",
                client_ip,
                user,
                getattr(request, "method", "?"),
                getattr(request, "path", "?"),
                wait,
                source or "(none)",
                telemetry.format_top_endpoints(client_ip),
                telemetry.format_sources(client_ip),
            )
        except Exception:
            logger.debug("429 forensic logging failed", exc_info=True)
    return response

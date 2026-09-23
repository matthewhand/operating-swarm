"""#800 — telemetry diagnostic endpoints.

GET ``/v1/telemetry/requests/``   the caller's own burst window (per-IP)
GET ``/v1/telemetry/throttles/``  recent 429 incidents (ring, capped)

Operators can ``curl`` these to see which endpoint/caller is flooding
without grepping server logs. Auth follows ``api_permission_classes()`` —
no guest-only access; the requests view only ever exposes the caller's
own client window.
"""

from __future__ import annotations

import logging
from collections import deque
from threading import Lock

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes

logger = logging.getLogger(__name__)

_THROTTLE_INCIDENTS: deque = deque(maxlen=50)
_INCIDENTS_LOCK = Lock()


def record_throttle_incident(incident: dict) -> None:
    """Called by the exception handler so the API can replay incidents."""
    try:
        with _INCIDENTS_LOCK:
            _THROTTLE_INCIDENTS.append(incident)
    except Exception:
        logger.debug("throttle incident recording failed", exc_info=True)


def _client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR") or "unknown"


class RequestTelemetryView(APIView):
    """Burst window for the *caller's own* client IP (self-diagnostics)."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_telemetry_requests",
        summary="Recent request burst window for this client (429 forensics)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        from swarm.core.request_telemetry import default_telemetry

        telemetry = default_telemetry()
        ip = _client_ip(request)
        summary = telemetry.client_summary(ip)
        return Response(
            {
                "object": "request_telemetry",
                "client_ip": ip,
                **summary,
            },
            status=status.HTTP_200_OK,
        )


class ThrottleIncidentsView(APIView):
    """Recent 429 incidents observed by the server."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_telemetry_throttles",
        summary="Recent 429 throttle incidents with client breakdowns",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        with _INCIDENTS_LOCK:
            incidents = list(_THROTTLE_INCIDENTS)
        return Response(
            {"object": "throttle_incidents", "count": len(incidents), "incidents": incidents},
            status=status.HTTP_200_OK,
        )

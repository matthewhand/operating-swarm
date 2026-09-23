"""#905 — read-only diagnostics endpoint for the WebUI (#906/#907 consume it)."""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.diagnostics import tech_support_dump

logger = logging.getLogger(__name__)

#: Query-param clamp bounds (#905). Default matches tech_support_dump's own.
DEFAULT_LINES = 100
MAX_LINES = 500


def _clamp_lines(raw: str | None) -> int:
    """Clamp the ?lines= query param to [1, MAX_LINES]; default when absent."""
    if not raw:
        return DEFAULT_LINES
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LINES
    return max(1, min(value, MAX_LINES))


class DiagnosticsView(APIView):
    """GET /v1/diagnostics/ — sanitized tech-support bundle. Read-only."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_diagnostics",
        summary="Tech-support diagnostics dump",
        description=(
            "Read-only, sanitized diagnostics bundle: recent swarm log lines "
            "(ring buffer), a masked configuration dump, and server facts. "
            "Secrets are masked server-side; this view never un-masks. "
            "The optional ``lines`` query param clamps the log window to "
            f"1..{MAX_LINES} (default {DEFAULT_LINES})."
        ),
        parameters=[
            OpenApiParameter(
                name="lines",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description=f"Log line window; clamped to 1..{MAX_LINES}.",
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        lines = _clamp_lines(request.query_params.get("lines"))
        try:
            payload = tech_support_dump(log_lines=lines)
        except Exception:
            logger.exception("Diagnostics endpoint degraded")
            payload = {
                "recent_logs": {"lines": [], "counts": {}, "unavailable": True},
                "config_dump": {},
                "server_facts": {},
            }
        return Response(payload)

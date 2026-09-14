"""REST surface for the #179 marketplace scan.

GET /v1/marketplace/?kind=teams|plugins
    Scan GitHub by well-known topics (``swarm-team-pack``,
    ``swarm-mcp-plugin``, ``open-swarm-plugin``) for community shareables.
    Responses are always ``external: true`` (community content) and carry
    honest ``warnings`` on rate limits / offline GitHub. Read-only proxy —
    no GitHub token required; ``GITHUB_TOKEN`` env is used if present.

Auth follows the project pattern: HasValidTokenOrSession when API auth is
enabled, AllowAny otherwise (matches /v1/mcp-plugins/).
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.marketplace import scan_marketplace

logger = logging.getLogger(__name__)


class MarketplaceScanView(APIView):
    """GET /v1/marketplace/?kind=teams|plugins — GitHub topic scan (#179)."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_marketplace_scan",
        summary="Scan GitHub for community team packs / MCP plugins by topic tags",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        kind = str(request.query_params.get("kind") or "").strip().lower()
        if kind not in ("teams", "plugins"):
            return Response(
                {
                    "error": "query param 'kind' must be 'teams' or 'plugins'.",
                    "code": "invalid_kind",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return Response(scan_marketplace(kind))
        except Exception:
            logger.exception("Marketplace scan failed")
            return Response(
                {"error": "Marketplace scan failed.", "code": "marketplace_error"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

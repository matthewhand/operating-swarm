"""REST surface for marketplace scan (#179) and catalog (#292 / REQ-887).

GET  /v1/marketplace/?kind=teams|plugins
    GitHub topic scan (precursor). Community/external; honest warnings.

GET  /v1/marketplace/catalog/?kind=teams|plugins|skills
    Real catalog: Official MCP Registry (cached) + GitHub fallback for
    plugins; Agent Skills for skills; OS team packs for teams.

GET  /v1/marketplace/preview/?kind=&id=
    Inspect before write (team members/CoS/wires; plugin env names).

POST /v1/marketplace/install/
    Install into existing plugin list / user skills dir / team_rosters.

Auth follows the project pattern: HasValidTokenOrSession when API auth is
enabled, AllowAny otherwise (matches /v1/mcp-plugins/).
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.marketplace import scan_marketplace
from swarm.core.marketplace_catalog import (
    MarketplaceCatalogError,
    build_catalog,
    install_item,
    preview_item,
)

logger = logging.getLogger(__name__)


def _catalog_error(exc: Exception) -> Response:
    if isinstance(exc, MarketplaceCatalogError):
        return Response({"error": str(exc), "code": exc.code}, status=exc.status)
    logger.exception("Marketplace request failed")
    return Response(
        {"error": "Marketplace request failed.", "code": "marketplace_error"},
        status=status.HTTP_502_BAD_GATEWAY,
    )


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


class MarketplaceCatalogView(APIView):
    """GET /v1/marketplace/catalog/?kind=teams|plugins|skills — REQ-887."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_marketplace_catalog",
        summary="Browse Teams / Plugins / Skills marketplace catalog",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        kind = str(request.query_params.get("kind") or "").strip().lower()
        try:
            return Response(build_catalog(kind))
        except Exception as exc:
            return _catalog_error(exc)


class MarketplacePreviewView(APIView):
    """GET /v1/marketplace/preview/?kind=&id= — inspect before install."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_marketplace_preview",
        summary="Preview a marketplace item before install (no write)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        kind = str(request.query_params.get("kind") or "").strip().lower()
        item_id = str(request.query_params.get("id") or "").strip()
        try:
            return Response(preview_item(kind, item_id))
        except Exception as exc:
            return _catalog_error(exc)


class MarketplaceInstallView(APIView):
    """POST /v1/marketplace/install/ — install into existing OS stores."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_marketplace_install",
        summary="Install a marketplace item (plugin / skill / team pack)",
        request=inline_serializer(
            name="MarketplaceInstallRequest",
            fields={
                "kind": serializers.CharField(),
                "id": serializers.CharField(),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        kind = str(body.get("kind") or "").strip().lower()
        item_id = str(body.get("id") or "").strip()
        try:
            return Response(install_item(kind, item_id))
        except Exception as exc:
            return _catalog_error(exc)

"""
Role descriptors API view for Settings -> Roles pane (REQ-25 / REQ-28 / #206).

GET /v1/roles/ -> {"object": "list", "data": [RoleDescriptor, ...]}
POST /v1/roles/ -> {"name": ..., ...} -> RoleDescriptor
DELETE /v1/roles/<str:role_id>/ -> 204 No Content
"""

from __future__ import annotations

import logging
import re
from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.agent_roles import (
    CANONICAL_ROLES,
    ROLE_ALIASES,
    get_all_role_descriptors,
)
from swarm.core.roles.custom import CustomRole
from swarm.core.roles.registry import ROLE_REGISTRY, register_role, unregister_role
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

ROLES_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


class RolesAPIView(APIView):
    """GET / POST / DELETE /v1/roles/ — Agent roles and custom role management."""

    permission_classes = ROLES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_roles_list",
        summary="List canonical and custom agent roles and their wiring mechanisms",
        description=(
            "Returns role definitions, badges, aliases, and execution "
            "mechanisms (intercept, parse, implement, allow-all, none) for settings."
        ),
        responses={200: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        try:
            data = get_all_role_descriptors()
            return Response({"object": "list", "data": data}, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error retrieving role descriptors.")
            return Response(
                {"error": "Failed to retrieve roles."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        operation_id="v1_roles_create",
        summary="Create or register a custom agent role",
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        payload: dict[str, Any] = request.data or {}
        raw_name = payload.get("name")
        if not raw_name or not str(raw_name).strip():
            return Response({"error": "Role name is required."}, status=status.HTTP_400_BAD_REQUEST)

        slug = str(raw_name).strip().lower().replace(" ", "_").replace("-", "_")
        if not re.match(r"^[a-z0-9_]+$", slug):
            return Response(
                {"error": "Role name must contain only alphanumeric characters, dashes, and underscores."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if slug in CANONICAL_ROLES:
            return Response(
                {"error": f"Cannot create role '{slug}': '{slug}' is a reserved canonical role."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        label = payload.get("label") or slug.capitalize()
        aliases = payload.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [a.strip() for a in aliases.split(",") if a.strip()]

        mechanism = payload.get("mechanism") or "none"
        mechanism_detail = payload.get("mechanism_detail") or ""
        allow_all = bool(payload.get("allow_all", False))
        css_class = payload.get("css_class") or ""

        try:
            custom_role = CustomRole(
                id=slug,
                label=str(label),
                aliases=aliases,
                mechanism=str(mechanism),
                mechanism_detail=str(mechanism_detail),
                allow_all=allow_all,
                css_class=str(css_class),
            )
            register_role(custom_role)
            for alias in custom_role.aliases:
                ROLE_ALIASES[alias] = slug

            return Response(custom_role.describe(), status=status.HTTP_201_CREATED)
        except Exception:
            logger.exception("Failed to register custom role.")
            return Response(
                {"error": "Failed to create role."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        operation_id="v1_roles_delete",
        summary="Delete a custom agent role",
        responses={204: OpenApiTypes.NONE, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def delete(self, request, role_id: str | None = None, *_args, **_kwargs):
        target = role_id or request.query_params.get("role_id") or (request.data and request.data.get("role_id"))
        if not target:
            return Response({"error": "Role ID is required for deletion."}, status=status.HTTP_400_BAD_REQUEST)

        slug = str(target).strip().lower().replace(" ", "_").replace("-", "_")
        if slug in CANONICAL_ROLES:
            return Response(
                {"error": f"Cannot delete canonical role '{slug}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if slug not in ROLE_REGISTRY:
            return Response({"error": f"Role '{slug}' not found."}, status=status.HTTP_404_NOT_FOUND)

        role = unregister_role(slug)
        if role:
            for alias in getattr(role, "aliases", ()):
                ROLE_ALIASES.pop(alias, None)

        return Response(status=status.HTTP_204_NO_CONTENT)

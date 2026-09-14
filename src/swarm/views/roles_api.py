"""
Role descriptors API view for Settings -> Roles pane (REQ-25 / REQ-28).

GET /v1/roles/ -> {"object": "list", "data": [RoleDescriptor, ...]}
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.agent_roles import get_canonical_role_descriptors
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

ROLES_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


class RolesAPIView(APIView):
    """GET /v1/roles/ — List canonical agent roles and their mechanisms."""

    permission_classes = ROLES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_roles_list",
        summary="List canonical agent roles and their wiring mechanisms",
        description=(
            "Returns canonical role definitions, badges, aliases, and execution "
            "mechanisms (intercept, parse, implement, allow-all, none) for settings."
        ),
        responses={200: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        try:
            data = get_canonical_role_descriptors()
            return Response({"object": "list", "data": data}, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error retrieving role descriptors.")
            return Response(
                {"error": "Failed to retrieve roles."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

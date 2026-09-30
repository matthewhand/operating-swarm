"""#1324 — declared seat capabilities for engine-switch warnings.

GET /v1/capabilities/seats/ returns kind-base seat_capabilities plus the
CLI hop rows (list / resume / export) the picker compares. No argv.
"""

from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes


class SeatCapabilitiesAPIView(APIView):
    """Published seat-capability directory. Read-only."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_capabilities_seats",
        summary="Declared seat capabilities per kind, plus CLI hop rows",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        from swarm.core.engine_switch_capabilities import seats_capability_directory

        return Response(seats_capability_directory(), status=status.HTTP_200_OK)

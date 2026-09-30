"""GET ``/v1/company-route/`` — auto-applied Company model (#1317).

The payload is routing parameters for the signed-in principal. It never
names a replacement seat or ``blueprint_id``. An unavailable Company model
falls back deterministically and records a company_model_fallback activity row.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes, request_principal
from swarm.core import org_policy

logger = logging.getLogger(__name__)


class CompanyRouteView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_company_route_get",
        summary="Resolved Company model route for the signed-in principal",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        try:
            route = org_policy.resolve_company_route(
                request_principal(request),
                org_policy.current_available_models(),
                record=True,
            )
        except Exception:
            logger.exception("company route resolve failed")
            route = None
        if route is None:
            body = {
                "object": "company_route",
                "applied": False,
                "model": "",
                "provider": "",
                "source": "none",
                "reason": "policy_off",
            }
        else:
            body = {"object": "company_route", **route.public()}
        try:
            request.company_route = route
        except Exception:
            pass
        return Response(body)

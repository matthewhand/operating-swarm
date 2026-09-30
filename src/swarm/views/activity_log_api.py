"""#1314 — operator activity log REST.

GET/POST ``/v1/activity/`` — append-only ``ActivityEvent`` feed. ``detail``
is redacted before persist and again on read. No secrets leave this view.

Visibility (``activity_log_visibility`` pref / file / env):

* ``off`` — 404 for every caller
* ``operator`` — staff / API token (or auth-off single-user); others 403
* ``all`` — operators see the full feed; everyone else sees only their events
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.activity_log import (
    VISIBILITY_ALL,
    VISIBILITY_OFF,
    VISIBILITY_OPERATOR,
    ActivityLogBusy,
    ActivityLogError,
    get_activity_log_visibility,
    is_operator_request,
    list_activity,
    persist_from_payload,
    public_list,
    request_actor_id,
)
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

ACTIVITY_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


def _activity_error(exc: ActivityLogError) -> Response:
    if isinstance(exc, ActivityLogBusy):
        return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
    return _error(str(exc), status.HTTP_400_BAD_REQUEST)


def _visibility_denied(request, *, write: bool = False):
    """Return a 404/403 response when the caller cannot use the feed.

    ``None`` means the request may proceed. For ``all`` reads, the second
    value is the owner principal used to filter the page.
    """
    mode = get_activity_log_visibility()
    if mode == VISIBILITY_OFF:
        return _error("activity log is off", status.HTTP_404_NOT_FOUND), None
    operator = is_operator_request(request)
    if write:
        if not operator:
            return _error("operator visibility only", status.HTTP_403_FORBIDDEN), None
        return None, None
    if mode == VISIBILITY_OPERATOR and not operator:
        return _error("operator visibility only", status.HTTP_403_FORBIDDEN), None
    owner = None
    if mode == VISIBILITY_ALL and not operator:
        owner = request_actor_id(request)
    return None, owner


class ActivityLogAPIView(APIView):
    """GET/POST /v1/activity/ — operator activity feed."""

    permission_classes = ACTIVITY_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_activity_list",
        summary="List operator activity events (newest first)",
        description=(
            "Append-only ActivityEvent feed. Filters: actor_type, action "
            "(prefix), entity_type, entity_id, agent_id, limit. "
            "ActivityEvent.detail is always redacted. "
            "Gated by activity_log_visibility (off|operator|all)."
        ),
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            503: OpenApiTypes.OBJECT,
        },
    )
    def get(self, request, *_args, **_kwargs):
        denied, owner = _visibility_denied(request)
        if denied is not None:
            return denied
        params = request.query_params
        try:
            limit = int(params.get("limit") or 50)
        except (TypeError, ValueError):
            return _error("limit must be an integer", status.HTTP_400_BAD_REQUEST)
        try:
            events = list_activity(
                actor_type=params.get("actor_type"),
                action=params.get("action"),
                entity_type=params.get("entity_type"),
                entity_id=params.get("entity_id"),
                agent_id=params.get("agent_id"),
                owner_principal=owner,
                limit=limit,
            )
        except ActivityLogError as exc:
            return _activity_error(exc)
        items = public_list(events)
        return Response(
            {
                "object": "activity_list",
                "items": items,
                "count": len(items),
                "visibility": get_activity_log_visibility(),
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        operation_id="v1_activity_create",
        summary="Append one operator activity event",
        description=(
            "Board/operator write. Required: actor_id (or session user), "
            "action, entity_type, entity_id. Optional: actor_type, agent_id, "
            "run_id, responsible_user_id, detail (alias: details). "
            "Credential-shaped detail is stored as [REDACTED]."
        ),
        request=OpenApiTypes.OBJECT,
        responses={
            201: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            503: OpenApiTypes.OBJECT,
        },
    )
    def post(self, request, *_args, **_kwargs):
        denied, _owner = _visibility_denied(request, write=True)
        if denied is not None:
            return denied
        body = getattr(request, "data", None)
        if not isinstance(body, dict):
            return _error("body must be an object", status.HTTP_400_BAD_REQUEST)
        payload = dict(body)
        if not str(payload.get("actor_id") or "").strip():
            payload["actor_id"] = request_actor_id(request)
        try:
            event = persist_from_payload(payload)
        except ActivityLogError as exc:
            return _activity_error(exc)
        return Response(
            {"object": "activity_event", **event.to_public_dict()},
            status=status.HTTP_201_CREATED,
        )

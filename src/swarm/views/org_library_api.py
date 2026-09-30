"""Org-shared bot library API (#1311).

GET    /v1/org-library/                 list presets + org/team-visible bots
POST   /v1/org-library/                 publish a bot recipe to the org library
GET    /v1/org-library/<id>/            one bot
DELETE /v1/org-library/<id>/            remove a non-preset bot
POST   /v1/org-library/<id>/share/      whole-team share (roster membership)

Recipes only — no conversation history, computer state, or secrets.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.org_bot_library import (
    OBJECT_BOT,
    OrgLibraryError,
    PresetProtectedError,
    TeamNotFoundError,
    delete_bot,
    get_bot,
    list_bots,
    publish_bot,
    share_with_team,
)
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

ORG_LIBRARY_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


def _actor(request) -> str:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return ""
    return str(getattr(user, "username", "") or getattr(user, "pk", "") or "")[:64]


class OrgLibraryAPIView(APIView):
    """GET/POST /v1/org-library/"""

    permission_classes = ORG_LIBRARY_PERMISSIONS

    @extend_schema(
        operation_id="v1_org_library_list",
        summary="List the org-shared bot library (#1311)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        team_id = str(request.query_params.get("team_id") or "").strip()
        rows = list_bots(team_id=team_id or None)
        return Response({"object": "list", "data": rows}, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_org_library_publish",
        summary="Publish a bot recipe to the org-shared library (#1311)",
        request=inline_serializer(
            name="OrgLibraryPublishRequest",
            fields={
                "id": serializers.CharField(required=False),
                "name": serializers.CharField(),
                "description": serializers.CharField(required=False, allow_blank=True),
                "kind": serializers.CharField(required=False),
                "role": serializers.CharField(required=False),
                "instructions": serializers.CharField(required=False, allow_blank=True),
                "visibility": serializers.CharField(required=False),
                "team_id": serializers.CharField(required=False),
            },
        ),
        examples=[
            OpenApiExample(
                "Publish",
                value={"name": "Account Health", "description": "Weekly churn watch."},
                request_only=True,
            )
        ],
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            row = publish_bot(body, created_by=_actor(request))
        except PresetProtectedError as exc:
            return _error(str(exc), status.HTTP_409_CONFLICT)
        except OrgLibraryError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Error publishing org library bot.")
            return _error("Failed to publish bot.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(row, status=status.HTTP_201_CREATED)


class OrgLibraryDetailAPIView(APIView):
    """GET/DELETE /v1/org-library/<bot_id>/"""

    permission_classes = ORG_LIBRARY_PERMISSIONS

    @extend_schema(
        operation_id="v1_org_library_get",
        summary="Read one org-library bot (#1311)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, bot_id: str, *_args, **_kwargs):
        row = get_bot(bot_id)
        if row is None:
            return _error("not found", status.HTTP_404_NOT_FOUND)
        return Response(row, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_org_library_delete",
        summary="Remove a non-preset org-library bot (#1311)",
        responses={204: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    def delete(self, request, bot_id: str, *_args, **_kwargs):
        try:
            removed = delete_bot(bot_id)
        except PresetProtectedError as exc:
            return _error(str(exc), status.HTTP_409_CONFLICT)
        if not removed:
            return _error("not found", status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrgLibraryShareAPIView(APIView):
    """POST /v1/org-library/<bot_id>/share/ — whole-team share."""

    permission_classes = ORG_LIBRARY_PERMISSIONS

    @extend_schema(
        operation_id="v1_org_library_share",
        summary="Share a library bot with a whole team (#1311)",
        request=inline_serializer(
            name="OrgLibraryShareRequest",
            fields={
                "scope": serializers.CharField(required=False, help_text="Must be 'team'."),
                "team_id": serializers.CharField(help_text="Roster id to receive the bot."),
            },
        ),
        examples=[
            OpenApiExample(
                "Whole team",
                value={"scope": "team", "team_id": "eng"},
                request_only=True,
            )
        ],
    )
    def post(self, request, bot_id: str, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        scope = str(body.get("scope") or "team").strip().lower()
        if scope != "team":
            return _error("Only whole-team share is supported.", status.HTTP_400_BAD_REQUEST)
        team_id = str(body.get("team_id") or body.get("roster_id") or "").strip()
        try:
            result = share_with_team(bot_id, team_id)
        except TeamNotFoundError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        except OrgLibraryError as exc:
            message = str(exc)
            code = status.HTTP_404_NOT_FOUND if "was not found" in message else status.HTTP_400_BAD_REQUEST
            return _error(message, code)
        except Exception:
            logger.exception("Error sharing org library bot %s.", bot_id)
            return _error("Failed to share bot.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(
            {
                "object": "org_library.share",
                "scope": "team",
                "team_id": result["team_id"],
                "roster_id": result["roster_id"],
                "bot": result["bot"],
            },
            status=status.HTTP_200_OK,
        )


# Keep the object name importable for OpenAPI examples / tests.
ORG_LIBRARY_OBJECT = OBJECT_BOT

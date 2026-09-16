"""Per-agent Routines API (REQ-80 / #432, REQ-884 / #285).

GET/POST ``/v1/agents/<id>/routines/``
GET/PATCH/DELETE ``/v1/agents/<id>/routines/<routine_id>/``
POST ``/v1/agents/<id>/routines/<routine_id>/test-run/``
POST ``/v1/routines/github-merge/`` — inbound fake GitHub PR-merged event.
POST ``/v1/routines/events/github/`` — signed GitHub webhook ingest.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.chat_store import normalize_agent_id
from swarm.core.routines import (
    create_routine,
    delete_routine,
    deliver_github_event,
    deliver_github_pr_merged,
    get_routine,
    github_webhook_secret,
    list_all_routines,
    list_routines,
    test_run,
    trigger_summary,
    update_routine,
    verify_github_webhook_signature,
)
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

ROUTINES_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


def _routine_payload(agent_id: str, routine: dict) -> dict:
    return {
        "object": "routine",
        "agent_id": agent_id,
        **routine,
        "when_to_run": trigger_summary(routine.get("trigger")),
    }


def _list_payload(agent_id: str, routines: list[dict]) -> dict:
    return {
        "object": "routine_list",
        "agent_id": agent_id,
        "routines": [_routine_payload(agent_id, row) for row in routines],
    }


class AgentRoutinesAPIView(APIView):
    """GET/POST /v1/agents/<agent_id>/routines/"""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_routines_list",
        summary="List routines for one agent (REQ-80)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        return Response(_list_payload(agent, list_routines(agent)), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_routines_create",
        summary="Create a routine for one agent (REQ-80)",
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            routine = create_routine(agent, body)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to create routine for %s", agent)
            return _error("Could not save routine.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_routine_payload(agent, routine), status=status.HTTP_201_CREATED)


class AgentRoutineDetailAPIView(APIView):
    """GET/PATCH/DELETE /v1/agents/<agent_id>/routines/<routine_id>/"""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_routine_get",
        summary="Get one agent routine (REQ-80)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, routine_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        routine = get_routine(agent, routine_id)
        if routine is None:
            return _error("Routine not found.", status.HTTP_404_NOT_FOUND)
        return Response(_routine_payload(agent, routine), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_routine_patch",
        summary="Update one agent routine (REQ-80)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def patch(self, request, agent_id: str, routine_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            routine = update_routine(agent, routine_id, body)
        except KeyError:
            return _error("Routine not found.", status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to update routine %s for %s", routine_id, agent)
            return _error("Could not save routine.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_routine_payload(agent, routine), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_routine_delete",
        summary="Delete one agent routine (REQ-80)",
        responses={204: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def delete(self, request, agent_id: str, routine_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        if not delete_routine(agent, routine_id):
            return _error("Routine not found.", status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentRoutineTestRunAPIView(APIView):
    """POST /v1/agents/<agent_id>/routines/<routine_id>/test-run/"""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_routine_test_run",
        summary="Test-run a routine instruction as the agent's prompt (REQ-80)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, routine_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            routine = test_run(agent, routine_id)
        except KeyError:
            return _error("Routine not found.", status.HTTP_404_NOT_FOUND)
        except OSError:
            logger.exception("Failed to test-run routine %s for %s", routine_id, agent)
            return _error("Could not test-run routine.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_routine_payload(agent, routine), status=status.HTTP_200_OK)


class GithubRoutineMergeAPIView(APIView):
    """POST /v1/routines/github-merge/ — fake or connector-delivered merge event."""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_routines_github_merge",
        summary="Deliver a GitHub PR-merged event to matching Active routines (REQ-80)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            fired = deliver_github_pr_merged(body)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "object": "routine_merge_delivery",
                "fired": [
                    {
                        "agent_id": row["agent_id"],
                        "routine": _routine_payload(row["agent_id"], row["routine"]),
                    }
                    for row in fired
                ],
                "count": len(fired),
            },
            status=status.HTTP_200_OK,
        )


class GithubRoutineEventsAPIView(APIView):
    """POST /v1/routines/events/github/ — signed GitHub webhook ingest (REQ-884)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    http_method_names = ["post"]

    @extend_schema(
        operation_id="v1_routines_github_events",
        summary="Ingest a GitHub webhook and fire matching github_event routines (REQ-884)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        secret = github_webhook_secret()
        if not secret:
            return _error("GITHUB_WEBHOOK_SECRET is not configured.", status.HTTP_503_SERVICE_UNAVAILABLE)
        signature = request.headers.get("X-Hub-Signature-256") or request.META.get(
            "HTTP_X_HUB_SIGNATURE_256",
            "",
        )
        if not verify_github_webhook_signature(request.body or b"", signature, secret=secret):
            return _error("Invalid GitHub webhook signature.", status.HTTP_401_UNAUTHORIZED)
        event_header = request.headers.get("X-GitHub-Event") or request.META.get("HTTP_X_GITHUB_EVENT", "")
        if str(event_header).strip().lower() == "ping":
            return Response(
                {"object": "github_event_delivery", "fired": [], "count": 0, "pong": True},
                status=status.HTTP_200_OK,
            )
        payload = request.data if isinstance(request.data, dict) else {}
        try:
            fired = deliver_github_event(payload, event_header=str(event_header or ""))
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to deliver GitHub webhook event")
            return _error("Could not deliver GitHub event.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(
            {
                "object": "github_event_delivery",
                "fired": [
                    {
                        "agent_id": row["agent_id"],
                        "routine": _routine_payload(row["agent_id"], row["routine"]),
                    }
                    for row in fired
                ],
                "count": len(fired),
            },
            status=status.HTTP_200_OK,
        )


class AllRoutinesAPIView(APIView):
    """GET /v1/routines/ — List all routines across agents."""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_routines_list_all",
        summary="List all routines across agents",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        rows = list_all_routines()
        return Response(
            {
                "object": "routine_list",
                "routines": [_routine_payload(r.get("agent_id", ""), r) for r in rows],
            },
            status=status.HTTP_200_OK,
        )

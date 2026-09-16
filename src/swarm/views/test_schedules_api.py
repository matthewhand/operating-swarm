"""Test schedule API (#222) — fleet proofs, harness checks, run-now.

GET/POST ``/v1/test-schedules/``
GET/PATCH/DELETE ``/v1/test-schedules/<schedule_id>/``
POST ``/v1/test-schedules/<schedule_id>/run-now/``
GET ``/v1/test-schedules/status/`` — open failure count for the rail badge.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.test_schedules import (
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedules,
    open_failures,
    run_now,
    update_schedule,
)
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

TEST_SCHEDULES_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


def _schedule_payload(schedule: dict) -> dict:
    return {"object": "test_schedule", **schedule}


def _list_payload(rows: list[dict]) -> dict:
    failures = open_failures()
    return {
        "object": "test_schedule_list",
        "schedules": [_schedule_payload(row) for row in rows],
        "failure_count": len(failures),
    }


class TestSchedulesAPIView(APIView):
    """GET/POST /v1/test-schedules/"""

    permission_classes = TEST_SCHEDULES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_test_schedules_list",
        summary="List test schedules (#222)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        return Response(_list_payload(list_schedules()), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_test_schedules_create",
        summary="Create a test schedule (#222)",
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            schedule = create_schedule(body)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to create test schedule")
            return _error("Could not save test schedule.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_schedule_payload(schedule), status=status.HTTP_201_CREATED)


class TestScheduleStatusAPIView(APIView):
    """GET /v1/test-schedules/status/ — rail badge / toast surfacing."""

    permission_classes = TEST_SCHEDULES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_test_schedules_status",
        summary="Open test-schedule failure count (#222)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        failures = open_failures()
        return Response(
            {
                "object": "test_schedule_status",
                "failure_count": len(failures),
                "failures": [
                    {
                        "id": row.get("id"),
                        "name": row.get("name"),
                        "status": (row.get("history") or [{}])[0].get("status"),
                        "summary": (row.get("history") or [{}])[0].get("summary")
                        or (row.get("history") or [{}])[0].get("error"),
                    }
                    for row in failures
                ],
            },
            status=status.HTTP_200_OK,
        )


class TestScheduleDetailAPIView(APIView):
    """GET/PATCH/DELETE /v1/test-schedules/<schedule_id>/"""

    permission_classes = TEST_SCHEDULES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_test_schedule_get",
        summary="Get one test schedule (#222)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, schedule_id: str, *_args, **_kwargs):
        schedule = get_schedule(schedule_id)
        if schedule is None:
            return _error("Test schedule not found.", status.HTTP_404_NOT_FOUND)
        return Response(_schedule_payload(schedule), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_test_schedule_patch",
        summary="Update one test schedule (#222)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def patch(self, request, schedule_id: str, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            schedule = update_schedule(schedule_id, body)
        except KeyError:
            return _error("Test schedule not found.", status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to update test schedule %s", schedule_id)
            return _error("Could not save test schedule.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_schedule_payload(schedule), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_test_schedule_delete",
        summary="Delete one test schedule (#222)",
        responses={204: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def delete(self, request, schedule_id: str, *_args, **_kwargs):
        if not delete_schedule(schedule_id):
            return _error("Test schedule not found.", status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TestScheduleRunNowAPIView(APIView):
    """POST /v1/test-schedules/<schedule_id>/run-now/"""

    permission_classes = TEST_SCHEDULES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_test_schedule_run_now",
        summary="Run a test schedule now (#222)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, schedule_id: str, *_args, **_kwargs):
        try:
            schedule = run_now(schedule_id)
        except KeyError:
            return _error("Test schedule not found.", status.HTTP_404_NOT_FOUND)
        except OSError:
            logger.exception("Failed to run-now test schedule %s", schedule_id)
            return _error("Could not run test schedule.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_schedule_payload(schedule), status=status.HTTP_200_OK)

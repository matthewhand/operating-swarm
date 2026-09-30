"""Operator control plane API (#1360).

Not a seat kind. Budgets, execution locks, revisioned approval gates, and
secret-scrubbed org packs live here.

``GET    /v1/operator-plane/``
``GET    /v1/operator-plane/budgets/``
``PUT    /v1/operator-plane/budgets/``
``POST   /v1/operator-plane/budgets/charge/``
``POST   /v1/operator-plane/budgets/reset/``
``POST   /v1/operator-plane/tasks/checkout/``
``POST   /v1/operator-plane/tasks/release/``
``GET    /v1/operator-plane/gates/``
``POST   /v1/operator-plane/gates/``
``POST   /v1/operator-plane/org/export/``
``POST   /v1/operator-plane/org/import/``
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.operator_plane import (
    ApprovalError,
    BudgetHardStop,
    OperatorPlaneError,
    OrgPackError,
    TaskBusy,
    TaskNotHeld,
    charge_budget,
    checkout_task,
    decide_gate,
    export_live_org,
    gate_state,
    install_org_pack,
    list_budgets,
    list_gates,
    plane_summary,
    propose_gate,
    release_task,
    reset_budget,
    rollback_gate,
    set_budget_policy,
)
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


def _body(request) -> dict | Response:
    payload = request.data
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        return _error("JSON object required.", status.HTTP_400_BAD_REQUEST)
    return payload


def _call(fn):
    try:
        return fn()
    except BudgetHardStop as exc:
        return _error(str(exc), status.HTTP_409_CONFLICT)
    except TaskBusy as exc:
        return _error(str(exc), status.HTTP_409_CONFLICT)
    except TaskNotHeld as exc:
        return _error(str(exc), status.HTTP_409_CONFLICT)
    except ApprovalError as exc:
        return _error(str(exc), status.HTTP_409_CONFLICT)
    except OrgPackError as exc:
        return _error(str(exc), status.HTTP_400_BAD_REQUEST)
    except KeyError as exc:
        return _error(str(exc).strip("'"), status.HTTP_404_NOT_FOUND)
    except ValueError as exc:
        return _error(str(exc), status.HTTP_400_BAD_REQUEST)
    except OperatorPlaneError as exc:
        logger.warning("Operator plane error: %s", exc)
        return _error(str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)


class OperatorPlaneAPIView(APIView):
    """GET /v1/operator-plane/ — budgets, locks, and gates. Not a seat."""

    permission_classes = PERMISSIONS

    @extend_schema(
        operation_id="v1_operator_plane_summary",
        summary="Operator control plane summary (#1360)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, _request, *_args, **_kwargs):
        result = _call(plane_summary)
        if isinstance(result, Response):
            return result
        return Response(result)


class OperatorPlaneBudgetsAPIView(APIView):
    """GET/PUT /v1/operator-plane/budgets/"""

    permission_classes = PERMISSIONS

    @extend_schema(
        operation_id="v1_operator_plane_budgets_list",
        summary="List seat and team budgets",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, _request, *_args, **_kwargs):
        return Response({"object": "list", "data": list_budgets()})

    @extend_schema(
        operation_id="v1_operator_plane_budgets_put",
        summary="Set a seat or team budget policy",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def put(self, request, *_args, **_kwargs):
        body = _body(request)
        if isinstance(body, Response):
            return body

        def act():
            reset_usage = body.get("reset_usage", False)
            if not isinstance(reset_usage, bool):
                raise ValueError("reset_usage must be a boolean.")
            return set_budget_policy(
                scope=body.get("scope"),
                scope_id=body.get("scope_id"),
                token_limit=body.get("token_limit"),
                cost_micros_limit=body.get("cost_micros_limit"),
                hard_stop=body.get("hard_stop", True),
                reset_usage=reset_usage,
            )

        result = _call(act)
        if isinstance(result, Response):
            return result
        return Response(result)


class OperatorPlaneBudgetChargeAPIView(APIView):
    """POST /v1/operator-plane/budgets/charge/"""

    permission_classes = PERMISSIONS

    @extend_schema(
        operation_id="v1_operator_plane_budgets_charge",
        summary="Debit a seat or team budget",
        responses={200: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = _body(request)
        if isinstance(body, Response):
            return body

        def act():
            charged = charge_budget(
                scope=body.get("scope"),
                scope_id=body.get("scope_id"),
                tokens=body.get("tokens") or 0,
                cost_micros=body.get("cost_micros") or 0,
            )
            return charged if charged is not None else {"unlimited": True}

        result = _call(act)
        if isinstance(result, Response):
            return result
        return Response(result)


class OperatorPlaneBudgetResetAPIView(APIView):
    """POST /v1/operator-plane/budgets/reset/"""

    permission_classes = PERMISSIONS

    @extend_schema(
        operation_id="v1_operator_plane_budgets_reset",
        summary="Clear budget usage and lift a hard-stop",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = _body(request)
        if isinstance(body, Response):
            return body

        def act():
            return reset_budget(scope=body.get("scope"), scope_id=body.get("scope_id"))

        result = _call(act)
        if isinstance(result, Response):
            return result
        return Response(result)


class OperatorPlaneTaskCheckoutAPIView(APIView):
    permission_classes = PERMISSIONS

    @extend_schema(
        operation_id="v1_operator_plane_task_checkout",
        summary="Atomically check out a task execution lock",
        responses={200: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = _body(request)
        if isinstance(body, Response):
            return body

        def act():
            return checkout_task(
                str(body.get("task_id") or ""),
                str(body.get("worker_id") or ""),
                lease_s=body.get("lease_s"),
            )

        result = _call(act)
        if isinstance(result, Response):
            return result
        return Response(result)


class OperatorPlaneTaskReleaseAPIView(APIView):
    permission_classes = PERMISSIONS

    @extend_schema(
        operation_id="v1_operator_plane_task_release",
        summary="Release a task execution lock",
        responses={200: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = _body(request)
        if isinstance(body, Response):
            return body

        def act():
            release_task(
                str(body.get("task_id") or ""), str(body.get("worker_id") or "")
            )
            return {"released": True, "task_id": body.get("task_id")}

        result = _call(act)
        if isinstance(result, Response):
            return result
        return Response(result)


class OperatorPlaneGatesAPIView(APIView):
    permission_classes = PERMISSIONS

    @extend_schema(
        operation_id="v1_operator_plane_gates_list",
        summary="List approval gates, or one gate when subject_id is set",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        subject_id = str(request.query_params.get("subject_id") or "").strip()
        if not subject_id:
            return Response({"object": "list", "data": list_gates()})

        result = _call(lambda: gate_state(subject_id))
        if isinstance(result, Response):
            return result
        return Response(result)

    @extend_schema(
        operation_id="v1_operator_plane_gates_act",
        summary="Propose, decide, or roll back an approval gate",
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            409: OpenApiTypes.OBJECT,
        },
    )
    def post(self, request, *_args, **_kwargs):
        body = _body(request)
        if isinstance(body, Response):
            return body
        action = str(body.get("action") or "").strip().lower()

        def act():
            subject_id = str(body.get("subject_id") or "")
            actor = str(body.get("actor") or "")
            if action == "propose":
                return propose_gate(subject_id, body.get("snapshot"), actor=actor)
            if action == "decide":
                return decide_gate(
                    subject_id,
                    body.get("revision"),
                    approved=body.get("approved"),
                    actor=actor,
                    reason=str(body.get("reason") or ""),
                )
            if action == "rollback":
                return rollback_gate(
                    subject_id,
                    body.get("to_revision"),
                    actor=actor,
                    reason=str(body.get("reason") or ""),
                )
            raise ValueError("action must be propose, decide, or rollback.")

        result = _call(act)
        if isinstance(result, Response):
            return result
        return Response(result)


class OperatorPlaneExportAPIView(APIView):
    permission_classes = PERMISSIONS

    @extend_schema(
        operation_id="v1_operator_plane_org_export",
        summary="Export a secret-scrubbed org pack",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = _body(request)
        if isinstance(body, Response):
            return body
        name = str(body.get("name") or "org")
        result = _call(lambda: export_live_org(name=name))
        if isinstance(result, Response):
            return result
        return Response(result)


class OperatorPlaneImportAPIView(APIView):
    permission_classes = PERMISSIONS

    @extend_schema(
        operation_id="v1_operator_plane_org_import",
        summary="Import an org pack with collision handling",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = _body(request)
        if isinstance(body, Response):
            return body

        def act():
            return install_org_pack(
                body.get("pack"),
                on_collision=str(body.get("on_collision") or "rename"),
            )

        result = _call(act)
        if isinstance(result, Response):
            return result
        return Response(result)

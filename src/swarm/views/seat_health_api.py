"""Seat health API — one honest verdict for API, CLI and remote seats (#1658).

Batch-shaped on purpose: the frontend polls every seat it shows, so one request
per tick beats one per seat. The probe itself is cached in
:mod:`swarm.core.seat_health`, so a chatty client costs nothing extra.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.seat_doctor import MAX_SEATS
from swarm.core.seat_health import VALID_KINDS


class SeatHealthBatchView(APIView):
    """Probe many seats at once.

    POST /v1/seats/health
      body: {"seats": [{"kind": "api|cli|remote", "seat_id": "...", ...}], "force": false}
      -> 200 {"object": "seat_health_batch", "results": [{seat_id, kind, state,
          reason, latency_ms, checked_at, broken}, ...]}

    A broken seat is reported, never raised: this is a status poll.
    """

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_seats_health",
        summary="Probe API/CLI/remote seats for reachability (never raises).",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs) -> Response:
        from swarm.core import seat_health

        body: Any = request.data if isinstance(request.data, dict) else {}
        seats = body.get("seats")
        if not isinstance(seats, list):
            seats = []
        results = seat_health.probe_seats(seats, force=bool(body.get("force")))
        return Response(
            {
                "object": "seat_health_batch",
                "results": results,
                "checked": len(results),
                "broken": sum(1 for row in results if row.get("broken")),
            }
        )


class SeatDoctorView(APIView):
    """The seat doctor over HTTP, so the UI can ask the same question the CLI can.

    GET /v1/seats/doctor?kind=remote&deep=1&limit=50
      -> 200 the ``seat_doctor`` report payload, unchanged.

    This is the *diagnostic*, and it is deliberately NOT the same signal as the
    batch probe above. Do not merge them:

    * a batch probe is cheap liveness, polled every 60s, and its ``broken`` verdict
      is what the rail's ``⚠ broken`` label is allowed to claim;
    * the doctor is a bounded, evidence-backed audit that buckets a fault and names
      the remediation, and whose ``ok`` verdict is stricter than the probe's (only a
      *proved turn* is ``ok``; a ``--version`` and a health GET are ``unverified``).

    Writing doctor verdicts into the liveness store would let a 40-second audit
    silently relabel the rail, which is the exact false-positive failure this
    module exists to prevent. The two stay separate and the caller decides.

    Read-only and never polled: a client must ask for it, and it is bounded by
    :data:`swarm.core.seat_doctor.MAX_SEATS` seats and 8 workers.
    """

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_seats_doctor",
        summary="Audit every api/cli/remote seat and return bucket + remediation.",
        parameters=[
            OpenApiParameter(
                name="kind",
                type=str,
                many=True,
                required=False,
                description="Repeatable: api | cli | remote. Omit for all.",
            ),
            OpenApiParameter(
                name="deep",
                type=bool,
                required=False,
                description="Spend a real round trip per seat (slower, more evidence).",
            ),
            OpenApiParameter(
                name="limit", type=int, required=False, description=f"Max seats (default {MAX_SEATS})."
            ),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs) -> Response:
        from swarm.core.seat_doctor import report_payload

        raw_kinds = request.query_params.getlist("kind")
        kinds = [str(k).strip().lower() for k in raw_kinds if str(k).strip()]
        unknown = sorted({k for k in kinds if k not in VALID_KINDS})
        if unknown:
            return Response(
                {
                    "error": f"unknown kind(s): {', '.join(unknown)}",
                    "valid": sorted(VALID_KINDS),
                },
                status=400,
            )

        raw_limit = request.query_params.get("limit")
        if raw_limit in (None, ""):
            limit = MAX_SEATS
        else:
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                return Response({"error": f"limit must be an integer, got {raw_limit!r}"}, status=400)
            # A limit of 0 or a negative one would silently mean "audit nothing",
            # which reads as "everything is fine". Clamp instead of honouring it.
            limit = max(1, min(limit, MAX_SEATS))

        deep_raw = str(request.query_params.get("deep") or "").strip().lower()
        deep = deep_raw in {"1", "true", "yes", "on"}

        return Response(report_payload(deep=deep, limit=limit, kinds=kinds or None))


class SeatHealthView(APIView):
    """Probe one seat.

    POST /v1/seats/<kind>/<seat_id>/health -> the same row shape as a batch item.
    """

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_seat_health",
        summary="Probe one seat (kind = api | cli | remote).",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, kind: str, seat_id: str, *_args, **_kwargs) -> Response:
        from swarm.core import seat_health

        body: Any = request.data if isinstance(request.data, dict) else {}
        verdict = seat_health.probe_seat(
            kind,
            seat_id,
            force=bool(body.get("force")),
            **{k: v for k, v in body.items() if k in {"cli", "base_url", "api_key_env", "api_key_ref", "model"}},
        )
        return Response({"object": "seat_health", **verdict.as_dict()})

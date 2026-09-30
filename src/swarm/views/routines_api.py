"""Per-agent Routines API (REQ-80 / #432, REQ-884 / #285, #222, #1394).

GET/POST ``/v1/agents/<id>/routines/``
GET/PATCH/DELETE ``/v1/agents/<id>/routines/<routine_id>/``
POST ``/v1/agents/<id>/routines/<routine_id>/test-run/``
POST ``/v1/agents/<id>/routines/<routine_id>/run-now/``
GET/POST ``/v1/agents/<id>/routines/pack/`` — routines-domain pack fragment.
POST ``/v1/agents/<id>/routines/import/`` — import pending enable.
POST ``/v1/routines/github-merge/`` — inbound fake GitHub PR-merged event.
POST ``/v1/routines/events/github/`` — signed GitHub webhook ingest.
POST ``/v1/routines/mailbox-message/`` — inbound mailbox event for matching routines.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.activity_log import bound_activity_actor, request_actor_id
from swarm.core.chat_store import normalize_agent_id
from swarm.core.mcp_plugins import swarm_config
from swarm.core.routine_pack import (
    PackValidationError,
    build_pack,
    import_pack,
    validate_pack,
)
from swarm.core.routine_tools import public_routine_tool_catalog
from swarm.core.routines import (
    DuplicateRoutineError,
    apply_routine_fill_ins,
    create_routine,
    delete_routine,
    deliver_github_event,
    deliver_github_pr_merged,
    deliver_mailbox_message,
    enable_routine,
    get_routine,
    github_webhook_secret,
    list_all_routines,
    list_routines,
    routine_presets,
    run_now,
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


def _pack_error(exc: PackValidationError) -> Response:
    return Response({"error": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)


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
        description=(
            "Creates a routine. An identical routine (same name, instruction, and "
            "trigger, compared case/whitespace-insensitively) returns 409 with the "
            "existing routine id. Send `allow_duplicate: true` to create a "
            "deliberate copy (#1316)."
        ),
        responses={
            201: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            409: OpenApiTypes.OBJECT,
        },
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            routine = create_routine(agent, body)
        except DuplicateRoutineError as exc:
            existing = exc.existing or {}
            return Response(
                {
                    "object": "routine_conflict",
                    "error": str(exc),
                    "duplicate": True,
                    "existing_routine_id": exc.existing_id,
                    "existing_routine": (
                        _routine_payload(agent, existing) if existing else None
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )
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
        summary="Dry-run preview of trigger match + prompt (no live side effects) (#1405)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, routine_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            with bound_activity_actor(request_actor_id(request)):
                result = test_run(agent, routine_id)
        except KeyError:
            return _error("Routine not found.", status.HTTP_404_NOT_FOUND)
        except OSError:
            logger.exception("Failed to test-run routine %s for %s", routine_id, agent)
            return _error("Could not test-run routine.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        preview = result.get("preview") if isinstance(result.get("preview"), dict) else {}
        payload = _routine_payload(agent, result)
        payload["object"] = "routine_dry_run"
        payload["preview"] = preview
        payload["dry_run"] = True
        return Response(payload, status=status.HTTP_200_OK)


class AgentRoutineRunNowAPIView(APIView):
    """POST /v1/agents/<agent_id>/routines/<routine_id>/run-now/"""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_routine_run_now",
        summary="Run a routine now without waiting for its trigger (#222)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, routine_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            with bound_activity_actor(request_actor_id(request)):
                routine = run_now(agent, routine_id)
        except KeyError:
            return _error("Routine not found.", status.HTTP_404_NOT_FOUND)
        except OSError:
            logger.exception("Failed to run-now routine %s for %s", routine_id, agent)
            return _error("Could not run routine.", status.HTTP_500_INTERNAL_SERVER_ERROR)
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


class RoutineToolCatalogAPIView(APIView):
    """GET /v1/routines/tool-catalog/ — built-in + plugin/MCP picker rows (#1406).

    With `?instruction=<text>` the catalog is also RANKED by confidence against
    those instructions (#1454), so a small or local model is never handed a flat
    catalog. Without it the response is the unranked catalog, byte-identical to
    before, so this is purely additive.

    The ranker is `swarm.core.routine_tool_suggestions.rank_tools_by_confidence`
    — the same rules #1410 uses to detect tools the instructions name, extended
    with a confidence ordering. That module previously had NO importer anywhere
    in `src/`, so its tests proved nothing about the product; this is the seam
    that makes it reachable. It is deterministic (`-confidence, id`) and takes
    no model call on this path, so the response never waits on inference.

    `scorer` on each row names the ranking that produced it (`lexical` today), so
    a client can label the result honestly and detect a degrade rather than guess.
    """

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_routines_tool_catalog",
        summary="List routine tools and installed MCP connectors for the builder picker",
        parameters=[
            OpenApiParameter(
                name="instruction",
                type=str,
                required=False,
                description="Rank the catalog against this routine instruction (#1454).",
            ),
            OpenApiParameter(
                name="top_n", type=int, required=False, description="Keep the top N (named tools are never dropped)."
            ),
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        payload = public_routine_tool_catalog(swarm_config())

        instruction = (request.query_params.get("instruction") or "").strip()
        if not instruction:
            payload["ranked"] = False
            return Response(payload, status=status.HTTP_200_OK)

        raw_top_n = request.query_params.get("top_n")
        top_n = None
        if raw_top_n not in (None, ""):
            try:
                top_n = int(raw_top_n)
            except (TypeError, ValueError):
                return Response(
                    {"error": f"top_n must be an integer, got {raw_top_n!r}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if top_n < 1:
                # top_n=0 would silently return nothing, which reads as "this
                # routine has no tools" rather than as a bad request.
                return Response(
                    {"error": f"top_n must be >= 1, got {top_n}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        from swarm.core.routine_tool_suggestions import rank_tools_by_confidence

        ranked = rank_tools_by_confidence(
            instruction,
            payload.get("items") or [],
            top_n=top_n,
        )
        payload["items"] = ranked
        payload["ranked"] = True
        # `top_n` is a floor for tools the instructions name, so the list can
        # legitimately exceed it. Say so, rather than letting a client that
        # hard-caps at N conclude that a named tool was dropped.
        payload["named_count"] = sum(1 for row in ranked if row.get("named"))
        return Response(payload, status=status.HTTP_200_OK)


class RoutinePresetsAPIView(APIView):
    """GET /v1/routines/presets/ — pre-built routine templates (#862)."""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_routines_presets",
        summary="List pre-built routine templates (GitHub Issue Solver, PR Reviewer)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        return Response({"presets": routine_presets()}, status=status.HTTP_200_OK)


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


class MailboxRoutineMessageAPIView(APIView):
    """POST /v1/routines/mailbox-message/ — deliver a mailbox event to matching routines."""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_routines_mailbox_message",
        summary="Deliver a mailbox message event to matching Active routines (#222)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            fired = deliver_mailbox_message(body)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to deliver mailbox routine event")
            return _error("Could not deliver mailbox event.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(
            {
                "object": "routine_mailbox_delivery",
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


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return False


class AgentRoutinesPackAPIView(APIView):
    """GET/POST /v1/agents/<agent_id>/routines/pack/ — routines pack fragment (#1394)."""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_routines_pack_export",
        summary="Export this agent's routines as a fill-in pack fragment (#1394)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        include_presets = _truthy(request.query_params.get("presets") or request.query_params.get("include_presets"))
        try:
            pack = build_pack(agent, include_presets=include_presets)
        except PackValidationError as exc:
            return _pack_error(exc)
        return Response(pack, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_routines_pack_build",
        summary="Build a routines pack from selected ids and/or presets (#1394)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        ids = body.get("routine_ids") or body.get("ids")
        if ids is not None and not isinstance(ids, list):
            return _error("routine_ids must be a list.", status.HTTP_400_BAD_REQUEST)
        try:
            pack = build_pack(
                agent,
                routine_ids=[str(item) for item in ids] if isinstance(ids, list) else None,
                include_presets=_truthy(body.get("presets") or body.get("include_presets")),
            )
        except PackValidationError as exc:
            return _pack_error(exc)
        return Response(pack, status=status.HTTP_200_OK)


class AgentRoutinesImportAPIView(APIView):
    """POST /v1/agents/<agent_id>/routines/import/ — import pending enable (#1394)."""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_routines_pack_import",
        summary="Import a routines pack; rows stay inactive until enabled (#1394)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        pack_raw = body.get("pack") if isinstance(body.get("pack"), dict) else body
        fill_ins = body.get("fill_ins") if isinstance(body.get("fill_ins"), dict) else None
        if fill_ins is None and isinstance(body.get("fill_in_values"), dict):
            fill_ins = body.get("fill_in_values")
        try:
            payload = import_pack(agent, pack_raw, fill_ins=fill_ins)
        except PackValidationError as exc:
            return _pack_error(exc)
        payload["routines"] = [_routine_payload(agent, row) for row in payload.get("routines") or []]
        return Response(payload, status=status.HTTP_200_OK)


class RoutinePackValidateAPIView(APIView):
    """POST /v1/routines/packs/validate/ — validate without writing (#1394)."""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_routines_pack_validate",
        summary="Validate a routines pack fragment (fill-ins, no secrets) (#1394)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        pack_raw = body.get("pack") if isinstance(body.get("pack"), dict) else body
        try:
            pack = validate_pack(pack_raw)
        except PackValidationError as exc:
            return _pack_error(exc)
        return Response(pack, status=status.HTTP_200_OK)


class AgentRoutineFillAPIView(APIView):
    """POST .../routines/<id>/fill/ — apply pack fill-ins without enabling (#1394)."""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_routine_fill",
        summary="Apply routine pack fill-ins (repo, channel) without enabling (#1394)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, routine_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        mapping = body.get("fill_ins")
        if mapping is None and isinstance(body.get("fill_in_values"), dict):
            mapping = body.get("fill_in_values")
        if mapping is not None and not isinstance(mapping, dict):
            return _error("fill_ins must be an object of key → value.", status.HTTP_400_BAD_REQUEST)
        try:
            routine = apply_routine_fill_ins(agent, routine_id, mapping if isinstance(mapping, dict) else {})
        except KeyError:
            return _error("Routine not found.", status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to fill routine %s for %s", routine_id, agent)
            return _error("Could not save routine.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_routine_payload(agent, routine), status=status.HTTP_200_OK)


class AgentRoutineEnableAPIView(APIView):
    """POST .../routines/<id>/enable/ — enable only after fill-ins are supplied (#1394)."""

    permission_classes = ROUTINES_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_routine_enable",
        summary="Enable a routine after required fill-ins are supplied (#1394)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, _request, agent_id: str, routine_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            routine = enable_routine(agent, routine_id)
        except KeyError:
            return _error("Routine not found.", status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to enable routine %s for %s", routine_id, agent)
            return _error("Could not save routine.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_routine_payload(agent, routine), status=status.HTTP_200_OK)

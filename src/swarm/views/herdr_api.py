"""
JSON Herdr agents API (REQ-21).

Persist operator-facing Herdr members (kind=herdr) so open-swarm can drive
Herdr via the official ``herdr`` CLI. Empty ``remote`` = localhost (no
``--remote`` flag). This is not Hermes/OMB/Rakazo.

Endpoints:
    GET    /v1/herdr-agents/            -> persisted rows
    POST   /v1/herdr-agents/            -> 201 + row
    GET    /v1/herdr-agents/discover/   -> live ``herdr agent list`` +
                                           ``herdr workspace list`` as addable
                                           members (mocked in CI)
    GET    /v1/herdr-agents/status/     -> normalized per-pane status for every
                                           live Herdr agent (#1728). One
                                           ``herdr agent list`` call.
    GET    /v1/herdr-agents/<id>/       -> row (id or unique name)
    DELETE /v1/herdr-agents/<id>/       -> 204

Permissions match /v1/teams/: HasValidTokenOrSession when API auth is on,
otherwise AllowAny.
"""

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.remotes import RemoteError
from swarm.herdr.client import HerdrCLIError, HerdrClient
from swarm.herdr.status import pane_statuses
from swarm.models import HerdrAgent
from swarm.permissions import HasValidTokenOrSession
from swarm.serializers import HerdrAgentSerializer
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

HERDR_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def herdr_client(remote: str = "") -> HerdrClient:
    """Same client Settings operate uses when ``remotes.herdr`` is configured.

    Explicit ``?remote=`` still prefixes ``herdr --remote``. Missing remotes
    card falls back to localhost (no ``--remote``). Tests patch this factory.
    """
    if (remote or "").strip():
        return HerdrClient(remote=remote)
    try:
        return HerdrClient.from_remote_config()
    except RemoteError:
        return HerdrClient(remote="")


def _lookup_agent(lookup: str) -> HerdrAgent | None:
    raw = (lookup or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        found = HerdrAgent.objects.filter(pk=int(raw)).first()
        if found:
            return found
    return HerdrAgent.objects.filter(name=raw).first()


class HerdrAgentsAPIView(APIView):
    """GET /v1/herdr-agents/  POST /v1/herdr-agents/"""

    permission_classes = HERDR_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_herdr_agents_list",
        summary="List Herdr agent rows",
        description=(
            "List persisted Herdr members (kind=herdr). Empty `remote` means "
            "localhost — invoke `herdr` with no `--remote`. Not Hermes/OMB/Rakazo."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        try:
            rows = HerdrAgent.objects.all().order_by("name")
            data = HerdrAgentSerializer(rows, many=True).data
            return Response({"object": "list", "data": data}, status=status.HTTP_200_OK)
        except Exception:
            logger.exception("Error listing Herdr agents.")
            return Response(
                {"error": "Failed to list Herdr agents."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        operation_id="v1_herdr_agents_create",
        summary="Add a Herdr agent row",
        description=(
            "`name` is required. `remote` is optional (default empty = localhost). "
            "Examples: you@gpu-box, workbox, ssh://you@server:2222."
        ),
        request=inline_serializer(
            name="HerdrAgentCreateRequest",
            fields={
                "name": serializers.CharField(help_text="Operator-facing name (unique)."),
                "remote": serializers.CharField(
                    required=False,
                    allow_blank=True,
                    help_text="herdr --remote target; empty = localhost.",
                ),
            },
        ),
        examples=[
            OpenApiExample(
                "Localhost",
                value={"name": "local-herdr"},
                request_only=True,
            ),
            OpenApiExample(
                "SSH remote",
                value={"name": "workbox", "remote": "you@gpu-box"},
                request_only=True,
            ),
        ],
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        try:
            serializer = HerdrAgentSerializer(data=request.data or {})
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            name = serializer.validated_data["name"]
            if HerdrAgent.objects.filter(name=name).exists():
                return Response(
                    {"error": f"Herdr agent '{name}' already exists."},
                    status=status.HTTP_409_CONFLICT,
                )
            agent = serializer.save()
            return Response(HerdrAgentSerializer(agent).data, status=status.HTTP_201_CREATED)
        except Exception:
            logger.exception("Error creating Herdr agent.")
            return Response(
                {"error": "Failed to create Herdr agent."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class HerdrDiscoverAPIView(APIView):
    """GET /v1/herdr-agents/discover/ — live agent/workspace list as addable members."""

    permission_classes = HERDR_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_herdr_agents_discover",
        summary="Discover live Herdr agents and workspaces",
        description=(
            "Runs `herdr agent list` and `herdr workspace list` (no `--remote` "
            "unless `remote` is passed). Returns addable members with "
            "`kind=herdr` and empty remote = localhost. Cloud CI must mock "
            "`herdr`; do not target a WORKING grok pane."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        remote = (request.query_params.get("remote") or "").strip()
        client = herdr_client(remote)
        try:
            data = client.discover_members()
        except HerdrCLIError as exc:
            logger.info("Herdr discover skipped: %s", exc)
            return Response(
                {
                    "object": "list",
                    "data": [],
                    "kind": "herdr",
                    "herdr_available": False,
                    "error": str(exc),
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            logger.exception("Error discovering Herdr members.")
            return Response(
                {"error": "Failed to discover Herdr members."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        saved = set(HerdrAgent.objects.values_list("name", flat=True))
        for item in data:
            item["added"] = item.get("name") in saved
        return Response(
            {
                "object": "list",
                "data": data,
                "kind": "herdr",
                "herdr_available": True,
            },
            status=status.HTTP_200_OK,
        )


class HerdrStatusAPIView(APIView):
    """GET /v1/herdr-agents/status/ — interrogate Herdr's live state (#1728).

    One ``herdr agent list`` answers for every pane, so this is a single
    subprocess rather than a query per seat. Each row carries the OS status
    (:mod:`swarm.herdr.status`) *and* the raw Herdr ``agent_status`` it was
    derived from, so a client can show what OS actually read.

    **Fails open, honestly.** A missing CLI, a stopped Herdr server, an SSH hop
    that refuses, or a timeout all answer ``200`` with
    ``herdr_available: false``, an empty list, and the real reason in ``error``.
    A pane whose status OS cannot vouch for reports ``"unknown"`` — never
    ``"idle"``, which would read as "nothing is happening" when the truth is
    "we do not know". This mirrors ``/v1/herdr-agents/discover/`` so the two
    Herdr query surfaces degrade the same way.
    """

    permission_classes = HERDR_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_herdr_agents_status",
        summary="Query live Herdr agent/session status",
        description=(
            "Runs `herdr agent list` (no `--remote` unless `remote` is passed) "
            "and returns one normalized row per pane. `status` is one of "
            "`unknown` | `idle` | `working` | `waiting` | `finished`, mapped "
            "from Herdr's `idle`/`working`/`blocked`/`done`. When the CLI is "
            "missing, the server is down, or the host answers with something "
            "unexpected, the response is still `200` with "
            "`herdr_available: false` and an `error` string — a down Herdr "
            "must never block the UI or fabricate a status."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        remote = (request.query_params.get("remote") or "").strip()
        client = herdr_client(remote)
        try:
            payload = client.agent_list()
        except HerdrCLIError as exc:
            # The CLI is missing, the server is not running, or the SSH hop
            # refused. Honest: say so, and report no panes.
            logger.info("Herdr status query failed: %s", exc)
            return Response(
                {
                    "object": "list",
                    "data": [],
                    "kind": "herdr",
                    "herdr_available": False,
                    "error": str(exc),
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            logger.exception("Error querying Herdr status.")
            return Response(
                {"error": "Failed to query Herdr status."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        rows = [row.as_dict() for row in pane_statuses(payload)]
        return Response(
            {
                "object": "list",
                "data": rows,
                "kind": "herdr",
                "herdr_available": True,
                "error": None,
            },
            status=status.HTTP_200_OK,
        )


class HerdrAgentDetailAPIView(APIView):
    """GET/DELETE /v1/herdr-agents/<id>/ (numeric pk or unique name)."""

    permission_classes = HERDR_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_herdr_agents_retrieve",
        summary="Read one Herdr agent row",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = _lookup_agent(agent_id)
        if agent is None:
            return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(HerdrAgentSerializer(agent).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_herdr_agents_delete",
        summary="Remove a Herdr agent row",
        responses={204: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def delete(self, request, agent_id: str, *_args, **_kwargs):
        try:
            agent = _lookup_agent(agent_id)
            if agent is None:
                return Response({"error": "not found"}, status=status.HTTP_404_NOT_FOUND)
            agent.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception:
            logger.exception("Error deleting Herdr agent '%s'.", agent_id)
            return Response(
                {"error": "Failed to delete Herdr agent."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

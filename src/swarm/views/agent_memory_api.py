"""Per-agent memory API (#1390).

GET/POST ``/v1/agents/<id>/memories/``
DELETE ``/v1/agents/<id>/memories/<memory_id>/``
GET ``/v1/agents/<id>/memories/pack/``
POST ``/v1/agents/<id>/memories/import/``

SPA surface is #1391.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.agent_memory import (
    PACK_OBJECT,
    create_memory,
    delete_memory,
    export_pack_fragment,
    import_pack_fragment,
    list_memories,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

MEMORY_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


def _memory_payload(memory: dict) -> dict:
    return {"object": "agent_memory", **memory}


def _list_payload(agent_id: str, memories: list[dict]) -> dict:
    return {
        "object": "agent_memory_list",
        "agent_id": agent_id,
        "memories": [_memory_payload(row) for row in memories],
    }


class AgentMemoriesAPIView(APIView):
    """GET/POST /v1/agents/<agent_id>/memories/"""

    permission_classes = MEMORY_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_memories_list",
        summary="List memories for one agent (#1390)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        kind = request.query_params.get("kind") or request.query_params.get("kinds")
        tier = request.query_params.get("tier")
        try:
            rows = list_memories(agent, kind=kind, tier=tier)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to list memories for %s", agent)
            return _error("Could not read memories.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_list_payload(agent, rows), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_memories_create",
        summary="Create a memory for one agent (#1390)",
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            memory = create_memory(agent, body)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to create memory for %s", agent)
            return _error("Could not save memory.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_memory_payload(memory), status=status.HTTP_201_CREATED)


class AgentMemoryDetailAPIView(APIView):
    """DELETE /v1/agents/<agent_id>/memories/<memory_id>/"""

    permission_classes = MEMORY_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_memory_delete",
        summary="Delete one agent memory (#1390)",
        responses={204: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def delete(self, _request, agent_id: str, memory_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            deleted = delete_memory(agent, memory_id)
        except OSError:
            logger.exception("Failed to delete memory for %s", agent)
            return _error("Could not delete memory.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        if not deleted:
            return _error("Memory not found.", status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentMemoryPackAPIView(APIView):
    """GET /v1/agents/<agent_id>/memories/pack/ — template pack fragment."""

    permission_classes = MEMORY_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_memory_pack_export",
        summary="Export scrubbed profile/log memories as a pack fragment (#1390)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, _request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            fragment = export_pack_fragment(agent)
        except OSError:
            logger.exception("Failed to export memories for %s", agent)
            return _error("Could not read memories.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(fragment, status=status.HTTP_200_OK)


class AgentMemoryImportAPIView(APIView):
    """POST /v1/agents/<agent_id>/memories/import/ — write scrubbed pack rows."""

    permission_classes = MEMORY_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_memory_pack_import",
        summary="Import a scrubbed memory pack fragment onto one agent (#1390)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data
        try:
            written = import_pack_fragment(agent, body)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to import memories for %s", agent)
            return _error("Could not import memories.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(
            {
                "object": PACK_OBJECT,
                "agent_id": agent,
                "imported": len(written),
                "memories": [_memory_payload(row) for row in written],
            },
            status=status.HTTP_200_OK,
        )

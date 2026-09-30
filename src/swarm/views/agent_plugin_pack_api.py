"""Per-agent plugin pack API (#1396).

GET  ``/v1/agents/<id>/plugins/``         current ids + host status
GET  ``/v1/agents/<id>/plugins/pack/``    pack fragment (marketplace ids only)
POST ``/v1/agents/<id>/plugins/import/``  install/enable; missing-auth vs missing-plugin

Backend only — SPA picker is #1397. Responses never include tokens,
``url``, ``command``, ``headers``, or env values.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.agent_plugin_pack import (
    PluginPackError,
    export_pack,
    host_status,
    import_pack,
)
from swarm.core.chat_store import normalize_agent_id

logger = logging.getLogger(__name__)


def _error(exc: Exception) -> Response:
    if isinstance(exc, PluginPackError):
        return Response({"error": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, ValueError):
        return Response({"error": str(exc), "code": "bad_payload"}, status=status.HTTP_400_BAD_REQUEST)
    logger.exception("Agent plugin pack API failed")
    return Response(
        {"error": "Plugin pack request failed.", "code": "plugin_pack_error"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


class AgentPluginsAPIView(APIView):
    """GET /v1/agents/<agent_id>/plugins/ — ids + host status, no tokens."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_agent_plugins_get",
        summary="List this agent's packed plugin ids and host install status (#1396)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, _request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            return Response(host_status(agent), status=status.HTTP_200_OK)
        except Exception as exc:
            return _error(exc)


class AgentPluginPackAPIView(APIView):
    """GET /v1/agents/<agent_id>/plugins/pack/ — template pack fragment."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_agent_plugin_pack_export",
        summary="Export this agent's plugin ids as a secret-free pack fragment (#1396)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, _request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            return Response(export_pack(agent), status=status.HTTP_200_OK)
        except Exception as exc:
            return _error(exc)


class AgentPluginPackImportAPIView(APIView):
    """POST /v1/agents/<agent_id>/plugins/import/ — write ids; status without tokens."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_agent_plugin_pack_import",
        summary="Import plugin ids onto one agent and report host status without tokens (#1396)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data
        try:
            return Response(import_pack(agent, body), status=status.HTTP_200_OK)
        except Exception as exc:
            return _error(exc)

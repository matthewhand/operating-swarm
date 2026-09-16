"""Per-agent MCP tools API (#142).

GET/PATCH ``/v1/agents/<id>/mcp/`` — mode + allowed servers
GET ``/v1/agents/<id>/mcp/tools/`` — list tools (all + progressive)
GET ``/v1/agents/<id>/mcp/tools/<name>/`` — inspect one tool
POST ``/v1/agents/<id>/mcp/tools/<name>/execute/`` — execute one tool
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core.agent_mcp import (
    KEY_MODE,
    KEY_SERVERS,
    McpAccessError,
    execute_tool,
    get_mcp,
    inspect_tool,
    list_tools,
    update_mcp,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.core.mcp_plugins import McpPluginError

logger = logging.getLogger(__name__)


def _error(message: str, code: int, *, error_code: str | None = None) -> Response:
    payload: dict[str, str] = {"error": message}
    if error_code:
        payload["code"] = error_code
    return Response(payload, status=code)


def _fail(exc: Exception) -> Response:
    if isinstance(exc, McpAccessError):
        return _error(str(exc), exc.status, error_code=exc.code)
    if isinstance(exc, McpPluginError):
        return _error(str(exc), exc.status, error_code=exc.code)
    if isinstance(exc, ValueError):
        return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code="bad_payload")
    logger.exception("Agent MCP API failed")
    return _error("MCP request failed.", status.HTTP_500_INTERNAL_SERVER_ERROR, error_code="mcp_error")


def _config_payload(agent_id: str, mcp: dict) -> dict:
    return {
        "object": "agent_mcp",
        "agent_id": agent_id,
        "mcp_mode": mcp.get(KEY_MODE),
        "mode": mcp.get(KEY_MODE),
        "mcp_servers": list(mcp.get(KEY_SERVERS) or []),
        "enabled": bool(mcp.get("enabled")),
    }


class AgentMcpAPIView(APIView):
    """GET/PATCH /v1/agents/<agent_id>/mcp/"""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_agent_mcp_get",
        summary="Get MCP tool mode for an API managed agent",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        return Response(_config_payload(agent, get_mcp(agent)), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_mcp_patch",
        summary="Set MCP tool mode (all or progressive) for an API managed agent",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def patch(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            mcp = update_mcp(agent, body)
        except Exception as exc:
            return _fail(exc)
        return Response(_config_payload(agent, mcp), status=status.HTTP_200_OK)


class AgentMcpToolsAPIView(APIView):
    """GET /v1/agents/<agent_id>/mcp/tools/"""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_agent_mcp_tools_list",
        summary="List MCP tools available to this agent",
        responses={200: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            tools = list_tools(agent)
        except Exception as exc:
            return _fail(exc)
        mcp = get_mcp(agent)
        return Response(
            {
                "object": "mcp_tool_list",
                "agent_id": agent,
                "mcp_mode": mcp.get(KEY_MODE),
                "tools": tools,
            },
            status=status.HTTP_200_OK,
        )


class AgentMcpToolDetailAPIView(APIView):
    """GET /v1/agents/<agent_id>/mcp/tools/<tool_name>/"""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_agent_mcp_tool_inspect",
        summary="Inspect one MCP tool (description and parameters)",
        responses={200: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, tool_name: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            details = inspect_tool(agent, tool_name)
        except Exception as exc:
            return _fail(exc)
        return Response(
            {"object": "mcp_tool", "agent_id": agent, **details},
            status=status.HTTP_200_OK,
        )


class AgentMcpToolExecuteAPIView(APIView):
    """POST /v1/agents/<agent_id>/mcp/tools/<tool_name>/execute/"""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_agent_mcp_tool_execute",
        summary="Execute one MCP tool this agent is allowed to use",
        responses={200: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, tool_name: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        if "arguments" in body and isinstance(body.get("arguments"), dict):
            arguments = body["arguments"]
        else:
            arguments = {
                key: value
                for key, value in body.items()
                if key not in {"arguments", "name", "tool", "tool_name"}
            }
        try:
            result = execute_tool(agent, tool_name, arguments)
        except Exception as exc:
            return _fail(exc)
        return Response(
            {"object": "mcp_tool_result", "agent_id": agent, **result},
            status=status.HTTP_200_OK,
        )

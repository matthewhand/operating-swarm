"""Mailbox ACL REST (REQ-162 / #573).

GET/PUT/DELETE over ``agent_mailbox_acl.json``. Per-agent or per-role
whitelist XOR blacklist. Entry kinds: agent, team, role, section. Support
defaults to whitelist everything. No secrets. No Neon.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.agent_mailbox_acl import (
    delete_agent_policy,
    delete_role_policy,
    public_policy,
    public_store,
    put_agent_policy,
    put_role_policy,
    resolve_acl_policy,
    resolve_role_policy,
)
from swarm.core.agent_roles import CANONICAL_ROLES, normalize_agent_role
from swarm.core.chat_store import normalize_agent_id
from swarm.core.team_isolation import role_of_member
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

ACL_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


def _agent_role(agent_id: str, request) -> str:
    body = request.data if isinstance(getattr(request, "data", None), dict) else {}
    explicit = body.get("role") if isinstance(body, dict) else None
    if explicit:
        return normalize_agent_role(explicit)
    query = request.query_params.get("role") if hasattr(request, "query_params") else None
    if query:
        return normalize_agent_role(query)
    return normalize_agent_role(role_of_member(agent_id, None, fallback=None))


class MailboxAclStoreAPIView(APIView):
    """GET /v1/mailbox-acl/ — full store + documented entry kinds."""

    permission_classes = ACL_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_mailbox_acl_store",
        summary="List mailbox ACL policies (per-agent and per-role)",
        description=(
            "Whitelist XOR blacklist for peer mailbox list_agents / send_message. "
            "Entries target agent, team, role, or section. Support defaults to whitelist everything."
        ),
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        return Response(public_store(), status=status.HTTP_200_OK)


class MailboxAclAgentAPIView(APIView):
    """GET/PUT/DELETE /v1/mailbox-acl/agents/<id>/"""

    permission_classes = ACL_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_mailbox_acl_agent_get",
        summary="Get effective mailbox ACL for one agent",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        role = _agent_role(agent, request)
        return Response(
            public_policy(resolve_acl_policy(agent, role), scope="agent"),
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        operation_id="v1_mailbox_acl_agent_put",
        summary="Set this agent's mailbox ACL (whitelist XOR blacklist)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def put(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        role = _agent_role(agent, request)
        try:
            put_agent_policy(agent, body.get("mode"), body.get("entries"))
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to persist mailbox ACL for agent %s", agent)
            return _error("Could not save mailbox ACL.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(
            public_policy(resolve_acl_policy(agent, role), scope="agent"),
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        operation_id="v1_mailbox_acl_agent_delete",
        summary="Clear this agent's mailbox ACL override (inherit role/default)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def delete(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        role = _agent_role(agent, request)
        delete_agent_policy(agent)
        return Response(
            public_policy(resolve_acl_policy(agent, role), scope="agent"),
            status=status.HTTP_200_OK,
        )


class MailboxAclRoleAPIView(APIView):
    """GET/PUT/DELETE /v1/mailbox-acl/roles/<role>/"""

    permission_classes = ACL_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_mailbox_acl_role_get",
        summary="Get mailbox ACL for one role",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request, role: str, *_args, **_kwargs):
        canonical = normalize_agent_role(role)
        if canonical not in CANONICAL_ROLES:
            return _error(f"Unknown role {role!r}.", status.HTTP_400_BAD_REQUEST)
        return Response(
            public_policy(resolve_role_policy(canonical), scope="role"),
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        operation_id="v1_mailbox_acl_role_put",
        summary="Set this role's mailbox ACL (whitelist XOR blacklist)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def put(self, request, role: str, *_args, **_kwargs):
        canonical = normalize_agent_role(role)
        if canonical not in CANONICAL_ROLES:
            return _error(f"Unknown role {role!r}.", status.HTTP_400_BAD_REQUEST)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            put_role_policy(canonical, body.get("mode"), body.get("entries"))
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to persist mailbox ACL for role %s", canonical)
            return _error("Could not save mailbox ACL.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(
            public_policy(resolve_role_policy(canonical), scope="role"),
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        operation_id="v1_mailbox_acl_role_delete",
        summary="Clear this role's mailbox ACL (restore default)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def delete(self, request, role: str, *_args, **_kwargs):
        canonical = normalize_agent_role(role)
        if canonical not in CANONICAL_ROLES:
            return _error(f"Unknown role {role!r}.", status.HTTP_400_BAD_REQUEST)
        delete_role_policy(canonical)
        return Response(
            public_policy(resolve_role_policy(canonical), scope="role"),
            status=status.HTTP_200_OK,
        )

"""Conversation directory API — list and hand off by conversation id (#1681).

Three endpoints over the canonical ``ChatConversation`` / ``ChatMessage``
store. No second registry: see :mod:`swarm.core.conversation_directory`.

======================================  =========================================
``GET  /v1/conversations/``             conversations the caller can see
``POST /v1/conversations/<id>/handoff`` message / handoff payload into an id
``POST /v1/conversations/<id>/move``    park a workstream with a status summary
======================================  =========================================

AuthZ is ownership. A caller sees and may post only into their own
conversations; an id owned by another user is reported exactly like an id that
does not exist, so the endpoint cannot be used to discover another tenant's
threads.
"""

from __future__ import annotations

import logging

from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND
from rest_framework.views import APIView

from swarm.core.conversation_directory import (
    ConversationNotFound,
    list_conversations,
    move_topic,
    post_to_conversation,
)
from swarm.views.agent_settings_api import SETTINGS_API_PERMISSIONS

logger = logging.getLogger(__name__)

# A handoff is a status line, not a document. Bounded so a caller cannot use
# this endpoint as an unbounded write into its own transcript.
MAX_HANDOFF_CHARS = 8000


def _not_found(cid: str) -> Response:
    # One message for "unknown" and "not yours".
    return Response(
        {
            "error": "unknown_conversation",
            "conversation_id": cid,
            "detail": "No such conversation for this account.",
        },
        status=HTTP_404_NOT_FOUND,
    )


def _body(request) -> dict:
    data = request.data
    return data if isinstance(data, dict) else {}


def _text(value) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))


class ConversationDirectoryView(APIView):
    """``GET /v1/conversations/`` — the conversations this account can see."""

    permission_classes = SETTINGS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_conversations_list",
        summary="List conversations (id, title, type, members) the caller can see",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        params = request.query_params
        raw_limit = _text(params.get("limit") or "").strip()
        limit = None
        if raw_limit:
            try:
                limit = int(raw_limit)
            except ValueError:
                return Response(
                    {"error": "invalid_limit", "detail": "limit must be an integer."},
                    status=HTTP_400_BAD_REQUEST,
                )
            if limit < 0:
                return Response(
                    {"error": "invalid_limit", "detail": "limit must not be negative."},
                    status=HTTP_400_BAD_REQUEST,
                )
        rows = list_conversations(
            request.user,
            agent_id=_text(params.get("agent_id") or "").strip(),
            limit=limit,
        )
        return Response(
            {
                "object": "conversation_list",
                "conversations": rows,
            },
            status=HTTP_200_OK,
        )


class ConversationHandoffView(APIView):
    """``POST /v1/conversations/<conversation_id>/handoff/``.

    Body: ``{"message": str, "role": "user"|"assistant"|"system",
    "from_conversation_id": str, "kind": str}``. ``message`` is required.
    """

    permission_classes = SETTINGS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_conversation_handoff",
        summary="Send a message / handoff payload into a named conversation id",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, conversation_id: str, *_args, **_kwargs):
        body = _body(request)
        message = _text(body.get("message") or body.get("content") or "").strip()
        if not message:
            return Response(
                {"error": "message_required", "detail": "message is required."},
                status=HTTP_400_BAD_REQUEST,
            )
        if len(message) > MAX_HANDOFF_CHARS:
            return Response(
                {
                    "error": "message_too_long",
                    "detail": f"message must be at most {MAX_HANDOFF_CHARS} characters.",
                },
                status=HTTP_400_BAD_REQUEST,
            )
        role = _text(body.get("role") or "user").strip() or "user"
        if role not in ("user", "assistant", "system"):
            return Response(
                {"error": "invalid_role", "detail": "role must be user, assistant or system."},
                status=HTTP_400_BAD_REQUEST,
            )
        try:
            row = post_to_conversation(
                request.user,
                conversation_id,
                {"role": role, "content": message},
                from_conversation_id=_text(body.get("from_conversation_id") or "").strip(),
                kind=_text(body.get("kind") or "").strip(),
            )
        except ConversationNotFound:
            return _not_found(conversation_id)
        except ValueError as exc:
            return Response({"error": "invalid_request", "detail": str(exc)}, status=HTTP_400_BAD_REQUEST)
        return Response(
            {"object": "conversation", "conversation": row, "delivered": True},
            status=HTTP_200_OK,
        )


class ConversationMoveTopicView(APIView):
    """``POST /v1/conversations/<conversation_id>/move/`` — park a workstream.

    Body: ``{"summary": str, "source_conversation_id": str}``. ``summary`` is
    required. Lands as one attributed turn in the target conversation; the
    source keeps its own history.
    """

    permission_classes = SETTINGS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_conversation_move_topic",
        summary="Park a workstream in a conversation with a short status summary",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request, conversation_id: str, *_args, **_kwargs):
        body = _body(request)
        summary = _text(body.get("summary") or "").strip()
        if not summary:
            return Response(
                {"error": "summary_required", "detail": "summary is required."},
                status=HTTP_400_BAD_REQUEST,
            )
        if len(summary) > MAX_HANDOFF_CHARS:
            return Response(
                {
                    "error": "summary_too_long",
                    "detail": f"summary must be at most {MAX_HANDOFF_CHARS} characters.",
                },
                status=HTTP_400_BAD_REQUEST,
            )
        try:
            row = move_topic(
                request.user,
                conversation_id,
                summary,
                source_conversation_id=_text(body.get("source_conversation_id") or "").strip(),
            )
        except ConversationNotFound as exc:
            # The offending id is named so a bad ``source_conversation_id`` is
            # not reported as if the target were missing.
            return _not_found(str(exc) or conversation_id)
        except ValueError as exc:
            return Response({"error": "invalid_request", "detail": str(exc)}, status=HTTP_400_BAD_REQUEST)
        return Response(
            {"object": "conversation", "conversation": row, "moved": True},
            status=HTTP_200_OK,
        )

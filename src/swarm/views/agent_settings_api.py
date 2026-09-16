"""Per-agent settings API (REQ-65).

GET/PATCH ``/v1/agents/<id>/settings/`` — agent-scoped only. Not global
Settings (Remotes / Retention / Hostname).
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.agent_sessions import (
    create_empty_session,
    list_agent_sessions,
    persist_allocated_session,
    session_to_dict,
)
from swarm.core.agent_settings import get_settings, update_settings
from swarm.core.chat_store import normalize_agent_id
from swarm.core.session_policy import allocate_task_session, list_active_task_sessions
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

SETTINGS_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int) -> Response:
    return Response({"error": message}, status=code)


def _payload(agent_id: str, settings: dict, request) -> dict:
    user = getattr(request, "user", None)
    user_key = ""
    try:
        from swarm.core.chat_store import user_key_for

        if user is not None and getattr(user, "is_authenticated", False):
            user_key = user_key_for(user)
    except Exception:
        user_key = ""
    sessions = list_active_task_sessions(user_key, agent_id) if user_key else []
    return {
        "object": "agent_settings",
        "agent_id": agent_id,
        "new_chat_per_task": bool(settings.get("new_chat_per_task")),
        "use_suggestions": bool(settings.get("use_suggestions")),
        "cli_session_id": settings.get("cli_session_id"),
        "remote_session_id": settings.get("remote_session_id"),
        "folder": settings.get("folder"),
        "speech_mode": settings.get("speech_mode") or "inherit",
        "tts_voice": settings.get("tts_voice") or "",
        "tts_voice_instruction": settings.get("tts_voice_instruction") or "",
        "stt_base_url": settings.get("stt_base_url") or "",
        "stt_model": settings.get("stt_model") or "",
        "stt_api_key_env": settings.get("stt_api_key_env") or "",
        "tts_base_url": settings.get("tts_base_url") or "",
        "tts_model": settings.get("tts_model") or "",
        "tts_api_key_env": settings.get("tts_api_key_env") or "",
        "auto_speak_replies": bool(settings.get("auto_speak_replies")),
        "active_sessions": sessions,
    }


class AgentSettingsAPIView(APIView):
    """GET/PATCH /v1/agents/<agent_id>/settings/"""

    permission_classes = SETTINGS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_settings_get",
        summary="Get agent-scoped settings (new chat per task)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        return Response(_payload(agent, get_settings(agent), request), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_settings_patch",
        summary="Update agent-scoped settings (new chat per task)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def patch(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        body = {
            key: value
            for key, value in body.items()
            if key not in {"object", "agent_id", "active_sessions"}
        }
        try:
            settings = update_settings(agent, body)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to persist agent settings for %s", agent)
            return _error("Could not save agent settings.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_payload(agent, settings, request), status=status.HTTP_200_OK)


class AgentTaskSessionAPIView(APIView):
    """GET/POST /v1/agents/<agent_id>/sessions/ — Django session list + create.

    POST ``{"new": true}`` (or ``{"empty": true}``) always mints an empty
    user session. POST without that flag keeps REQ-65 allocate-task behaviour.
    """

    permission_classes = SETTINGS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_sessions_list",
        summary="List Django-backed sessions for one agent (REQ-105)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        user = request.user
        user_key = ""
        try:
            from swarm.core.chat_store import user_key_for

            if user is not None and getattr(user, "is_authenticated", False):
                user_key = user_key_for(user)
        except Exception:
            user_key = ""
        active = list_active_task_sessions(user_key, agent) if user_key else []
        rows = list_agent_sessions(user, agent)
        return Response(
            {
                "object": "agent_session_list",
                "agent_id": agent,
                "sessions": [session_to_dict(row, active_ids=active) for row in rows],
            },
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        operation_id="v1_agent_task_session_create",
        summary="Allocate a chat session (task reuse, or New session)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        new_session = body.get("new") is True or body.get("empty") is True
        if new_session:
            labels = body.get("labels") if isinstance(body.get("labels"), list) else None
            title = str(body.get("title") or "").strip()
            row = create_empty_session(request.user, agent, title=title, labels=labels)
            payload = session_to_dict(row)
            payload.update(
                {
                    "object": "agent_session",
                    "new_chat_per_task": False,
                    "empty": True,
                    "resume_external": False,
                    "task_id": "",
                },
            )
            return Response(payload, status=status.HTTP_200_OK)

        task_id = str(body.get("task_id") or "").strip() or None
        session = allocate_task_session(request.user, agent, task_id=task_id)
        try:
            persist_allocated_session(
                request.user,
                agent,
                session.conversation_id,
                empty=session.empty,
            )
        except Exception:
            logger.exception("Failed to persist allocated session %s", session.conversation_id)
        return Response(
            {
                "object": "agent_task_session",
                "agent_id": session.agent_id,
                "conversation_id": session.conversation_id,
                "id": session.conversation_id,
                "new_chat_per_task": session.new_chat_per_task,
                "empty": session.empty,
                "resume_external": session.resume_external,
                "task_id": session.task_id,
            },
            status=status.HTTP_200_OK,
        )

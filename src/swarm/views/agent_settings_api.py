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

from swarm.core.activity_log import bound_activity_actor, request_actor_id
from swarm.core.agent_sessions import (
    create_empty_session,
    list_agent_sessions,
    persist_allocated_session,
    session_to_dict,
)
from swarm.core.agent_profile import (
    PACK_SECRET_KEYS,
    PROFILE_BODY_ALIASES,
    PROFILE_FIELD_KEY_SET,
    extract_profile_patch,
    rail_header_fields,
    serialize_template_pack,
)
from swarm.core.agent_settings import (
    get_profile,
    get_settings,
    replace_profile,
    update_profile,
    update_settings,
)
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
    identity = rail_header_fields(settings.get("profile"))
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
        "command_allowlist": settings.get("command_allowlist")
        or {"allow": [], "deny": [], "ask": []},
        "mcp_tool_grants": list(settings.get("mcp_tool_grants") or []),
        "mcp_tool_grants_set": bool(settings.get("mcp_tool_grants_set")),
        "active_sessions": sessions,
        **identity,
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
        profile_patch = extract_profile_patch(body)
        body = {
            key: value
            for key, value in body.items()
            if key not in {"object", "agent_id", "active_sessions"}
            and key not in PROFILE_BODY_ALIASES
        }
        if profile_patch is not None:
            body["profile"] = profile_patch
        try:
            with bound_activity_actor(request_actor_id(request)):
                # #1706 D.16 — the RAW `agent_id`, not the slugified `agent`.
                # `update_settings` normalizes for its own store key, but a
                # `chat:` / `team:` row id must reach the role gate intact or
                # the slug cannot classify and the write is wrongly accepted.
                settings = update_settings(agent_id, body)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to persist agent settings for %s", agent)
            return _error("Could not save agent settings.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_payload(agent, settings, request), status=status.HTTP_200_OK)


def _profile_payload(agent_id: str, profile: dict) -> dict:
    identity = rail_header_fields(profile)
    return {
        "object": "agent_profile",
        "agent_id": agent_id,
        **identity,
        "pack": serialize_template_pack(agent_id, profile),
    }


class AgentProfileAPIView(APIView):
    """GET/PUT/PATCH /v1/agents/<agent_id>/profile/ — storefront identity (#1388).

    PUT replaces the profile (missing fields become defaults). PATCH merges.
    GET returns rail/header fields plus a secret-free ``pack.profile`` section.
    """

    permission_classes = SETTINGS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_profile_get",
        summary="Get agent storefront / rail profile",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        return Response(_profile_payload(agent, get_profile(agent)), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_profile_put",
        summary="Replace agent storefront / rail profile",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def put(self, request, agent_id: str, *_args, **_kwargs):
        return self._write(request, agent_id, replace=True)

    @extend_schema(
        operation_id="v1_agent_profile_patch",
        summary="Update agent storefront / rail profile",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def patch(self, request, agent_id: str, *_args, **_kwargs):
        return self._write(request, agent_id, replace=False)

    def _write(self, request, agent_id: str, *, replace: bool):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        reserved = {"object", "agent_id", "pack", "profile", "storefront_description"}
        secret_keys = [key for key in body if key in PACK_SECRET_KEYS]
        if secret_keys:
            return _error(
                "Profile must not include secrets or session settings "
                f"({', '.join(sorted(secret_keys))}).",
                status.HTTP_400_BAD_REQUEST,
            )
        unknown = [
            key
            for key in body
            if key not in PROFILE_FIELD_KEY_SET and key not in reserved
        ]
        if unknown:
            return _error(
                f"Unknown profile field(s): {', '.join(sorted(unknown))}.",
                status.HTTP_400_BAD_REQUEST,
            )
        patch = extract_profile_patch(body)
        if patch is None:
            patch = body.get("profile") if isinstance(body.get("profile"), dict) else body
        try:
            # #1706 D.16 — the RAW `agent_id`, not the slugified `agent`.
            # `role` is a profile field, so this is a role write path too.
            # `update_profile` normalizes for its own store key, but a `chat:` /
            # `team:` row id must reach the role gate intact or the slug cannot
            # classify and the write is wrongly accepted.
            profile = replace_profile(agent_id, patch) if replace else update_profile(agent_id, patch)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to persist agent profile for %s", agent)
            return _error("Could not save agent profile.", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(_profile_payload(agent, profile), status=status.HTTP_200_OK)


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

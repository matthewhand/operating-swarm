"""Per-agent skills CRUD + pack (#1392).

GET/POST ``/v1/agents/<id>/skills/``
GET/PATCH/DELETE ``/v1/agents/<id>/skills/<name>/``
POST ``/v1/agents/<id>/pack/`` — selected skills as prose
POST ``/v1/agents/<id>/pack/import/`` — recreate skills; mark gettingStarted first-run
POST ``/v1/agent-packs/validate/`` — validate without writing

SPA editor is #1393. No secrets.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.agent_pack import (
    PackValidationError,
    build_pack,
    import_pack,
    validate_pack,
)
from swarm.core.agent_skills import (
    agent_skills_payload,
    create_skill,
    delete_skill,
    get_skill,
    set_getting_started,
    update_skill,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

SKILLS_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int, *, error_code: str | None = None) -> Response:
    payload: dict[str, str] = {"error": message}
    if error_code:
        payload["code"] = error_code
    return Response(payload, status=code)


def _skill_payload(agent_id: str, skill: dict) -> dict:
    return {
        "object": "agent_skill",
        "agent_id": agent_id,
        **skill,
    }


def _fail(exc: Exception) -> Response:
    if isinstance(exc, PackValidationError):
        return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code=exc.code)
    if isinstance(exc, KeyError):
        return _error(str(exc), status.HTTP_404_NOT_FOUND, error_code="skill_not_found")
    if isinstance(exc, ValueError):
        return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code="bad_payload")
    logger.exception("Agent skills API failed")
    return _error("Could not save agent skills.", status.HTTP_500_INTERNAL_SERVER_ERROR)


class AgentSkillsAPIView(APIView):
    """GET/POST/PATCH /v1/agents/<agent_id>/skills/"""

    permission_classes = SKILLS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_skills_list",
        summary="List prose skills attached to one agent (#1392)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        return Response(agent_skills_payload(agent), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_skills_create",
        summary="Create a prose skill or attach a library SKILL.md (#1392)",
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            skill = create_skill(agent, body)
        except Exception as exc:
            return _fail(exc)
        return Response(_skill_payload(agent, skill), status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="v1_agent_skills_patch_list",
        summary="Set gettingStarted.skill on this agent (#1392)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def patch(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        if "gettingStarted" not in body and "getting_started" not in body:
            return _error(
                "PATCH the list with gettingStarted.skill (must name an attached skill).",
                status.HTTP_400_BAD_REQUEST,
                error_code="bad_payload",
            )
        raw = body.get("gettingStarted", body.get("getting_started"))
        first_run = body.get("first_run")
        try:
            payload = set_getting_started(
                agent,
                raw,
                first_run=first_run if isinstance(first_run, bool) else None,
            )
        except Exception as exc:
            return _fail(exc)
        return Response(payload, status=status.HTTP_200_OK)


class AgentSkillDetailAPIView(APIView):
    """GET/PATCH/DELETE /v1/agents/<agent_id>/skills/<name>/"""

    permission_classes = SKILLS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_skill_get",
        summary="Get one agent skill (#1392)",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def get(self, request, agent_id: str, name: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        skill = get_skill(agent, name)
        if skill is None:
            return _error("Skill not found.", status.HTTP_404_NOT_FOUND, error_code="skill_not_found")
        return Response(_skill_payload(agent, skill), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_skill_patch",
        summary="Update one agent skill (#1392)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def patch(self, request, agent_id: str, name: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            skill = update_skill(agent, name, body)
        except Exception as exc:
            return _fail(exc)
        return Response(_skill_payload(agent, skill), status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_skill_delete",
        summary="Delete one agent skill (#1392)",
        responses={204: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def delete(self, request, agent_id: str, name: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        if not delete_skill(agent, name):
            return _error("Skill not found.", status.HTTP_404_NOT_FOUND, error_code="skill_not_found")
        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentPackAPIView(APIView):
    """POST /v1/agents/<agent_id>/pack/ — pack selected skills as prose."""

    permission_classes = SKILLS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_pack_export",
        summary="Pack selected skills as prose; gettingStarted.skill must name a packed skill",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        names = body.get("skills")
        skill_names: list[str] | None
        if names is None:
            skill_names = None
        elif isinstance(names, str) and names.strip():
            skill_names = [names.strip()]
        elif isinstance(names, list):
            skill_names = [str(item).strip() for item in names if str(item).strip()]
        else:
            return _error(
                "skills must be a list of skill names",
                status.HTTP_400_BAD_REQUEST,
                error_code="bad_payload",
            )
        started = body.get("gettingStarted", body.get("getting_started"))
        try:
            pack = build_pack(agent, skill_names=skill_names, getting_started=started)
        except Exception as exc:
            return _fail(exc)
        return Response(pack, status=status.HTTP_200_OK)


class AgentPackImportAPIView(APIView):
    """POST /v1/agents/<agent_id>/pack/import/ — recreate skills; mark first-run."""

    permission_classes = SKILLS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_pack_import",
        summary="Import a pack: recreate skills and mark gettingStarted for first-run",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        body = request.data if isinstance(request.data, dict) else {}
        pack_raw = body.get("pack") if isinstance(body.get("pack"), dict) else body
        try:
            payload = import_pack(agent, pack_raw)
        except Exception as exc:
            return _fail(exc)
        return Response(payload, status=status.HTTP_200_OK)


class AgentPackValidateAPIView(APIView):
    """POST /v1/agent-packs/validate/ — validate without writing."""

    permission_classes = SKILLS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_pack_validate",
        summary="Validate an agent pack (gettingStarted.skill must name a packed skill)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        pack_raw = body.get("pack") if isinstance(body.get("pack"), dict) else body
        try:
            pack = validate_pack(pack_raw)
        except Exception as exc:
            return _fail(exc)
        return Response(pack, status=status.HTTP_200_OK)

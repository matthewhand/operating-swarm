"""Unified agent template export/import APIs (#1398).

GET  ``/v1/agents/<id>/template/`` — export the stacked pack as JSON
POST ``/v1/agents/<id>/template/`` — same pack as a downloadable file
GET  ``/v1/agents/<id>/template/grok/`` — file projection, not a live Grok call
POST ``/v1/agents/<id>/template/import/`` — import a pack, Grok shape, or file
POST ``/v1/agent-templates/import/`` — create an agent from a pack or file upload
POST ``/v1/agent-templates/validate/`` — JSON Schema plus scrub, no writes
POST ``/v1/agent-templates/from-grok/`` — file mapper, Grok shape to canonical pack
GET  ``/v1/agent-templates/grok-mapper/`` — documented file-only mapper

Backend only — SPA gallery / installer is #1399.
"""

from __future__ import annotations

import json
import logging

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.agent_template import (
    TemplateValidationError,
    create_agent_from_template,
    export_template,
    from_grok_template,
    import_template,
    to_grok_template,
    validate_template,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.core.template_fragments import grok_mapper_document
from swarm.permissions import HasValidTokenOrSession
from swarm.settings import ENABLE_API_AUTH

logger = logging.getLogger(__name__)

TEMPLATE_API_PERMISSIONS = [HasValidTokenOrSession] if ENABLE_API_AUTH else [AllowAny]


def _error(message: str, code: int, *, error_code: str | None = None) -> Response:
    payload: dict[str, str] = {"error": message}
    if error_code:
        payload["code"] = error_code
    return Response(payload, status=code)


_MAX_UPLOAD_BYTES = 512_000


def _body(request) -> dict | list | str | None:
    """JSON object, list, or string. Non-JSON bodies stay empty."""
    data = getattr(request, "data", None)
    if isinstance(data, (dict, list, str)):
        return data
    return {}


def _uploaded_file(request):
    files = getattr(request, "FILES", None)
    if not files:
        return None
    return files.get("file") or files.get("pack")


def _template_payload(request):
    """JSON body, a nested template object, or a UTF-8 JSON file upload."""
    upload = _uploaded_file(request)
    if upload is not None:
        raw_bytes = upload.read(_MAX_UPLOAD_BYTES + 1)
        if len(raw_bytes) > _MAX_UPLOAD_BYTES:
            raise TemplateValidationError(
                "template file is too large", code="template_file_too_large"
            )
        try:
            decoded = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TemplateValidationError(
                "template file must be UTF-8 JSON",
                code="template_file_invalid",
            ) from exc
        try:
            return json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise TemplateValidationError(
                f"template file is not valid JSON: {exc.msg}",
                code="template_file_invalid",
            ) from exc
    body = _body(request)
    if isinstance(body, dict) and isinstance(body.get("template"), (dict, list)):
        return body["template"]
    return body


def _preferred_agent_id(request) -> str | None:
    """Honor an explicit agent_id field sent beside a file upload."""
    if _uploaded_file(request) is None:
        return None
    data = request.data if isinstance(getattr(request, "data", None), dict) else {}
    chosen = str(data.get("agent_id") or "").strip()
    return chosen or None


def _download(agent_id: str, pack: dict) -> HttpResponse:
    payload = json.dumps(pack, indent=2) + "\n"
    response = HttpResponse(payload, content_type="application/json")
    response["Content-Disposition"] = (
        f'attachment; filename="{agent_id}-agent-template.json"'
    )
    return response


class AgentTemplateAPIView(APIView):
    """GET /v1/agents/<agent_id>/template/ — export the unified pack."""

    permission_classes = TEMPLATE_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_template_export",
        summary="Export a secret-free agent template pack (#1398)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, _request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            pack = export_template(agent)
        except TemplateValidationError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code=exc.code)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        return Response(pack, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="v1_agent_template_export_download",
        summary="Download the agent template pack as a JSON file (#1398)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, _request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            pack = export_template(agent)
        except TemplateValidationError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code=exc.code)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        return _download(agent, pack)


class AgentTemplateGrokAPIView(APIView):
    """GET /v1/agents/<agent_id>/template/grok/ — Grok Bot dogfood projection."""

    permission_classes = TEMPLATE_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_template_grok_export",
        summary="Export the agent as a Grok Bot template (#1398)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, _request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            pack = to_grok_template(export_template(agent))
        except TemplateValidationError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code=exc.code)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        return Response(pack, status=status.HTTP_200_OK)


class AgentTemplateImportAPIView(APIView):
    """POST /v1/agents/<agent_id>/template/import/ — apply a pack onto a seat."""

    permission_classes = TEMPLATE_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_template_import",
        summary="Import an agent template or Grok Bot template onto one agent (#1398)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, agent_id: str, *_args, **_kwargs):
        agent = normalize_agent_id(agent_id)
        try:
            payload = import_template(agent, _template_payload(request))
        except TemplateValidationError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code=exc.code)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to import template for %s", agent)
            return _error(
                "Could not import template.", status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return Response(payload, status=status.HTTP_200_OK)


class AgentTemplateValidateAPIView(APIView):
    """POST /v1/agent-templates/validate/ — schema check, no writes."""

    permission_classes = TEMPLATE_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_template_validate",
        summary="Validate an agent template or Grok Bot template (#1398)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        try:
            pack = validate_template(_template_payload(request))
        except TemplateValidationError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code=exc.code)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        return Response(pack, status=status.HTTP_200_OK)


class AgentTemplateFromGrokAPIView(APIView):
    """POST /v1/agent-templates/from-grok/ — Grok → canonical pack, no writes."""

    permission_classes = TEMPLATE_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_template_from_grok",
        summary="Project a Grok Bot template into the canonical pack (#1398)",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        try:
            pack = from_grok_template(_template_payload(request))
        except TemplateValidationError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code=exc.code)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        return Response(pack, status=status.HTTP_200_OK)


class AgentTemplateCreateAPIView(APIView):
    """POST /v1/agent-templates/import/ — create an agent from a pack or file."""

    permission_classes = TEMPLATE_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_template_create",
        summary="Create an agent from a template pack or uploaded file (#1398)",
        responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        try:
            payload = _template_payload(request)
            result = create_agent_from_template(
                payload, agent_id=_preferred_agent_id(request)
            )
        except TemplateValidationError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST, error_code=exc.code)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        except OSError:
            logger.exception("Failed to create agent from template")
            return _error(
                "Could not import template.", status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        return Response(result, status=status.HTTP_201_CREATED)


class AgentTemplateGrokMapperAPIView(APIView):
    """GET /v1/agent-templates/grok-mapper/ — documented file mapper, no live call."""

    permission_classes = TEMPLATE_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_agent_template_grok_mapper",
        summary="Document the file-only Grok template mapper (#1398)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, _request, *_args, **_kwargs):
        return Response(grok_mapper_document(), status=status.HTTP_200_OK)

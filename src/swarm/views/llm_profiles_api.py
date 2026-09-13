"""REST surface for REQ-43 Settings default LLM + per-task override.

GET    /v1/llm-profiles/     configured profiles + effective default / map
POST   /v1/llm-profiles/     upsert a named profile (id + model + optional base_url)
PUT    /v1/llm-profiles/     same as POST
PATCH  /v1/llm-profiles/     persist settings.default_llm_profile (+ override)

Permissions follow ``api_permission_classes()`` — never guest-only. Responses
never include api keys or other secrets.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core import llm_task_routing as routing

logger = logging.getLogger(__name__)


def _payload(config=None) -> dict:
    return routing.settings_public_payload(config)


def _truthy(raw) -> bool:
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def _upsert_named_profile(body: dict):
    nested = body.get("profile") if isinstance(body.get("profile"), dict) else None
    src = nested if nested is not None else body
    profile_id = str(src.get("id") or src.get("name") or body.get("id") or "").strip()
    skip = {
        "id",
        "name",
        "object",
        "set_default",
        "default_llm_profile",
        "override_per_task",
        "task_llm_profiles",
        "profile",
    }
    spec = {key: value for key, value in src.items() if key not in skip}
    set_default = _truthy(src.get("set_default") if "set_default" in src else body.get("set_default"))
    if str(body.get("default_llm_profile") or "").strip() == profile_id:
        set_default = True
    return routing.persist_named_llm_profile(
        profile_id=profile_id,
        spec=spec,
        set_default=set_default,
    )


def _ownership_error_response(exc):
    from swarm.core.config_ownership import ConfigOwnershipError

    if isinstance(exc, ConfigOwnershipError):
        return Response({"error": str(exc), "code": exc.code}, status=exc.status)
    if isinstance(exc, OSError):
        logger.exception("Failed to persist LLM profile")
        return Response(
            {"error": f"failed to persist: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    raise exc


class LlmProfilesView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_llm_profiles_get",
        summary="List configured LLM profiles and the effective default / task map",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, _request, *_args, **_kwargs):
        try:
            return Response(_payload())
        except Exception:
            logger.exception("Failed to load LLM profile settings")
            return Response(
                {
                    "object": "llm_profiles",
                    "profiles": [],
                    "default_llm_profile": routing.BUILTIN_FALLBACK,
                    "default_is_auto": True,
                    "override_per_task": False,
                    "task_llm_profiles": {},
                    "auto_picks": {},
                    "warnings": ["Failed to load LLM profiles; using default."],
                    "routes": {},
                    "task_classes": list(routing.TASK_CLASSES),
                    "list_models_source": "stub",
                    "cli_model_lists": [],
                },
                status=status.HTTP_200_OK,
            )

    @extend_schema(
        operation_id="v1_llm_profiles_post",
        summary="Create or replace a named LLM profile (model + optional base URL)",
        request=inline_serializer(
            name="LlmProfilesUpsertRequest",
            fields={
                "id": serializers.CharField(),
                "model": serializers.CharField(),
                "base_url": serializers.CharField(required=False, allow_blank=True),
                "provider": serializers.CharField(required=False, allow_blank=True),
                "api_key": serializers.CharField(required=False, allow_blank=True),
                "set_default": serializers.BooleanField(required=False),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            cfg, path = _upsert_named_profile(body)
        except Exception as exc:
            return _ownership_error_response(exc)
        payload = _payload(cfg)
        payload["persisted_to"] = str(path)
        return Response(payload)

    def put(self, request, *_args, **_kwargs):
        return self.post(request, *_args, **_kwargs)

    @extend_schema(
        operation_id="v1_llm_profiles_patch",
        summary="Persist default LLM profile and optional per-task override",
        request=inline_serializer(
            name="LlmProfilesPatchRequest",
            fields={
                "default_llm_profile": serializers.CharField(required=False, allow_blank=True),
                "override_per_task": serializers.BooleanField(required=False),
                "task_llm_profiles": serializers.DictField(required=False),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def patch(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        if not any(
            key in body
            for key in ("default_llm_profile", "override_per_task", "task_llm_profiles")
        ):
            return Response(
                {
                    "error": (
                        "Provide at least one of default_llm_profile, "
                        "override_per_task, task_llm_profiles."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "default_llm_profile" in body:
            raw_default = body.get("default_llm_profile")
            default = "" if raw_default is None else str(raw_default)
        else:
            default = None

        override = body.get("override_per_task") if "override_per_task" in body else None
        if override is not None:
            if isinstance(override, str):
                override = override.strip().lower() in {"1", "true", "yes", "on"}
            else:
                override = bool(override)

        task_map = body.get("task_llm_profiles") if "task_llm_profiles" in body else None
        if task_map is not None and not isinstance(task_map, dict):
            return Response(
                {"error": "task_llm_profiles must be an object of task class → model id."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cfg, path = routing.persist_llm_settings(
                default_llm_profile=default,
                override_per_task=override,
                task_llm_profiles=task_map,
            )
        except Exception as exc:
            from swarm.core.config_ownership import ConfigOwnershipError

            if isinstance(exc, ConfigOwnershipError):
                return Response(
                    {"error": str(exc), "code": exc.code},
                    status=exc.status,
                )
            if isinstance(exc, OSError):
                logger.exception("Failed to persist LLM profile settings")
                return Response(
                    {"error": f"failed to persist: {exc}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            raise

        payload = _payload(cfg)
        payload["persisted_to"] = str(path)
        return Response(payload)

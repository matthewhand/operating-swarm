"""GET/PATCH ``/v1/preferences/`` — per-user rail chrome prefs (REQ-144).

Permissions follow ``api_permission_classes()`` — never guest-only. Responses
never include secrets. SQLite/Postgres only; no Neon.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core import user_preferences as prefs
from swarm.models.preferences import UserPreference

logger = logging.getLogger(__name__)


def _row_for(request) -> tuple[UserPreference | None, str, bool]:
    user, principal, guest = prefs.preference_identity(request)
    if user is not None:
        row = UserPreference.objects.filter(user=user).first()
        if row is None:
            row = UserPreference.objects.filter(principal=principal).first()
        return row, principal, guest
    return UserPreference.objects.filter(principal=principal).first(), principal, guest


def _payload(request, row: UserPreference | None) -> dict:
    _user, principal, guest = prefs.preference_identity(request)
    empty = row is None
    values = row.values if row is not None else None
    return prefs.public_payload(
        principal=principal,
        guest=guest,
        empty=empty,
        values=values,
    )


class UserPreferencesView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_preferences_get",
        summary="Load this caller's UI preferences (favourites, Hidden Bots, hostname)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        row, _principal, _guest = _row_for(request)
        return Response(_payload(request, row))

    @extend_schema(
        operation_id="v1_preferences_patch",
        summary="Persist favourites, Hidden Bots, and/or hostname override",
        request=inline_serializer(
            name="UserPreferencesPatchRequest",
            fields={
                "favourites": serializers.ListField(required=False),
                "hidden_agents": serializers.ListField(required=False),
                "hostname_override": serializers.CharField(
                    required=False, allow_blank=True
                ),
                "context_auto_compress_pct": serializers.IntegerField(
                    required=False, min_value=1, max_value=99
                ),
                "context_strategy": serializers.ChoiceField(
                    required=False, choices=["compress", "cull"]
                ),
                "context_cull_trigger_pct": serializers.IntegerField(
                    required=False, min_value=1, max_value=99
                ),
                "context_cull_fraction_pct": serializers.IntegerField(
                    required=False, min_value=1, max_value=99
                ),
                "theme": serializers.ChoiceField(
                    required=False, choices=["system", "light", "dark"]
                ),
                "theme_navbar_mode": serializers.ChoiceField(
                    required=False, choices=["if_not_system", "always", "never"]
                ),
                "bubble_theme": serializers.CharField(
                    required=False, allow_blank=True, max_length=64
                ),
                "values": serializers.DictField(required=False),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def patch(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        if not any(
            key in body
            for key in (
                "favourites",
                "hidden_agents",
                "hostname_override",
                prefs.AUTO_COMPRESS_KEY,
                prefs.CONTEXT_STRATEGY,
                prefs.CULL_TRIGGER_KEY,
                prefs.CULL_FRACTION_KEY,
                prefs.THEME_KEY,
                prefs.THEME_NAVBAR_MODE_KEY,
                prefs.BUBBLE_THEME_KEY,
                "values",
            )
        ):
            return Response(
                {
                    "error": (
                        "Provide at least one of favourites, hidden_agents, "
                        "hostname_override, context_auto_compress_pct, "
                        "context_strategy, context_cull_trigger_pct, "
                        "context_cull_fraction_pct, theme, theme_navbar_mode, "
                        "bubble_theme, values."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "favourites" in body and not isinstance(body.get("favourites"), list):
            return Response(
                {"error": "favourites must be a list of agent ids or {id, name} objects."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if "hidden_agents" in body and not isinstance(body.get("hidden_agents"), list):
            return Response(
                {"error": "hidden_agents must be a list of agent ids."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if "hostname_override" in body and body.get("hostname_override") is not None:
            if not isinstance(body.get("hostname_override"), str):
                return Response(
                    {"error": "hostname_override must be a string."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if "theme" in body and body.get("theme") is not None:
            if not isinstance(body.get("theme"), str):
                return Response(
                    {"error": "theme must be a string ('system', 'light', 'dark')."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if "theme_navbar_mode" in body and body.get("theme_navbar_mode") is not None:
            if not isinstance(body.get("theme_navbar_mode"), str):
                return Response(
                    {"error": "theme_navbar_mode must be a string ('if_not_system', 'always', 'never')."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if "bubble_theme" in body and body.get("bubble_theme") is not None:
            if not isinstance(body.get("bubble_theme"), str):
                return Response(
                    {"error": "bubble_theme must be a string."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if "values" in body and not isinstance(body.get("values"), dict):
            return Response(
                {"error": "values must be an object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, principal, _guest = prefs.preference_identity(request)
        row, _p, _g = _row_for(request)
        patch: dict = {}
        if "values" in body:
            patch.update(body["values"])
        if "favourites" in body:
            patch[prefs.FAVOURITES_KEY] = body["favourites"]
        if "hidden_agents" in body:
            patch[prefs.HIDDEN_KEY] = body["hidden_agents"]
        if "hostname_override" in body:
            patch[prefs.HOSTNAME_KEY] = body["hostname_override"]
        if prefs.AUTO_COMPRESS_KEY in body:
            patch[prefs.AUTO_COMPRESS_KEY] = body[prefs.AUTO_COMPRESS_KEY]
        if prefs.CONTEXT_STRATEGY in body:
            patch[prefs.CONTEXT_STRATEGY] = body[prefs.CONTEXT_STRATEGY]
        if prefs.CULL_TRIGGER_KEY in body:
            patch[prefs.CULL_TRIGGER_KEY] = body[prefs.CULL_TRIGGER_KEY]
        if prefs.CULL_FRACTION_KEY in body:
            patch[prefs.CULL_FRACTION_KEY] = body[prefs.CULL_FRACTION_KEY]
        if prefs.THEME_KEY in body:
            patch[prefs.THEME_KEY] = body[prefs.THEME_KEY]
        if prefs.THEME_NAVBAR_MODE_KEY in body:
            patch[prefs.THEME_NAVBAR_MODE_KEY] = body[prefs.THEME_NAVBAR_MODE_KEY]
        if prefs.BUBBLE_THEME_KEY in body:
            patch[prefs.BUBBLE_THEME_KEY] = body[prefs.BUBBLE_THEME_KEY]

        current = row.values if row is not None else {}
        merged = prefs.merge_values(current, patch)

        try:
            if row is None:
                row = UserPreference(user=user, principal=principal, values=merged)
                row.save()
            else:
                if user is not None and row.user_id is None:
                    row.user = user
                if not row.principal:
                    row.principal = principal
                row.values = merged
                row.save()
        except Exception:
            logger.exception("Failed to persist user preferences for %s", principal)
            return Response(
                {"error": "Could not save preferences."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(_payload(request, row))

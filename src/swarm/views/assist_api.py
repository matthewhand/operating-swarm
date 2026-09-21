"""#858 & #860: Assist APIs for prompt enhancement and inline autocompletion."""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.core.llm_assist import enhance_user_prompt
from swarm.core.llm_autocomplete import generate_autocomplete
from swarm.views.agent_settings_api import SETTINGS_API_PERMISSIONS

logger = logging.getLogger(__name__)


class EnhancePromptAPIView(APIView):
    """POST /v1/assist/enhance-prompt — expand and refine draft prompt via tiny model."""

    permission_classes = SETTINGS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_assist_enhance_prompt",
        summary="Enhance a draft user prompt via the tiny model override (#858)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        prompt = request.data.get("prompt", "")
        if not prompt or not isinstance(prompt, str) or not prompt.strip():
            return Response(
                {"error": "prompt is required and must be non-empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            enhanced = enhance_user_prompt(prompt.strip())
            return Response(
                {
                    "object": "assist.enhanced_prompt",
                    "prompt": prompt,
                    "enhanced": enhanced,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.warning("Enhance prompt failed: %s", exc)
            return Response(
                {"error": f"Enhance prompt failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ChatAutocompleteAPIView(APIView):
    """POST /v1/chat/autocomplete — inline ghost text completions via autocomplete model."""

    permission_classes = SETTINGS_API_PERMISSIONS

    @extend_schema(
        operation_id="v1_chat_autocomplete",
        summary="Generate inline ghost text completions for composer (#860)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        prefix = str(request.data.get("prefix") or "")
        suffix = str(request.data.get("suffix") or "")
        agent_id = str(request.data.get("agent_id") or "")
        conversation_id = str(request.data.get("conversation_id") or "")

        raw_max_tokens = request.data.get("max_tokens", 32)
        try:
            max_tokens = int(raw_max_tokens)
        except (ValueError, TypeError):
            max_tokens = 32

        if not prefix.strip():
            return Response(
                {
                    "object": "chat.autocomplete",
                    "completion": "",
                    "duration_ms": 0.0,
                },
                status=status.HTTP_200_OK,
            )

        try:
            completion, duration_ms = generate_autocomplete(
                prefix=prefix,
                suffix=suffix,
                agent_id=agent_id,
                conversation_id=conversation_id,
                max_tokens=max_tokens,
            )
            return Response(
                {
                    "object": "chat.autocomplete",
                    "completion": completion,
                    "duration_ms": duration_ms,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.warning("Chat autocomplete failed: %s", exc)
            return Response(
                {
                    "object": "chat.autocomplete",
                    "completion": "",
                    "duration_ms": 0.0,
                    "error": str(exc),
                },
                status=status.HTTP_200_OK,
            )

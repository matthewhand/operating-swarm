"""REST for Settings speech + custom STT/TTS (REQ-77 / #422).

GET/PATCH ``/v1/speech/`` — per-endpoint source (system|custom), base URL,
model id, api-key env name only.
POST ``/v1/speech/transcribe/`` — custom Whisper-style transcription.
POST ``/v1/speech/speak/`` — custom ``/v1/audio/speech``.

Empty/off never guesses a host. Responses never include live tokens.
"""

from __future__ import annotations

import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from django.http import HttpResponse
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes
from swarm.core import speech as speech_core

logger = logging.getLogger(__name__)


def _agent_id_from_request(request) -> str:
    body = getattr(request, "data", None)
    if isinstance(body, dict):
        raw = body.get("agent_id") or body.get("agent")
        if raw:
            return str(raw).strip()
    query = getattr(request, "query_params", None)
    if query is not None:
        raw = query.get("agent_id") or query.get("agent")
        if raw:
            return str(raw).strip()
    return ""


def _bind_for_request(request, *, settings=None):
    try:
        return speech_core.bind_for_agent(_agent_id_from_request(request), settings=settings)
    except Exception:
        logger.exception("speech bind: falling back to global settings")
        spec = settings if settings is not None else speech_core.load_settings()
        return speech_core.AgentSpeechBind(settings=spec)


def _settings_payload(probe: bool = True) -> dict:
    spec = speech_core.load_settings()
    if probe:
        return speech_core.probe_status(spec)
    payload = spec.public_dict()
    for kind, endpoint in (("stt", spec.stt), ("tts", spec.tts)):
        row = payload[kind]
        if endpoint.source != speech_core.SOURCE_CUSTOM:
            row["status"] = "system"
            row["detail"] = (
                "Using the browser/OS implementation. Status was not probed."
            )
        elif endpoint.custom_configured():
            row["status"] = "unknown"
            row["detail"] = f"Custom {kind.upper()} is configured. Status was not probed."
        else:
            row["status"] = "off"
            row["detail"] = (
                f"Custom {kind.upper()} is off. No host is used until you set a base URL."
            )
    return payload


class SpeechSettingsView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_speech_get",
        summary="Speech STT/TTS settings (env name only, no secrets)",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request, *_args, **_kwargs):
        probe = str(request.query_params.get("probe") or "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        return Response(_settings_payload(probe=probe))

    @extend_schema(
        operation_id="v1_speech_patch",
        summary="Persist STT/TTS source, base URL, model, and api-key env name",
        request=inline_serializer(
            name="SpeechPatchRequest",
            fields={
                "stt": serializers.DictField(required=False),
                "tts": serializers.DictField(required=False),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def patch(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        if "api_key" in body or (
            isinstance(body.get("stt"), dict) and "api_key" in body["stt"]
        ) or (
            isinstance(body.get("tts"), dict) and "api_key" in body["tts"]
        ):
            return Response(
                {"error": "Send api_key_env (environment variable name) only. Never a live token."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        kwargs: dict[str, dict] = {}
        for field in ("stt", "tts"):
            if field in body:
                if body[field] is None:
                    kwargs[field] = {}
                elif isinstance(body[field], dict):
                    kwargs[field] = body[field]
                else:
                    return Response(
                        {"error": f"{field} must be an object."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        if not kwargs:
            return Response(
                {"error": "Provide stt and/or tts (source, base_url, model, api_key_env)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            spec, path = speech_core.persist_settings(**kwargs)
        except speech_core.SpeechError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except OSError as exc:
            logger.exception("Failed to persist speech settings")
            return Response(
                {"error": f"failed to persist: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        payload = speech_core.probe_status(spec)
        payload["persisted_to"] = str(path)
        return Response(payload)


class SpeechTranscribeView(APIView):
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_speech_transcribe",
        summary="Transcribe audio via the configured custom OpenAI-compat STT endpoint",
        request=inline_serializer(
            name="SpeechTranscribeRequest",
            fields={"file": serializers.FileField(required=True)},
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        uploaded = request.FILES.get("file") or request.FILES.get("audio")
        if uploaded is None:
            return Response(
                {"error": "file is required (multipart audio)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = uploaded.read()
        spec = speech_core.load_settings()
        bind = _bind_for_request(request, settings=spec)
        try:
            text = speech_core.transcribe_audio(
                data,
                filename=getattr(uploaded, "name", "") or "audio.webm",
                content_type=getattr(uploaded, "content_type", "") or "audio/webm",
                settings=bind.settings,
            )
        except speech_core.SpeechError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "object": "transcription",
                "text": text,
                "path": "custom",
            }
        )


class SpeechSpeakView(APIView):
    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(
        operation_id="v1_speech_speak",
        summary="Synthesize speech via the configured custom OpenAI-compat TTS endpoint",
        request=inline_serializer(
            name="SpeechSpeakRequest",
            fields={
                "text": serializers.CharField(required=False, allow_blank=True),
                "input": serializers.CharField(required=False, allow_blank=True),
                "voice": serializers.CharField(required=False, allow_blank=True),
                "instruction": serializers.CharField(required=False, allow_blank=True),
                "agent_id": serializers.CharField(required=False, allow_blank=True),
            },
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        text = str(body.get("text") or body.get("input") or "").strip()
        spec = speech_core.load_settings()
        bind = _bind_for_request(request, settings=spec)
        voice = str(body.get("voice") or bind.voice or "").strip()
        instruction = str(body.get("instruction") or bind.instruction or "").strip()
        try:
            audio, content_type = speech_core.synthesize_speech(
                text,
                voice=voice,
                instruction=instruction,
                settings=bind.settings,
            )
        except speech_core.SpeechError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response = HttpResponse(audio, content_type=content_type or "audio/mpeg")
        response["X-Speech-Path"] = "custom"
        if bind.mode:
            response["X-Speech-Mode"] = bind.mode
        return response

"""Per-agent robot voice bind (#116). Stub HTTP only — no live paid calls."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from swarm.core import agent_settings as store
from swarm.core import speech as speech_core


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.setenv("SWARM_CONFIG_PATH", str(cfg))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    store.reset_agent_settings_cache()
    for name in (
        "SPEECH_STT_BASE_URL",
        "SPEECH_TTS_BASE_URL",
        "SPEECH_STT_SOURCE",
        "SPEECH_TTS_SOURCE",
        "STT_API_KEY",
        "TTS_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    yield cfg
    store.reset_agent_settings_cache()


def _enable_global_custom(cfg: Path) -> None:
    speech_core.persist_settings(
        stt={"source": "custom", "base_url": "http://127.0.0.1:9", "model": "global-stt"},
        tts={"source": "custom", "base_url": "http://127.0.0.1:9", "model": "global-tts"},
        config_path=cfg,
    )


def test_unset_bind_get_never_500s(api_client):
    resp = api_client.get("/v1/agents/missing-robot/settings/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["speech_mode"] == "inherit"
    assert body["auto_speak_replies"] is False
    assert body["tts_voice_instruction"] == ""


def test_inherit_speak_and_transcribe_hit_global(api_client, _isolate: Path):
    _enable_global_custom(_isolate)
    store.update_settings("worker", {"speech_mode": "inherit", "tts_voice_instruction": "ignored"})

    captured = {}

    def _transcribe(payload, **kwargs):
        captured["transcribe_settings"] = kwargs.get("settings")
        return "global hello"

    def _speak(text, **kwargs):
        captured["speak"] = kwargs
        return b"ID3global", "audio/mpeg"

    with patch("swarm.core.speech.transcribe_audio", side_effect=_transcribe):
        transcribed = api_client.post(
            "/v1/speech/transcribe/",
            {
                "file": SimpleUploadedFile("clip.webm", b"abc", content_type="audio/webm"),
                "agent_id": "worker",
            },
            format="multipart",
        )
    assert transcribed.status_code == 200
    assert transcribed.json()["text"] == "global hello"
    assert captured["transcribe_settings"].stt.model == "global-stt"

    with patch("swarm.core.speech.synthesize_speech", side_effect=_speak):
        spoken = api_client.post(
            "/v1/speech/speak/",
            {"text": "Read this", "agent_id": "worker"},
            format="json",
        )
    assert spoken.status_code == 200
    assert captured["speak"]["instruction"] == ""
    assert captured["speak"]["settings"].tts.model == "global-tts"


def test_voice_instruction_is_per_agent(api_client, _isolate: Path):
    _enable_global_custom(_isolate)
    store.update_settings(
        "bee",
        {
            "speech_mode": "voice",
            "tts_voice": "alloy",
            "tts_voice_instruction": "Speak like a bee.",
        },
    )
    store.update_settings(
        "blob",
        {
            "speech_mode": "voice",
            "tts_voice": "verse",
            "tts_voice_instruction": "Speak like a blob.",
        },
    )
    captured = []

    def _speak(text, **kwargs):
        captured.append(
            {
                "voice": kwargs.get("voice"),
                "instruction": kwargs.get("instruction"),
                "model": kwargs.get("settings").tts.model if kwargs.get("settings") else "",
            }
        )
        return b"ID3stub", "audio/mpeg"

    with patch("swarm.core.speech.synthesize_speech", side_effect=_speak):
        bee = api_client.post(
            "/v1/speech/speak/",
            {"text": "Hello", "agent_id": "bee"},
            format="json",
        )
        blob = api_client.post(
            "/v1/speech/speak/",
            {"text": "Hello", "agent_id": "blob"},
            format="json",
        )
    assert bee.status_code == 200
    assert blob.status_code == 200
    assert captured[0]["instruction"] == "Speak like a bee."
    assert captured[0]["voice"] == "alloy"
    assert captured[1]["instruction"] == "Speak like a blob."
    assert captured[1]["voice"] == "verse"
    assert captured[0]["model"] == "global-tts"
    assert captured[1]["model"] == "global-tts"


def test_endpoint_stores_env_placeholders_and_overlays_url(api_client, _isolate: Path):
    _enable_global_custom(_isolate)
    patched = api_client.patch(
        "/v1/agents/robot/settings/",
        {
            "speech_mode": "endpoint",
            "stt_base_url": "http://127.0.0.1:19",
            "tts_base_url": "http://127.0.0.1:19",
            "stt_api_key_env": "STT_API_KEY",
            "tts_api_key_env": "TTS_API_KEY",
            "tts_voice_instruction": "Robot voice.",
        },
        format="json",
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["speech_mode"] == "endpoint"
    assert body["stt_api_key_env"] == "STT_API_KEY"
    assert "api_key" not in body
    dumped = Path(_isolate.parent / "agent_settings.json").read_text(encoding="utf-8")
    assert "${STT_API_KEY}" in dumped
    assert "${TTS_API_KEY}" in dumped
    assert "sk-" not in dumped

    captured = {}

    def _speak(text, **kwargs):
        captured["settings"] = kwargs.get("settings")
        captured["instruction"] = kwargs.get("instruction")
        return b"ID3robot", "audio/mpeg"

    with patch("swarm.core.speech.synthesize_speech", side_effect=_speak):
        spoken = api_client.post(
            "/v1/speech/speak/",
            {"text": "Hi", "agent_id": "robot"},
            format="json",
        )
    assert spoken.status_code == 200
    assert captured["instruction"] == "Robot voice."
    assert captured["settings"].tts.base_url.rstrip("/") == "http://127.0.0.1:19"


def test_unset_bind_speak_never_500s(api_client, _isolate: Path):
    resp = api_client.post(
        "/v1/speech/speak/",
        {"text": "Hi", "agent_id": "no-such-agent"},
        format="json",
    )
    assert resp.status_code == 400
    assert "not configured" in resp.json()["error"]


def test_live_token_rejected_on_agent_settings(api_client):
    resp = api_client.patch(
        "/v1/agents/worker/settings/",
        {"speech_mode": "endpoint", "stt_api_key": "sk-live-secret"},
        format="json",
    )
    assert resp.status_code == 400
    assert "api_key_env" in resp.json()["error"]

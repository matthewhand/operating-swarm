"""REQ-77: speech persist, empty URL, stub STT/TTS. No live host / :8001."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from swarm.core import speech as speech_core


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, dict | bytes]] = {}
    hits: list[tuple[str, str]] = []
    last_body: bytes = b""

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        self.last_body = self.rfile.read(length) if length else b""
        type(self).last_body = self.last_body
        self.hits.append((method, path))
        status, body = self.routes.get((method, path), (404, {"error": "no route"}))
        self.send_response(status)
        if isinstance(body, bytes):
            self.send_header("Content-Type", "audio/mpeg")
            payload = body
        else:
            self.send_header("Content-Type", "application/json")
            payload = json.dumps(body).encode("utf-8")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def http_router():
    server = HTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield host, port, _Router
    server.shutdown()
    _Router.routes = {}
    _Router.hits = []
    _Router.last_body = b""


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.setenv("SWARM_CONFIG_PATH", str(cfg))
    for name in (
        "SPEECH_STT_BASE_URL",
        "SPEECH_TTS_BASE_URL",
        "SPEECH_STT_SOURCE",
        "SPEECH_TTS_SOURCE",
        "SPEECH_STT_MODEL",
        "SPEECH_TTS_MODEL",
        "STT_API_KEY",
        "TTS_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    yield cfg


def test_default_is_system_and_empty_url_does_not_guess_host(isolated_store: Path):
    spec = speech_core.load_settings()
    assert spec.stt.source == "system"
    assert spec.tts.source == "system"
    assert spec.stt.base_url == ""
    assert spec.tts.base_url == ""
    assert speech_core.transcriptions_url("") == ""
    assert speech_core.speech_url("") == ""
    probed = speech_core.probe_status(spec, opener=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no host")))
    assert probed["stt"]["status"] == "system"
    assert probed["tts"]["status"] == "system"
    assert "No custom host" in probed["stt"]["detail"]


def test_persist_stores_env_placeholder_not_key(isolated_store: Path):
    spec, path = speech_core.persist_settings(
        stt={
            "source": "custom",
            "base_url": "http://127.0.0.1:9",
            "model": "whisper-1",
            "api_key_env": "STT_API_KEY",
        },
        tts={
            "source": "system",
            "base_url": "http://127.0.0.1:9",
            "model": "tts-1",
            "api_key_env": "TTS_API_KEY",
        },
        config_path=isolated_store,
    )
    data = json.loads(isolated_store.read_text(encoding="utf-8"))
    assert data["speech"]["stt"]["api_key"] == "${STT_API_KEY}"
    assert data["speech"]["stt"]["api_key_env"] == "STT_API_KEY"
    assert data["speech"]["stt"]["source"] == "custom"
    assert data["speech"]["tts"]["source"] == "system"
    assert data["speech"]["tts"]["base_url"] == "http://127.0.0.1:9"
    pub = spec.public_dict()
    assert pub["stt"]["api_key_env"] == "STT_API_KEY"
    assert "api_key" not in pub["stt"]
    assert "sk-" not in json.dumps(pub)
    assert path == isolated_store


def test_system_source_does_not_probe_stored_custom_url(isolated_store: Path):
    spec, _ = speech_core.persist_settings(
        stt={"source": "system", "base_url": "http://127.0.0.1:9"},
        config_path=isolated_store,
    )
    called = []

    def _boom(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("must not call a host when source is system")

    probed = speech_core.probe_status(spec, opener=_boom)
    assert probed["stt"]["status"] == "system"
    assert probed["stt"]["configured"] is True
    assert called == []


def test_empty_custom_url_does_not_call_any_host(isolated_store: Path):
    spec, _ = speech_core.persist_settings(
        stt={"source": "custom", "base_url": ""},
        tts={"source": "custom", "base_url": ""},
        config_path=isolated_store,
    )
    called = []

    def _boom(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("must not call a host when custom URL is empty")

    probed = speech_core.probe_status(spec, opener=_boom)
    assert probed["stt"]["status"] == "off"
    assert "No host" in probed["stt"]["detail"]
    assert called == []
    with pytest.raises(speech_core.SpeechError, match="not configured"):
        speech_core.transcribe_audio(b"abc", settings=spec, opener=_boom)
    with pytest.raises(speech_core.SpeechError, match="not configured"):
        speech_core.synthesize_speech("hello", settings=spec, opener=_boom)
    assert called == []


def test_refuse_forbidden_hosts(isolated_store: Path):
    with pytest.raises(speech_core.SpeechError, match=":8001"):
        speech_core.persist_settings(
            stt={"base_url": "http://127.0.0.1:8001/v1"},
            config_path=isolated_store,
        )
    with pytest.raises(speech_core.SpeechError, match="open-litellm"):
        speech_core.persist_settings(
            tts={"base_url": "https://open-litellm.fly.dev/v1"},
            config_path=isolated_store,
        )


def test_refuse_live_api_key_on_persist(isolated_store: Path):
    with pytest.raises(speech_core.SpeechError, match="api_key_env"):
        speech_core.persist_settings(
            stt={"base_url": "http://127.0.0.1:9", "api_key": "sk-live-secret"},
            config_path=isolated_store,
        )
    assert "sk-live" not in isolated_store.read_text(encoding="utf-8")


def test_stub_transcribe_and_speak(isolated_store: Path, http_router):
    host, port, router = http_router
    router.routes[("POST", "/v1/audio/transcriptions")] = (200, {"text": "hello from stub"})
    router.routes[("POST", "/v1/audio/speech")] = (200, b"ID3stub-audio")
    spec, _ = speech_core.persist_settings(
        stt={
            "source": "custom",
            "base_url": f"http://{host}:{port}",
            "model": "whisper-1",
            "api_key_env": "STT_API_KEY",
        },
        tts={
            "source": "custom",
            "base_url": f"http://{host}:{port}",
            "model": "tts-1",
            "api_key_env": "TTS_API_KEY",
        },
        config_path=isolated_store,
    )
    text = speech_core.transcribe_audio(b"fake-webm", filename="clip.webm", settings=spec)
    assert text == "hello from stub"
    audio, ctype = speech_core.synthesize_speech(
        "Read this aloud",
        voice="alloy",
        instruction="Speak like a bee.",
        settings=spec,
    )
    assert audio == b"ID3stub-audio"
    assert "audio" in ctype
    sent = json.loads(router.last_body.decode("utf-8"))
    assert sent["voice"] == "alloy"
    assert sent["instruction"] == "Speak like a bee."
    assert ("POST", "/v1/audio/transcriptions") in router.hits
    assert ("POST", "/v1/audio/speech") in router.hits
    dumped = isolated_store.read_text(encoding="utf-8")
    assert "sk-" not in dumped
    assert ":8001" not in dumped

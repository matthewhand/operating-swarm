"""REQ-83: image-gen persist, empty URL, still avatars. No live host."""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from swarm.core import image_gen as image_gen_core

# 1x1 still PNG (not animated).
_STILL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_GIF = b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, dict | bytes]] = {}
    hits: list[tuple[str, str]] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        self.hits.append((method, path))
        status, body = self.routes.get((method, path), (404, {"error": "no route"}))
        self.send_response(status)
        if isinstance(body, bytes):
            self.send_header("Content-Type", "image/png")
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


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.setenv("SWARM_CONFIG_PATH", str(cfg))
    monkeypatch.setenv("SWARM_AGENT_AVATARS_PATH", str(tmp_path / "agent_avatars.json"))
    monkeypatch.setenv("SWARM_AVATAR_STORAGE", str(tmp_path / "avatars"))
    monkeypatch.delenv("IMAGE_GEN_BASE_URL", raising=False)
    monkeypatch.delenv("IMAGE_GEN_MODEL", raising=False)
    yield cfg


def test_persist_stores_env_placeholder_not_key(isolated_store: Path):
    spec, path = image_gen_core.persist_settings(
        base_url="http://127.0.0.1:9",
        model="local-still",
        api_key_env="IMAGE_GEN_API_KEY",
        config_path=isolated_store,
    )
    data = json.loads(isolated_store.read_text(encoding="utf-8"))
    assert data["image_gen"]["base_url"] == "http://127.0.0.1:9"
    assert data["image_gen"]["model"] == "local-still"
    assert data["image_gen"]["api_key"] == "${IMAGE_GEN_API_KEY}"
    assert data["image_gen"]["api_key_env"] == "IMAGE_GEN_API_KEY"
    pub = spec.public_dict()
    assert pub["api_key_env"] == "IMAGE_GEN_API_KEY"
    assert pub["api_key_set"] is False
    assert "sk-" not in json.dumps(pub)
    assert "IMAGE_GEN_API_KEY" not in json.dumps(pub) or pub["api_key_env"] == "IMAGE_GEN_API_KEY"
    dumped = json.dumps(pub)
    assert "sk-live" not in dumped
    assert path == isolated_store


def test_empty_url_does_not_call_any_host(isolated_store: Path):
    spec, _ = image_gen_core.persist_settings(base_url="", config_path=isolated_store)
    assert spec.configured() is False
    called = []

    def _boom(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("must not call a host when image-gen is off")

    probed = image_gen_core.probe_status(spec)
    assert probed["status"] == "off"
    assert "No host" in probed["detail"]

    with pytest.raises(image_gen_core.ImageGenError, match="not configured"):
        image_gen_core.generate_still("a still portrait", settings=spec, opener=_boom)
    assert called == []


def test_refuse_fly_litellm_persist(isolated_store: Path):
    with pytest.raises(image_gen_core.ImageGenError, match="open-litellm"):
        image_gen_core.persist_settings(
            base_url="https://open-litellm.fly.dev/v1",
            config_path=isolated_store,
        )


def test_stub_generations_returns_bytes_then_avatar_set(isolated_store: Path, http_router):
    host, port, router = http_router
    router.routes[("POST", "/v1/images/generations")] = (
        200,
        {"data": [{"b64_json": base64.b64encode(_STILL_PNG).decode("ascii")}]},
    )
    spec, _ = image_gen_core.persist_settings(
        base_url=f"http://{host}:{port}",
        model="stub-still",
        api_key_env="IMAGE_GEN_API_KEY",
        config_path=isolated_store,
    )
    url = image_gen_core.generate_and_store("codey", "still portrait of Codey", settings=spec)
    assert url.endswith("codey_still.png")
    stored = Path(image_gen_core.avatar_storage_dir()) / "codey_still.png"
    assert stored.is_file()
    payload = stored.read_bytes()
    assert payload.startswith(b"\x89PNG")
    assert image_gen_core._is_still_image(payload)
    assert image_gen_core.avatar_path_for("codey") == url
    assert router.hits == [("POST", "/v1/images/generations")]


def test_rejects_gif_as_not_still(isolated_store: Path, http_router):
    host, port, router = http_router
    router.routes[("POST", "/v1/images/generations")] = (
        200,
        {"data": [{"b64_json": base64.b64encode(_GIF).decode("ascii")}]},
    )
    spec, _ = image_gen_core.persist_settings(
        base_url=f"http://{host}:{port}",
        config_path=isolated_store,
    )
    with pytest.raises(image_gen_core.ImageGenError, match="not a still"):
        image_gen_core.generate_still("animated", settings=spec)
    assert image_gen_core.load_avatar_map() == {}


def test_is_still_image_rejects_gif_accepts_png():
    assert image_gen_core._is_still_image(_STILL_PNG) is True
    assert image_gen_core._is_still_image(_GIF) is False
    assert image_gen_core._is_still_image(b"") is False

def test_normalize_base_url_rejects_schemeless(isolated_store: Path):
    with pytest.raises(image_gen_core.ImageGenError, match="must include a scheme"):
        image_gen_core.persist_settings(
            base_url="api.example.com/v1",
            config_path=isolated_store,
        )


def test_generate_still_rejects_insecure_remote_http(isolated_store: Path, monkeypatch):
    monkeypatch.setenv("INSECURE_API_KEY", "sk-secret-key")
    spec, _ = image_gen_core.persist_settings(
        base_url="http://remote-api.example.com/v1",
        api_key_env="INSECURE_API_KEY",
        config_path=isolated_store,
    )
    with pytest.raises(image_gen_core.ImageGenError, match="Insecure HTTP connection"):
        image_gen_core.generate_still("a prompt", settings=spec)


def test_apng_acTL_detected():
    apng = _STILL_PNG[:16] + b"acTL" + _STILL_PNG[16:]
    assert image_gen_core._is_still_image(apng) is False


def test_http_error_closes_fp(isolated_store: Path):
    import io
    import urllib.error

    spec, _ = image_gen_core.persist_settings(
        base_url="http://127.0.0.1:9/v1",
        config_path=isolated_store,
    )
    fp = io.BytesIO(b'{"error": "rate limited"}')

    def _raise_http_error(*_args, **_kwargs):
        raise urllib.error.HTTPError("http://127.0.0.1:9/v1", 429, "Too Many Requests", {}, fp)

    with pytest.raises(image_gen_core.ImageGenError, match="HTTP 429"):
        image_gen_core.generate_still("test", settings=spec, opener=_raise_http_error)
    assert fp.closed is True


def test_store_still_avatar_path_traversal(isolated_store: Path):
    assert isolated_store.is_file()
    with pytest.raises(image_gen_core.ImageGenError, match="safe for an avatar filename|escaped storage root"):
        image_gen_core.store_still_avatar("../escape", _STILL_PNG)


def test_store_still_avatar_concurrency(isolated_store: Path):
    assert isolated_store.is_file()
    import concurrent.futures

    def _worker(i: int):
        image_gen_core.store_still_avatar(f"worker_{i}", _STILL_PNG)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        list(executor.map(_worker, range(10)))

    avatar_map = image_gen_core.load_avatar_map()
    assert len(avatar_map) == 10
    for i in range(10):
        assert f"worker_{i}" in avatar_map


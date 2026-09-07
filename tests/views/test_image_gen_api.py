"""API tests for /v1/image-gen/ and avatar generate (REQ-83)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from swarm.core import image_gen as image_gen_core

_STILL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def api_client():
    from django.conf import settings
    client = APIClient()
    if getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture(autouse=True)
def _isolate_image_gen(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "swarm_config.json"
    cfg.write_text(json.dumps({"llm": {}}), encoding="utf-8")
    monkeypatch.setenv("SWARM_CONFIG_PATH", str(cfg))
    monkeypatch.setenv("SWARM_AGENT_AVATARS_PATH", str(tmp_path / "agent_avatars.json"))
    monkeypatch.setenv("SWARM_AVATAR_STORAGE", str(tmp_path / "avatars"))
    monkeypatch.delenv("IMAGE_GEN_BASE_URL", raising=False)
    yield cfg


def test_get_off_does_not_include_secrets(api_client):
    resp = api_client.get("/v1/image-gen/?probe=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "image_gen"
    assert body["configured"] is False
    assert body["base_url"] == ""
    assert body["status"] == "off"
    assert "api_key" not in body or body.get("api_key") in (None, "")
    dumped = json.dumps(body)
    assert "sk-" not in dumped
    assert body["avatars"] == {}


def test_patch_persists_env_name_only(api_client, _isolate_image_gen: Path):
    live = api_client.patch(
        "/v1/image-gen/",
        {"base_url": "http://127.0.0.1:9", "model": "still-1", "api_key": "sk-live-secret"},
        format="json",
    )
    assert live.status_code == 400
    assert "api_key_env" in live.json()["error"]

    resp = api_client.patch(
        "/v1/image-gen/",
        {
            "base_url": "http://127.0.0.1:9",
            "model": "still-1",
            "api_key_env": "IMAGE_GEN_API_KEY",
        },
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["base_url"] == "http://127.0.0.1:9"
    assert body["model"] == "still-1"
    assert body["api_key_env"] == "IMAGE_GEN_API_KEY"
    assert "sk-" not in json.dumps(body)
    data = json.loads(_isolate_image_gen.read_text(encoding="utf-8"))
    assert data["image_gen"]["api_key"] == "${IMAGE_GEN_API_KEY}"
    assert data["image_gen"]["api_key_env"] == "IMAGE_GEN_API_KEY"


def test_generate_disabled_when_unset(api_client):
    resp = api_client.post(
        "/v1/agents/codey/avatar/generate/",
        {"prompt": "still portrait"},
        format="json",
    )
    assert resp.status_code == 400
    assert "Settings" in resp.json()["error"]


def test_generate_stub_sets_still_avatar(api_client, _isolate_image_gen: Path):
    image_gen_core.persist_settings(
        base_url="http://127.0.0.1:9",
        model="stub",
        api_key_env="IMAGE_GEN_API_KEY",
        config_path=_isolate_image_gen,
    )

    def _fake_generate(prompt, **_kwargs):
        assert "still" in prompt.lower() or prompt
        return _STILL_PNG

    with patch("swarm.core.image_gen.generate_still", side_effect=_fake_generate):
        resp = api_client.post(
            "/v1/agents/codey/avatar/generate/",
            {"prompt": "still portrait of Codey"},
            format="json",
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "agent_avatar"
    assert body["agent_id"] == "codey"
    assert body["still"] is True
    assert body["avatar_path"].endswith("codey_still.png")
    stored = Path(image_gen_core.avatar_storage_dir()) / "codey_still.png"
    assert stored.is_file()
    assert stored.read_bytes().startswith(b"\x89PNG")

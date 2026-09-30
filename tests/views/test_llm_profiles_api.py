"""API tests for GET/PATCH /v1/llm-profiles/ (REQ-43)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import resolve
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _disable_api_auth(settings):
    """Keep these tests hermetic: .env may set API_AUTH_TOKEN on the host,
    which would flip ENABLE_API_AUTH on and 403 every unauthenticated call
    (the view resolves permissions per-request). Same convention as
    test_api_views.py."""
    settings.ENABLE_API_AUTH = False


@pytest.fixture
def api_client():
    return APIClient()


def _config():
    return {
        "llm": {
            "gpt-4o-mini": {"provider": "openai", "model": "gpt-4o-mini"},
            "gpt-5.6-terra": {"provider": "openai", "model": "gpt-5.6-terra"},
            "o3": {"provider": "openai", "model": "o3"},
        },
        "settings": {
            "default_llm_profile": "gpt-5.6-terra",
            "override_per_task": False,
        },
    }


def test_llm_profiles_urls_accept_trailing_slash():
    assert resolve("/v1/llm-profiles").url_name == "llm-profiles-api-no-slash"
    assert resolve("/v1/llm-profiles/").url_name == "llm-profiles-api"


class TestLlmProfilesGet:
    @patch("swarm.core.llm_task_routing.load_swarm_config", return_value=_config())
    def test_lists_configured_profiles_and_default(self, _mock_load, api_client):
        resp = api_client.get("/v1/llm-profiles/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "llm_profiles"
        ids = [row["id"] for row in data["profiles"]]
        assert "gpt-5.6-terra" in ids
        assert data["default_llm_profile"] == "gpt-5.6-terra"
        assert data["override_per_task"] is False
        blob = json.dumps(data)
        assert "api_key" not in blob
        assert "sk-" not in blob
        assert "REQ-" not in blob
        assert not any("REQ-" in (w or "") for w in data.get("warnings") or [])

    @patch("swarm.core.llm_task_routing.load_swarm_config", return_value={"llm": {}})
    def test_empty_catalog_is_200_with_warning(self, _mock_load, api_client):
        resp = api_client.get("/v1/llm-profiles/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_llm_profile"] == "default"
        assert data["warnings"]


class TestLlmProfilesPatch:
    def test_patch_empty_is_400(self, api_client):
        resp = api_client.patch("/v1/llm-profiles/", {}, format="json")
        assert resp.status_code == 400

    def test_patch_persists_default(self, api_client, tmp_path: Path):
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps(_config()), encoding="utf-8")
        with patch("swarm.core.remotes.load_raw_config", return_value=(_config(), path)):
            resp = api_client.patch(
                "/v1/llm-profiles/",
                {
                    "default_llm_profile": "o3",
                    "override_per_task": True,
                    "task_llm_profiles": {
                        "auxiliary": "gpt-4o-mini",
                        "delegation": "o3",
                        "orchestration": "gpt-5.6-terra",
                    },
                },
                format="json",
            )
        assert resp.status_code == 200
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["settings"]["default_llm_profile"] == "o3"
        assert raw["settings"]["override_per_task"] is True
        assert resp.json()["persisted_to"] == str(path)
        assert "sk-" not in path.read_text(encoding="utf-8")

    def test_patch_default_refreshes_app_config_for_new_blueprints(self, api_client, tmp_path: Path):
        """REQ-188B-4 / #666: PATCH default -> new BlueprintBase resolves new profile without restart."""
        from django.apps import apps
        from swarm.core.blueprint_base import BlueprintBase

        class LiveBlueprint(BlueprintBase):
            async def run(self, messages, **kwargs):
                yield {"messages": []}

        path = tmp_path / "swarm_config.json"
        initial_cfg = _config()
        path.write_text(json.dumps(initial_cfg), encoding="utf-8")

        app = apps.get_app_config("swarm")
        orig_config = getattr(app, "config", None)
        try:
            app.config = json.loads(json.dumps(initial_cfg))
            bp_before = LiveBlueprint("bp_before")
            assert bp_before._resolve_llm_profile() == "gpt-5.6-terra"

            with patch("swarm.core.remotes.load_raw_config", return_value=(json.loads(json.dumps(initial_cfg)), path)):
                resp = api_client.patch(
                    "/v1/llm-profiles/",
                    {"default_llm_profile": "o3"},
                    format="json",
                )
            assert resp.status_code == 200

            # Newly constructed blueprint sees updated default without process restart
            bp_after = LiveBlueprint("bp_after")
            assert bp_after._resolve_llm_profile() == "o3"
        finally:
            app.config = orig_config


def _load_from_disk(path: Path):
    def _load(_config_path=None):
        return json.loads(path.read_text(encoding="utf-8")), path

    return _load


class TestLlmProfilesUpsertRoundTrip:
    def test_post_then_get_returns_model_and_base_url(self, api_client, tmp_path: Path):
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps({"llm": {}, "settings": {}}), encoding="utf-8")
        loader = _load_from_disk(path)
        with patch("swarm.core.remotes.load_raw_config", side_effect=loader):
            created = api_client.post(
                "/v1/llm-profiles/",
                {
                    "id": "local",
                    "model": "auxiliary",
                    "base_url": "http://198.51.100.30:8000/v1",
                    "provider": "openai",
                    "api_key": "${LITELLM_API_KEY}",
                    "set_default": True,
                },
                format="json",
            )
            assert created.status_code == 200
            listed = api_client.get("/v1/llm-profiles/")
        assert listed.status_code == 200
        data = listed.json()
        by_id = {row["id"]: row for row in data["profiles"]}
        assert "local" in by_id
        assert by_id["local"]["model"] == "auxiliary"
        assert by_id["local"]["base_url"] == "http://198.51.100.30:8000/v1"
        assert data["default_llm_profile"] == "local"
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["llm"]["local"]["model"] == "auxiliary"
        assert raw["llm"]["local"]["base_url"] == "http://198.51.100.30:8000/v1"
        assert raw["llm"]["local"]["api_key"] == "${LITELLM_API_KEY}"
        assert "sk-" not in path.read_text(encoding="utf-8")

    def test_put_updates_existing_profile(self, api_client, tmp_path: Path):
        path = tmp_path / "swarm_config.json"
        path.write_text(
            json.dumps(
                {
                    "llm": {
                        "local": {
                            "provider": "openai",
                            "model": "old",
                            "base_url": "http://127.0.0.1:8000/v1",
                        }
                    },
                    "settings": {},
                }
            ),
            encoding="utf-8",
        )
        with patch("swarm.core.remotes.load_raw_config", side_effect=_load_from_disk(path)):
            resp = api_client.put(
                "/v1/llm-profiles/",
                {
                    "id": "local",
                    "model": "auxiliary",
                    "base_url": "http://198.51.100.30:8000/v1",
                    "api_key": "${OPENAI_API_KEY}",
                },
                format="json",
            )
            listed = api_client.get("/v1/llm-profiles/")
        assert resp.status_code == 200
        by_id = {row["id"]: row for row in listed.json()["profiles"]}
        assert by_id["local"]["model"] == "auxiliary"
        assert by_id["local"]["base_url"] == "http://198.51.100.30:8000/v1"

    def test_post_plaintext_secret_is_400(self, api_client, tmp_path: Path):
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps({"llm": {}}), encoding="utf-8")
        with patch("swarm.core.remotes.load_raw_config", side_effect=_load_from_disk(path)):
            resp = api_client.post(
                "/v1/llm-profiles/",
                {
                    "id": "leaky",
                    "model": "gpt-4o-mini",
                    "api_key": "sk-live-token",
                },
                format="json",
            )
        assert resp.status_code == 400
        assert resp.json()["code"] == "plaintext_secret"
        assert "sk-live" not in path.read_text(encoding="utf-8")


# --- #1745 — System1 is a first-class model type on this endpoint ---


def _system1_config() -> dict:
    """Chat model + System1 gate. Env placeholders only, no credentials."""
    return {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "${OPENAI_API_KEY}",
            },
            "system1-filter": {
                "provider": "system1",
                "model": "system1-categorizer",
                "model_type": "categorizer",
                "base_url": "${SYSTEM1_BASE_URL}",
                "api_key": "${SYSTEM1_API_KEY}",
            },
        },
        "settings": {"default_llm_profile": "default"},
    }


class TestLlmProfilesModelType:
    @patch("swarm.core.llm_task_routing.load_swarm_config", return_value=_system1_config())
    def test_get_lists_system1_with_its_model_type(self, _mock_load, api_client):
        resp = api_client.get("/v1/llm-profiles/")
        assert resp.status_code == 200
        data = resp.json()
        by_id = {row["id"]: row for row in data["profiles"]}
        # A first-class type, not a hidden custom base URL.
        assert by_id["system1-filter"]["model_type"] == "categorizer"
        assert by_id["system1-filter"]["source"] == "config"
        assert by_id["default"]["model_type"] == "chat"
        assert "categorizer" in data["model_types"]
        # The credential is a reference, never a value, and never echoed.
        blob = json.dumps(data)
        assert "api_key" not in blob
        assert "${SYSTEM1_API_KEY}" not in blob
        assert "sk-" not in blob

    def test_post_system1_profile_round_trips_type(self, api_client, tmp_path: Path):
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps({"llm": {}, "settings": {}}), encoding="utf-8")
        with patch("swarm.core.remotes.load_raw_config", side_effect=_load_from_disk(path)):
            created = api_client.post(
                "/v1/llm-profiles/",
                {
                    "id": "system1-filter",
                    "model": "system1-categorizer",
                    "provider": "system1",
                    "model_type": "System1",
                    "base_url": "${SYSTEM1_BASE_URL}",
                    "api_key": "${SYSTEM1_API_KEY}",
                },
                format="json",
            )
            assert created.status_code == 200
            listed = api_client.get("/v1/llm-profiles/")
        assert listed.status_code == 200
        by_id = {row["id"]: row for row in listed.json()["profiles"]}
        assert by_id["system1-filter"]["model_type"] == "categorizer"
        # "System1" is normalised, and the vendor alone would have sufficed.
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["llm"]["system1-filter"]["model_type"] == "categorizer"
        assert raw["llm"]["system1-filter"]["api_key"] == "${SYSTEM1_API_KEY}"
        assert "sk-" not in path.read_text(encoding="utf-8")

    def test_post_plaintext_system1_key_is_400(self, api_client, tmp_path: Path):
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps({"llm": {}}), encoding="utf-8")
        with patch("swarm.core.remotes.load_raw_config", side_effect=_load_from_disk(path)):
            resp = api_client.post(
                "/v1/llm-profiles/",
                {
                    "id": "system1-filter",
                    "model": "system1-categorizer",
                    "provider": "system1",
                    "model_type": "categorizer",
                    "api_key": "sk-live-system1",
                },
                format="json",
            )
        assert resp.status_code == 400
        assert resp.json()["code"] == "plaintext_secret"
        assert "sk-live" not in path.read_text(encoding="utf-8")

    def test_post_categorizer_as_set_default_is_400(self, api_client, tmp_path: Path):
        """A gate is not a chat model — the default write is refused, not fixed."""
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps({"llm": {}, "settings": {}}), encoding="utf-8")
        with patch("swarm.core.remotes.load_raw_config", side_effect=_load_from_disk(path)):
            resp = api_client.post(
                "/v1/llm-profiles/",
                {
                    "id": "system1-filter",
                    "model": "system1-categorizer",
                    "provider": "system1",
                    "model_type": "categorizer",
                    "set_default": True,
                },
                format="json",
            )
        assert resp.status_code == 400
        assert resp.json()["code"] == "categorizer_not_default"
        assert "System1" in resp.json()["error"]
        assert json.loads(path.read_text(encoding="utf-8"))["llm"] == {}

    def test_patch_default_to_a_categorizer_is_400(self, api_client, tmp_path: Path):
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps(_system1_config()), encoding="utf-8")
        with patch("swarm.core.remotes.load_raw_config", side_effect=_load_from_disk(path)):
            resp = api_client.patch(
                "/v1/llm-profiles/",
                {"default_llm_profile": "system1-filter"},
                format="json",
            )
        assert resp.status_code == 400
        assert resp.json()["code"] == "categorizer_not_chat"
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["settings"]["default_llm_profile"] == "default"

    def test_patch_task_map_to_a_categorizer_is_400(self, api_client, tmp_path: Path):
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps(_system1_config()), encoding="utf-8")
        with patch("swarm.core.remotes.load_raw_config", side_effect=_load_from_disk(path)):
            resp = api_client.patch(
                "/v1/llm-profiles/",
                {
                    "override_per_task": True,
                    "task_llm_profiles": {"compaction": "system1-filter"},
                },
                format="json",
            )
        assert resp.status_code == 400
        assert resp.json()["code"] == "categorizer_not_chat"
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert "task_llm_profiles" not in stored["settings"]

    def test_patch_chat_defaults_still_succeed(self, api_client, tmp_path: Path):
        """The guard is narrow: ordinary chat routing is untouched."""
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps(_system1_config()), encoding="utf-8")
        with patch("swarm.core.remotes.load_raw_config", side_effect=_load_from_disk(path)):
            resp = api_client.patch(
                "/v1/llm-profiles/",
                {
                    "override_per_task": True,
                    "task_llm_profiles": {"compaction": "default"},
                },
                format="json",
            )
        assert resp.status_code == 200
        assert resp.json()["task_llm_profiles"]["compaction"] == "default"


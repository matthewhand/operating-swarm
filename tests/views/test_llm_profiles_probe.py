"""API tests for POST /v1/llm-profiles/test (REQ-854). Hermetic — HTTP is mocked."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

from swarm.core.remotes import HttpResult


@pytest.fixture(autouse=True)
def _disable_api_auth(settings):
    settings.ENABLE_API_AUTH = False


@pytest.fixture
def api_client():
    return APIClient()


def _http(status=200, body=None, error="", latency_ms=17, text=""):
    return HttpResult(
        status=status,
        body=body,
        text=text,
        error=error,
        url="http://198.51.100.30:4000/v1/models",
        latency_ms=latency_ms,
    )


def _assert_sanitized(data: dict) -> None:
    blob = json.dumps(data)
    assert "sk-" not in blob
    assert "api_key" not in blob
    assert "REQ-" not in blob
    assert "Bearer" not in blob


def test_probe_urls_accept_trailing_slash():
    assert resolve("/v1/llm-profiles/test").url_name == "llm-profiles-test-no-slash"
    assert resolve("/v1/llm-profiles/test/").url_name == "llm-profiles-test"


class TestLlmProfilesProbe:
    def test_ok(self, api_client):
        with patch(
            "swarm.core.llm_profile_probe.http_json",
            return_value=_http(body={"data": [{"id": "orchestration"}]}),
        ) as mock_http:
            resp = api_client.post(
                "/v1/llm-profiles/test/",
                {
                    "base_url": "http://198.51.100.30:4000/v1",
                    "api_key_env": "LITELLM_API_KEY",
                },
                format="json",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["state"] == "ok"
        assert data["error_class"] is None
        assert data["models"] == ["orchestration"]
        assert data["latency_ms"] == 17
        assert mock_http.call_count == 1
        _assert_sanitized(data)

    def test_auth_fail(self, api_client):
        with patch(
            "swarm.core.llm_profile_probe.http_json",
            return_value=_http(status=401, error="http 401"),
        ):
            resp = api_client.post(
                "/v1/llm-profiles/test/",
                {
                    "base_url": "http://198.51.100.30:4000/v1",
                    "api_key_ref": "LITELLM_API_KEY",
                },
                format="json",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error_class"] == "auth"
        assert data["hint"] == "check key"
        _assert_sanitized(data)

    def test_unreachable(self, api_client):
        with patch(
            "swarm.core.llm_profile_probe.http_json",
            return_value=_http(status=None, error="URLError: Connection refused", latency_ms=4),
        ):
            resp = api_client.post(
                "/v1/llm-profiles/test/",
                {"base_url": "http://127.0.0.1:9/v1"},
                format="json",
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert data["error_class"] == "unreachable"
        _assert_sanitized(data)

    def test_model_missing(self, api_client):
        with patch(
            "swarm.core.llm_profile_probe.http_json",
            return_value=_http(body={"data": [{"id": "orchestration"}]}),
        ):
            resp = api_client.post(
                "/v1/llm-profiles/test/",
                {
                    "base_url": "http://198.51.100.30:4000/v1",
                    "api_key_env": "LITELLM_API_KEY",
                    "model": "missing-model",
                },
                format="json",
            )
        data = resp.json()
        assert resp.status_code == 200
        assert data["ok"] is True
        assert data["state"] == "warn"
        assert data["error_class"] == "model_missing"
        assert "orchestration" in data["models"]
        _assert_sanitized(data)

    def test_ssrf_blocked(self, api_client):
        with patch("swarm.core.llm_profile_probe.http_json") as mock_http:
            resp = api_client.post(
                "/v1/llm-profiles/test/",
                {
                    "base_url": "https://open-litellm.fly.dev/v1",
                    "api_key_env": "LITELLM_API_KEY",
                },
                format="json",
            )
        mock_http.assert_not_called()
        data = resp.json()
        assert resp.status_code == 200
        assert data["ok"] is False
        assert data["error_class"] == "ssrf"
        _assert_sanitized(data)

    def test_list_models(self, api_client):
        with patch(
            "swarm.core.llm_profile_probe.http_json",
            return_value=_http(body={"data": [{"id": "gpt-4o-mini"}, {"id": "o3"}]}),
        ):
            resp = api_client.post(
                "/v1/llm-profiles/test/",
                {
                    "base_url": "http://198.51.100.30:4000/v1",
                    "api_key_env": "OPENAI_API_KEY",
                    "action": "list_models",
                },
                format="json",
            )
        data = resp.json()
        assert resp.status_code == 200
        assert data["action"] == "list_models"
        assert data["models"] == ["gpt-4o-mini", "o3"]
        _assert_sanitized(data)

    def test_plaintext_secret_is_400(self, api_client):
        with patch("swarm.core.llm_profile_probe.http_json") as mock_http:
            resp = api_client.post(
                "/v1/llm-profiles/test/",
                {
                    "base_url": "http://198.51.100.30:4000/v1",
                    "api_key_env": "sk-live-token",
                },
                format="json",
            )
        mock_http.assert_not_called()
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == "plaintext_secret"
        assert "sk-live" not in json.dumps(data)

    def test_never_persists(self, api_client, tmp_path):
        path = tmp_path / "swarm_config.json"
        path.write_text(json.dumps({"llm": {}}), encoding="utf-8")
        with (
            patch("swarm.core.remotes.load_raw_config", return_value=({"llm": {}}, path)),
            patch(
                "swarm.core.llm_profile_probe.http_json",
                return_value=_http(body={"data": [{"id": "orchestration"}]}),
            ),
        ):
            resp = api_client.post(
                "/v1/llm-profiles/test/",
                {
                    "base_url": "http://198.51.100.30:4000/v1",
                    "api_key_env": "LITELLM_API_KEY",
                    "model": "orchestration",
                },
                format="json",
            )
        assert resp.status_code == 200
        assert json.loads(path.read_text(encoding="utf-8")) == {"llm": {}}
        _assert_sanitized(resp.json())

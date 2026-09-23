"""Unit tests for REQ-854 LLM provider probe (no Django, no live HTTP)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from swarm.core.config_ownership import ConfigOwnershipError
from swarm.core.llm_profile_probe import (
    ERROR_AUTH,
    ERROR_BAD_MODEL,
    ERROR_DNS,
    ERROR_MODEL_MISSING,
    ERROR_SSRF,
    ERROR_TIMEOUT,
    ERROR_UNREACHABLE,
    classify_transport,
    extract_model_ids,
    hint_for,
    probe_llm_profile,
)
from swarm.core.remotes import HttpResult


def _http(status=200, body=None, error="", latency_ms=12, text=""):
    return HttpResult(
        status=status,
        body=body,
        text=text,
        error=error,
        url="http://198.51.100.30:4000/v1/models",
        latency_ms=latency_ms,
    )


def _assert_sanitized(payload: dict) -> None:
    blob = json.dumps(payload)
    assert "sk-" not in blob
    assert "api_key" not in blob
    assert "REQ-" not in blob
    assert "Bearer" not in blob


def test_classify_transport_dns_timeout_unreachable():
    assert classify_transport("URLError: <urlopen error [Errno -2] Name or service not known>") == ERROR_DNS
    assert classify_transport("TimeoutError: timed out") == ERROR_TIMEOUT
    assert classify_transport("URLError: <urlopen error Connection refused>") == ERROR_UNREACHABLE


def test_extract_model_ids_from_openai_list():
    ids = extract_model_ids(
        {"object": "list", "data": [{"id": "gpt-4o-mini"}, {"id": "orchestration"}, {"id": "gpt-4o-mini"}]}
    )
    assert ids == ["gpt-4o-mini", "orchestration"]


def test_hint_for_auth_and_timeout():
    assert hint_for(ERROR_AUTH) == "check key"
    assert hint_for(ERROR_TIMEOUT) == "is the host up?"


def test_ssrf_blocked_does_not_call_http():
    with patch("swarm.core.llm_profile_probe.http_json") as mock_http:
        result = probe_llm_profile(
            base_url="https://open-litellm.fly.dev/v1",
            api_key_env="LITELLM_API_KEY",
        )
    mock_http.assert_not_called()
    assert result["ok"] is False
    assert result["error_class"] == ERROR_SSRF
    assert result["state"] == "error"
    assert "not allowed" in result["hint"]
    _assert_sanitized(result)


def test_ok_lists_models_without_chat():
    with patch(
        "swarm.core.llm_profile_probe.http_json",
        return_value=_http(body={"data": [{"id": "orchestration"}, {"id": "auxiliary"}]}),
    ) as mock_http:
        result = probe_llm_profile(
            base_url="http://198.51.100.30:4000/v1",
            api_key_env="LITELLM_API_KEY",
        )
    mock_http.assert_called_once()
    assert mock_http.call_args[0][0] == "GET"
    assert result["ok"] is True
    assert result["state"] == "ok"
    assert result["error_class"] is None
    assert result["models"] == ["orchestration", "auxiliary"]
    assert result["latency_ms"] == 12
    _assert_sanitized(result)


def test_auth_fail():
    with patch("swarm.core.llm_profile_probe.http_json", return_value=_http(status=401, error="http 401")):
        result = probe_llm_profile(
            base_url="http://198.51.100.30:4000/v1",
            api_key_ref="LITELLM_API_KEY",
        )
    assert result["ok"] is False
    assert result["error_class"] == ERROR_AUTH
    assert result["hint"] == "check key"
    _assert_sanitized(result)


def test_unreachable():
    with patch(
        "swarm.core.llm_profile_probe.http_json",
        return_value=_http(status=None, error="URLError: Connection refused", latency_ms=3),
    ):
        result = probe_llm_profile(base_url="http://127.0.0.1:9/v1")
    assert result["ok"] is False
    assert result["error_class"] == ERROR_UNREACHABLE
    assert result["latency_ms"] == 3
    _assert_sanitized(result)


def test_model_missing_is_warn_and_returns_catalog():
    with patch(
        "swarm.core.llm_profile_probe.http_json",
        return_value=_http(body={"data": [{"id": "orchestration"}]}),
    ) as mock_http:
        result = probe_llm_profile(
            base_url="http://198.51.100.30:4000/v1",
            api_key_env="LITELLM_API_KEY",
            model="does-not-exist",
        )
    assert mock_http.call_count == 1
    assert result["ok"] is True
    assert result["state"] == "warn"
    assert result["error_class"] == ERROR_MODEL_MISSING
    assert result["models"] == ["orchestration"]
    _assert_sanitized(result)


def test_list_models_action():
    with patch(
        "swarm.core.llm_profile_probe.http_json",
        return_value=_http(body={"data": [{"id": "gpt-4o-mini"}]}),
    ):
        result = probe_llm_profile(
            base_url="http://198.51.100.30:4000/v1",
            action="list_models",
        )
    assert result["action"] == "list_models"
    assert result["ok"] is True
    assert result["models"] == ["gpt-4o-mini"]
    _assert_sanitized(result)


def test_chat_fallback_when_models_missing():
    def _fake(method, _url, **_kwargs):
        if method == "GET":
            return _http(status=404, error="http 404")
        return _http(status=200, body={"choices": [{"message": {"content": "ok"}}]}, latency_ms=40)

    with patch("swarm.core.llm_profile_probe.http_json", side_effect=_fake) as mock_http:
        result = probe_llm_profile(
            base_url="http://198.51.100.30:4000/v1",
            model="local-model",
        )
    assert [call[0][0] for call in mock_http.call_args_list] == ["GET", "POST"]
    assert result["ok"] is True
    assert result["state"] == "ok"
    _assert_sanitized(result)


def test_bad_model_from_chat_fallback():
    def _fake(method, _url, **_kwargs):
        if method == "GET":
            return _http(status=404, error="http 404")
        return _http(status=404, text="model not found", error="http 404")

    with patch("swarm.core.llm_profile_probe.http_json", side_effect=_fake):
        result = probe_llm_profile(
            base_url="http://198.51.100.30:4000/v1",
            model="nope",
        )
    assert result["ok"] is False
    assert result["error_class"] == ERROR_BAD_MODEL
    _assert_sanitized(result)


def test_plaintext_secret_is_refused_before_http(monkeypatch):
    monkeypatch.setenv("LEAKY_KEY", "sk-live-should-never-appear")
    with (
        patch("swarm.core.llm_profile_probe.http_json") as mock_http,
        pytest.raises(ConfigOwnershipError) as exc,
    ):
        probe_llm_profile(
            base_url="http://198.51.100.30:4000/v1",
            api_key_env="sk-live-should-never-appear",
        )
    mock_http.assert_not_called()
    assert exc.value.code == "plaintext_secret"


def test_resolved_key_never_echoed(monkeypatch):
    monkeypatch.setenv("LITELLM_API_KEY", "sk-live-super-secret-value")
    captured = {}

    def _fake(_method, _url, **kwargs):
        captured["headers"] = kwargs.get("headers") or {}
        return _http(body={"data": [{"id": "orchestration"}]})

    with patch("swarm.core.llm_profile_probe.http_json", side_effect=_fake):
        result = probe_llm_profile(
            base_url="http://198.51.100.30:4000/v1",
            api_key_env="LITELLM_API_KEY",
        )
    assert captured["headers"]["Authorization"] == "Bearer sk-live-super-secret-value"
    _assert_sanitized(result)
    assert "sk-live-super-secret-value" not in json.dumps(result)

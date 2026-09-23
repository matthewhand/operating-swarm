"""Unit tests for /v1/assist/enhance-prompt and /v1/chat/autocomplete (#858, #860)."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_enhance_prompt_api_success(authenticated_client, monkeypatch):
    monkeypatch.setenv("SWARM_LLM_ASSIST", "1")
    monkeypatch.setattr(
        "swarm.views.assist_api.enhance_user_prompt",
        lambda prompt: f"Detailed and enhanced: {prompt}",
    )

    resp = authenticated_client.post(
        "/v1/assist/enhance-prompt",
        data={"prompt": "write a summary"},
        format="json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "assist.enhanced_prompt"
    assert data["prompt"] == "write a summary"
    assert data["enhanced"] == "Detailed and enhanced: write a summary"


@pytest.mark.django_db
def test_enhance_prompt_api_validation(authenticated_client):
    # Empty prompt
    resp = authenticated_client.post(
        "/v1/assist/enhance-prompt",
        data={"prompt": ""},
        format="json",
    )
    assert resp.status_code == 400
    assert "prompt is required" in resp.json()["error"]

    # Missing prompt
    resp = authenticated_client.post(
        "/v1/assist/enhance-prompt",
        data={},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_chat_autocomplete_api_success(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "swarm.views.assist_api.generate_autocomplete",
        lambda prefix, suffix="", agent_id="", conversation_id="", max_tokens=32: (
            "return x + y",
            12.5,
        ),
    )

    resp = authenticated_client.post(
        "/v1/chat/autocomplete",
        data={"prefix": "def add(x, y): "},
        format="json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "chat.autocomplete"
    assert data["completion"] == "return x + y"
    assert data["duration_ms"] == 12.5


@pytest.mark.django_db
def test_chat_autocomplete_api_empty_prefix(authenticated_client):
    resp = authenticated_client.post(
        "/v1/chat/autocomplete",
        data={"prefix": "   "},
        format="json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["completion"] == ""
    assert data["duration_ms"] == 0.0


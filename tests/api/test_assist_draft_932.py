"""#932 (part C) — the AI-writer endpoint behind the system-instruction overlay.

``POST /v1/agents/assist-draft/`` turns a short user brief (plus the current
instruction and agent name) into a drafted system instruction via the default
LLM. Graceful degradation: when no LLM is reachable it returns a heuristic
template rather than erroring, so the popup's overlay never dead-ends.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_url_resolves():
    assert reverse("assist-draft") == "/v1/agents/assist-draft/"


def test_draft_uses_default_llm(client: Client, monkeypatch):
    from swarm.core import llm_assist

    captured: dict = {}

    def fake_chat(messages, **kwargs):
        captured["messages"] = messages
        return "You are Charles, a careful suggestions engine. Always answer in JSON."

    monkeypatch.setattr(llm_assist, "default_chat", fake_chat)
    resp = Client().post(
        reverse("assist-draft"),
        data=json.dumps(
            {"name": "Charles", "brief": "suggests 3 chips", "current": "old text"}
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert "Charles" in body["draft"]
    assert body["draft"] == "You are Charles, a careful suggestions engine. Always answer in JSON."
    # The brief and current instruction must reach the LLM prompt.
    flattened = json.dumps(captured["messages"])
    assert "suggests 3 chips" in flattened
    assert "old text" in flattened


def test_draft_degrades_without_llm(client: Client, monkeypatch):
    from swarm.core import llm_assist

    def boom(messages, **kwargs):
        raise RuntimeError("no upstream")

    monkeypatch.setattr(llm_assist, "default_chat", boom)
    resp = Client().post(
        reverse("assist-draft"),
        data=json.dumps({"name": "Charles", "brief": "suggests chips"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "fallback"
    assert "Charles" in body["draft"]
    assert "suggests chips" in body["draft"]


def test_draft_requires_payload():
    resp = Client().post(reverse("assist-draft"), data="{}", content_type="application/json")
    assert resp.status_code == 200
    body = resp.json()
    # Empty brief falls back to a name-based template — never a 500.
    assert body["status"] in ("success", "fallback")
    assert body["draft"].strip()


def test_custom_blueprint_patch_accepts_instructions_and_model_fields(client: Client, monkeypatch):
    """The popup writes name + instruction + provider/model through PATCH."""
    from swarm.views import api_views

    lib = {"custom": [{"id": "charles", "name": "Charles", "kind": "api", "rail": True}]}
    monkeypatch.setattr(api_views, "get_user_blueprint_library", lambda: lib)
    monkeypatch.setattr(api_views, "save_user_blueprint_library", lambda l: True)
    monkeypatch.setattr(api_views, "invalidate_blueprint_meta_cache", lambda: None)

    resp = Client().patch(
        "/v1/blueprints/custom/charles/",
        data=json.dumps(
            {
                "name": "Charles Prime",
                "instructions": "You are Charles Prime.",
                "provider": "openai",
                "model": "gpt-5-mini",
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    assert lib["custom"][0]["instructions"] == "You are Charles Prime."
    assert lib["custom"][0]["provider"] == "openai"
    assert lib["custom"][0]["model"] == "gpt-5-mini"
    assert lib["custom"][0]["name"] == "Charles Prime"

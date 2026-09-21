"""#843 — blueprint rows carry rail activity so every seat shows a timestamp.

CLI seats get disk mtime, remotes/teams get ``rail_activity_index`` stamps
(already wired). Blueprints were the gap: ``BlueprintsListView`` never asked
the chat store, so API agents showed a timestamp only from the *current
browser's* localStorage. The store is the cross-device source of truth.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    client = APIClient()
    from django.conf import settings

    if getattr(settings, "ENABLE_API_AUTH", False) and getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture
def chat_dir(tmp_path, monkeypatch):
    d = tmp_path / "chats"
    monkeypatch.setenv("SWARM_CHAT_DIR", str(d))
    return d


class TestBlueprintActivity:
    def test_blueprints_carry_last_message_at(self, api_client, chat_dir):
        from swarm.core import chat_store

        # A persisted thread for one seat — the stamp must flow to its row.
        chat_store.save("u0", "support", [{"role": "user", "content": "hi"}])
        resp = api_client.get("/v1/blueprints/")
        assert resp.status_code == 200
        rows = {r["id"]: r for r in resp.json()["data"] if isinstance(r, dict)}
        assert "last_message_at" in rows["support"], rows["support"].keys()

    def test_untouched_blueprint_has_no_fabricated_stamp(self, api_client, chat_dir):
        from swarm.core import chat_store

        chat_store.save("u0", "support", [{"role": "user", "content": "hi"}])
        resp = api_client.get("/v1/blueprints/")
        rows = {r["id"]: r for r in resp.json()["data"] if isinstance(r, dict)}
        others = [r for rid, r in rows.items() if rid != "support"]
        assert others, "expected other catalog rows"
        assert all("last_message_at" not in r for r in others)

    def test_custom_seats_are_stamped_too(self, api_client, chat_dir, monkeypatch):
        from swarm.core import chat_store

        # A custom Add-agent seat (blueprint kind, rail-visible) must also
        # receive the store stamp — the merge path builds its rows separately.
        custom_row = {
            "id": "custom-seat-1",
            "name": "Custom Seat",
            "kind": "api",
            "rail": True,
            "source": "add-agent",
        }
        monkeypatch.setattr(
            "swarm.views.api_views.get_user_blueprint_library",
            lambda: {"installed": [], "custom": [custom_row]},
        )
        chat_store.save("u0", "custom-seat-1", [{"role": "user", "content": "hi"}])
        resp = api_client.get("/v1/blueprints/")
        rows = {r["id"]: r for r in resp.json()["data"] if isinstance(r, dict)}
        assert "last_message_at" in rows.get("custom-seat-1", {})

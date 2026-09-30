"""#1314 — /v1/activity/ GET/POST with redacted ActivityEvent.detail."""

from __future__ import annotations

import json

import pytest
from filelock import FileLock
from rest_framework.test import APIClient

from swarm.core import activity_log as al


@pytest.fixture
def api_client():
    client = APIClient()
    from django.conf import settings

    if getattr(settings, "ENABLE_API_AUTH", False) and getattr(
        settings, "SWARM_API_KEY", None
    ):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture
def log_path(tmp_path, monkeypatch):
    path = tmp_path / "activity_log.jsonl"
    monkeypatch.setenv(al.ENV_LOG_PATH, str(path))
    return path


class TestActivityLogAPI:
    def test_empty_feed(self, api_client, log_path):
        resp = api_client.get("/v1/activity/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "activity_list"
        assert body["items"] == []
        assert body["count"] == 0

    def test_post_then_get_newest_first(self, api_client, log_path):
        first = api_client.post(
            "/v1/activity/",
            {
                "actor_type": "user",
                "actor_id": "alice",
                "action": "agent.updated",
                "entity_type": "agent",
                "entity_id": "support",
                "detail": {"from": "paused", "to": "active"},
            },
            format="json",
        )
        assert first.status_code == 201
        created = first.json()
        assert created["object"] == "activity_event"
        assert created["action"] == "agent.updated"
        assert created["detail"]["from"] == "paused"

        second = api_client.post(
            "/v1/activity/",
            {
                "actor_type": "system",
                "action": "routine.fired",
                "entity_type": "routine",
                "entity_id": "nightly",
            },
            format="json",
        )
        assert second.status_code == 201

        feed = api_client.get("/v1/activity/")
        assert feed.status_code == 200
        items = feed.json()["items"]
        assert [row["action"] for row in items] == ["routine.fired", "agent.updated"]

    def test_post_redacts_secret_detail_and_never_echoes_it(self, api_client, log_path):
        secret = "sk-live-must-not-appear"
        resp = api_client.post(
            "/v1/activity/",
            {
                "action": "settings.patched",
                "entity_type": "agent",
                "entity_id": "support",
                "details": {"api_key": secret, "note": "rotated"},
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.json()["actor_id"]  # defaulted once in the view, not twice
        body = json.dumps(resp.json())
        assert secret not in body
        assert resp.json()["detail"]["api_key"] == al.SCRUB_MASK
        assert resp.json()["detail"]["note"] == "rotated"
        disk = log_path.read_text(encoding="utf-8")
        assert secret not in disk

        listed = api_client.get("/v1/activity/")
        listed_text = json.dumps(listed.json())
        assert secret not in listed_text
        assert listed.json()["items"][0]["detail"]["api_key"] == al.SCRUB_MASK

    def test_filters_and_bad_actor_type(self, api_client, log_path):
        api_client.post(
            "/v1/activity/",
            {
                "actor_type": "agent",
                "actor_id": "ceo",
                "action": "agent.paused",
                "entity_type": "agent",
                "entity_id": "intern",
                "agent_id": "ceo",
            },
            format="json",
        )
        api_client.post(
            "/v1/activity/",
            {
                "action": "company.updated",
                "entity_type": "company",
                "entity_id": "acme",
            },
            format="json",
        )
        filtered = api_client.get(
            "/v1/activity/", {"entity_type": "agent", "agent_id": "ceo"}
        )
        assert filtered.status_code == 200
        items = filtered.json()["items"]
        assert len(items) == 1
        assert items[0]["entity_id"] == "intern"

        bad = api_client.get("/v1/activity/", {"actor_type": "ghost"})
        assert bad.status_code == 400
        assert "actor_type" in bad.json()["error"]

        missing = api_client.post(
            "/v1/activity/",
            {"entity_type": "agent", "entity_id": "support"},
            format="json",
        )
        assert missing.status_code == 400
        assert "action" in missing.json()["error"]

    def test_post_rejects_non_object_body(self, api_client, log_path):
        resp = api_client.post("/v1/activity/", ["not-an-event"], format="json")
        assert resp.status_code == 400
        assert resp.json()["error"] == "body must be an object"
        assert not log_path.exists()

    def test_post_returns_503_when_log_busy(self, api_client, log_path, monkeypatch):
        monkeypatch.setattr(al, "LOCK_TIMEOUT_SECONDS", 0.2)
        held = FileLock(al.activity_lock_path(log_path), timeout=1)
        held.acquire()
        try:
            resp = api_client.post(
                "/v1/activity/",
                {
                    "action": "agent.updated",
                    "entity_type": "agent",
                    "entity_id": "support",
                },
                format="json",
            )
        finally:
            held.release()
        assert resp.status_code == 503
        assert "busy" in resp.json()["error"]
        assert not log_path.exists()


@pytest.mark.django_db
class TestActivityLogVisibilityRBAC:
    def test_off_is_hidden(self, api_client, log_path, monkeypatch):
        monkeypatch.delenv(al.ENV_VISIBILITY, raising=False)
        al.set_activity_log_visibility("off")
        hidden = api_client.get("/v1/activity/")
        assert hidden.status_code == 404
        assert "off" in hidden.json()["error"]
        blocked = api_client.post(
            "/v1/activity/",
            {
                "action": "agent.updated",
                "entity_type": "agent",
                "entity_id": "support",
            },
            format="json",
        )
        assert blocked.status_code == 404

    def test_non_operator_denied_when_operator(self, log_path, monkeypatch, django_user_model):
        from django.test import override_settings
        from rest_framework.test import APIClient

        monkeypatch.delenv(al.ENV_VISIBILITY, raising=False)
        al.set_activity_log_visibility("operator")
        viewer = django_user_model.objects.create_user(username="viewer", password="x")
        client = APIClient()
        client.force_authenticate(user=viewer)
        with override_settings(ENABLE_API_AUTH=True):
            denied = client.get("/v1/activity/")
        assert denied.status_code == 403
        assert "operator" in denied.json()["error"]

    def test_owner_sees_own_events_when_all(self, log_path, monkeypatch, django_user_model):
        from django.test import override_settings
        from rest_framework.test import APIClient

        monkeypatch.delenv(al.ENV_VISIBILITY, raising=False)
        al.set_activity_log_visibility("all")
        al.persist_activity(
            actor_id="user:alice",
            action="agent.created",
            entity_type="agent",
            entity_id="desk",
        )
        al.persist_activity(
            actor_id="user:bob",
            action="agent.created",
            entity_type="agent",
            entity_id="other",
        )
        alice = django_user_model.objects.create_user(username="alice", password="x")
        staff = django_user_model.objects.create_user(
            username="ops", password="x", is_staff=True
        )
        owner = APIClient()
        owner.force_authenticate(user=alice)
        with override_settings(ENABLE_API_AUTH=True):
            mine = owner.get("/v1/activity/")
        assert mine.status_code == 200
        items = mine.json()["items"]
        assert [row["actor_id"] for row in items] == ["user:alice"]
        assert mine.json()["visibility"] == "all"

        ops = APIClient()
        ops.force_authenticate(user=staff)
        with override_settings(ENABLE_API_AUTH=True):
            full = ops.get("/v1/activity/")
        assert full.status_code == 200
        assert {row["actor_id"] for row in full.json()["items"]} == {"user:alice", "user:bob"}

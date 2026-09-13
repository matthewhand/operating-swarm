"""REQ-21 Herdr agent rows: Django ORM + DRF. Mock the CLI. SQLite only."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from swarm.herdr.client import MEMBER_KIND
from swarm.models import HerdrAgent


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
class TestHerdrAgentsAPI:
    def test_list_empty(self, api_client):
        response = api_client.get("/v1/herdr-agents/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"object": "list", "data": []}

    def test_create_localhost_then_list_and_delete(self, api_client):
        created = api_client.post("/v1/herdr-agents/", {"name": "w3:p1"}, format="json")
        assert created.status_code == status.HTTP_201_CREATED
        body = created.json()
        assert body["name"] == "w3:p1"
        assert body["remote"] == ""
        assert body["kind"] == MEMBER_KIND
        assert body["object"] == "herdr.agent"

        listed = api_client.get("/v1/herdr-agents/").json()
        assert listed["object"] == "list"
        assert len(listed["data"]) == 1
        assert listed["data"][0]["remote"] == ""

        by_name = api_client.get("/v1/herdr-agents/w3:p1/")
        assert by_name.status_code == status.HTTP_200_OK

        deleted = api_client.delete(f"/v1/herdr-agents/{body['id']}/")
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        assert HerdrAgent.objects.count() == 0

    def test_create_with_remote(self, api_client):
        response = api_client.post(
            "/v1/herdr-agents/",
            {"name": "workbox", "remote": "matthewh@198.51.100.36"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["remote"] == "matthewh@198.51.100.36"
        assert response.json()["kind"] == "herdr"

    def test_duplicate_name_conflict(self, api_client):
        HerdrAgent.objects.create(name="local-herdr", remote="")
        response = api_client.post("/v1/herdr-agents/", {"name": "local-herdr"}, format="json")
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_name_required(self, api_client):
        response = api_client.post("/v1/herdr-agents/", {"remote": "workbox"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_unknown_404(self, api_client):
        response = api_client.delete("/v1/herdr-agents/missing/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestHerdrDiscoverAPI:
    def test_discover_maps_cli_lists_to_addable_members(self, api_client):
        fake = MagicMock()
        fake.discover_members.return_value = [
            {
                "kind": "herdr",
                "name": "w3:p1",
                "remote": "",
                "source": "agent",
                "state": "idle",
                "object": "herdr.member",
            }
        ]
        with patch("swarm.views.herdr_api.herdr_client", return_value=fake):
            response = api_client.get("/v1/herdr-agents/discover/")
        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["kind"] == "herdr"
        assert payload["data"][0]["name"] == "w3:p1"
        assert payload["data"][0]["remote"] == ""
        assert payload["data"][0]["added"] is False
        fake.discover_members.assert_called_once()

    def test_discover_marks_already_persisted(self, api_client):
        HerdrAgent.objects.create(name="w3:p1", remote="")
        fake = MagicMock()
        fake.discover_members.return_value = [
            {"kind": "herdr", "name": "w3:p1", "remote": "", "source": "agent", "object": "herdr.member"}
        ]
        with patch("swarm.views.herdr_api.herdr_client", return_value=fake):
            payload = api_client.get("/v1/herdr-agents/discover/").json()
        assert payload["data"][0]["added"] is True

    def test_discover_without_herdr_is_empty_not_500(self, api_client):
        from swarm.herdr import HerdrCLIError

        fake = MagicMock()
        fake.discover_members.side_effect = HerdrCLIError("herdr CLI not found on PATH")
        with patch("swarm.views.herdr_api.herdr_client", return_value=fake):
            response = api_client.get("/v1/herdr-agents/discover/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"] == []
        assert response.json()["herdr_available"] is False


@pytest.mark.django_db
def test_model_remote_defaults_empty_localhost():
    row = HerdrAgent.objects.create(name="local")
    assert row.remote == ""
    assert row.is_localhost is True


@pytest.mark.django_db
def test_settings_dashboard_lists_herdr_section(client, django_user_model):
    django_user_model.objects.create_user(username="h", password="p")
    HerdrAgent.objects.create(name="w3:p1", remote="")
    client.login(username="h", password="p")
    html = client.get("/settings/").content.decode()
    assert "Herdr agents" in html
    assert "kind=herdr" in html
    assert "w3:p1" in html
    assert "localhost" in html
    assert "discover-herdr-agents" in html
    assert "Add Herdr remote" in html
    assert "herdr-remote-form" in html
    assert "OpenMousBot" in html
    assert "api-key-env" in html


@pytest.mark.django_db
def test_teams_admin_can_pick_herdr_members(client, django_user_model):
    django_user_model.objects.create_user(username="h2", password="p")
    HerdrAgent.objects.create(name="w3:p1", remote="")
    client.login(username="h2", password="p")
    html = client.get("/teams/").content.decode()
    assert 'id="herdr-members"' in html
    assert "w3:p1" in html
    assert "kind=herdr" in html
    assert "Discover live Herdr" in html

"""REQ-171B / #607 — Add-agent CLI/API creates a rail-visible seat.

Own-diff: create stamps ``rail: true`` + a first-class CLI command; GET
``/v1/blueprints/`` merges those customs so the AGENTS rail filter can list
them. Failure paths return honest copy. No secrets, no Neon, no :8001.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework import status

from swarm.core.rail_seats import (
    CLI_COMMAND_REQUIRED_ERROR,
    UNSUPPORTED_ADD_AGENT_KIND_ERROR,
)
from swarm.views import api_views


@pytest.fixture(autouse=True)
def _disable_api_auth(settings):
    settings.ENABLE_API_AUTH = False


def _empty_library():
    return {"installed": [], "custom": []}


@patch("swarm.views.api_views.save_user_blueprint_library", return_value=True)
@patch("swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library())
def test_create_cli_seat_persists_rail_and_command(
    _mock_get, mock_save, api_client
):
    api_views._custom_blueprints_registry.clear()
    response = api_client.post(
        "/v1/blueprints/custom/",
        data={
            "name": "Desk CLI",
            "kind": "cli",
            "command": "grok -p",
            "category": "cli",
            "tags": ["cli"],
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["id"] == "desk_cli"
    assert body["rail"] is True
    assert body["kind"] == "cli"
    assert body["command"] == "grok -p"
    assert body["source"] == "add-agent"
    saved = mock_save.call_args[0][0]["custom"][0]
    assert saved["rail"] is True
    assert saved["command"] == "grok -p"


@patch("swarm.views.api_views.save_user_blueprint_library", return_value=True)
@patch("swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library())
def test_create_cli_seat_persists_remote_endpoint_for_capable_cli(
    _mock_get, mock_save, api_client
):
    api_views._custom_blueprints_registry.clear()
    response = api_client.post(
        "/v1/blueprints/custom/",
        data={
            "name": "GPU OpenCode",
            "kind": "cli",
            "command": "opencode",
            "category": "cli",
            "tags": ["cli"],
            "remote": {"host": "dev-gpu.lan", "port": 4096, "password": "secret"},
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["remote"]["host"] == "dev-gpu.lan"
    assert body["remote"]["port"] == 4096
    assert "password" not in body["remote"]
    saved = mock_save.call_args[0][0]["custom"][0]
    assert saved["remote"]["host"] == "dev-gpu.lan"
    assert "password" not in saved["remote"]


@patch("swarm.views.api_views.save_user_blueprint_library", return_value=True)
@patch("swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library())
def test_create_cli_without_command_is_honest_error(_mock_get, _mock_save, api_client):
    response = api_client.post(
        "/v1/blueprints/custom/",
        data={"name": "Blank CLI", "kind": "cli", "category": "cli", "tags": ["cli"]},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"] == CLI_COMMAND_REQUIRED_ERROR


@patch("swarm.views.api_views.save_user_blueprint_library", return_value=True)
@patch("swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library())
def test_create_cli_accepts_command_comment_when_field_omitted(
    _mock_get, mock_save, api_client
):
    response = api_client.post(
        "/v1/blueprints/custom/",
        data={
            "name": "Comment CLI",
            "category": "cli",
            "tags": ["cli"],
            "code": "# CLI agent: Comment CLI\n# Command: agy\n",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["command"] == "agy"
    assert response.json()["rail"] is True
    assert mock_save.called


@patch("swarm.views.api_views.save_user_blueprint_library", return_value=True)
@patch("swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library())
def test_create_api_seat_is_rail_visible(_mock_get, _mock_save, api_client):
    response = api_client.post(
        "/v1/blueprints/custom/",
        data={
            "name": "Researcher",
            "kind": "api",
            "tags": ["api"],
            "description": "Deep research",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["rail"] is True
    assert body["kind"] == "api"
    assert body["source"] == "add-agent"


@patch("swarm.views.api_views.save_user_blueprint_library", return_value=True)
@patch("swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library())
def test_create_remote_kind_is_rejected(_mock_get, _mock_save, api_client):
    response = api_client.post(
        "/v1/blueprints/custom/",
        data={"name": "OMB", "kind": "remote"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"] == UNSUPPORTED_ADD_AGENT_KIND_ERROR


@patch("swarm.views.api_views.get_available_blueprints")
@patch("swarm.views.api_views.get_user_blueprint_library")
def test_blueprints_list_merges_custom_rail_seats_newest_first(
    mock_library, mock_discovery, api_client
):
    mock_discovery.return_value = {
        "support": {"metadata": {"name": "Support", "rail": True}},
        "poets": {"metadata": {"name": "poets"}},
    }
    mock_library.return_value = {
        "installed": [],
        "custom": [
            {
                "id": "older_cli",
                "name": "Older CLI",
                "kind": "cli",
                "command": "agy",
                "rail": True,
            },
            {
                "id": "catalog_only",
                "name": "Scratch",
                "category": "test",
                "rail": False,
            },
            {
                "id": "newer_api",
                "name": "Newer API",
                "kind": "api",
                "tags": ["api"],
                "rail": True,
            },
        ],
    }

    response = api_client.get("/v1/blueprints/")
    assert response.status_code == status.HTTP_200_OK
    rows = response.json()["data"]
    by_id = {row["id"]: row for row in rows}
    assert by_id["newer_api"]["rail"] is True
    assert by_id["older_cli"]["rail"] is True
    assert by_id["older_cli"]["command"] == "agy"
    assert by_id["older_cli"]["kind"] == "cli"
    assert by_id["support"]["rail"] is True
    assert by_id["poets"]["rail"] is False
    assert "catalog_only" not in by_id
    custom_ids = [row["id"] for row in rows if row["id"] in {"newer_api", "older_cli"}]
    assert custom_ids == ["newer_api", "older_cli"]


@patch("swarm.views.api_views.get_available_blueprints")
@patch("swarm.views.api_views.get_user_blueprint_library")
def test_blueprints_list_does_not_override_discovery_ids(
    mock_library, mock_discovery, api_client
):
    mock_discovery.return_value = {
        "support": {"metadata": {"name": "Support", "rail": True}},
    }
    mock_library.return_value = {
        "installed": [],
        "custom": [
            {
                "id": "support",
                "name": "Fake Support",
                "kind": "api",
                "rail": True,
            }
        ],
    }
    response = api_client.get("/v1/blueprints/")
    rows = response.json()["data"]
    support = [row for row in rows if row["id"] == "support"]
    assert len(support) == 1
    assert support[0]["name"] == "Support"
    assert support[0].get("user_created") is not True


@patch("swarm.views.api_views.save_user_blueprint_library", return_value=True)
@patch("swarm.views.api_views.get_user_blueprint_library")
def test_patch_cli_without_command_fails(mock_get, _mock_save, api_client):
    mock_get.return_value = {
        "installed": [],
        "custom": [
            {
                "id": "desk_cli",
                "name": "Desk",
                "kind": "cli",
                "command": "grok",
                "rail": True,
            }
        ],
    }
    response = api_client.patch(
        "/v1/blueprints/custom/desk_cli/",
        data={"command": ""},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["error"] == CLI_COMMAND_REQUIRED_ERROR

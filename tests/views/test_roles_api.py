"""API tests for /v1/roles/ (REQ-25 / REQ-28)."""

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from swarm.core.agent_roles import CANONICAL_ROLES, ROLE_DEFAULT, ROLE_SUPPORT, ROLE_CHIEF_OF_STAFF


@pytest.fixture
def api_client():
    client = APIClient()
    if getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


def test_list_roles_returns_all_canonical_roles(api_client):
    response = api_client.get("/v1/roles/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert "data" in body
    roles = body["data"]
    assert len(roles) == len(CANONICAL_ROLES)

    by_name = {r["name"]: r for r in roles}
    for canonical in CANONICAL_ROLES:
        assert canonical in by_name

    # Default role
    default_role = by_name[ROLE_DEFAULT]
    assert default_role["allow_all"] is False
    assert default_role["mechanism"] == "none"
    assert "default" in default_role["aliases"]
    assert "worker" in default_role["aliases"]

    # Support role
    support_role = by_name[ROLE_SUPPORT]
    assert support_role["label"] == "Support"
    assert support_role["mechanism"] == "implement"
    assert "helper" in support_role["aliases"]

    # Chief of Staff role
    cos_role = by_name[ROLE_CHIEF_OF_STAFF]
    assert cos_role["label"] == "CoS"
    assert cos_role["allow_all"] is True
    assert cos_role["mechanism"] == "intercept"
    assert "cos" in cos_role["aliases"]
    assert "chief" in cos_role["aliases"]


def test_list_roles_no_slash_endpoint(api_client):
    response = api_client.get("/v1/roles")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert len(body["data"]) >= len(CANONICAL_ROLES)


def test_create_and_delete_custom_role(api_client):
    role_payload = {
        "name": "qa_inspector",
        "label": "QA Inspector",
        "aliases": ["qa", "tester"],
        "mechanism": "parse",
        "mechanism_detail": "Validates test outcomes and inspects code diffs.",
        "allow_all": False,
    }
    # Create role
    create_res = api_client.post("/v1/roles/", role_payload, format="json")
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["name"] == "qa_inspector"
    assert created_data["label"] == "QA Inspector"
    assert "qa" in created_data["aliases"]
    assert created_data["mechanism"] == "parse"
    assert created_data["custom"] is True

    # Check that it appears in list
    list_res = api_client.get("/v1/roles/")
    assert list_res.status_code == 200
    names = [r["name"] for r in list_res.json()["data"]]
    assert "qa_inspector" in names

    # Delete role
    del_res = api_client.delete("/v1/roles/qa_inspector/")
    assert del_res.status_code == 204

    # Check it no longer appears in list
    list_res_after = api_client.get("/v1/roles/")
    names_after = [r["name"] for r in list_res_after.json()["data"]]
    assert "qa_inspector" not in names_after


def test_reject_create_canonical_role(api_client):
    res = api_client.post("/v1/roles/", {"name": "support", "label": "Fake Support"}, format="json")
    assert res.status_code == 400
    assert "reserved canonical role" in res.json()["error"]


def test_reject_delete_canonical_role(api_client):
    res = api_client.delete("/v1/roles/gate/")
    assert res.status_code == 400
    assert "Cannot delete canonical role" in res.json()["error"]


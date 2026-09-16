"""API tests for /v1/mailbox-acl/ (REQ-162)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from swarm.core import agent_mailbox_acl as store


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate_acl(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_MAILBOX_ACL_PATH", str(tmp_path / "agent_mailbox_acl.json"))
    store.reset_mailbox_acl_cache()
    yield
    store.reset_mailbox_acl_cache()


def test_store_documents_entry_kinds(api_client):
    response = api_client.get("/v1/mailbox-acl/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "mailbox_acl_store"
    kinds = {row["kind"] for row in body["entry_kinds"]}
    assert kinds == {"agent", "team", "role", "section"}
    assert body["defaults"]["support"]["allow_all"] is True
    assert ":8001" not in str(body)


def test_support_default_whitelist_allow_all(api_client):
    response = api_client.get("/v1/mailbox-acl/agents/support/?role=support")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "mailbox_acl"
    assert body["mode"] == "whitelist"
    assert body["allow_all"] is True
    assert body["entries"] == []
    assert body["source"] == "default"


def test_put_agent_whitelist_roundtrip(api_client):
    response = api_client.put(
        "/v1/mailbox-acl/agents/pat/?role=default",
        {"mode": "whitelist", "entries": [{"kind": "team", "id": "office"}]},
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "whitelist"
    assert body["source"] == "agent"
    assert body["entries"] == [{"kind": "team", "id": "office"}]
    again = api_client.get("/v1/mailbox-acl/agents/pat/?role=default")
    assert again.json()["entries"] == [{"kind": "team", "id": "office"}]


def test_toggle_mode_xor(api_client):
    api_client.put(
        "/v1/mailbox-acl/agents/pat/?role=default",
        {"mode": "whitelist", "entries": [{"kind": "agent", "id": "cos"}]},
        format="json",
    )
    flipped = api_client.put(
        "/v1/mailbox-acl/agents/pat/?role=default",
        {"mode": "blacklist", "entries": [{"kind": "agent", "id": "cos"}]},
        format="json",
    )
    assert flipped.status_code == 200
    assert flipped.json()["mode"] == "blacklist"
    bad = api_client.put(
        "/v1/mailbox-acl/agents/pat/",
        {"mode": "both", "entries": []},
        format="json",
    )
    assert bad.status_code == 400


def test_role_policy_and_reset(api_client):
    created = api_client.put(
        "/v1/mailbox-acl/roles/support/",
        {"mode": "blacklist", "entries": [{"kind": "role", "id": "gate"}]},
        format="json",
    )
    assert created.status_code == 200
    assert created.json()["scope"] == "role"
    assert created.json()["mode"] == "blacklist"
    inherited = api_client.get("/v1/mailbox-acl/agents/support/?role=support")
    assert inherited.json()["source"] == "role"
    assert inherited.json()["inherited"] is True
    reset = api_client.delete("/v1/mailbox-acl/roles/support/")
    assert reset.status_code == 200
    assert reset.json()["source"] == "default"
    assert reset.json()["allow_all"] is True


def test_delete_agent_override_inherits(api_client):
    api_client.put(
        "/v1/mailbox-acl/agents/pat/?role=default",
        {"mode": "whitelist", "entries": [{"kind": "agent", "id": "support"}]},
        format="json",
    )
    deleted = api_client.delete("/v1/mailbox-acl/agents/pat/?role=default")
    assert deleted.status_code == 200
    assert deleted.json()["source"] == "default"
    assert deleted.json()["mode"] == "blacklist"

"""#1316 — API contract for blocked duplicate routines.

POST /v1/agents/<id>/routines/ returns 409 (not 201) when a routine with the
same normalized name/instruction/trigger already exists, and still creates a
distinct routine for an explicit ``allow_duplicate: true``.
"""

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from swarm.core import routines as store


@pytest.fixture
def api_client():
    client = APIClient()
    if getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture(autouse=True)
def _isolate_routines(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    yield
    store.reset_routines_cache()
    store.set_instruction_runner(None)


def _payload(**overrides):
    payload = {
        "name": "Ship notes",
        "instruction": "Summarize the merged pull request.",
        "trigger": {"kind": "github_pr_merged", "owner_repo": "owner/repo"},
    }
    payload.update(overrides)
    return payload


def test_duplicate_create_returns_409_with_existing_id(api_client):
    first = api_client.post("/v1/agents/codey/routines/", _payload(), format="json")
    assert first.status_code == 201
    existing_id = first.json()["id"]

    conflict = api_client.post("/v1/agents/codey/routines/", _payload(), format="json")
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["object"] == "routine_conflict"
    assert body["duplicate"] is True
    assert body["existing_routine_id"] == existing_id
    assert body["existing_routine"]["id"] == existing_id
    assert "already exists" in body["error"].lower()

    listed = api_client.get("/v1/agents/codey/routines/")
    assert len(listed.json()["routines"]) == 1


def test_whitespace_case_variant_returns_409(api_client):
    first = api_client.post("/v1/agents/codey/routines/", _payload(), format="json").json()
    conflict = api_client.post(
        "/v1/agents/codey/routines/",
        _payload(name="  SHIP   notes ", instruction="Summarize the merged pull request. "),
        format="json",
    )
    assert conflict.status_code == 409
    assert conflict.json()["existing_routine_id"] == first["id"]


def test_distinct_and_allow_duplicate_still_create(api_client):
    first = api_client.post("/v1/agents/codey/routines/", _payload(), format="json").json()

    distinct = api_client.post(
        "/v1/agents/codey/routines/",
        _payload(instruction="Publish the release notes."),
        format="json",
    )
    assert distinct.status_code == 201

    twin = api_client.post(
        "/v1/agents/codey/routines/",
        {**_payload(), "allow_duplicate": True},
        format="json",
    )
    assert twin.status_code == 201
    twin_id = twin.json()["id"]
    assert twin_id not in {first["id"], distinct.json()["id"]}

    listed = api_client.get("/v1/agents/codey/routines/")
    assert len(listed.json()["routines"]) == 3

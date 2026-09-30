"""API tests for per-agent skills CRUD + pack (#1392)."""

import pytest
from django.conf import settings
from django.urls import resolve
from rest_framework.test import APIClient

from swarm.core import agent_skills as store


@pytest.fixture
def api_client():
    client = APIClient()
    if getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture(autouse=True)
def _isolate_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SKILLS_PATH", str(tmp_path / "agent_skills.json"))
    store.reset_agent_skills_cache()
    yield
    store.reset_agent_skills_cache()


def test_skills_and_pack_urls_accept_trailing_slash():
    assert resolve("/v1/agents/codey/skills").url_name == "agent-skills-api-no-slash"
    assert resolve("/v1/agents/codey/skills/").url_name == "agent-skills-api"
    assert resolve("/v1/agents/codey/skills/welcome-tour").url_name == "agent-skill-detail-api-no-slash"
    assert resolve("/v1/agents/codey/skills/welcome-tour/").url_name == "agent-skill-detail-api"
    assert resolve("/v1/agents/codey/pack").url_name == "agent-pack-api-no-slash"
    assert resolve("/v1/agents/codey/pack/").url_name == "agent-pack-api"
    assert resolve("/v1/agents/codey/pack/import").url_name == "agent-pack-import-api-no-slash"
    assert resolve("/v1/agents/codey/pack/import/").url_name == "agent-pack-import-api"
    assert resolve("/v1/agent-packs/validate").url_name == "agent-pack-validate-api-no-slash"
    assert resolve("/v1/agent-packs/validate/").url_name == "agent-pack-validate-api"


def test_crud_roundtrip(api_client):
    listed = api_client.get("/v1/agents/codey/skills/")
    assert listed.status_code == 200
    body = listed.json()
    assert body["object"] == "agent_skill_list"
    assert body["skills"] == []
    assert body["gettingStarted"] is None

    created = api_client.post(
        "/v1/agents/codey/skills/",
        {
            "name": "welcome-tour",
            "description": "Walk the first conversation.",
            "instructions": "Greet the operator and list three first steps.",
        },
        format="json",
    )
    assert created.status_code == 201
    row = created.json()
    assert row["object"] == "agent_skill"
    assert row["agent_id"] == "codey"
    assert row["name"] == "welcome-tour"
    assert "helper.py" not in str(row)
    assert "sk-" not in row["instructions"]

    detail = api_client.get("/v1/agents/codey/skills/welcome-tour/")
    assert detail.status_code == 200
    assert detail.json()["instructions"].startswith("Greet")

    patched = api_client.patch(
        "/v1/agents/codey/skills/welcome-tour/",
        {"instructions": "Keep the welcome shorter."},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["instructions"] == "Keep the welcome shorter."

    deleted = api_client.delete("/v1/agents/codey/skills/welcome-tour/")
    assert deleted.status_code == 204
    missing = api_client.get("/v1/agents/codey/skills/welcome-tour/")
    assert missing.status_code == 404


def test_attach_library_skill(api_client):
    created = api_client.post(
        "/v1/agents/codey/skills/",
        {"attach": "conventional-commit"},
        format="json",
    )
    assert created.status_code == 201
    row = created.json()
    assert row["name"] == "conventional-commit"
    assert row["source"] == "library"
    assert row["instructions"]


def test_pack_export_import_and_first_run(api_client):
    api_client.post(
        "/v1/agents/codey/skills/",
        {"name": "welcome-tour", "instructions": "Greet the operator."},
        format="json",
    )
    api_client.post(
        "/v1/agents/codey/skills/",
        {"name": "review-notes", "instructions": "Review the diff."},
        format="json",
    )
    packed = api_client.post(
        "/v1/agents/codey/pack/",
        {
            "skills": ["welcome-tour", "review-notes"],
            "gettingStarted": {"skill": "welcome-tour"},
        },
        format="json",
    )
    assert packed.status_code == 200
    pack = packed.json()
    assert pack["object"] == "agent_pack"
    assert pack["gettingStarted"]["skill"] == "welcome-tour"
    assert {row["name"] for row in pack["skills"]} == {"welcome-tour", "review-notes"}
    assert all("instructions" in row for row in pack["skills"])
    assert all("assets" not in row for row in pack["skills"])

    imported = api_client.post(
        "/v1/agents/writer/pack/import/",
        pack,
        format="json",
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["object"] == "agent_pack_import"
    assert {row["name"] for row in body["skills"]} == {"welcome-tour", "review-notes"}
    assert body["gettingStarted"] == {"skill": "welcome-tour"}
    assert body["first_run_pending"] is True

    listed = api_client.get("/v1/agents/writer/skills/")
    assert listed.json()["first_run_pending"] is True
    assert listed.json()["gettingStarted"]["skill"] == "welcome-tour"


def test_pack_validation_missing_getting_started_skill_fails(api_client):
    response = api_client.post(
        "/v1/agent-packs/validate/",
        {"skills": [{"name": "welcome-tour", "instructions": "Greet the operator."}]},
        format="json",
    )
    assert response.status_code == 400
    body = response.json()
    assert "gettingStarted.skill" in body["error"]
    assert body["code"] == "pack_getting_started_missing"


def test_pack_export_fails_when_getting_started_not_packed(api_client):
    api_client.post(
        "/v1/agents/codey/skills/",
        {"name": "welcome-tour", "instructions": "Greet the operator."},
        format="json",
    )
    api_client.post(
        "/v1/agents/codey/skills/",
        {"name": "review-notes", "instructions": "Review the diff."},
        format="json",
    )
    response = api_client.post(
        "/v1/agents/codey/pack/",
        {
            "skills": ["review-notes"],
            "gettingStarted": {"skill": "welcome-tour"},
        },
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "pack_getting_started_missing"


def test_import_missing_getting_started_skill_fails(api_client):
    response = api_client.post(
        "/v1/agents/writer/pack/import/",
        {"skills": [{"name": "welcome-tour", "instructions": "Greet the operator."}]},
        format="json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "pack_getting_started_missing"
    assert api_client.get("/v1/agents/writer/skills/").json()["skills"] == []


def test_getting_started_patch_requires_attached_skill(api_client):
    api_client.post(
        "/v1/agents/codey/skills/",
        {"name": "welcome-tour", "instructions": "Greet the operator."},
        format="json",
    )
    bad = api_client.patch(
        "/v1/agents/codey/skills/",
        {"gettingStarted": {"skill": "not-attached"}},
        format="json",
    )
    assert bad.status_code == 400
    ok = api_client.patch(
        "/v1/agents/codey/skills/",
        {"gettingStarted": {"skill": "welcome-tour"}, "first_run": True},
        format="json",
    )
    assert ok.status_code == 200
    assert ok.json()["first_run_pending"] is True

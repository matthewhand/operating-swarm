"""API tests for /v1/agents/<id>/template/ (#1398). Backend only."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.urls import resolve
from rest_framework.test import APIClient

from swarm.core import agent_memory as memories
from swarm.core import agent_plugin_pack as plugin_pack
from swarm.core import agent_settings as store
from swarm.core import agent_skills as skills
from swarm.core.agent_template import load_template_file
from swarm.core.routines import list_routines, reset_routines_cache
from swarm.core.template_fragments import reset_fragment_cache

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent_template_pack.json"
GROK_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "grok_bot_template.json"
)
FAKE_OPENAI = "sk-notarealkeyABCDEFGH"


@pytest.fixture
def api_client():
    client = APIClient()
    if getattr(django_settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {django_settings.SWARM_API_KEY}")
    return client


@pytest.fixture(autouse=True)
def _isolate_stores(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json")
    )
    monkeypatch.setenv(
        "SWARM_AGENT_MEMORIES_PATH", str(tmp_path / "agent_memories.json")
    )
    monkeypatch.setenv("SWARM_AGENT_SKILLS_PATH", str(tmp_path / "agent_skills.json"))
    monkeypatch.setenv(
        "SWARM_AGENT_TEMPLATE_FRAGMENTS_PATH",
        str(tmp_path / "agent_template_fragments.json"),
    )
    monkeypatch.setenv(
        "SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json")
    )
    monkeypatch.setenv("SWARM_AGENT_PLUGINS_PATH", str(tmp_path / "agent_plugins.json"))
    store.reset_agent_settings_cache()
    memories.reset_memories_cache()
    skills.reset_agent_skills_cache()
    reset_fragment_cache()
    reset_routines_cache()
    plugin_pack.reset_agent_plugin_pack_cache()
    yield
    store.reset_agent_settings_cache()
    memories.reset_memories_cache()
    skills.reset_agent_skills_cache()
    reset_fragment_cache()
    reset_routines_cache()
    plugin_pack.reset_agent_plugin_pack_cache()


def test_template_urls_accept_trailing_slash():
    assert (
        resolve("/v1/agents/codey/template").url_name == "agent-template-api-no-slash"
    )
    assert resolve("/v1/agents/codey/template/").url_name == "agent-template-api"
    assert (
        resolve("/v1/agents/codey/template/import/").url_name
        == "agent-template-import-api"
    )
    assert (
        resolve("/v1/agents/codey/template/grok/").url_name == "agent-template-grok-api"
    )
    assert (
        resolve("/v1/agent-templates/validate/").url_name
        == "agent-template-validate-api"
    )
    assert (
        resolve("/v1/agent-templates/from-grok/").url_name
        == "agent-template-from-grok-api"
    )


def test_export_empty_agent_is_valid_template(api_client):
    response = api_client.get("/v1/agents/fresh/template/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "agent_template"
    assert body["kind"] == "agent_template"
    assert body["profile"]["display_name"] == ""
    assert body["memories"] == []
    assert body["skills"] == []
    assert body["gettingStarted"] is None


def test_validate_and_import_file_fixture(api_client):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    validated = api_client.post("/v1/agent-templates/validate/", raw, format="json")
    assert validated.status_code == 200
    pack = validated.json()
    assert pack["profile"]["display_name"] == "Storefront Bee"
    assert pack["gettingStarted"]["skill"] == "welcome-tour"

    imported = api_client.post("/v1/agents/target/template/import/", raw, format="json")
    assert imported.status_code == 200
    body = imported.json()
    assert body["object"] == "agent_template_import"
    assert body["applied"]["memories"] == 2
    assert body["applied"]["skills"] == 1

    exported = api_client.get("/v1/agents/target/template/")
    assert exported.status_code == 200
    again = exported.json()
    assert again["profile"]["display_name"] == "Storefront Bee"
    assert [row["kind"] for row in again["memories"]] == ["profile", "log"]
    assert again["skills"][0]["name"] == "welcome-tour"


def test_validate_rejects_secrets_and_missing_getting_started(api_client):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    dirty = dict(raw)
    dirty["skills"] = [
        {
            "name": "welcome-tour",
            "description": "Walk the first conversation.",
            "instructions": f"Use {FAKE_OPENAI} never.",
        }
    ]
    leaked = api_client.post("/v1/agent-templates/validate/", dirty, format="json")
    assert leaked.status_code == 400
    assert leaked.json()["code"] == "template_secrets"

    missing = dict(raw)
    missing.pop("gettingStarted")
    failed = api_client.post("/v1/agent-templates/validate/", missing, format="json")
    assert failed.status_code == 400
    assert failed.json()["code"] == "template_getting_started_missing"

    imported = api_client.post(
        "/v1/agents/target/template/import/", dirty, format="json"
    )
    assert imported.status_code == 400
    empty = api_client.get("/v1/agents/target/template/")
    assert empty.json()["profile"]["display_name"] == ""


def test_grok_export_and_from_grok(api_client):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    api_client.post("/v1/agents/bee/template/import/", raw, format="json")

    grok = api_client.get("/v1/agents/bee/template/grok/")
    assert grok.status_code == 200
    body = grok.json()
    assert body["kind"] == "grok_bot_template"
    assert body["name"] == "Storefront Bee"
    assert body["avatar"]["shape"] == "hexagon"
    assert body["gettingStarted"]["skill"] == "welcome-tour"

    fixture = json.loads(GROK_FIXTURE.read_text(encoding="utf-8"))
    projected = api_client.post(
        "/v1/agent-templates/from-grok/", fixture, format="json"
    )
    assert projected.status_code == 200
    pack = projected.json()
    assert pack["kind"] == "agent_template"
    assert pack["profile"]["display_name"] == "Storefront Bee"

    other = api_client.post("/v1/agents/other/template/import/", fixture, format="json")
    assert other.status_code == 200
    replay = api_client.get("/v1/agents/other/template/").json()
    assert replay["profile"]["display_name"] == "Storefront Bee"
    assert replay["gettingStarted"]["skill"] == "welcome-tour"


def test_file_fixture_load_matches_validate(api_client):
    loaded = load_template_file(FIXTURE)
    response = api_client.post("/v1/agent-templates/validate/", loaded, format="json")
    assert response.status_code == 200
    assert response.json()["profile"] == loaded["profile"]


ENGINEER = (
    Path(__file__).resolve().parents[1] / "fixtures" / "swarm_engineer_template.json"
)


def test_template_create_and_mapper_urls():
    assert (
        resolve("/v1/agent-templates/import/").url_name == "agent-template-create-api"
    )
    assert (
        resolve("/v1/agent-templates/import").url_name
        == "agent-template-create-api-no-slash"
    )
    assert (
        resolve("/v1/agent-templates/grok-mapper/").url_name
        == "agent-template-grok-mapper-api"
    )


def test_post_export_then_create_import_round_trip(api_client, monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    raw = json.loads(ENGINEER.read_text(encoding="utf-8"))
    seeded = api_client.post(
        "/v1/agents/seed-engineer/template/import/", raw, format="json"
    )
    assert seeded.status_code == 200

    exported = api_client.post("/v1/agents/seed-engineer/template/")
    assert exported.status_code == 200
    disposition = exported["Content-Disposition"]
    assert disposition.startswith("attachment;")
    assert "seed-engineer-agent-template.json" in disposition
    pack = json.loads(exported.content)
    assert pack["routines"][0]["fill_ins"][0]["status"] == "pending"
    assert pack["plugins"][0]["pluginId"] == "github"

    created = api_client.post("/v1/agent-templates/import/", pack, format="json")
    assert created.status_code == 201
    body = created.json()
    assert body["created"] is True
    assert body["agent_id"] != "seed-engineer"
    assert body["fill_ins"][0]["key"] == "owner_repo"
    assert body["fill_ins"][0]["status"] == "pending"
    assert body["connect"][0]["status"] == "pending"
    assert body["gettingStarted"]["status"] == "pending"

    replay = api_client.get(f"/v1/agents/{body['agent_id']}/template/")
    assert replay.status_code == 200
    again = replay.json()
    assert again["profile"]["display_name"] == "Swarm Engineer"
    assert "{{owner_repo}}" in again["routines"][0]["instruction"]
    stored = list_routines(body["agent_id"])
    assert stored[0]["active"] is False
    assert plugin_pack.list_plugin_rows(body["agent_id"])[0]["pluginId"] == "github"


def test_file_upload_creates_agent(api_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    blob = ENGINEER.read_bytes()
    upload = SimpleUploadedFile(
        "swarm-engineer.json", blob, content_type="application/json"
    )
    created = api_client.post(
        "/v1/agent-templates/import/", {"file": upload}, format="multipart"
    )
    assert created.status_code == 201
    body = created.json()
    assert body["agent_id"] == "Swarm-Engineer"
    assert body["applied"]["skills"] == 1
    assert body["applied"]["routines"] == 1
    assert "sk-" not in json.dumps(body)


def test_grok_share_link_returns_400(api_client):
    response = api_client.post(
        "/v1/agent-templates/from-grok/",
        {"share_id": "bot_example", "deep_link": "https://grok.com/bot/example"},
        format="json",
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "grok_share_unsupported"
    assert "file-only" in body["error"]
    bare = api_client.post(
        "/v1/agent-templates/from-grok/",
        "https://grok.com/bot/example",
        format="json",
    )
    assert bare.status_code == 400
    assert bare.json()["code"] == "grok_share_unsupported"


def test_grok_mapper_endpoint_is_file_only(api_client, monkeypatch):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    response = api_client.get("/v1/agent-templates/grok-mapper/")
    assert response.status_code == 200
    body = response.json()
    assert body["live_call"] == "skipped"
    assert body["transport"] == "file-only"
    assert body["share_id"] == "not-used"
    assert "no XAI_API_KEY or GROK_API_KEY" in body["reason"]
    assert "field_map" in body

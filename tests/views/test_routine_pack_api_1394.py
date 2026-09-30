"""API tests for routines pack export/import (#1394)."""

import json
from pathlib import Path

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from swarm.core import routines as store

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent_routines_pack.json"


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


def test_export_pack_includes_fill_ins_for_empty_github_repo(api_client):
    created = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Ship notes",
            "instruction": "Summarize acme/widgets merges.",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "acme/widgets"},
        },
        format="json",
    )
    assert created.status_code == 201
    exported = api_client.get("/v1/agents/codey/routines/pack/")
    assert exported.status_code == 200
    body = exported.json()
    assert body["object"] == "agent_routines_pack"
    assert body["routines"][0]["name"] == "Ship notes"
    assert "history" not in body["routines"][0]
    keys = {slot["key"] for slot in body["fill_ins"]}
    assert keys == {"owner_repo"}
    assert body["routines"][0]["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert "{{owner_repo}}" in body["routines"][0]["instruction"]
    assert "acme/widgets" not in json.dumps(body["routines"])


def test_export_presets_query_adds_builtin_templates(api_client):
    store.create_routine(
        "codey",
        {
            "name": "Local interval",
            "instruction": "Ping.",
            "trigger": {"kind": "interval", "seconds": 3600},
        },
    )
    exported = api_client.get("/v1/agents/codey/routines/pack/?presets=1")
    assert exported.status_code == 200
    names = {row["name"] for row in exported.json()["routines"]}
    assert "Local interval" in names
    assert any("Issue Solver" in name for name in names)


def test_validate_fixture_and_import_pending(api_client):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    validated = api_client.post("/v1/routines/packs/validate/", raw, format="json")
    assert validated.status_code == 200, validated.content
    assert validated.json()["fill_ins"][0]["key"] == "owner_repo"

    imported = api_client.post(
        "/v1/agents/writer/routines/import/",
        {"pack": raw, "fill_ins": {"owner_repo": "acme/widgets"}},
        format="json",
    )
    assert imported.status_code == 200, imported.content
    body = imported.json()
    assert body["object"] == "agent_routines_pack_import"
    assert body["pending_enable"] is True
    assert body["created_count"] == 1
    row = body["routines"][0]
    assert row["active"] is False
    assert row["trigger"]["owner_repo"] == "acme/widgets"
    listed = api_client.get("/v1/agents/writer/routines/")
    assert listed.json()["routines"][0]["active"] is False


def test_import_secret_fill_in_is_400(api_client):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    response = api_client.post(
        "/v1/agents/writer/routines/import/",
        {"pack": raw, "fill_ins": {"owner_repo": "Bearer sk-abcdefghijklmnopqrst"}},
        format="json",
    )
    assert response.status_code == 400
    body = response.json()
    assert "secret" in body["error"].lower()
    assert body["code"] == "pack_secret"


def test_import_invalid_later_row_is_400_and_writes_nothing(api_client):
    response = api_client.post(
        "/v1/agents/writer/routines/import/",
        {
            "pack": {
                "routines": [
                    {
                        "name": "Keep me out",
                        "instruction": "Ping.",
                        "trigger": {"kind": "interval", "seconds": 3600},
                    },
                    {
                        "name": "Bad repo",
                        "instruction": "Watch {{owner_repo}}",
                        "trigger": {
                            "kind": "github_event",
                            "event_type": "issues.opened",
                            "owner_repo": "{{owner_repo}}",
                        },
                    },
                ]
            },
            "fill_ins": {"owner_repo": "not a repo"},
        },
        format="json",
    )
    assert response.status_code == 400, response.content
    assert response.json()["code"] == "pack_import_invalid"
    listed = api_client.get("/v1/agents/writer/routines/")
    assert listed.json()["routines"] == []


def test_export_import_export_round_trips_tools_and_model(api_client):
    """#1668 — the REST surface keeps a routine's tools and model."""
    created = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Ship notes",
            "instruction": "Summarize merges.",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "acme/widgets"},
            "tools": ["open_pull_request", "web-search"],
            "model": "litellm/orchestration",
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    assert created.json()["tools"] == ["open_pull_request", "web-search"]

    exported = api_client.get("/v1/agents/codey/routines/pack/")
    assert exported.status_code == 200, exported.content
    pack = exported.json()
    assert pack["routines"][0]["tools"] == ["open_pull_request", "web-search"]
    assert pack["routines"][0]["model"] == "litellm/orchestration"

    imported = api_client.post(
        "/v1/agents/writer/routines/import/",
        {"pack": pack, "fill_ins": {"owner_repo": "acme/widgets"}},
        format="json",
    )
    assert imported.status_code == 200, imported.content
    row = imported.json()["routines"][0]
    assert row["active"] is False
    assert row["tools"] == ["open_pull_request", "web-search"]
    assert row["model"] == "litellm/orchestration"

    replay = api_client.get("/v1/agents/writer/routines/pack/")
    assert replay.status_code == 200, replay.content
    assert replay.json()["routines"] == pack["routines"]


def test_patch_enable_after_fill_and_blocked_before(api_client):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pending = api_client.post(
        "/v1/agents/writer/routines/import/",
        {"pack": raw},
        format="json",
    )
    assert pending.status_code == 200, pending.content
    pending_row = pending.json()["routines"][0]
    assert pending_row["slug"] == "github_issue_solver"
    blocked = api_client.patch(
        f"/v1/agents/writer/routines/{pending_row['id']}/",
        {"enabled": True},
        format="json",
    )
    assert blocked.status_code == 400
    assert "fill-ins remain" in blocked.json()["error"]
    listed = api_client.get("/v1/agents/writer/routines/")
    assert listed.json()["routines"][0]["active"] is False
    assert listed.json()["routines"][0]["enabled"] is False

    filled = api_client.post(
        "/v1/agents/codey/routines/import/",
        {"pack": raw, "fill_ins": {"owner_repo": "acme/widgets"}},
        format="json",
    )
    assert filled.status_code == 200, filled.content
    filled_row = filled.json()["routines"][0]
    assert filled_row["slug"] == "github_issue_solver"
    assert "acme/widgets" in filled_row["description"]
    enabled = api_client.patch(
        f"/v1/agents/codey/routines/{filled_row['id']}/",
        {"enabled": True},
        format="json",
    )
    assert enabled.status_code == 200, enabled.content
    assert enabled.json()["active"] is True
    assert enabled.json()["enabled"] is True
    assert enabled.json()["slug"] == "github_issue_solver"


def test_pack_path_is_not_a_routine_id(api_client):
    missing = api_client.get("/v1/agents/codey/routines/pack/")
    assert missing.status_code == 400
    assert missing.json()["error"]
    listed = api_client.get("/v1/agents/codey/routines/")
    assert listed.status_code == 200
    assert listed.json()["routines"] == []


def test_enable_is_gated_until_fill_ins_supplied(api_client):
    created = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "GitHub Issue Solver",
            "description": "When an issue is opened, open a fix PR.",
            "instruction": "Investigate the issue and open a pull request.",
            "slug": "github-issue-solver",
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.opened",
                "owner_repo": "acme/widgets",
                "channel": "C0123ABCDEF",
            },
        },
        format="json",
    )
    assert created.status_code == 201, created.content
    exported = api_client.get("/v1/agents/codey/routines/pack/")
    assert exported.status_code == 200
    pack = exported.json()
    imported = api_client.post(
        "/v1/agents/writer/routines/import/",
        {"pack": pack},
        format="json",
    )
    assert imported.status_code == 200, imported.content
    row = imported.json()["routines"][0]
    assert row["active"] is False
    assert row["pending_fill"] is True
    assert row["description"].startswith("When an issue")
    routine_id = row["id"]
    blocked = api_client.post(
        f"/v1/agents/writer/routines/{routine_id}/enable/",
        {},
        format="json",
    )
    assert blocked.status_code == 400
    assert "fill-in" in blocked.json()["error"].lower()
    filled = api_client.post(
        f"/v1/agents/writer/routines/{routine_id}/fill/",
        {"fill_ins": {"owner_repo": "acme/widgets", "channel": "C0123ABCDEF"}},
        format="json",
    )
    assert filled.status_code == 200, filled.content
    assert filled.json()["pending_fill"] is False
    enabled = api_client.post(
        f"/v1/agents/writer/routines/{routine_id}/enable/",
        {},
        format="json",
    )
    assert enabled.status_code == 200, enabled.content
    assert enabled.json()["enabled"] is True
    listed = api_client.get("/v1/agents/writer/routines/")
    listed_row = listed.json()["routines"][0]
    assert listed_row["pending_fill"] is False
    assert listed_row["enabled"] is True

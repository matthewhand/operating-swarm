"""API tests for /v1/agents/<id>/memories/ (#1390). Backend only."""

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

from swarm.core import agent_memory as store

FAKE_OPENAI = "sk-notarealkeyABCDEFGH"
FAKE_EMAIL = "ada@example.test"
FAKE_PRIVATE_LINK = "http://127.0.0.1:9/internal"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate_memories(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_MEMORIES_PATH", str(tmp_path / "agent_memories.json"))
    store.reset_memories_cache()
    yield
    store.reset_memories_cache()


def test_memory_urls_accept_trailing_slash():
    assert resolve("/v1/agents/codey/memories").url_name == "agent-memories-api-no-slash"
    assert resolve("/v1/agents/codey/memories/").url_name == "agent-memories-api"
    assert resolve("/v1/agents/codey/memories/pack/").url_name == "agent-memory-pack-api"
    assert resolve("/v1/agents/codey/memories/import/").url_name == "agent-memory-import-api"
    assert resolve("/v1/agents/codey/memories/abc/").url_name == "agent-memory-detail-api"


def test_list_empty_then_create_and_delete(api_client):
    listed = api_client.get("/v1/agents/codey/memories/")
    assert listed.status_code == 200
    body = listed.json()
    assert body["object"] == "agent_memory_list"
    assert body["memories"] == []

    created = api_client.post(
        "/v1/agents/codey/memories/",
        {"kind": "profile", "title": "Voice", "body": "Prefers short answers."},
        format="json",
    )
    assert created.status_code == 201
    row = created.json()
    assert row["object"] == "agent_memory"
    assert row["kind"] == "profile"
    assert row["tier"] == "pack"
    assert row["body"] == "Prefers short answers."

    again = api_client.get("/v1/agents/codey/memories/")
    assert len(again.json()["memories"]) == 1

    deleted = api_client.delete(f"/v1/agents/codey/memories/{row['id']}/")
    assert deleted.status_code == 204
    missing = api_client.delete(f"/v1/agents/codey/memories/{row['id']}/")
    assert missing.status_code == 404


def test_create_rejects_credential_shaped_strings(api_client):
    response = api_client.post(
        "/v1/agents/codey/memories/",
        {"kind": "log", "body": f"api_key={FAKE_OPENAI}"},
        format="json",
    )
    assert response.status_code == 400
    assert "credential" in response.json()["error"].lower()
    empty = api_client.get("/v1/agents/codey/memories/")
    assert empty.json()["memories"] == []


def test_tier_filter(api_client):
    api_client.post(
        "/v1/agents/codey/memories/",
        {"kind": "profile", "body": "Identity."},
        format="json",
    )
    api_client.post(
        "/v1/agents/codey/memories/",
        {"kind": "log", "body": "Weekly review."},
        format="json",
    )
    api_client.post(
        "/v1/agents/codey/memories/",
        {"kind": "episode", "body": "Tuesday chat."},
        format="json",
    )
    api_client.post(
        "/v1/agents/codey/memories/",
        {"kind": "note", "body": "Scratch."},
        format="json",
    )

    pack = api_client.get("/v1/agents/codey/memories/?tier=pack")
    assert pack.status_code == 200
    assert {row["kind"] for row in pack.json()["memories"]} == {"profile", "log"}

    local = api_client.get("/v1/agents/codey/memories/?tier=local")
    assert {row["kind"] for row in local.json()["memories"]} == {"episode", "note"}

    logs = api_client.get("/v1/agents/codey/memories/?kind=log")
    assert [row["kind"] for row in logs.json()["memories"]] == ["log"]

    both = api_client.get("/v1/agents/codey/memories/?kind=log&tier=pack")
    assert [row["kind"] for row in both.json()["memories"]] == ["log"]
    crossed = api_client.get("/v1/agents/codey/memories/?kind=episode&tier=pack")
    assert crossed.status_code == 200
    assert crossed.json()["memories"] == []


def test_pack_round_trip_fragment(api_client):
    api_client.post(
        "/v1/agents/source/memories/",
        {"kind": "profile", "body": f"Keep the motto. Contact {FAKE_EMAIL}."},
        format="json",
    )
    api_client.post(
        "/v1/agents/source/memories/",
        {"kind": "log", "body": f"Shipped. Notes at {FAKE_PRIVATE_LINK}"},
        format="json",
    )
    api_client.post(
        "/v1/agents/source/memories/",
        {"kind": "episode", "body": "Private Tuesday chat."},
        format="json",
    )
    api_client.post(
        "/v1/agents/source/memories/",
        {"kind": "note", "body": "Do not pack this."},
        format="json",
    )

    exported = api_client.get("/v1/agents/source/memories/pack/")
    assert exported.status_code == 200
    fragment = exported.json()
    assert fragment["object"] == "agent_memory_pack"
    kinds = {row["kind"] for row in fragment["memories"]}
    assert kinds == {"profile", "log"}
    blob = " ".join(row["body"] for row in fragment["memories"])
    assert FAKE_EMAIL not in blob
    assert FAKE_PRIVATE_LINK not in blob
    assert "Keep the motto." in blob
    assert "Tuesday chat" not in blob

    dirty = {
        "object": "agent_memory_pack",
        "memories": [
            *fragment["memories"],
            {"kind": "episode", "body": "Should be ignored on import."},
            {"kind": "profile", "body": f"Use {FAKE_OPENAI} never."},
        ],
    }
    imported = api_client.post(
        "/v1/agents/target/memories/import/",
        dirty,
        format="json",
    )
    assert imported.status_code == 200
    assert imported.json()["imported"] >= 2
    listed = api_client.get("/v1/agents/target/memories/")
    bodies = [row["body"] for row in listed.json()["memories"]]
    joined = " ".join(bodies)
    assert FAKE_OPENAI not in joined
    assert "Should be ignored on import." not in joined
    assert any("Keep the motto." in body for body in bodies)
    assert any("[REDACTED]" in body for body in bodies)


def test_import_skips_rows_without_a_kind(api_client):
    imported = api_client.post(
        "/v1/agents/target/memories/import/",
        {"memories": [{"body": "no kind"}, {"kind": "profile", "body": "keep"}]},
        format="json",
    )
    assert imported.status_code == 200
    assert imported.json()["imported"] == 1
    listed = api_client.get("/v1/agents/target/memories/")
    assert [row["body"] for row in listed.json()["memories"]] == ["keep"]


def test_corrupt_store_is_not_replaced(api_client, tmp_path):
    path = tmp_path / "agent_memories.json"
    path.write_text("{", encoding="utf-8")
    store.reset_memories_cache()
    listed = api_client.get("/v1/agents/codey/memories/")
    assert listed.status_code == 500
    created = api_client.post(
        "/v1/agents/codey/memories/",
        {"kind": "note", "body": "should not wipe the file"},
        format="json",
    )
    assert created.status_code == 500
    assert path.read_text(encoding="utf-8") == "{"

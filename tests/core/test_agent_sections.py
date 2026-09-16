"""Issue #219 — persisted rail section store."""

from __future__ import annotations

import pytest

from swarm.core.agent_sections import (
    STORE_NAME,
    UNASSIGNED_SECTION_ID,
    empty_store,
    find_section,
    membership_map,
    normalize_store,
    reset_sections_cache,
    sections_path,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SECTIONS_PATH", str(tmp_path / STORE_NAME))
    reset_sections_cache()
    yield
    reset_sections_cache()


def test_store_path_is_sections_json_not_teams():
    path = sections_path()
    assert path.name == STORE_NAME
    assert path.name != "teams.json"


def test_normalize_drops_unassigned_and_archived_membership():
    payload = normalize_store(
        {
            "sections": [
                {"id": UNASSIGNED_SECTION_ID, "name": "nope"},
                {"id": "sec_a", "name": "Review"},
                {"id": "sec_b", "name": "Old", "archived": True},
            ],
            "membership": {
                "pat": "sec_a",
                "lee": UNASSIGNED_SECTION_ID,
                "ivy": "sec_b",
                "ghost": "sec_missing",
            },
        }
    )
    ids = {row["id"] for row in payload["sections"]}
    assert UNASSIGNED_SECTION_ID not in ids
    assert payload["membership"] == {"pat": "sec_a"}
    assert find_section("sec_a", payload)["name"] == "Review"
    assert membership_map(payload)["pat"] == "sec_a"


def test_empty_store_shape():
    store = empty_store()
    assert store["schema"] == 1
    assert store["sections"] == []
    assert store["membership"] == {}

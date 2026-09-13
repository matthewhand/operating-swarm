"""Lock tests: fast designed-agents feed for the rail (router_designs.json).

The sidebar lists designer-created agents via ``GET /v1/agents/designs/``,
which reads the designs file directly instead of initializing the agent
router blueprint (whose /v1/agents/ listing takes ~55s when cold).
"""

import pytest
from django.test import Client

from swarm.core.router_designs import upsert_design

pytestmark = pytest.mark.django_db


@pytest.fixture
def designs_file(tmp_path, monkeypatch):
    path = tmp_path / "router_designs.json"
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(path))
    return path


def test_designs_feed_lists_designs(designs_file):
    upsert_design({
        "kind": "cli",
        "name": "Waveshare OpenCode",
        "agent_id": "waveshare-opencode",
        "cli": "opencode",
        "description": "Waveshare rover driver",
    })
    response = Client().get("/v1/agents/designs/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    ids = [row["agent_id"] for row in payload["data"]]
    assert "waveshare-opencode" in ids
    row = next(r for r in payload["data"] if r["agent_id"] == "waveshare-opencode")
    assert row["kind"] == "cli"
    assert row["cli"] == "opencode"
    assert row["name"] == "Waveshare OpenCode"


def test_designs_feed_empty_when_no_designs(designs_file):
    response = Client().get("/v1/agents/designs/")
    assert response.status_code == 200
    assert response.json() == {"object": "list", "data": []}


def test_designs_feed_reflects_deletion(designs_file):
    spec = upsert_design({
        "kind": "personality",
        "name": "Night Editor",
        "instructions": "Tighten prose.",
    })
    client = Client()
    listed = client.get("/v1/agents/designs/").json()
    assert [r["agent_id"] for r in listed["data"]] == ["night-editor"]

    delete = client.delete(f"/v1/agents/design/{spec['agent_id']}/")
    assert delete.status_code == 200
    listed = client.get("/v1/agents/designs/").json()
    assert listed["data"] == []

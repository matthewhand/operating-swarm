"""#601 — /v1/remotes/ and /v1/team-rosters/ carry the rail activity instant.

The rail's time slot can never fill for remote/team rows unless the payloads
that feed them carry a timestamp. Both views stamp ``last_message_at`` from
``chat_store.rail_activity_index`` when the store knows the seat; honest
absence (no thread) stays absent — no fabricated "now" (issue #601).
"""

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from swarm.core.remotes import RemoteSpec


@pytest.fixture
def api_client():
    return APIClient()


def _spec(rid: str) -> RemoteSpec:
    return RemoteSpec(
        id=rid,
        title="TrueForge box",
        host_label="box",
        base_url="http://198.51.100.36:8791",
        source="config",
    )


def _remotes_ctx(specs, activity):
    """``activity`` maps store stems (``remote-<id>``, ``team-<id>``) to ISO stamps."""
    p1 = patch("swarm.views.remotes_api.remotes_core.load_all_remotes", lambda: dict(specs))
    p2 = patch(
        "swarm.views.remotes_api.remotes_core.list_configured_remotes",
        lambda: list(specs.values()),
    )
    p3 = patch("swarm.views.remotes_api.remotes_core.list_team_members", lambda: [])
    p4 = patch("swarm.core.chat_store.rail_activity_index", lambda **_activity: activity)
    return p1, p2, p3, p4


def test_remotes_list_stamps_last_message_at(api_client):
    activity = {"remote-trueforge": "2026-09-18T10:00:00+00:00"}
    p1, p2, p3, p4 = _remotes_ctx({"trueforge": _spec("trueforge")}, activity)
    with p1, p2, p3, p4:
        resp = api_client.get("/v1/remotes/")
    assert resp.status_code == 200
    rows = {row["id"]: row for row in resp.json()["data"]}
    assert rows["trueforge"]["last_message_at"] == "2026-09-18T10:00:00+00:00"


def test_remotes_list_omits_instant_when_store_has_none(api_client):
    p1, p2, p3, p4 = _remotes_ctx({"trueforge": _spec("trueforge")}, {})
    with p1, p2, p3, p4:
        resp = api_client.get("/v1/remotes/")
    row = resp.json()["data"][0]
    assert not row.get("last_message_at")


def test_team_rosters_list_stamps_last_message_at(api_client, monkeypatch):
    # The view imports load_team_rosters into its own namespace — patch there.
    monkeypatch.setattr(
        "swarm.views.team_rosters_api.load_team_rosters",
        lambda: {"demo-team": {"id": "demo-team", "name": "Demo Team", "members": []}},
    )
    monkeypatch.setattr(
        "swarm.core.chat_store.rail_activity_index",
        lambda **_activity: {"team-demo-team": "2026-09-18T11:00:00+00:00"},
    )
    resp = api_client.get("/v1/team-rosters/")
    assert resp.status_code == 200
    row = resp.json()["data"][0]
    assert row["id"] == "demo-team"
    assert row["last_message_at"] == "2026-09-18T11:00:00+00:00"


def test_team_rosters_list_omits_instant_when_store_has_none(api_client, monkeypatch):
    monkeypatch.setattr(
        "swarm.views.team_rosters_api.load_team_rosters",
        lambda: {"demo-team": {"id": "demo-team", "name": "Demo Team", "members": []}},
    )
    monkeypatch.setattr("swarm.core.chat_store.rail_activity_index", lambda **_activity: {})
    resp = api_client.get("/v1/team-rosters/")
    row = resp.json()["data"][0]
    assert not row.get("last_message_at")

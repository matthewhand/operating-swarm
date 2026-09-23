"""#642 — /v1/remotes/ stamps the agents that depend on each remote.

Settings must grey a remote's Remove control while agents are registered on
it. The data lives server-side (blueprint library custom seats carry a
``remote`` binding), so the list payload stamps an ``agents`` row-list per
remote — honest absence (no dependents) stays absent, like #601's stamp.
"""

from contextlib import ExitStack
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


def _remotes_ctx(specs):
    p1 = patch("swarm.views.remotes_api.remotes_core.load_all_remotes", lambda: dict(specs))
    p2 = patch(
        "swarm.views.remotes_api.remotes_core.list_configured_remotes",
        lambda: list(specs.values()),
    )
    p3 = patch("swarm.views.remotes_api.remotes_core.list_team_members", lambda: [])
    p4 = patch("swarm.core.chat_store.rail_activity_summaries", lambda **_activity: {})
    return p1, p2, p3, p4


def _library_ctx(library):
    # The view imports the getter at call time from its own module — patch the
    # source module so the call-time import picks up the stub.
    return patch(
        "swarm.views.blueprint_library_views.get_user_blueprint_library",
        lambda: library,
    )

def test_remotes_list_stamps_dependent_agents(api_client):
    specs = {"trueforge": _spec("trueforge"), "herdr": _spec("herdr")}
    library = {
        "custom": [
            {
                "id": "tf-seat",
                "name": "TF seat",
                "remote": {"id": "trueforge", "kind": "trueforge"},
            },
            {"id": "other", "name": "Other", "remote": {"id": "herdr", "kind": "herdr"}},
            {"id": "unbound", "name": "Unbound"},
        ]
    }
    with ExitStack() as stack:
        for ctx in (*_remotes_ctx(specs), _library_ctx(library)):
            stack.enter_context(ctx)
        response = api_client.get("/v1/remotes/")
    assert response.status_code == 200
    body = response.json()
    by_id = {row["id"]: row for row in body["configured"]}
    assert by_id["trueforge"]["agents"] == [{"id": "tf-seat", "name": "TF seat"}]
    assert by_id["herdr"]["agents"] == [{"id": "other", "name": "Other"}]


def test_remotes_list_omits_agents_key_when_unbound(api_client):
    specs = {"trueforge": _spec("trueforge")}
    library = {"custom": [{"id": "unbound", "name": "Unbound"}]}
    with ExitStack() as stack:
        for ctx in (*_remotes_ctx(specs), _library_ctx(library)):
            stack.enter_context(ctx)
        response = api_client.get("/v1/remotes/")
    row = response.json()["configured"][0]
    assert "agents" not in row

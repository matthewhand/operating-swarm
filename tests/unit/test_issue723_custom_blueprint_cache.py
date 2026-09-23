"""#723 — custom-blueprint writes must invalidate the blueprint metadata cache.

The defect: Support's "Add as agent" (POST /v1/blueprints/custom/) persisted
the seat but the long-running server kept serving the pre-creation metadata
map, so `/chat?blueprint=<id>` 404'd ("was not found or could not be
initialized") until a restart. Same gap in PATCH/PUT/DELETE and the
edit-source path.
"""

from __future__ import annotations

from unittest.mock import patch

from rest_framework import status

from swarm.views import api_views
from swarm.views.utils import (
    get_available_blueprints_sync,
    invalidate_blueprint_meta_cache,
)


def _empty_library():
    return {"installed": [], "custom": []}


def setup_function(_fn):
    # Start each test from a populated (stale) cache, like a long-running server.
    invalidate_blueprint_meta_cache()
    api_views._custom_blueprints_registry.clear()


def teardown_function(_fn):
    invalidate_blueprint_meta_cache()
    api_views._custom_blueprints_registry.clear()


def test_create_custom_seat_visible_to_chat_without_restart(api_client):
    # Prime the cache BEFORE the seat exists — the server's pre-creation map.
    before = get_available_blueprints_sync()
    assert isinstance(before, dict)
    assert "desk_cli" not in before

    with patch(
        "swarm.views.api_views.save_user_blueprint_library", return_value=True
    ), patch(
        "swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library()
    ):
        response = api_client.post(
            "/v1/blueprints/custom/",
            data={
                "name": "Desk CLI",
                "kind": "cli",
                "command": "grok -p",
                "category": "cli",
                "tags": ["cli"],
            },
            format="json",
        )
    assert response.status_code == status.HTTP_201_CREATED

    # The cache must have been dropped and rebuilt with the new seat —
    # get_blueprint_instance resolves chat lookups through this same map.
    after = get_available_blueprints_sync()
    assert "desk_cli" in after


def test_delete_custom_seat_removed_from_chat_without_restart(api_client):
    with patch(
        "swarm.views.api_views.save_user_blueprint_library", return_value=True
    ), patch(
        "swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library()
    ):
        api_client.post(
            "/v1/blueprints/custom/",
            data={
                "name": "Desk CLI",
                "kind": "cli",
                "command": "grok -p",
                "category": "cli",
                "tags": ["cli"],
            },
            format="json",
        )
    assert "desk_cli" in get_available_blueprints_sync()

    with patch(
        "swarm.views.api_views.save_user_blueprint_library", return_value=True
    ), patch(
        "swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library()
    ):
        response = api_client.delete("/v1/blueprints/custom/desk_cli/")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert "desk_cli" not in get_available_blueprints_sync()


def test_persist_custom_item_invalidates_cache():
    from swarm.core.support_nl_blueprint import persist_custom_item

    # Prime the cache first (long-running-server shape).
    get_available_blueprints_sync()
    item = {
        "id": "ba_eng_tester",
        "name": "BA → Engineer → Tester",
        "description": "NL team",
        "kind": "api",
        "code": "class X:\n    pass\n",
        "tags": ["support-nl", "handoff", "team"],
        "rail": True,
        "source": "support-nl",
    }
    persist_custom_item(item, disk=False)
    assert "ba_eng_tester" in get_available_blueprints_sync()

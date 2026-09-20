"""#809 — custom blueprint ID conflicts auto-suffix instead of 409.

"Add as agent" on a Support-generated card used to fail with
``{"error": "id already exists"}`` when the ID was taken. The server now
resolves the collision itself: the created seat gets the next free
``<base>_2``, ``<base>_3``… suffix and the client navigates to the
returned ``id``.
"""

from __future__ import annotations

from unittest.mock import patch

from rest_framework import status

from swarm.views import api_views


def _empty_library():
    return {"installed": [], "custom": []}


def setup_function(_fn):
    api_views.invalidate_blueprint_meta_cache()
    api_views._custom_blueprints_registry.clear()


def teardown_function(_fn):
    api_views.invalidate_blueprint_meta_cache()
    api_views._custom_blueprints_registry.clear()


def _post(api_client, bp_id, **overrides):
    body = {
        "id": bp_id,
        "name": overrides.pop("name", bp_id),
        "description": "d",
        "code": "x = 1",
    }
    body.update(overrides)
    return api_client.post("/v1/blueprints/custom/", body, format="json")


def test_duplicate_id_gets_incremented_suffix(api_client):
    existing = {"installed": [], "custom": [{"id": "philosophers", "name": "Philosophers"}]}
    with patch(
        "swarm.views.api_views.save_user_blueprint_library", return_value=True
    ), patch(
        "swarm.views.api_views.get_user_blueprint_library", return_value=existing
    ):
        response = _post(api_client, "philosophers")
    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["id"] == "philosophers_2"
    # The suffixed seat is appended to the library next to the original.
    assert [i["id"] for i in existing["custom"]] == ["philosophers", "philosophers_2"]


def test_suffix_skips_taken_ids(api_client):
    existing = {
        "installed": [],
        "custom": [
            {"id": "team_x", "name": "X"},
            {"id": "team_x_2", "name": "X 2"},
        ],
    }
    with patch(
        "swarm.views.api_views.save_user_blueprint_library", return_value=True
    ), patch(
        "swarm.views.api_views.get_user_blueprint_library", return_value=existing
    ):
        response = _post(api_client, "team_x")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["id"] == "team_x_3"


def test_unique_id_unchanged(api_client):
    with patch(
        "swarm.views.api_views.save_user_blueprint_library", return_value=True
    ), patch(
        "swarm.views.api_views.get_user_blueprint_library", return_value=_empty_library()
    ):
        response = _post(api_client, "fresh_seat")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["id"] == "fresh_seat"

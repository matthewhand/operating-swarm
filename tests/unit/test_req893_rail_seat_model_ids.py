"""#426 — a rail seat that looks chattable must resolve, or not be a model id.

``GET /v1/agents/`` is the rail roster: every row reports ``agent_type``, and an
``api`` row is assumed to be a completions ``model`` id. Before this the roster
advertised three seats that ``POST /v1/chat/completions`` answered with ``404
requested model (blueprint) was not found``:

* ``starter-support`` — the builtin Support seat. It *does* have a real
  blueprint (``support``), it just never got the ``/v1/models`` alias that
  ``api_agent`` -> ``chatbot`` already has (#136). Option A.
* ``researcher`` / ``writer`` — ``agent_router`` specialists. No standalone
  blueprint exists and their persona lives inside the router design, so
  aliasing them would silently drop the persona. They are rail chrome:
  the roster reports ``chat_model: None``. Option B.

Both REST and the websocket funnel through ``resolve_chat_blueprint_id`` +
``get_blueprint_instance`` (``consumers.py`` imports the same helper), so the
parity the ticket asks for ("WS path must match REST") holds by construction —
these tests pin the shared recipe rather than re-testing it twice.
"""

from __future__ import annotations

import pytest
from django.test import Client

from swarm.core.agent_kind import resolve_chat_blueprint_id
from swarm.views.utils import get_available_blueprints_sync, validate_model_access

# Specialist sub-agents of agent_router — rail chrome, never completions ids.
ROUTER_SPECIALISTS = ("researcher", "writer")
STARTER_SUPPORT = "starter-support"
SUPPORT_BLUEPRINT = "support"


@pytest.fixture
def client():
    return Client()


# --- Option A: starter-support resolves like api_agent -> chatbot -------------


def test_starter_support_resolves_to_the_support_recipe():
    assert resolve_chat_blueprint_id(STARTER_SUPPORT) == SUPPORT_BLUEPRINT
    # The alias must be case-insensitive, like the api_agent one.
    assert resolve_chat_blueprint_id("STARTER-SUPPORT") == SUPPORT_BLUEPRINT


def test_starter_support_is_a_v1_models_id_cloned_from_support():
    avail = get_available_blueprints_sync()
    assert SUPPORT_BLUEPRINT in avail
    assert STARTER_SUPPORT in avail
    # Same recipe the websocket runs — not a stub class of its own.
    assert avail[STARTER_SUPPORT]["class_type"] is avail[SUPPORT_BLUEPRINT]["class_type"]
    assert avail[STARTER_SUPPORT]["metadata"]["name"] == STARTER_SUPPORT


def test_starter_support_passes_the_completions_model_gate():
    # This is exactly the check that produced the 404.
    assert validate_model_access(None, STARTER_SUPPORT) is True


@pytest.mark.asyncio
async def test_starter_support_is_drivable_by_the_shared_recipe():
    from swarm.views.utils import get_blueprint_instance

    instance = await get_blueprint_instance(STARTER_SUPPORT)
    assert instance is not None


# --- Option B: router specialists are not completions ids --------------------


@pytest.mark.django_db
def test_roster_marks_starter_support_as_a_model_id(client):
    resp = client.get("/v1/agents/")
    assert resp.status_code == 200
    rows = resp.json()["data"]["agents"]
    assert STARTER_SUPPORT in rows
    assert rows[STARTER_SUPPORT]["chat_model"] == STARTER_SUPPORT


@pytest.mark.django_db
def test_roster_does_not_offer_router_specialists_as_model_ids(client):
    resp = client.get("/v1/agents/")
    rows = resp.json()["data"]["agents"]
    for seat in ROUTER_SPECIALISTS:
        assert seat in rows, seat
        row = rows[seat]
        assert row["kind"] == "builtin"
        assert row["agent_type"] == "api"
        # Still on the rail, just honestly labelled as specialist-only.
        assert row["chat_model"] is None, seat


@pytest.mark.django_db
def test_every_seat_advertising_a_chat_model_resolves_on_completions(client):
    """The #426 invariant: nothing may look chattable and then 404."""
    rows = client.get("/v1/agents/").json()["data"]["agents"]
    avail = get_available_blueprints_sync()
    for seat_id, row in rows.items():
        model_id = row.get("chat_model")
        if not model_id:
            continue
        assert resolve_chat_blueprint_id(model_id) in avail, seat_id
        assert validate_model_access(None, model_id) is True, seat_id


@pytest.mark.django_db
def test_router_specialists_are_not_in_v1_models(client):
    """The other half of the contract — they must not be listed as models."""
    models = client.get("/v1/models").json()["data"]
    ids = {row["id"] for row in models}
    for seat in ROUTER_SPECIALISTS:
        assert seat not in ids, seat
    assert STARTER_SUPPORT in ids

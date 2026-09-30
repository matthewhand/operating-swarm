"""#1706 D.16 — the API refuses a role write for a team or a chat.

The rule itself is pinned in ``test_req1706_role_capability``. This file is
about the thing that was actually broken: the API accepted the write. Three
write paths took a ``role`` from a caller, and none of them asked
``validate_role_for_kind``:

* ``PATCH``/``PUT /v1/agents/<id>/settings/`` → ``update_settings``
  (``profile.role`` — the seat the SPA editor writes through)
* ``POST /v1/org-library/`` → ``normalize_bot`` (``role`` + ``kind``)
* ``POST``/``PATCH /v1/blueprints/custom/`` → ``build_custom_rail_item``
  (which stores a raw ``role`` straight onto the rail row)

Each is exercised through its real entry point, and the assertions are on
behaviour — the store afterwards, the exception, the HTTP status — never on
the source text.
"""

from __future__ import annotations

import pytest

TEAM_ID = "team:alpha"
CHAT_ID = "chat:codey:conv-1"
API_SEAT_ID = "codey"


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Keep the settings store inside tmp; never touch a real config dir."""
    from swarm.core import agent_settings

    monkeypatch.setenv(agent_settings.ENV_SETTINGS_PATH, str(tmp_path / "agent_settings.json"))
    agent_settings.reset_agent_settings_cache()
    yield
    agent_settings.reset_agent_settings_cache()


# --------------------------------------------------------------------------
# PATCH /v1/agents/<id>/settings/  (the editor's write path)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("agent_id", [TEAM_ID, CHAT_ID])
@pytest.mark.parametrize("role", ["gate", "support", "chief_of_staff", "custom_thing"])
def test_settings_patch_rejects_role_for_team_or_chat(agent_id: str, role: str) -> None:
    from swarm.core.agent_settings import get_settings, update_settings

    with pytest.raises(ValueError) as excinfo:
        update_settings(agent_id, {"profile": {"role": role}})
    assert "cannot be assigned a role" in str(excinfo.value)
    # The rejection must leave the store untouched — a refused write that
    # half-applied would be worse than one that was accepted.
    assert get_settings(agent_id)["profile"]["role"] == ""


@pytest.mark.parametrize("agent_id", [TEAM_ID, CHAT_ID])
def test_settings_patch_accepts_clearing_the_role(agent_id: str) -> None:
    from swarm.core.agent_settings import update_settings

    assert update_settings(agent_id, {"profile": {"role": ""}})["profile"]["role"] == ""
    assert update_settings(agent_id, {"profile": {"role": "default"}})["profile"]["role"] == ""


def test_settings_patch_still_accepts_a_role_for_an_api_seat() -> None:
    # The gate is scoped to team/chat. If this breaks, ordinary seats lost
    # their role editor entirely — the far worse failure.
    from swarm.core.agent_settings import get_settings, update_settings

    assert update_settings(API_SEAT_ID, {"profile": {"role": "gate"}})["profile"]["role"] == "gate"
    assert get_settings(API_SEAT_ID)["profile"]["role"] == "gate"


def test_settings_patch_without_a_role_is_untouched_for_a_team() -> None:
    # The gate fires on the WRITE, not on the seat's kind: a team id must
    # still accept every unrelated setting, or this fix would break voice,
    # folder and MCP-grant saves for every team row.
    from swarm.core.agent_settings import update_settings

    out = update_settings(TEAM_ID, {"new_chat_per_task": True, "folder": "/srv/work"})
    assert out["new_chat_per_task"] is True
    assert out["folder"] == "/srv/work"


def test_settings_http_patch_returns_400_for_a_chat_role(api_client) -> None:
    # The view's own contract, end to end: a refused role must be a 400 whose
    # body carries the reason, not a 200 that quietly dropped the field.
    response = api_client.patch(
        f"/v1/agents/{CHAT_ID}/settings/",
        {"profile": {"role": "gate"}},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert b"cannot be assigned a role" in response.content


def test_profile_http_patch_rejects_a_role_for_a_team_seat(api_client) -> None:
    # The profile endpoint is a SECOND role write path (`role` is in
    # PROFILE_FIELD_KEY_SET), and it slugified the agent id before the core
    # call — which is exactly how a `team:` id slipped past the gate there.
    response = api_client.patch(
        f"/v1/agents/{TEAM_ID}/profile/",
        {"role": "gate"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert b"cannot be assigned a role" in response.content


def test_profile_http_patch_still_200_for_an_api_seat_role(api_client) -> None:
    # Non-regression guard on the same endpoint. Passes before and after.
    response = api_client.patch(
        f"/v1/agents/{API_SEAT_ID}/profile/",
        {"role": "gate"},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["role"] == "gate"


def test_settings_http_patch_still_200_for_an_api_seat_role(api_client) -> None:
    # Non-regression guard on the same endpoint: the gate must not have closed
    # the settings API for ordinary seats. Passes before and after by design.
    response = api_client.patch(
        f"/v1/agents/{API_SEAT_ID}/settings/",
        {"profile": {"role": "gate"}},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["profile"]["role"] == "gate"


# --------------------------------------------------------------------------
# POST /v1/org-library/
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["cli"])
def test_org_library_rejects_support_on_non_api_seats(kind: str) -> None:
    from swarm.core.org_bot_library import OrgLibraryError, normalize_bot

    with pytest.raises(OrgLibraryError) as excinfo:
        normalize_bot({"id": "probe_bot", "name": "probe_bot", "kind": kind, "role": "support"})
    assert "Support role is exclusively available to API agents" in str(excinfo.value)


@pytest.mark.parametrize("kind", ["api", "blueprint"])
def test_org_library_still_accepts_support_on_api_family_seats(kind: str) -> None:
    # Non-regression guard: the org library's api/blueprint bots keep the role
    # #853 allows them. Passes before and after by design.
    from swarm.core.org_bot_library import normalize_bot

    assert normalize_bot({"id": "probe_bot", "name": "p", "kind": kind, "role": "support"})["role"] == "support"


def test_org_library_accepts_an_ordinary_role_on_a_cli_bot() -> None:
    from swarm.core.org_bot_library import normalize_bot

    row = normalize_bot({"id": "probe_bot", "name": "probe_bot", "kind": "cli", "role": "gate"})
    assert row["role"] == "gate"


# --------------------------------------------------------------------------
# POST / PATCH /v1/blueprints/custom/  (the rail seat write)
# --------------------------------------------------------------------------


def test_custom_seat_write_refuses_a_role_the_rule_forbids() -> None:
    from swarm.core.rail_seats import CustomSeatError, build_custom_rail_item

    with pytest.raises(CustomSeatError) as excinfo:
        build_custom_rail_item(
            {"id": "y", "name": "y", "kind": "cli", "command": "echo hi", "role": "support"}
        )
    assert "Support role is exclusively available to API agents" in str(excinfo.value)


def test_custom_seat_write_refuses_a_role_on_a_team_row() -> None:
    # #1706 D.16 — the team half, on the same chokepoint, addressed by id when
    # the row carries no `kind` field.
    from swarm.core.rail_seats import CustomSeatError, build_custom_rail_item

    with pytest.raises(CustomSeatError) as excinfo:
        build_custom_rail_item({"id": "team:alpha", "name": "alpha", "role": "gate"})
    assert "cannot be assigned a role" in str(excinfo.value)


def test_custom_seat_write_accepts_an_allowed_role() -> None:
    from swarm.core.rail_seats import build_custom_rail_item

    item = build_custom_rail_item(
        {"id": "y", "name": "y", "kind": "cli", "command": "echo hi", "role": "gate"}
    )
    assert item["role"] == "gate"


def test_custom_seat_unrelated_update_is_not_blocked() -> None:
    # Non-regression guard: a later edit to a seat that carries a role must not
    # be refused for it, or a mislabelled row could never be renamed/re-modelled.
    from swarm.core.rail_seats import build_custom_rail_item

    item = build_custom_rail_item(
        {"id": "y", "name": "y", "kind": "cli", "command": "echo hi", "role": "gate"},
        existing={"id": "y", "role": "gate"},
    )
    assert item["name"] == "y"

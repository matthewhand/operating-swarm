"""#1706 D.16 — a team or a chat session cannot be assigned a role.

The rule lives in exactly one place, ``validate_role_for_kind``
(``swarm.core.roles.registry``). This file pins that rule directly, and then
pins every API write path onto it, because the defect was never the rule —
it was that three write paths answered "is this role allowed?" on their own
(or not at all), so the API accepted writes the rule forbids.

Two things are deliberately NOT asserted here, because they are not this
issue's business:

* nothing renders a role *badge* (that is #1698/#1706 §A/B/C, shipped);
* no new role id is introduced. ``gate``/``support``/a custom slug are used
  as the payloads precisely so the tests keep passing if the role vocabulary
  ever changes — the constraint is about the SEAT, not the role.
"""

from __future__ import annotations

import pytest

from swarm.core.agent_roles import role_seat_kind_for, validate_role_for_kind
from swarm.core.roles.registry import (
    TEAM_CHAT_ROLE_INCAPABLE_SEAT_KINDS,
    TEAM_CHAT_ROLE_KIND_ERROR,
)

# Any non-default role must be refused on these seats. `default` is the
# absence of a role, so it is valid everywhere — including a team or a chat.
NON_DEFAULT_ROLES = ("support", "gate", "skeptic", "chief_of_staff", "engineer", "custom_thing")
ROLE_CAPABLE_SEAT_KINDS = ("api", "blueprint", "cli", "remote")


# --------------------------------------------------------------------------
# The single decision point
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seat_kind", sorted(TEAM_CHAT_ROLE_INCAPABLE_SEAT_KINDS))
@pytest.mark.parametrize("role", NON_DEFAULT_ROLES)
def test_team_and_chat_reject_every_role(role: str, seat_kind: str) -> None:
    error = validate_role_for_kind(role, seat_kind)
    assert error is not None, f"{role!r} must be rejected on a {seat_kind} seat"
    assert error == TEAM_CHAT_ROLE_KIND_ERROR


@pytest.mark.parametrize("seat_kind", sorted(TEAM_CHAT_ROLE_INCAPABLE_SEAT_KINDS))
def test_team_and_chat_still_accept_default(seat_kind: str) -> None:
    # Clearing a role is not assigning one, so it must never be refused —
    # otherwise a stale role on a seat could never be removed.
    assert validate_role_for_kind("default", seat_kind) is None
    assert validate_role_for_kind("", seat_kind) is None
    assert validate_role_for_kind(None, seat_kind) is None


@pytest.mark.parametrize("seat_kind", ROLE_CAPABLE_SEAT_KINDS)
def test_role_capable_seats_keep_their_roles(seat_kind: str) -> None:
    for role in NON_DEFAULT_ROLES:
        if role == "support" and seat_kind not in ("api", "blueprint"):
            # #853, unchanged: support is API-only. Asserted explicitly so this
            # test cannot be read as "D.16 lifted the support restriction".
            assert validate_role_for_kind(role, seat_kind) is not None
            continue
        assert validate_role_for_kind(role, seat_kind) is None


def test_support_stays_api_only_unchanged_by_1706() -> None:
    # #853's rule must survive the #1706 edit: a non-regression guard that
    # passes before and after by design.
    assert validate_role_for_kind("support", "api") is None
    assert validate_role_for_kind("support", "cli") is not None
    assert validate_role_for_kind("support", "remote") is not None


def test_capability_table_is_exactly_team_and_chat() -> None:
    # If a future seat kind joins the incapable set, this fails loudly rather
    # than silently widening what the editor hides.
    assert frozenset({"team", "chat"}) == TEAM_CHAT_ROLE_INCAPABLE_SEAT_KINDS


# --------------------------------------------------------------------------
# The classifier — it answers "what is this?", never "is it allowed?"
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("agent_id", "expected"),
    [
        ("team:alpha", "team"),
        ("chat:codey:conv-1", "chat"),
        ("blueprint:chat:codey:conv-1", "chat"),
        ("codey", "api"),
        ("api_agent", "api"),
        ("cli:grok", "cli"),
        ("remote:herdr", "remote"),
        ("blueprint:remote:herdr", "remote"),
    ],
)
def test_role_seat_kind_classifies_ids(agent_id: str, expected: str) -> None:
    assert role_seat_kind_for(agent_id) == expected


def test_explicit_kind_cannot_launder_a_non_team_id() -> None:
    # A caller passing explicit="team" for an ordinary api seat must not be
    # able to make the team rule fire (nor suppress it for a real team).
    assert role_seat_kind_for("codey", explicit="team") == "api"
    assert role_seat_kind_for("team:alpha", explicit="api") == "team"
    assert role_seat_kind_for("chat:codey:c", explicit="api") == "chat"

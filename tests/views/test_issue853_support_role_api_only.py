"""#853 — the ``support`` role is exclusive to API-kind seats.

Support capabilities depend on structured function-calling / tool-invocation
hooks that only API agents have, so assigning ``support`` to a CLI or remote
seat is a broken configuration. The agent-settings write path must
reject it with an explicit validation error.

``team`` is deliberately NOT asserted here for the *support* message. #1706
D.16 widened the rule: a team carries no role at all, so ``support`` on a team
is now rejected by the stronger team/chat rule (and with that message) before
the #853 rule is ever consulted. Both outcomes are refusals, so #853's actual
guarantee — "support is refused off API seats" — is unchanged; the reason
string just became the more specific one. The team/chat behaviour is pinned in
``tests/core/test_req1706_role_capability.py``.
"""

from __future__ import annotations

import pytest

from swarm.core.roles.registry import (
    TEAM_CHAT_ROLE_KIND_ERROR,
    validate_role_for_kind,
)


@pytest.mark.parametrize("kind", ["api", "blueprint"])
def test_support_allowed_for_api_family(kind):
    assert validate_role_for_kind("support", kind) is None


@pytest.mark.parametrize("kind", ["cli", "remote"])
def test_support_rejected_for_non_api_kinds(kind):
    error = validate_role_for_kind("support", kind)
    assert error is not None
    assert "Support role is exclusively available to API agents" in error


def test_support_rejected_for_a_team_with_the_wider_1706_reason():
    # Still a refusal (#853's guarantee holds), now for the stronger reason
    # #1706 D.16 introduced. Asserted explicitly so the change of message is
    # intentional and visible rather than an accident.
    assert validate_role_for_kind("support", "team") == TEAM_CHAT_ROLE_KIND_ERROR


@pytest.mark.parametrize("role", ["default", "skeptic", "gate", "advisor", "custom_thing"])
def test_other_roles_unrestricted(role):
    # #853 only ever restricted ``support``. ``team`` is excluded from this
    # loop because #1706 D.16 made it role-incapable outright — that is a
    # different, stronger rule with its own tests, not a #853 regression.
    for kind in ("api", "cli", "remote"):
        assert validate_role_for_kind(role, kind) is None

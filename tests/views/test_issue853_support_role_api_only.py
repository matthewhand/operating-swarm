"""#853 — the ``support`` role is exclusive to API-kind seats.

Support capabilities depend on structured function-calling / tool-invocation
hooks that only API agents have, so assigning ``support`` to a CLI, remote or
team seat is a broken configuration. The agent-settings write path must
reject it with an explicit validation error.
"""

from __future__ import annotations

import pytest

from swarm.core.roles.registry import validate_role_for_kind


@pytest.mark.parametrize("kind", ["api", "blueprint"])
def test_support_allowed_for_api_family(kind):
    assert validate_role_for_kind("support", kind) is None


@pytest.mark.parametrize("kind", ["cli", "remote", "team"])
def test_support_rejected_for_non_api_kinds(kind):
    error = validate_role_for_kind("support", kind)
    assert error is not None
    assert "Support role is exclusively available to API agents" in error


@pytest.mark.parametrize("role", ["default", "skeptic", "gate", "advisor", "custom_thing"])
def test_other_roles_unrestricted(role):
    for kind in ("api", "cli", "remote", "team"):
        assert validate_role_for_kind(role, kind) is None

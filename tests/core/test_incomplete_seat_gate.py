"""#1658 — one gate, two honest outcomes for a seat that cannot answer.

`blueprint_discovery` already documents `status` in blueprint metadata for
incomplete blueprints ("skip in list or warn in CLI/UI") but nothing consumed it,
while a separate change made the gate drop seats with no runnable recipe. Two
mechanisms were solving "don't pretend a broken seat works" in different files.

The unified contract:

  * no runnable recipe -> the seat is NOT advertised (it would 404 every turn)
  * recipe + `metadata["status"] == "incomplete"` -> advertised, flagged
    `incomplete: true`, so the operator sees why before clicking instead of
    discovering it from a refusal in the bubble
  * anything else -> advertised, unflagged

`cli` / `remote` seats are never flagged: they carry their own execution path and
have no blueprint recipe to read a status from.

The resolver is imported *inside* the helper, so these tests patch
`swarm.core.agent_kind.resolve_chat_blueprint_id` — patching the router module
would not take effect and the assertions would pass for the wrong reason.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.django_db

from swarm.blueprints.agent_router import blueprint_agent_router as router  # noqa: E402


class _Recipe:
    def __init__(self, status: str | None = None) -> None:
        self.metadata = {"status": status} if status else {}


def _resolve_to(value: str):
    """Patch the resolver the helper actually calls at runtime."""
    return patch("swarm.core.agent_kind.resolve_chat_blueprint_id", return_value=value)


def test_the_patch_really_takes_effect():
    """Guard: patching the router module would be a no-op and hide real bugs."""
    with _resolve_to("some_other_bp"):
        from swarm.core.agent_kind import resolve_chat_blueprint_id

        assert resolve_chat_blueprint_id("anything") == "some_other_bp"


def test_a_seat_with_no_recipe_is_not_incomplete():
    with _resolve_to("other_bp"):
        assert router._is_incomplete_seat("ghost", "specialist", {"other_bp": _Recipe()}) is False


def test_a_recipe_marked_incomplete_is_flagged():
    with _resolve_to("skeptic"):
        recipes = {"skeptic": _Recipe("incomplete")}
        assert router._is_incomplete_seat("skeptic", "specialist", recipes) is True


def test_status_matching_is_case_and_space_insensitive():
    with _resolve_to("gate"):
        recipes = {"gate": _Recipe("  InComplete ")}
        assert router._is_incomplete_seat("gate", "specialist", recipes) is True


def test_a_working_recipe_is_not_flagged():
    with _resolve_to("security_reviewer"):
        recipes = {"security_reviewer": _Recipe("stable")}
        assert router._is_incomplete_seat("security_reviewer", "specialist", recipes) is False


def test_a_recipe_with_no_status_is_not_flagged():
    with _resolve_to("database_reviewer"):
        recipes = {"database_reviewer": _Recipe(None)}
        assert router._is_incomplete_seat("database_reviewer", "specialist", recipes) is False


def test_cli_and_remote_seats_are_never_flagged():
    """They have their own execution path and no recipe to read a status from."""
    for kind in ("cli", "remote"):
        with _resolve_to("anything"):
            recipes = {"anything": _Recipe("incomplete")}
            assert router._is_incomplete_seat("anything", kind, recipes) is False


def test_an_unloadable_seat_is_not_also_claimed_as_a_flagged_placeholder():
    with _resolve_to("ghost"):
        assert router._is_incomplete_seat("ghost", "specialist", {}) is False


def test_a_recipe_whose_metadata_is_not_a_dict_is_not_flagged():
    with _resolve_to("weird"):
        recipes = {"weird": type("R", (), {"metadata": ["not", "a", "dict"]})()}
        assert router._is_incomplete_seat("weird", "specialist", recipes) is False

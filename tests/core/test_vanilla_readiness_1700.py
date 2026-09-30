"""#1700 — a seat that cannot run a turn is not a silent chat target.

``GET /v1/blueprints/`` publishes, per row, whether this host can actually run
it (``chat_ready``) plus the operator words for why and an in-product route that
repairs it (``unavailable_reason`` / ``manage_links``). These tests pin the
honesty rules, which matter more than the coverage:

* **Fail open.** Only a *positively proven* blocker flips a flag. An unreadable
  config must leave every row listed and ready — a gate that hides a working
  seat is the same defect as the one being fixed.
* **Never tell the user to do something already done.** A resolvable profile
  means no API tip; a configured CLI means no CLI tip. Both are asserted
  positively, because a tip that is always on is worse than no tip.
* **No probing.** This is a *list* endpoint. It must not make a network call
  or fork a process, so it is pinned with traps rather than a comment.
* **One answer.** ``host.inference_ready`` and
  ``support_context.inference_status()["configured"]`` must agree — they are two
  consumers of one fact, and a disagreement would put the tip and the badge in
  different states at the same time.
"""

from __future__ import annotations

import socket
import subprocess

import pytest

pytestmark = pytest.mark.django_db

from swarm.core import vanilla_seats  # noqa: E402


class _RemoteRecipe:
    kind = "remote"
    metadata: dict = {}


class _ApiRecipe:
    kind = "api"
    metadata: dict = {}


class _CliRecipe:
    kind = "cli"
    metadata: dict = {}


def _caps(**kw) -> vanilla_seats.HostCapabilities:
    base = {
        "configured_remote_ids": frozenset(),
        "on_path_clis": frozenset({"opencode"}),
        "inference_ready": True,
        "resolved_profiles": frozenset({"default"}),
        "unreadable": False,
    }
    base.update(kw)
    return vanilla_seats.HostCapabilities(**base)


# --- fail-open -------------------------------------------------------------


def test_an_unreadable_host_leaves_every_row_listed_and_ready():
    """#1700's own constraint: "If a tip can be wrong, it is worse than no tip."
    The gate could not read the host, so it must say nothing — not hide seats,
    and not accuse the operator of having no provider."""
    caps = _caps(inference_ready=True, unreadable=True)
    offer = vanilla_seats.seat_offer("support", metadata={}, caps=caps)
    assert offer.seat_listed is True
    assert offer.chat_ready is True
    assert offer.unavailable_reason == ""
    assert offer.manage_links == ()


def test_every_host_read_failure_degrades_to_silent(monkeypatch):
    """Each of the three host reads is guarded independently. Break all three
    at once and assert the gate is still silent — a partially-raised read must
    not leave a half-computed verdict looking authoritative."""
    for target, attr in (
        ("swarm.core.remotes", "configured_remote_ids"),
        ("swarm.core.cli_catalog", "discover_host_clis"),
        ("swarm.core.seat_doctor", "enumerate_seats"),
    ):
        module_path, name = target, attr

        def _raise(*_a, **_k):
            raise RuntimeError("host read exploded")

        monkeypatch.setattr(f"{module_path}.{name}", _raise)
        caps = vanilla_seats.host_capabilities({})
        assert caps.unreadable is True, module_path
        assert caps.notes, module_path
        assert caps.inference_ready is True, module_path
        offer = vanilla_seats.seat_offer("support", metadata={}, caps=caps)
        assert offer.chat_ready is True, module_path
        monkeypatch.undo()


# --- positive, actionable verdicts ----------------------------------------


def test_no_provider_means_not_ready_with_a_route_to_repair():
    caps = _caps(inference_ready=False, resolved_profiles=frozenset())
    offer = vanilla_seats.seat_offer("support", metadata={}, caps=caps, class_type=_ApiRecipe)
    assert offer.chat_ready is False
    assert offer.unavailable_reason
    assert [link["href"] for link in offer.manage_links] == [
        vanilla_seats.MANAGE_HREF_LLM_PROFILES
    ]


def test_a_manage_link_is_a_settings_deep_link_the_spa_owns():
    """A link is only actionable if the SPA can act on it. The SPA's parser
    (`lib/settingsLinks.ts`) accepts `/chat?settings=<section>` and resolves the
    section against `components/settings/kernel`'s `SettingsSection` union — so
    every href this module publishes must name a section in that vocabulary.

    The second half is the sharper claim and the reason #1725 exists: a declared
    constant with no emitter is a trap for the next reader. Both directions are
    asserted — every declared href is emitted by some real verdict, and no
    verdict ever emits an href nobody declared."""
    sections = {
        "general", "aesthetics", "providers", "definition", "blueprint", "remotes",
        "retention", "hostname", "about-me", "llm-profiles", "mcp", "cli-agents",
        "roles", "sandboxes", "backend-audit", "seat-doctor", "operator-activity",
        "rail", "image-gen", "speech", "system", "plugins", "experimental",
    }
    declared = {
        vanilla_seats.MANAGE_HREF_LLM_PROFILES,
        vanilla_seats.MANAGE_HREF_CLI_AGENTS,
        vanilla_seats.MANAGE_HREF_REMOTES,
    }
    for href in declared:
        assert href.startswith("/chat?settings=")
        assert href.split("settings=", 1)[1] in sections, href
    emitted = _every_link()
    # …every declared href is reachable from a real verdict, …
    assert declared <= {link["href"] for link in emitted}
    # …and no verdict invents a route the module does not declare.
    assert {link["href"] for link in emitted} <= declared
    # Every link carries a label too, so the UI never renders a bare URL as the
    # call to action.
    assert all(link["label"] for link in emitted)


def _every_link():
    """Every manage link the gate can emit, across all three verdicts."""
    out = []
    for caps in (
        _caps(inference_ready=False, resolved_profiles=frozenset()),
        _caps(inference_ready=True, configured_remote_ids=frozenset()),
        _caps(inference_ready=True, on_path_clis=frozenset()),
        _caps(inference_ready=True),
    ):
        for recipe, meta, ident in (
            (_ApiRecipe, {}, "support"),
            (_RemoteRecipe, {}, "remote_harness"),
            (_CliRecipe, {}, "cli_fusion"),
            (None, {"kind": "cli"}, "cli_fusion"),
        ):
            out.extend(
                vanilla_seats.seat_offer(
                    ident, metadata=meta, caps=caps, class_type=recipe
                ).manage_links
            )
    return out


def test_a_row_that_pins_its_own_model_is_ready_with_no_profile():
    """The gate must not be a blanket "no profiles → everything broken". A
    recipe that names its own model is as ready as that provider, and telling
    such an operator to go configure one would be the wrong advice."""
    caps = _caps(inference_ready=False, resolved_profiles=frozenset())
    offer = vanilla_seats.seat_offer(
        "my_recipe", metadata={"model": "gpt-4o-mini"}, caps=caps, class_type=_ApiRecipe
    )
    assert offer.chat_ready is True
    assert offer.unavailable_reason == ""


def test_a_composition_seat_on_a_host_with_no_cli_is_not_ready():
    caps = _caps(on_path_clis=frozenset())
    offer = vanilla_seats.seat_offer(
        "cli_fusion", metadata={}, caps=caps, class_type=_CliRecipe
    )
    assert offer.kind == "cli"
    assert offer.chat_ready is False
    assert [link["href"] for link in offer.manage_links] == [
        vanilla_seats.MANAGE_HREF_CLI_AGENTS
    ]


def test_a_configured_cli_leaves_a_composition_seat_ready():
    """The mirror of the previous test, and the one that keeps the gate from
    nagging a working install."""
    caps = _caps(on_path_clis=frozenset({"opencode"}))
    offer = vanilla_seats.seat_offer(
        "cli_fusion", metadata={}, caps=caps, class_type=_CliRecipe
    )
    assert offer.chat_ready is True
    assert offer.manage_links == ()


def test_a_configured_remote_makes_a_remote_recipe_ready():
    caps = _caps(configured_remote_ids=frozenset({"hermes"}))
    offer = vanilla_seats.seat_offer(
        "remote_harness", metadata={}, caps=caps, class_type=_RemoteRecipe
    )
    assert offer.seat_listed is True
    assert offer.chat_ready is True
    assert offer.manage_links == ()


# --- a list endpoint must not probe ---------------------------------------


def test_the_gate_never_touches_the_network_or_forks_a_process(monkeypatch):
    """`seat_health` and `seat_doctor` own the live verdict (liveness, a real
    turn). Calling them from a list endpoint would make every rail paint fork
    binaries and open sockets. The gate reads *static* facts; this pins that."""

    def _no_socket(*_a, **_k):
        raise AssertionError("the gate must not open a socket")

    def _no_process(*_a, **_k):
        raise AssertionError("the gate must not fork a process")

    monkeypatch.setattr(socket, "socket", _no_socket)
    monkeypatch.setattr(socket, "create_connection", _no_socket)
    monkeypatch.setattr(subprocess, "run", _no_process)
    monkeypatch.setattr(subprocess, "Popen", _no_process)
    # Both a real host read and a full verdict pass must survive the traps.
    # A silent `unreadable` result would hide a genuine probe call behind a
    # swallowed exception, so the note list is asserted empty.
    caps = vanilla_seats.host_capabilities({})
    assert caps.unreadable is False
    assert caps.notes == []
    offers = vanilla_seats.catalog_offers(
        [("remote_harness", None, _RemoteRecipe), ("support", None, _ApiRecipe)],
        caps=caps,
    )
    assert set(offers) == {"remote_harness", "support"}


# --- one answer, two consumers --------------------------------------------


def test_the_host_verdict_agrees_with_support_context():
    """`/v1/blueprints/`'s ``host.inference_ready`` and
    ``/v1/support/context/`'s ``inference.configured`` are two consumers of one
    fact. If they disagreed, the rail badge and the first-run tip would show
    opposite states on the same screen."""
    from swarm.core import support_context

    empty = {"llm": {}}
    caps = vanilla_seats.host_capabilities(empty)
    assert caps.inference_ready is False
    assert caps.inference_ready == support_context.inference_status(empty)["configured"]

    wired = {
        "llm": {
            "profiles": {
                "default": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "api_key_env": "OPENAI_API_KEY",
                    "base_url": "https://api.openai.com/v1",
                }
            }
        }
    }
    ready = vanilla_seats.host_capabilities(wired)
    assert ready.inference_ready is True
    assert ready.resolved_profiles
    assert ready.inference_ready == support_context.inference_status(wired)["configured"]


# --- the endpoint publishes what the gate decided -------------------------


def test_the_endpoint_publishes_the_host_facts_once():
    from django.test import Client

    payload = Client().get("/v1/blueprints/").json()
    host = payload["host"]
    assert set(host) == {
        "configured_remotes",
        "on_path_clis",
        "inference_ready",
        "resolved_profiles",
        "unreadable",
        "notes",
    }
    assert isinstance(host["configured_remotes"], list)
    assert isinstance(host["inference_ready"], bool)
    # Host facts, not a per-row verdict: this is the one place a client reads
    # to know *why* the rows read the way they do.
    assert "data" in payload


def test_a_not_ready_row_never_appears_as_ready_anywhere_in_the_payload():
    from django.test import Client

    payload = Client().get("/v1/blueprints/").json()
    for row in payload["data"]:
        if row["chat_ready"] is False:
            assert row["unavailable_reason"], row["id"]
            assert row["manage_links"], row["id"]
        else:
            assert row["unavailable_reason"] == "", row["id"]
            assert row["manage_links"] == [], row["id"]

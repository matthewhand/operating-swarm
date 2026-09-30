"""#1699 — a greenfield install must not ship Remote-kind agents as seats.

What the fix is
---------------
`GET /v1/blueprints/` is the only "what seats exist" endpoint the SPA reads
(the rail, the composer picker and `/v1/models`' model ids are all views onto
it). It used to be served straight out of the discovery cache, so a fresh
install advertised ``remote_harness`` and friends as agents the operator could
chat to — a seat that can only fail until a remote is added.

``swarm.core.vanilla_seats`` now answers two questions per row and the endpoint
publishes both (``seat_listed`` and ``chat_ready`` + reason + manage link).
These tests pin the admission half.

Why the gate is a capability check, not a name list
---------------------------------------------------
``test_withholds_a_remote_recipe_no_catalog_has_ever_heard_of`` invents a
blueprint id that does not exist in the tree and asserts it is still withheld,
while ``test_offers_an_api_recipe_no_catalog_has_ever_heard_of`` invents a
different one and asserts it is offered. A denylist of ids could pass the first
and fail the second; only a kind-resolution check passes both. That pair is the
real content of "not a name allowlist".

Why an existing install is unaffected
-------------------------------------
``test_the_gate_writes_nothing`` snapshots every byte under the config home and
the chat dir around a real endpoint call, and additionally makes every known
writer raise. The gate is a read: it changes what a consumer is *offered*, not
what any install *has*. ``test_a_user_created_remote_seat_is_never_withheld``
covers the other half — an operator's own remote-backed seat is never hidden,
because hiding it would lose their work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.django_db

from swarm.core import org_bot_library, vanilla_seats  # noqa: E402
from swarm.core.kind_bases import (  # noqa: E402
    KIND_API,
    KIND_CLI,
    KIND_REMOTE,
    KIND_TEAM,
)
from swarm.views import api_views, blueprint_library_views  # noqa: E402
from swarm.views import utils as views_utils  # noqa: E402

# --- helpers ---------------------------------------------------------------


def _caps(
    *,
    remotes: frozenset[str] = frozenset(),
    clis: frozenset[str] = frozenset({"opencode"}),
    profiles: frozenset[str] = frozenset({"default"}),
    unreadable: bool = False,
) -> vanilla_seats.HostCapabilities:
    return vanilla_seats.HostCapabilities(
        configured_remote_ids=remotes,
        on_path_clis=clis,
        inference_ready=bool(profiles) or unreadable,
        resolved_profiles=profiles,
        unreadable=unreadable,
    )


@pytest.fixture
def host(monkeypatch):
    """Pin the host facts; the gate's own logic still runs for real."""
    state = {"caps": _caps()}

    def _install(value: vanilla_seats.HostCapabilities) -> None:
        state["caps"] = value
        monkeypatch.setattr(
            vanilla_seats, "host_capabilities", lambda *_a, **_k: state["caps"]
        )

    _install(state["caps"])
    return _install


def _rows(client) -> list[dict]:
    response = client.get("/v1/blueprints/")
    assert response.status_code == 200, response.content
    return response.json()["data"]


def _by_id(client) -> dict[str, dict]:
    return {str(row["id"]): row for row in _rows(client)}


class _FakeRemoteRecipe:
    """Stands in for a ``RemoteKindBase`` subclass: the declared kind is the
    class's own ClassVar, which is the strongest evidence ``row_kind`` uses."""

    kind = KIND_REMOTE
    metadata: dict = {}


class _FakeApiRecipe:
    kind = KIND_API
    metadata: dict = {}


# --- #1699: the admission rule ---------------------------------------------


def test_greenfield_withholds_every_remote_kind_seat(host):
    """The headline: no Remote-kind row is offered as a seat on a fresh install."""
    from django.test import Client

    host(_caps(remotes=frozenset()))
    rows = _by_id(Client())
    offered_remote_seats = [
        row["id"]
        for row in rows.values()
        if row.get("seat_kind") == KIND_REMOTE and row.get("seat_listed") is not False
    ]
    assert offered_remote_seats == [], offered_remote_seats
    # …and the rule is not vacuous: the catalog really does serve Remote-kind
    # rows, it just refuses to call them seats.
    withheld = [row["id"] for row in rows.values() if row.get("seat_listed") is False]
    assert "remote_harness" in withheld
    assert "example_remote_minimal" in withheld


def test_greenfield_still_offers_cli_api_and_blueprint_seats(host):
    """#1699 success 2: CLI, API and custom blueprints (incl. teams) are the
    allowed onboard seeds — the gate must not take them with it."""
    from django.test import Client

    host(_caps(remotes=frozenset()))
    rows = _by_id(Client())
    offered = {
        row["id"] for row in rows.values() if row.get("seat_listed") is not False
    }
    assert "support" in offered  # api recipe
    assert "api_agent" in offered  # the rail API seat
    assert "cli_agent" in offered  # cli recipe
    assert "chatbot" in offered
    kinds = {row.get("seat_kind") for row in rows.values() if row["id"] in offered}
    assert KIND_REMOTE not in kinds


def test_a_configured_remote_puts_the_remote_recipe_back(host):
    """#1699 success 3: remotes appear once the operator adds one. The gate is
    a capability check, so it must be reversible — a hardcoded exclusion would
    need an un-gating code path nobody remembers."""
    from django.test import Client

    host(_caps(remotes=frozenset({"hermes"})))
    row = _by_id(Client())["remote_harness"]
    assert row["seat_listed"] is True
    assert row["chat_ready"] is True
    assert row["unavailable_reason"] == ""
    assert row["manage_links"] == []


def test_every_served_row_carries_the_gate_fields(host):
    """No row may escape unlabelled: a row with no verdict would let the picker
    guess, which is the #1725 shape (a field the reader has to interpret)."""
    from django.test import Client

    host(_caps())
    rows = _rows(Client())
    assert rows
    for row in rows:
        for field in (
            "seat_kind",
            "seat_source",
            "seat_listed",
            "chat_ready",
            "unavailable_reason",
            "manage_links",
        ):
            assert field in row, (row["id"], field)
        assert row["seat_source"] in {"discovery", "user"}
        assert isinstance(row["manage_links"], list)


def test_gate_never_clobbers_the_seats_own_kind_field(host):
    """``kind`` on a custom-library row is its *navbar provider* choice, owned by
    `rail_seats.custom_library_to_blueprint_rows`. The gate publishes under
    ``seat_kind`` precisely so it cannot retype the seat."""
    from django.test import Client

    host(_caps())
    row = _by_id(Client())["api_agent"]
    assert row["seat_kind"] == KIND_API
    # The raw row keeps whatever `kind` the seat itself declared (absent for a
    # plain discovery row, a provider name for a custom seat).
    assert row.get("kind") in (None, "", "api", "cli", "blueprint")


# --- "not a name allowlist": invented ids go both ways ----------------------


def test_withholds_a_remote_recipe_no_catalog_has_ever_heard_of():
    caps = _caps(remotes=frozenset())
    offer = vanilla_seats.seat_offer(
        "zzz_brand_new_remote_recipe",
        metadata={},
        caps=caps,
        class_type=_FakeRemoteRecipe,
    )
    assert offer.seat_listed is False
    assert offer.kind == KIND_REMOTE
    assert offer.chat_ready is False
    assert offer.manage_links and offer.manage_links[0]["href"]


def test_offers_an_api_recipe_no_catalog_has_ever_heard_of():
    caps = _caps(remotes=frozenset())
    offer = vanilla_seats.seat_offer(
        "zzz_brand_new_api_recipe",
        metadata={},
        caps=caps,
        class_type=_FakeApiRecipe,
    )
    assert offer.seat_listed is True
    assert offer.kind == KIND_API


def test_metadata_cannot_talk_a_remote_recipe_out_of_the_gate():
    """The strongest evidence is the recipe's own declared kind base. A
    ``kind: "api"`` field in metadata must not make a ``RemoteKindBase`` recipe
    a seed seat — that would be a one-line bypass of #1699."""
    caps = _caps(remotes=frozenset())
    offer = vanilla_seats.seat_offer(
        "remote_harness",
        metadata={"kind": "api"},
        caps=caps,
        class_type=_FakeRemoteRecipe,
    )
    assert offer.seat_listed is False
    assert offer.kind == KIND_REMOTE


def test_a_metadata_only_remote_claim_still_withholds():
    """…and with no class available, a row whose *only* remote evidence is its
    own metadata is still caught (id rule first, metadata as the last resort)."""
    caps = _caps(remotes=frozenset())
    offer = vanilla_seats.seat_offer(
        "some_recipe", metadata={"kind": KIND_REMOTE}, caps=caps
    )
    assert offer.seat_listed is False


# --- the kind vocabulary must stay a deliberate decision -------------------


def test_offer_kinds_is_every_kind_base_except_remote():
    """A new kind base has to make an explicit decision here, rather than being
    silently excluded (or silently seeded) by a forgotten list."""
    from swarm.core.agent_kind import _VALID_KINDS

    harness_kinds = {KIND_API, KIND_CLI, KIND_TEAM, KIND_REMOTE}
    # ``blueprint`` is the recipe identity from agent_kind's own AgentKind union.
    assert harness_kinds - {KIND_REMOTE} | {"blueprint"} == vanilla_seats.SEAT_OFFER_KINDS
    assert KIND_REMOTE not in vanilla_seats.SEAT_OFFER_KINDS
    # Every harness kind base is accounted for: the set is derived, not guessed.
    assert harness_kinds - set(vanilla_seats.SEAT_OFFER_KINDS) == {KIND_REMOTE}
    # And ``blueprint`` is a real agent kind, not an invention.
    assert "blueprint" in _VALID_KINDS


# --- new install vs existing install ---------------------------------------


def test_a_user_created_remote_seat_is_never_withheld(host, monkeypatch):
    """The operator's own remote-backed seat must survive the gate. This is the
    "do not break a working install" half of #1699: the row exists because they
    installed it, and a fresh-install admission rule has nothing to say about it.
    """
    from django.test import Client

    host(_caps(remotes=frozenset()))
    monkeypatch.setattr(
        api_views,
        "_custom_library_items",
        lambda: [
            {
                "id": "my-remote-seat",
                "name": "My remote seat",
                "kind": "remote",
                "rail": True,
                "source": "add-agent",
            }
        ],
    )
    row = _by_id(Client())["my-remote-seat"]
    assert row["seat_source"] == "user"
    assert row["seat_listed"] is True


def test_provenance_is_structural_not_a_name_list():
    """A row counts as the operator's only when it came from a store they write
    to. An id the gate has never heard of is treated as shipped, so inventing
    provenance cannot switch the gate off."""
    assert vanilla_seats.row_source("x", discovery_ids=["x"], user_ids=[]) == "discovery"
    assert vanilla_seats.row_source("x", discovery_ids=[], user_ids=["x"]) == "user"
    assert vanilla_seats.row_source("x", discovery_ids=[], user_ids=[]) == "discovery"


def test_the_gate_writes_nothing(host, monkeypatch):
    """A vanilla-admission change must not be able to touch an install's data.

    Proven two ways, because they fail differently: (a) every persistence entry
    point in the modules the gate reads *through* is made to raise, and (b) every
    byte under the config home and the chat dir is compared before/after a real
    endpoint call. (a) alone misses a writer added later; (b) alone misses a
    write to a path this test does not enumerate.
    """
    import os

    from django.test import Client

    def _boom(*_a, **_k):
        raise AssertionError("the vanilla gate must never write")

    # Writers in the stores the gate and the endpoint read through.
    monkeypatch.setattr(blueprint_library_views, "save_user_blueprint_library", _boom)
    monkeypatch.setattr(
        "swarm.core.org_bot_library._save_unlocked", _boom, raising=False
    )
    monkeypatch.setattr("swarm.views.utils.save_dynamic_registry", _boom)
    monkeypatch.setattr("swarm.core.remotes.add_remote", _boom)
    monkeypatch.setattr("swarm.core.remotes.remove_remote", _boom)

    xdg = Path(os.environ["XDG_CONFIG_HOME"])
    chat_dir = Path(os.environ["SWARM_CHAT_DIR"])

    def _snapshot() -> dict[str, bytes]:
        out: dict[str, bytes] = {}
        for root in (xdg, chat_dir):
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    out[str(path)] = path.read_bytes()
        return out

    host(_caps(remotes=frozenset()))

    # Prove the traps are armed: a patched name that the endpoint never calls
    # would make the byte comparison the only real evidence, and a typo'd name
    # would make it vacuous. Each trap must actually raise when invoked.
    for armed in (
        lambda: blueprint_library_views.save_user_blueprint_library({}),
        lambda: org_bot_library._save_unlocked({}),
        lambda: views_utils.save_dynamic_registry(),
    ):
        with pytest.raises(AssertionError, match="must never write"):
            armed()

    before = _snapshot()
    _rows(Client())
    assert _snapshot() == before

    # A second read is byte-identical too: no cache warms a file, no id is
    # stamped, no "first run" marker is written. (The gate has no memory, so a
    # second call cannot be excused as a warmed cache.)
    _rows(Client())
    assert _snapshot() == before

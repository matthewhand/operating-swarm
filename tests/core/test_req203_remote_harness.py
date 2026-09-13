"""REQ-203: each concrete remote satisfies RemoteHarness. No fifth kind."""

from __future__ import annotations

from typing import get_args

from swarm.core import remotes as remotes_core
from swarm.core.agent_kind import AgentKind, classify_agent_kind
from swarm.core.agent_types import AGENT_TYPES, agent_type_for_kind
from swarm.core.remote_harness import (
    COMPUTER_OPS,
    REMOTE_IMPL_IDS,
    USER_FACING_KIND,
    BoundRemoteHarness,
    RemoteCapabilities,
    RemoteHarness,
    all_harnesses,
    capabilities_for,
    computer_operate_stub,
    get_harness,
    implementation_catalog,
    is_remote_impl_id,
    normalize_impl_id,
    user_facing_kind,
)


def test_user_facing_kind_is_always_remote():
    assert USER_FACING_KIND == "remote"
    assert user_facing_kind("herdr") == "remote"
    assert user_facing_kind("hermes") == "remote"
    assert set(REMOTE_IMPL_IDS) == {"hermes", "omb", "rakazo", "herdr", "swarm"}


def test_registry_covers_every_catalog_impl():
    # remotes.py registers wrappers at import.
    assert remotes_core.REMOTE_KIND_IDS == REMOTE_IMPL_IDS
    harnesses = {row.impl_id: row for row in all_harnesses()}
    assert set(harnesses) == set(REMOTE_IMPL_IDS)
    for impl_id, harness in harnesses.items():
        assert isinstance(harness, RemoteHarness)
        assert isinstance(harness, BoundRemoteHarness)
        assert harness.impl_id == impl_id
        assert harness.label
        assert harness.label != "OMB"
        assert isinstance(harness.capabilities, RemoteCapabilities)
        assert callable(harness.health)
        assert callable(harness.list)
        assert callable(harness.send)
        assert callable(harness.operate)
        assert get_harness(impl_id) is harness


def test_capabilities_computer_only_on_omb_and_rakazo():
    assert capabilities_for("omb").operate is True
    assert capabilities_for("rakazo").operate is True
    assert capabilities_for("hermes").operate is False
    assert capabilities_for("herdr").operate is False
    assert capabilities_for("herdr").interrogate is True
    assert capabilities_for("herdr").transport == "cli"
    assert capabilities_for("hermes").transport == "http"


def test_implementation_catalog_kind_is_remote_impl_is_id():
    catalog = remotes_core.list_remote_kinds()
    ids = [row["id"] for row in catalog]
    assert ids == list(REMOTE_IMPL_IDS)
    for row in catalog:
        assert row["kind"] == "remote"
        assert row["impl"] == row["id"]
        assert row["label"]
        assert "OMB" not in row["label"]
        caps = row["capabilities"]
        assert caps["list"] is True
        assert caps["send"] is True
        assert caps["health"] is True
        if row["id"] in {"omb", "rakazo"}:
            assert caps["operate"] is True
        else:
            assert caps["operate"] is False


def test_public_dict_user_kind_is_remote():
    spec = remotes_core.default_spec("hermes")
    pub = spec.public_dict()
    assert pub["kind"] == "hermes"
    assert pub["impl"] == "hermes"
    assert pub["user_kind"] == "remote"
    assert pub["member"]["kind"] == "remote"


def test_computer_operate_stub_honest():
    omb = computer_operate_stub("omb", "computer-status")
    assert omb.ok is False
    assert omb.gap == "computer_operate_unwired"
    hermes = computer_operate_stub("hermes", "computer-status")
    assert hermes.ok is False
    assert hermes.gap == "computer_not_supported"
    listed = remotes_core.operate("omb", "computer-status", config={"llm": {}, "remotes": {}})
    assert listed.ok is False
    assert listed.op in COMPUTER_OPS or listed.op == "computer-status"


def test_herdr_is_remote_impl_not_fifth_kind():
    assert "herdr" not in AGENT_TYPES
    assert AGENT_TYPES == ("api", "cli", "remote")
    assert set(get_args(AgentKind)) == {"api", "cli", "remote"}
    assert agent_type_for_kind("herdr") == "remote"
    assert classify_agent_kind("herdr") == "remote"
    assert classify_agent_kind("w3:p1", explicit="herdr") == "remote"
    assert classify_agent_kind("herdr:w3:p1") == "remote"
    assert classify_agent_kind("hermes") == "remote"
    assert classify_agent_kind("omb") == "remote"
    assert classify_agent_kind("rakazo") == "remote"
    # Design-kind swarm stays API (not the nested remote impl).
    assert classify_agent_kind("swarm") == "api"
    assert agent_type_for_kind("swarm") == "api"
    assert is_remote_impl_id("herdr")
    assert is_remote_impl_id("open-swarm")
    assert not is_remote_impl_id("swarm")
    assert normalize_impl_id("openmousbot") == "omb"
    assert normalize_impl_id("open-swarm") == "swarm"


def test_wrappers_expose_contract_methods_without_lan():
    """Protocol methods exist. Computer operate is a stub — no LAN HTTP."""
    spec = remotes_core.default_spec("hermes")
    harness = get_harness("hermes")
    assert harness is not None
    computer = harness.operate(spec, "computer-status", timeout=0.2)
    assert computer.ok is False
    assert computer.gap == "computer_not_supported"
    empty = {"llm": {}, "remotes": {}}
    health = harness.health(spec, timeout=0.2, config=empty)
    assert health.ok is False
    assert "not added as a remote" in health.detail
    assert "swarm-cli remotes set hermes" in health.detail


def test_implementation_catalog_helper_matches_settings_kinds():
    from_helper = implementation_catalog()
    from_remotes = remotes_core.list_remote_kinds()
    assert [row["id"] for row in from_helper] == [row["id"] for row in from_remotes]
    assert all(row["kind"] == "remote" for row in from_helper)

"""#1374 Phase A — ``parallel_fan_out`` is a declared seat capability.

ADR-016: a control appears because the seat advertises the capability, never
because a string compared equal to ``'api'``. API and team seats fan out
sibling turns (ADR-017); CLI/remote stay process-at-a-time / provider-owned.
Unknown names stay not-offered (doctrine rule 4).
"""

from swarm.core.kind_bases import (
    ApiKindBase,
    CliKindBase,
    KindBase,
    RemoteKindBase,
    TeamKindBase,
    seat_capabilities,
    seat_capability,
)


class TestVocabulary:
    def test_parallel_fan_out_is_in_the_declared_vocabulary(self) -> None:
        from swarm.core.kind_bases import _capability_names

        assert "parallel_fan_out" in _capability_names()

    def test_unknown_capability_stays_not_offered(self) -> None:
        cap = seat_capability(ApiKindBase, "does_not_exist")
        assert cap["enabled"] is False
        assert cap["reason"]


class TestKindDefaults:
    def test_api_declares_parallel_fan_out_true(self) -> None:
        caps = seat_capabilities(ApiKindBase)
        assert caps["parallel_fan_out"]["enabled"] is True
        assert caps["parallel_fan_out"]["reason"] == ""

    def test_team_declares_parallel_fan_out_true(self) -> None:
        caps = seat_capabilities(TeamKindBase)
        assert caps["parallel_fan_out"]["enabled"] is True

    def test_cli_defaults_parallel_fan_out_false(self) -> None:
        caps = seat_capabilities(CliKindBase)
        assert caps["parallel_fan_out"]["enabled"] is False
        assert caps["parallel_fan_out"]["reason"]

    def test_remote_defaults_parallel_fan_out_false(self) -> None:
        caps = seat_capabilities(RemoteKindBase)
        assert caps["parallel_fan_out"]["enabled"] is False
        assert caps["parallel_fan_out"]["reason"]

    def test_kind_neutral_root_does_not_invent_fan_out(self) -> None:
        caps = seat_capabilities(KindBase)
        assert caps["parallel_fan_out"]["enabled"] is False


class TestSubclassOverride:
    def test_single_axis_override_enables_one_cli_only(self) -> None:
        class FanOutCli(CliKindBase):
            kind = "cli"
            blueprint_id = "fanouty"

            parallel_fan_out = {"enabled": True}

        caps = seat_capabilities(FanOutCli)
        assert caps["parallel_fan_out"]["enabled"] is True
        assert seat_capabilities(CliKindBase)["parallel_fan_out"]["enabled"] is False


class TestCatalogPublication:
    def test_payload_publishes_parallel_fan_out_per_kind(self) -> None:
        from swarm.core.cli_catalog import seat_capabilities_payload

        payload = seat_capabilities_payload()
        assert payload["api"]["parallel_fan_out"]["enabled"] is True
        assert payload["team"]["parallel_fan_out"]["enabled"] is True
        assert payload["cli"]["parallel_fan_out"]["enabled"] is False
        assert payload["remote"]["parallel_fan_out"]["enabled"] is False
        for kind, caps in payload.items():
            assert "parallel_fan_out" in caps, kind
            row = caps["parallel_fan_out"]
            assert set(row) == {"enabled", "reason"}
            assert isinstance(row["enabled"], bool)
            assert isinstance(row["reason"], str)

    def test_subclass_override_flows_through_the_payload(self) -> None:
        class FanOutCli(CliKindBase):
            kind = "cli"
            blueprint_id = "fanouty"

            parallel_fan_out = {"enabled": True}

        from swarm.core.cli_catalog import seat_capabilities_payload

        payload = seat_capabilities_payload(extra_bases=[FanOutCli])
        assert payload["cli"]["parallel_fan_out"] == {"enabled": True, "reason": ""}

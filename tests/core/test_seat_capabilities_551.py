"""#551 — seat capabilities are declared by the kind base, published as data.

The acceptance pilot: ``attach`` leaves the hand-written frontend gate and
becomes a declaration. ``ApiKindBase`` declares it (API + blueprint seats
accept attachments); CLI/remote do not — a CLI recipe that *does* accept
attachments overrides the single axis on its own subclass, with no frontend
change and no new conditional.
"""

from swarm.core.kind_bases import (
    ApiKindBase,
    CliKindBase,
    KindBase,
    RemoteKindBase,
    seat_capabilities,
    seat_capability,
)


class TestKindBaseDeclarations:
    def test_api_declares_attach_true(self) -> None:
        caps = seat_capabilities(ApiKindBase)
        assert caps["attach"]["enabled"] is True

    def test_cli_defaults_attach_false(self) -> None:
        caps = seat_capabilities(CliKindBase)
        assert caps["attach"]["enabled"] is False
        assert caps["attach"]["reason"], "a disabled capability must say why"

    def test_remote_defaults_attach_false(self) -> None:
        caps = seat_capabilities(RemoteKindBase)
        assert caps["attach"]["enabled"] is False

    def test_unknown_capability_returns_not_offered(self) -> None:
        # Doctrine rule 4: unknown capability = don't offer the action. The
        # singular accessor is how a surface probes a name it does not know.
        cap = seat_capability(CliKindBase, "does_not_exist")
        assert cap["enabled"] is False
        assert cap["reason"]


class TestSubclassOverride:
    def test_single_axis_override_changes_one_seat_only(self) -> None:
        class AttachyCli(CliKindBase):
            kind = "cli"
            blueprint_id = "attachy"

            attach = {"enabled": True}

        caps = seat_capabilities(AttachyCli)
        assert caps["attach"]["enabled"] is True
        # The base default is untouched for every other CLI.
        assert seat_capabilities(CliKindBase)["attach"]["enabled"] is False

    def test_kind_neutral_root_declares_nothing_kind_specific(self) -> None:
        # BlueprintBase must stay kind-neutral: the shared root does not guess.
        caps = seat_capabilities(KindBase)
        assert caps["attach"]["enabled"] is False


class TestCatalogPublication:
    def test_publish_payload_is_json_safe(self) -> None:
        from swarm.core.cli_catalog import seat_capabilities_payload

        payload = seat_capabilities_payload()
        assert set(payload) >= {"api", "cli", "remote"}
        for kind, caps in payload.items():
            assert set(caps) >= {"attach", "compact", "plugins"}
            for name, cap in caps.items():
                assert set(cap) == {"enabled", "reason"}
                assert isinstance(cap["enabled"], bool)
                assert isinstance(cap["reason"], str)

    def test_declared_capability_drives_the_decision(self) -> None:
        # The acceptance probe: a capability declared on the base is reflected
        # without frontend change — the payload is the only carrier.
        class AttachyCli(CliKindBase):
            kind = "cli"
            blueprint_id = "attachy"

            attach = {"enabled": True}

        from swarm.core.cli_catalog import seat_capabilities_payload

        payload = seat_capabilities_payload(extra_bases=[AttachyCli])
        assert payload["cli"]["attach"] == {"enabled": True, "reason": ""}

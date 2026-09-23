"""#641 — CLI slash commands are a declared ``CliKindBase`` capability.

ADR-005 / #551: each provider declares its own slash commands; the composer
popup derives its list from the published catalog, never a hardcoded JSX list.

Blocking investigation (recorded in #641): **omp print mode does not dispatch
slash commands.** oh-my-pi's own docs (``slash-command-internals.md`` §2) state
built-ins are dispatched only in *TUI and ACP/RPC modes*; ``cli-reference.md``
shows no ``--compress``/compaction launch flag; and the ``omp compress``
*subcommand* is an unrelated file-to-prompt-register tool. So omp declares
``/compress`` with ``available=False`` + reason: the popup greys it with that
reason and it is never sent as chat text.
"""

from __future__ import annotations

from typing import ClassVar

from swarm.core.cli_catalog import (
    CLI_SLASH_COMMANDS,
    cli_agents_catalog_payload,
    cli_slash_commands_payload,
)
from swarm.core.kind_bases import CliKindBase, CliSlashCommand


class _OmpLikeCli(CliKindBase):
    """A provider subclass declaring its own command, house-style."""

    cli_slash_commands: ClassVar = {
        "compress": CliSlashCommand(
            name="compress",
            description="Compact the CLI session's context",
        )
    }


class TestCliSlashCapability:
    def test_capability_defaults_to_empty(self) -> None:
        assert CliKindBase.cli_slash_commands == {}
        assert CliKindBase.supports_slash_command("compress") is False

    def test_supports_slash_command_answers_for_declared_available(self) -> None:
        assert _OmpLikeCli.supports_slash_command("compress") is True
        # Leading slash and case are normalised away.
        assert _OmpLikeCli.supports_slash_command("/Compress") is True

    def test_supports_slash_command_false_when_declared_unavailable(self) -> None:
        class _Broken(CliKindBase):
            cli_slash_commands: ClassVar = {
                "compress": CliSlashCommand(
                    name="compress",
                    description="…",
                    available=False,
                    unavailable_reason="nope",
                )
            }

        assert _Broken.supports_slash_command("compress") is False

    def test_slash_command_returns_the_declaration(self) -> None:
        cmd = _OmpLikeCli.slash_command("compress")
        assert cmd is not None
        assert cmd.description == "Compact the CLI session's context"
        assert _OmpLikeCli.slash_command("unknown") is None


class TestCatalogPublication:
    def test_omp_declares_compress_unavailable(self) -> None:
        (spec,) = CLI_SLASH_COMMANDS["omp"]
        assert spec.name == "compress"
        assert spec.available is False
        assert "print" in spec.unavailable_reason.lower()

    def test_catalog_does_not_declare_commands_for_other_clis(self) -> None:
        assert "grok" not in CLI_SLASH_COMMANDS
        assert "agy" not in CLI_SLASH_COMMANDS

    def test_payload_shape_is_json_safe(self) -> None:
        payload = cli_slash_commands_payload()
        assert payload["omp"] == [
            {
                "name": "compress",
                "description": spec_description(),
                "available": False,
                "unavailable_reason": spec_reason(),
            }
        ]

    def test_cli_agents_payload_publishes_slash_commands(self) -> None:
        body = cli_agents_catalog_payload(config={})
        assert body["slash_commands"] == cli_slash_commands_payload()


def spec_description() -> str:
    return CLI_SLASH_COMMANDS["omp"][0].description


def spec_reason() -> str:
    return CLI_SLASH_COMMANDS["omp"][0].unavailable_reason

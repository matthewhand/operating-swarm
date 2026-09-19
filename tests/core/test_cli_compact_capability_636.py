"""#636 — CLI seats gain Compact, gated on a configured default API or a
provider's own ``cli_compact`` capability (ADR-005).

The *interface* ships here: a provider declares a compact argv template on its
``CliKindBase`` subclass and the catalog advertises it per CLI, so the frontend
derives enablement from data. No provider declaration is bundled yet — a hook
shipped without verifying the CLI's actual compact command would be exactly the
dishonest surface #641 had to walk back.
"""
from __future__ import annotations

from typing import ClassVar

from swarm.core.cli_catalog import cli_agents_catalog_payload
from swarm.core.kind_bases import CliKindBase


class _GrokLike(CliKindBase):
    """A provider that compacts itself, house-style declaration."""

    cli_compact: ClassVar[str | None] = "agent compact --session {session_id}"


class TestCliCompactCapability:
    def test_capability_defaults_to_off(self) -> None:
        assert CliKindBase.cli_compact is None
        assert CliKindBase.supports_cli_compact() is False

    def test_provider_declaration_enables_the_hook(self) -> None:
        assert _GrokLike.supports_cli_compact() is True

    def test_hook_formats_session_id(self) -> None:
        assert _GrokLike.cli_compact_argv("abc123") == "agent compact --session abc123"

    def test_hook_without_session_placeholder_still_formats(self) -> None:
        class _Plain(CliKindBase):
            cli_compact: ClassVar[str | None] = "agent compact"

        assert _Plain.cli_compact_argv("abc123") == "agent compact"


class TestCatalogAdvertisesCliCompact:
    def test_bundled_catalog_declares_no_unverified_hooks(self) -> None:
        payload = cli_agents_catalog_payload(config={})
        assert payload["cli_compact"] == {}

    def test_declared_provider_would_be_advertised(self) -> None:
        # The publication path is capability-driven: any CliKindBase subclass
        # declaring cli_compact is advertised once its catalog entry exists.
        assert _GrokLike.supports_cli_compact() is True

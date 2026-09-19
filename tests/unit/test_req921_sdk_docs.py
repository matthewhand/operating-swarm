"""REQ-921 / #540 — the Blueprint SDK docs cannot silently rot.

The doc must mention every public hook the base classes actually expose.
When a hook is added to BlueprintBase / KindBase / ApiKindBase /
CliKindBase / RemoteKindBase, this test fails until docs/sdk/BLUEPRINT_SDK.md
documents it.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from swarm.core.blueprint_base import BlueprintBase
from swarm.core.kind_bases import ApiKindBase, CliKindBase, KindBase, RemoteKindBase

DOC = Path(__file__).resolve().parents[2] / "docs" / "sdk" / "BLUEPRINT_SDK.md"

# Hooks deliberately NOT documented: dunder plumbing, private helpers, and
# deprecated/legacy shims listed in the doc's exclusions table instead.
UNDOCUMENTED_PREFIXES = ("_",)
UNDOCUMENTED_NAMES = {
    # object plumbing
    "run_with_memory",  # wrapped variant created internally by memory mixin
}


def _public_hooks(cls: type) -> set[str]:
    """Callable attributes declared on the class itself (not inherited)."""
    hooks: set[str] = set()
    for name, member in vars(cls).items():
        if name.startswith(UNDOCUMENTED_PREFIXES) or name in UNDOCUMENTED_NAMES:
            continue
        if callable(member) or isinstance(member, (property, classmethod, staticmethod)):
            hooks.add(name)
    return hooks


def _doc_text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_sdk_doc_exists():
    assert DOC.is_file(), f"{DOC} missing — the SDK reference must ship"


def test_doc_mentions_every_declared_hook():
    """Every hook declared on the base classes appears in the doc text."""
    text = _doc_text()
    all_hooks: set[str] = set()
    for cls in (BlueprintBase, KindBase, ApiKindBase, CliKindBase, RemoteKindBase):
        all_hooks |= _public_hooks(cls)
    missing = sorted(name for name in all_hooks if name not in text)
    assert not missing, (
        f"hooks not documented in BLUEPRINT_SDK.md: {missing} — "
        "add them (or move them to the documented-legacy table)"
    )


def test_doc_states_enforcement_constants():
    """The enforced limits are stated with their real names and values."""
    text = _doc_text()
    from swarm.core.blueprint_source import ALLOWED_SOURCE_SUFFIXES, MAX_SOURCE_CHARS

    assert "MAX_SOURCE_CHARS" in text
    assert str(MAX_SOURCE_CHARS) in text.replace(",", "").replace("_", "")
    for suffix in (".py", ".md", ".json"):
        assert suffix in text, f"suite suffix {suffix} missing from the doc"
    assert "validate_writable_source" in text
    assert "assert_safe_blueprint_source" in text


def test_doc_covers_hierarchy_and_selection():
    text = _doc_text()
    for needle in (
        "ApiKindBase",
        "CliKindBase",
        "RemoteKindBase",
        "KindBase",
        "BlueprintBase",
        "base_class_for_kind",
        "ADR-005",
    ):
        assert needle in text, f"hierarchy/selection item {needle!r} missing"


def test_doc_states_provider_constraint_and_antipatterns():
    """The agy-class exclusion and the footgun list are present."""
    text = _doc_text()
    assert "Gemini-only" in text
    assert "orchestration" in text
    assert "Anti-patterns" in text
    assert "event loop" in text
    assert "final: True" in text


def test_doc_describes_rail_gate_and_lifecycle():
    text = _doc_text()
    assert "railSeats" in text or "isRailSeat" in text
    assert "discover_blueprints" in text
    assert "BLUEPRINT_EXTRA_DIRS" in text
    assert "create_starting_agent" in text

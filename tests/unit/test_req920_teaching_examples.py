"""REQ-920 / #539 — the teaching-example blueprint bundle.

The bundle contract, enforced:
    1. every `example_*` blueprint IMPORTS (loads with zero credentials);
    2. it instantiates and its `kind` matches its declared kind base;
    3. its docstring teaches: base named, hooks motivated, exclusions
       stated ("deliberately" / "NOT" markers present);
    4. metadata is catalog-complete but never `rail: True` (examples
       live in the catalog/library, not the rail);
    5. the sanitization gate covers the bundle (run alongside).
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

from swarm.core.kind_bases import (
    ApiKindBase,
    CliKindBase,
    RemoteKindBase,
    TeamKindBase,
    base_class_for_kind,
)

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "src" / "swarm" / "blueprints"

# example dir name → (expected kind base, kind string)
EXPECTED: dict[str, tuple[type, str]] = {
    "example_api_minimal": (ApiKindBase, "api"),
    "example_cli_minimal": (CliKindBase, "cli"),
    "example_remote_minimal": (RemoteKindBase, "remote"),
    "example_cli_provider_agy": (CliKindBase, "cli"),
    "example_cli_provider_omp": (CliKindBase, "cli"),
    # #813: the team orchestrator teaches the dedicated team kind now.
    "example_team_orchestrator": (TeamKindBase, "team"),
    "example_advisor_tool": (ApiKindBase, "api"),
}


def _example_dirs() -> list[str]:
    return sorted(d.name for d in EXAMPLES_DIR.iterdir() if d.name.startswith("example_"))


def _load_class(example_dir: str):
    module_name = f"swarm.blueprints.{example_dir}.blueprint_{example_dir}"
    module = importlib.import_module(module_name)
    classes = [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if obj.__module__ == module_name
    ]
    assert classes, f"{module_name} defines no blueprint class"
    return classes[0]


def test_bundle_is_complete():
    """The seven-axis bundle ships: one example per extension point."""
    dirs = _example_dirs()
    for required in EXPECTED:
        assert required in dirs, f"teaching example missing: {required}"


@pytest.mark.parametrize("example_dir", sorted(EXPECTED.keys()))
def test_example_loads_without_credentials(example_dir: str):
    """Zero-credential load contract: import + inspect must succeed."""
    cls = _load_class(example_dir)
    assert inspect.isclass(cls)


@pytest.mark.parametrize("example_dir", sorted(EXPECTED.keys()))
def test_example_declares_expected_kind_base(example_dir: str):
    """Right base, right kind — and `base_class_for_kind` agrees."""
    expected_base, expected_kind = EXPECTED[example_dir]
    cls = _load_class(example_dir)
    assert issubclass(cls, expected_base), f"{example_dir} must extend {expected_base.__name__}"
    assert cls.kind == expected_kind
    assert base_class_for_kind(expected_kind) == expected_base.__name__


@pytest.mark.parametrize("example_dir", sorted(EXPECTED.keys()))
def test_example_metadata_is_catalog_complete_and_never_rail(example_dir: str):
    """Catalog-complete metadata; `rail` never opts an example onto the rail."""
    cls = _load_class(example_dir)
    meta = getattr(cls, "metadata", {})
    for key in ("name", "title", "description", "version", "tags"):
        assert meta.get(key), f"{example_dir} metadata missing {key!r}"
    assert "example" in meta["tags"], f"{example_dir} must be tagged 'example'"
    assert meta.get("rail") is not True, f"{example_dir} must not sit on the rail"


@pytest.mark.parametrize("example_dir", sorted(EXPECTED.keys()))
def test_example_docstring_teaches(example_dir: str):
    """The docstring names the base, motivates hooks, states exclusions."""
    cls = _load_class(example_dir)
    doc = inspect.getdoc(cls) or ""
    module_doc = (inspect.getmodule(cls).__doc__ or "") if inspect.getmodule(cls) else ""
    teaching_text = f"{doc}\n{module_doc}"
    assert "Base:" in teaching_text, f"{example_dir} must name its base"
    assert "deliberately" in teaching_text, (
        f"{example_dir} must state what it deliberately does NOT do"
    )
    # A one-line subclass teaches nothing — require real commentary.
    assert len(teaching_text.split()) > 150, f"{example_dir} docstring is too thin to teach"


def test_examples_do_not_shard_the_rail_contract():
    """No example flips a capability axis without saying why."""
    for example_dir in EXPECTED:
        cls = _load_class(example_dir)
        for axis in ("attach", "compact", "plugins", "routines"):
            override = getattr(cls, axis, None)
            if isinstance(override, dict) and override.get("enabled") is True:
                assert override.get("reason"), (
                    f"{example_dir} enables '{axis}' without a reason string"
                )

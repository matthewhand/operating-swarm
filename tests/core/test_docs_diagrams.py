"""Diagram honesty tests.

The diagrams under ``docs/diagrams/`` document abstractions that the code
defines. These tests keep them honest by asserting that every class, module,
and hook named in a diagram actually exists in the tree, so a code change
that outdates a diagram fails here until the diagram is updated in the same
PR (the issue's regenerate-alongside-code constraint).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs" / "diagrams"
REPO_ROOT = DOCS.parent.parent


def _diagram_text(name: str) -> str:
    path = DOCS / name
    if not path.exists():  # pragma: no cover - guards wrong test run cwd
        pytest.skip(f"{path} not present")
    return path.read_text(encoding="utf-8")


def _module_exists(rel_path: str) -> bool:
    return (REPO_ROOT / rel_path).exists()


@pytest.mark.parametrize(
    ("diagram", "expected_names", "expected_modules"),
    [
        pytest.param(
            "roles.md",
            [
                "Role",
                "RoleContext",
                "RoleOutcome",
                "DefaultRole",
                "SupportRole",
                "GateRole",
                "SkepticRole",
                "AdvisorRole",
                "ChiefOfStaffRole",
                "EngineerRole",
                "SuggestionsRole",
            ],
            [
                "src/swarm/core/roles/__init__.py",
                "src/swarm/core/roles/base.py",
                "src/swarm/core/roles/registry.py",
                "src/swarm/core/roles/adapters.py",
                "src/swarm/core/agent_roles.py",
                "src/swarm/views/roles_api.py",
            ],
            id="roles-diagram-names-real-classes-and-modules",
        ),
    ],
)
def test_diagram_names_real_classes_and_modules(
    diagram: str, expected_names: list[str], expected_modules: list[str]
) -> None:
    text = _diagram_text(diagram)
    for name in expected_names:
        assert re.search(rf"\b{re.escape(name)}\b", text), (
            f"{diagram} no longer names {name}; update docs/diagrams/{diagram} "
            "alongside the code change (diagram honesty constraint)."
        )
    for rel in expected_modules:
        assert _module_exists(rel), f"{diagram} references missing module {rel}"


def test_roles_diagram_override_matrix_matches_adapters() -> None:
    """Every hook the diagram's override matrix claims must exist in the source."""
    text = _diagram_text("roles.md")
    for hook in ("on_turn_start", "wrap_tool_calls", "on_turn_end", "as_tool"):
        assert hook in text, f"override matrix lost hook {hook}"
    adapters = _module_text("src/swarm/core/roles/adapters.py")
    for role in ("GateRole", "SkepticRole", "AdvisorRole", "SuggestionsRole"):
        assert f"class {role}" in adapters, f"{role} missing from adapters.py"
    base = _module_text("src/swarm/core/roles/base.py")
    for hook in ("on_turn_start", "wrap_tool_calls", "on_turn_end", "as_tool"):
        assert f"def {hook}" in base, f"Role base lost default hook {hook}"


def _module_text(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")

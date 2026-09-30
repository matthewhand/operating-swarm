"""The confidence ranker must be REACHABLE, not just well tested (#1454).

`routine_tool_suggestions.py` shipped with 50 tests and **no importer anywhere
in `src/`** — so every one of those tests passed while the product could never
call the code. That is the same defect filed as #1669 for the #1410 twin, and
this file is the guard against recreating it.

These tests deliberately go through the HTTP endpoint rather than calling the
function, because "the function is correct" and "the product can reach the
function" are different claims and only the second one matters here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

REPO_ROOT = Path(__file__).resolve().parents[2]
RANKER = REPO_ROOT / "src/swarm/core/routine_tool_suggestions.py"


def _client() -> APIClient:
    client = APIClient()
    client.force_authenticate(user=None)
    return client


def test_the_tool_catalog_route_resolves():
    assert reverse("routines-tool-catalog").endswith("/v1/routines/tool-catalog/")


# --- reachability: the guard against another dead module -------------------


def test_the_ranker_has_a_production_importer():
    """A module with no importer in src/ is dead code wearing a green test suite."""
    callers: list[str] = []
    for path in (REPO_ROOT / "src/swarm").rglob("*.py"):
        if path == RANKER:
            continue
        if "routine_tool_suggestions" in path.read_text():
            callers.append(str(path.relative_to(REPO_ROOT)))
    assert callers, (
        "routine_tool_suggestions.py has no importer in src/ — its tests cannot "
        "fail for a product reason. Wire it or delete it (see #1669)."
    )


def test_the_importer_is_a_view_not_just_a_test():
    """An importer could be a lazy shim; this one must be a real request path."""
    url_text = (REPO_ROOT / "src/swarm/urls.py").read_text()
    routines = REPO_ROOT / "src/swarm/views/routines_api.py"
    assert "RoutineToolCatalogAPIView" in url_text
    assert "rank_tools_by_confidence" in routines.read_text()


# --- behaviour through the endpoint ---------------------------------------


def test_without_an_instruction_the_catalog_is_unranked_and_unchanged():
    body = _client().get("/v1/routines/tool-catalog/").json()
    assert body["object"] == "routine_tool_catalog"
    assert body["ranked"] is False
    # Nothing ranker-specific may leak into the unranked shape.
    assert not any("confidence" in item for item in body["items"])


def test_an_instruction_ranks_the_catalog():
    body = _client().get(
        "/v1/routines/tool-catalog/",
        {"instruction": "open a pull request when the tests pass"},
    ).json()
    assert body["ranked"] is True
    rows = body["items"]
    assert rows, "the catalog is never empty in a configured host"
    for row in rows:
        assert {"id", "confidence", "named", "pinned", "scorer"} <= set(row)
    scores = [row["confidence"] for row in rows]
    assert scores == sorted(scores, reverse=True), "rows must come back ordered"
    assert body["named_count"] == sum(1 for row in rows if row["named"])


def test_the_ranker_labels_its_own_scorer_so_a_client_need_not_guess():
    body = _client().get("/v1/routines/tool-catalog/", {"instruction": "read a file"}).json()
    assert {row["scorer"] for row in body["items"]} <= {"lexical"}


def test_a_named_tool_is_never_dropped_by_top_n():
    instruction = "when the build breaks open a pull request with the log"
    ranked = _client().get(
        "/v1/routines/tool-catalog/", {"instruction": instruction, "top_n": "1"}
    ).json()
    names = {row["id"] for row in ranked["items"] if row["named"]}
    assert names <= {row["id"] for row in ranked["items"]}
    # top_n is a floor, not a hard cap, and the response says so.
    assert ranked["named_count"] >= len(names)


def test_top_n_must_be_a_positive_integer():
    for raw in ("0", "-3", "lots"):
        response = _client().get(
            "/v1/routines/tool-catalog/", {"instruction": "do a thing", "top_n": raw}
        )
        assert response.status_code == 400, raw
        assert "top_n" in response.json()["error"]


def test_a_blank_instruction_is_not_treated_as_a_ranking_request():
    body = _client().get("/v1/routines/tool-catalog/", {"instruction": "   "}).json()
    assert body["ranked"] is False


def test_ranking_never_raises_on_a_weird_instruction():
    """A picker that 500s on odd input is worse than an unranked one."""
    # Whitespace-only is excluded on purpose: it strips to empty, which is the
    # "not a ranking request" case covered by its own test below.
    for instruction in ("?", "🙂" * 50, "a" * 5000, "'; DROP TABLE routines; --", "\t\t"):
        if not instruction.strip():
            continue
        response = _client().get("/v1/routines/tool-catalog/", {"instruction": instruction})
        assert response.status_code == 200, instruction[:32]
        assert response.json()["ranked"] is True, instruction[:32]


def test_the_endpoint_never_returns_a_secret_shaped_field():
    """The ranker must not widen what the public catalog exposes."""
    body = _client().get("/v1/routines/tool-catalog/", {"instruction": "use the api key"}).json()
    banned = {"api_key", "token", "secret", "password", "env_value"}
    for row in body["items"]:
        assert not (banned & {key.lower() for key in row}), row.get("id")


def test_the_ranker_module_has_no_unexpected_imports():
    """A ranking helper must stay dependency-free; it runs on every picker open.

    Intra-repo `swarm.*` imports are fine — the point is that no THIRD-PARTY
    package is pulled in, since the browser/WebGPU scorer plugs into this seam.
    """
    tree = ast.parse(RANKER.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    third_party = {
        name
        for name in imported
        if name not in _STDLIB_ALLOWED and not name.startswith("swarm")
    }
    assert not third_party, f"unexpected dependency: {sorted(third_party)}"


_STDLIB_ALLOWED = {
    "__future__",
    "collections",
    "dataclasses",
    "difflib",
    "functools",
    "hashlib",
    "logging",
    "re",
    "typing",
    "unicodedata",
}

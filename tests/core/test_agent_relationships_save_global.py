"""Regression: `save_relationships` needs `global _store`.

Found by `ruff check --select F823 src/` ("local variable referenced before
assignment") — the same static class as the 2026-09-28 boot failure, which
cost every server process its ability to start.

`save_relationships` assigned to `_store` without declaring it `global`, which
made `_store` a *local* for the whole function body. Two consequences, both
silent:

1. `save_relationships()` with no argument read that unbound local and raised
   ``UnboundLocalError`` — always, on every call.
2. `save_relationships(edges)` did not raise, but the assignment landed in a
   discarded local, so the module cache was never updated and every later
   `load_relationships()` silently re-read the file instead of the cache.

`save_relationships` is a public export (``__all__``) with no in-tree caller,
which is exactly why this survived: no test reached it.
"""

from __future__ import annotations

import json

import pytest

from swarm.core import agent_relationships as rel


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point the store at a tmp file and clear the module cache."""
    path = tmp_path / "agent_relationships.json"
    monkeypatch.setattr(rel, "relationships_path", lambda: path)
    rel.reset_relationships(None)
    yield path
    rel.reset_relationships(None)


_EDGE = {"from_kind": "team", "from_id": "ops", "to_kind": "agent", "to_id": "pat"}
# `normalize_edge` canonicalises an undirected edge by ordering the endpoints,
# so a team↔agent edge is always stored agent-first. Assert the canonical form
# rather than the input order.
_CANONICAL_EDGE = {"from_kind": "agent", "from_id": "pat", "to_kind": "team", "to_id": "ops"}


def test_save_with_no_argument_does_not_raise(tmp_path):
    """The crash. `UnboundLocalError` is a `NameError` subclass.

    On a warm cache this reads the local (now bound by the assignment below)
    and is less dramatic; the unfailable case is a cold cache, so reset first
    and assert on both orders.
    """
    rel.reset_relationships([_EDGE])  # warm the cache
    rel.save_relationships()  # must not raise

    rel.reset_relationships(None)  # cold: `_store` is None
    rel.save_relationships()  # must still not raise
    assert (tmp_path / "agent_relationships.json").exists()


def test_save_populates_the_module_cache(tmp_path):
    """The silent half: the write must land in the *module* `_store`.

    Without `global`, `_store = [...]` on the last line of the function bound a
    local and the cache stayed `None`, so the next `load_relationships()`
    would go back to disk. Deleting the file proves which one answered.
    """
    rel.save_relationships([_EDGE])

    # The cache is populated, not left cold.
    assert rel._store is not None, "save_relationships did not populate the module cache"
    assert rel._store == [_CANONICAL_EDGE]

    # Now make the file unreadable-by-deletion: a cache hit must still answer.
    (tmp_path / "agent_relationships.json").unlink()
    loaded = rel.load_relationships()
    assert len(loaded) == 1, "load_relationships went back to disk; the cache was never written"
    assert (loaded[0].from_kind, loaded[0].from_id) == ("agent", "pat")


def test_save_round_trips_through_disk(tmp_path):
    """And the file is still correct — the `global` must not skip the write."""
    rel.save_relationships([_EDGE])
    on_disk = json.loads((tmp_path / "agent_relationships.json").read_text(encoding="utf-8"))
    assert on_disk == {"schema": 1, "edges": [_CANONICAL_EDGE]}

    rel.reset_relationships(None)
    reloaded = rel.load_relationships()
    assert [(e.from_id, e.to_id) for e in reloaded] == [("pat", "ops")]


def test_save_refuses_a_non_relationship_path(tmp_path, monkeypatch):
    """The guard the function opens with must survive the `global` edit."""
    monkeypatch.setattr(rel, "relationships_path", lambda: tmp_path / "teams.json")
    with pytest.raises(RuntimeError, match="Refusing to persist"):
        rel.save_relationships([_EDGE])

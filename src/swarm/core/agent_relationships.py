"""Team/agent relationship edges for peer-mailbox discoverability (REQ-153).

An explicit **undirected** graph of who can list/message whom, stored beside
``team_rosters.json`` as ``agent_relationships.json``. This is **not** a
global mesh and **not** openai-agents handoff edges.

Allowed endpoint kinds:

* ``team`` — a composition roster id
* ``agent`` — a rail / roster member id

Allowed pairs (v1): team↔agent, team↔team. Agent↔agent can be added later
without changing the file shape.

Members become **mutually discoverable** across an edge (then same-kind and
ACL still apply). See ``docs/adr/009-peer-mailbox.md``.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm

logger = logging.getLogger(__name__)

ENDPOINT_KINDS = ("team", "agent")
EndpointKind = Literal["team", "agent"]

_store: list[dict[str, str]] | None = None
_lock = threading.RLock()


@dataclass(frozen=True)
class RelationshipEdge:
    """One undirected discoverability edge."""

    from_kind: EndpointKind
    from_id: str
    to_kind: EndpointKind
    to_id: str

    def ends(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return ((self.from_kind, self.from_id), (self.to_kind, self.to_id))

    def as_dict(self) -> dict[str, str]:
        return {
            "from_kind": self.from_kind,
            "from_id": self.from_id,
            "to_kind": self.to_kind,
            "to_id": self.to_id,
        }


def relationships_path() -> Path:
    """XDG path for the relationship store. Never ``teams.json``."""
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "agent_relationships.json"


def _normalize_kind(raw: Any) -> EndpointKind:
    kind = str(raw or "").strip().lower()
    if kind not in ENDPOINT_KINDS:
        raise ValueError(f"Relationship endpoint kind must be one of {', '.join(ENDPOINT_KINDS)}.")
    return kind  # type: ignore[return-value]


def _normalize_id(raw: Any, *, label: str) -> str:
    ident = str(raw or "").strip()
    if not ident:
        raise ValueError(f"Relationship {label} is required.")
    if len(ident) > 64:
        raise ValueError(f"Relationship {label} too long (max 64).")
    return ident


def _pair_allowed(from_kind: str, to_kind: str) -> bool:
    kinds = {from_kind, to_kind}
    if kinds == {"agent"}:
        # Reserved; v1 documents team↔* only so we do not silently mesh agents.
        return False
    return True


def normalize_edge(raw: Any) -> RelationshipEdge:
    """Validate one edge. Raises ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("Each relationship must be an object.")
    from_kind = _normalize_kind(raw.get("from_kind") or raw.get("fromKind"))
    to_kind = _normalize_kind(raw.get("to_kind") or raw.get("toKind"))
    from_id = _normalize_id(raw.get("from_id") or raw.get("fromId") or raw.get("from"), label="from_id")
    to_id = _normalize_id(raw.get("to_id") or raw.get("toId") or raw.get("to"), label="to_id")
    if from_kind == to_kind and from_id == to_id:
        raise ValueError("A relationship cannot connect an endpoint to itself.")
    if not _pair_allowed(from_kind, to_kind):
        raise ValueError("v1 relationships are team↔agent or team↔team (not agent↔agent).")
    # Canonical order so duplicates collapse (team before agent, then id).
    left = (from_kind, from_id)
    right = (to_kind, to_id)
    if left > right:
        from_kind, from_id, to_kind, to_id = to_kind, to_id, from_kind, from_id
    return RelationshipEdge(
        from_kind=from_kind,
        from_id=from_id,
        to_kind=to_kind,
        to_id=to_id,
    )


def normalize_edges(raw: Any) -> list[RelationshipEdge]:
    if raw is None:
        return []
    if isinstance(raw, dict) and "edges" in raw:
        raw = raw.get("edges")
    if not isinstance(raw, list):
        raise ValueError("relationships must be an array of edges.")
    seen: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    out: list[RelationshipEdge] = []
    for item in raw:
        edge = normalize_edge(item)
        key = edge.ends()
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


def _document(edges: Iterable[RelationshipEdge]) -> dict[str, Any]:
    return {"schema": 1, "edges": [edge.as_dict() for edge in edges]}


def load_relationships() -> list[RelationshipEdge]:
    """Load edges from the in-memory cache / XDG file."""
    global _store
    with _lock:
        if _store is not None:
            return [normalize_edge(item) for item in _store]
        try:
            path = relationships_path()
            if not path.exists():
                _store = []
                return []
            parsed = json.loads(path.read_text(encoding="utf-8") or "{}")
            edges = normalize_edges(parsed)
            _store = [edge.as_dict() for edge in edges]
            return edges
        except Exception:
            logger.exception("Failed to load agent_relationships.json; using empty graph.")
            _store = []
            return []


def save_relationships(edges: Iterable[RelationshipEdge] | None = None) -> None:
    """Persist the in-memory graph. Never writes ``teams.json``."""
    path = relationships_path()
    if path.name != "agent_relationships.json":
        raise RuntimeError("Refusing to persist relationships to a non-relationship path.")
    # `global` is load-bearing, not decoration. Without it the `_store = ...`
    # below makes `_store` a *local* for the whole function, so the read on the
    # `edges is None` branch raised UnboundLocalError (a NameError subclass —
    # `save_relationships()` with no argument always crashed) and the write
    # landed in a discarded local, leaving the module cache stale. ruff F823
    # ("local variable referenced before assignment") is the check that found it.
    global _store
    with _lock:
        current = list(edges) if edges is not None else [normalize_edge(item) for item in (_store or [])]
        normalized = normalize_edges([edge.as_dict() if isinstance(edge, RelationshipEdge) else edge for edge in current])
        _store = [edge.as_dict() for edge in normalized]
        path.write_text(json.dumps(_document(normalized), indent=2), encoding="utf-8")


def reset_relationships(initial: Any = None) -> None:
    """Replace the in-memory cache (tests). Does not write disk unless save is called."""
    global _store
    with _lock:
        if initial is None:
            _store = None
            return
        _store = [edge.as_dict() for edge in normalize_edges(initial)]


def iter_edges(edges: Any | None = None) -> list[RelationshipEdge]:
    """Normalize an explicit list or load the store."""
    if edges is None:
        return load_relationships()
    return normalize_edges(edges)


__all__ = [
    "ENDPOINT_KINDS",
    "RelationshipEdge",
    "iter_edges",
    "load_relationships",
    "normalize_edge",
    "normalize_edges",
    "relationships_path",
    "reset_relationships",
    "save_relationships",
]

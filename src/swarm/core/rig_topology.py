"""Rig topology (Issue #1222).

A read-only projection of a **team roster** (``team_rosters.json``) into the
OpenRig node/edge vocabulary. There is no parallel model: nodes come from the
roster's ``members`` and wires come from its Tools slots (``handoff`` /
``as_tool``), falling back to the legacy ``wires`` booleans only when the
roster declares no tools.

OpenRig mapping::

    handoff  -> delegates_to
    as_tool  -> collaborates_with

No edge is invented for a relationship the roster does not declare.
"""

from __future__ import annotations

from typing import Any

OBJECT = "rig_topology"
EDGE_DELEGATES_TO = "delegates_to"
EDGE_COLLABORATES_WITH = "collaborates_with"


def _member_id(value: Any) -> str:
    return str(value or "").strip()


def build_rig_topology(roster: dict[str, Any]) -> dict[str, Any]:
    """Derive the topology payload for one normalized-or-raw roster dict."""
    if not isinstance(roster, dict):
        raise ValueError("roster must be an object.")

    member_rows = roster.get("members") or roster.get("agent_team") or []
    if not isinstance(member_rows, list):
        member_rows = []

    ordered: list[tuple[str, dict[str, Any]]] = []
    node_ids: set[str] = set()
    for raw in member_rows:
        if not isinstance(raw, dict):
            continue
        mid = _member_id(raw.get("id"))
        if not mid or mid in node_ids:
            continue
        node_ids.add(mid)
        ordered.append((mid, raw))

    rid = _member_id(roster.get("id"))
    name = _member_id(roster.get("name")) or rid
    requested_lead = _member_id(roster.get("chief_of_staff_id"))
    lead_id = requested_lead if requested_lead in node_ids else (ordered[0][0] if ordered else None)

    nodes = [
        {
            "id": mid,
            "name": _member_id(raw.get("name")) or mid,
            "kind": _member_id(raw.get("kind")) or "api",
            "role": _member_id(raw.get("role")) or "default",
            "pod": _member_id(raw.get("kind")) == "team",
            "lead": mid == lead_id,
        }
        for mid, raw in ordered
    ]

    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(from_id: str, to_id: str, kind: str, channel: str) -> None:
        if not from_id or not to_id or from_id == to_id:
            return
        if from_id not in node_ids or to_id not in node_ids:
            return
        key = (from_id, to_id, kind)
        if key in seen:
            return
        seen.add(key)
        edges.append({"from": from_id, "to": to_id, "kind": kind, "channel": channel})

    tools = roster.get("tools") or []
    if not isinstance(tools, list):
        tools = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_type = _member_id(tool.get("type"))
        if tool_type == "handoff":
            add(
                _member_id(tool.get("from")) or (lead_id or ""),
                _member_id(tool.get("to")),
                EDGE_DELEGATES_TO,
                "handoff",
            )
        elif tool_type == "as_tool":
            add(lead_id or "", _member_id(tool.get("agent")), EDGE_COLLABORATES_WITH, "as_tool")

    # Legacy rosters predate Tools slots and only carry wires booleans. Consult
    # them only when no tools are declared so the two never double-count.
    if not tools:
        wires = roster.get("wires")
        if isinstance(wires, dict) and lead_id:
            for mid in ordered[1:]:
                if wires.get("handoff"):
                    add(lead_id, mid[0], EDGE_DELEGATES_TO, "handoff")
                if wires.get("as_tool"):
                    add(lead_id, mid[0], EDGE_COLLABORATES_WITH, "as_tool")

    return {
        "object": OBJECT,
        "id": rid,
        "name": name,
        "lead_id": lead_id,
        "nodes": nodes,
        "edges": edges,
    }

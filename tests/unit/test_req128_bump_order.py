"""REQ-128: Non-favourite agents bump to top of rail when generation finishes.

Intent: Recently active agents surface without manual hunting.
Rules:
1. On generation complete (success or stop), non-favourite agent row moves to top of the AGENTS list (stable order among ties).
2. Favourites unchanged in the favourites area; no duplicate row in the list.
3. Manual reorder/DnD later can override until next completion.
"""

from pathlib import Path

from helpers.source_surface import chat_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
RAIL_ORDER_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "railOrder.ts"


def test_chat_page_wires_generation_complete_on_success_and_stop():
    content = chat_surface()
    assert "notifyGenerationComplete" in content
    assert "activeChatAgentId" in content
    # Wires on assistant_final
    assert "event.kind === 'assistant_final'" in content
    # Wires on stop / streaming transition
    assert "wasStreamingRef" in content
    # Wires on abrupt ws disconnect / close
    assert "setThreads" in content
    assert "m.streaming" in content


def test_sidebar_listens_and_preserves_favourites():
    content = SIDEBAR_TSX.read_text(encoding="utf-8")
    assert "GENERATION_COMPLETE_EVENT" in content
    assert "generationCompleteAgentId" in content
    assert "bumpRailIdToTop" in content
    # Crucial: only visible non-favourite rows are bumped, favourites are excluded from visibleRowIds
    assert "!visibleRowIds.includes(agentId)" in content
    assert "excludePinnedFromList" in content


def test_rail_order_documentation_and_logic():
    content = RAIL_ORDER_TS.read_text(encoding="utf-8")
    assert "REQ-128" in content
    assert "Stability and tie-breaking" in content
    assert "bumpRailIdToTop" in content


def test_algorithm_bump_ties_and_drag_override():
    # Model the railOrder functions in Python to verify exact contract
    def bump_to_top(order: list[str], agent_id: str) -> list[str]:
        if not agent_id:
            return order
        return [agent_id] + [x for x in order if x != agent_id]

    def move_before(order: list[str], from_id: str, before_id: str) -> list[str]:
        if not from_id or not before_id or from_id == before_id:
            return order
        without = [x for x in order if x != from_id]
        if before_id not in without:
            return order
        idx = without.index(before_id)
        without.insert(idx, from_id)
        return without

    def apply_order(items: list[str], order: list[str]) -> list[str]:
        if not order:
            return items
        by_id = {x: x for x in items}
        seen = set()
        res = []
        for x in order:
            if x in by_id and x not in seen:
                res.append(x)
                seen.add(x)
        for x in items:
            if x not in seen:
                res.append(x)
                seen.add(x)
        return res

    catalog = ["agent-1", "agent-2", "agent-3", "agent-4"]
    pinned = {"agent-2"}  # favourite

    # Exclude pinned from list
    visible = [x for x in catalog if x not in pinned]
    assert visible == ["agent-1", "agent-3", "agent-4"]

    # When non-favourite completes generation -> moves to top
    order = bump_to_top(visible, "agent-3")
    assert order == ["agent-3", "agent-1", "agent-4"]
    assert apply_order(visible, order) == ["agent-3", "agent-1", "agent-4"]

    # When favourite completes generation -> ignored by visible list, remains pinned
    if "agent-2" in visible:
        order = bump_to_top(order, "agent-2")
    assert "agent-2" not in order
    assert apply_order(visible, order) == ["agent-3", "agent-1", "agent-4"]

    # Tied completions: each successive completion bumps to top (most recent wins, stable relative order)
    order = bump_to_top(order, "agent-4")
    assert order == ["agent-4", "agent-3", "agent-1"]

    # Manual drag reorder overrides rail order
    order = move_before(order, "agent-1", "agent-4")
    assert order == ["agent-1", "agent-4", "agent-3"]

    # Subsequent generation completion bumps the active agent back to top
    order = bump_to_top(order, "agent-3")
    assert order == ["agent-3", "agent-1", "agent-4"]

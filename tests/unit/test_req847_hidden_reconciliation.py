"""REQ-847 / #170 — stale hidden prefs are reconciled against the live rail.

Hide ids (agent:/team:/remote:) that match no live rail row and no pinned id
are dropped each session; the next prefs PATCH self-heals the server bag.
Reconciliation waits for ALL rail feeds so a mid-load moment can neither flash
rows visible nor persist a trimmed list. Behaviour spec of record (vitest):
webui/frontend/src/lib/__tests__/hiddenAgents.test.ts
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HIDDEN = REPO / "webui" / "frontend" / "src" / "lib" / "hiddenAgents.ts"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"

RAIL_FEEDS = (
    "blueprintsQuery",
    "teamsQuery",
    "remotesQuery",
    "cliQuery",
    "herdrQuery",
)


def test_req847_reconcile_drops_only_dead_ids():
    text = HIDDEN.read_text(encoding="utf-8")
    assert "export function reconcileHiddenAgentIds" in text
    assert "pinnedIds" in text
    assert "live.has(id) || pinned.has(id)" in text


def test_req847_gate_covers_every_rail_feed():
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert "railDataPending" in sidebar
    for feed in RAIL_FEEDS:
        assert f"{feed}.isPending" in sidebar, f"{feed} must gate reconciliation"
    assert "reconcileHiddenAgentIds(" in sidebar
    assert "pins.map((pin) => pin.id)" in sidebar
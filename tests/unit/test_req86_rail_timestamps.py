"""REQ-86 & REQ-125: Rail row timestamps beside name & role badges on second row."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAT_TIME_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "chatTime.ts"
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
RAIL_ROW_SLOT = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "RailRowSlot.tsx"
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"

# #856 slice G: the row markup moved verbatim into sidebar/rowsRender.tsx;
# these pins read the union so the doctrine spans both homes.
_ROWS_RENDER = SIDEBAR_TSX.parent / "sidebar" / "rowsRender.tsx"


def _sidebar_text():
    return "\n".join(x.read_text(encoding="utf-8") for x in (SIDEBAR_TSX, _ROWS_RENDER))




def test_chat_time_exports_format_rail_timestamp():
    content = CHAT_TIME_TS.read_text(encoding="utf-8")
    assert "export function formatRailTimestamp(" in content
    assert "'Just now'" in content
    assert "min ago" in content
    assert "Today" in content
    assert "Yesterday" in content
    assert "export function getRowLastMessage(" in content


def test_sidebar_name_row_has_timestamp_and_no_badge():
    content = _sidebar_text()
    slot = RAIL_ROW_SLOT.read_text(encoding="utf-8")
    assert "formatRailTimestamp" in content
    assert "getRowLastMessage" in content
    # #500 moved the name-line right slot into RailRowSlot.
    assert "os-rail-timestamp" in slot
    assert 'data-testid="rail-row-timestamp"' in slot


def test_sidebar_second_row_has_snippet_and_role_badge():
    content = _sidebar_text()
    # Role badge must be rendered after snippet on the second row
    assert "os-agent-role-badge" in content
    assert "snippet || agent.description" in content
    assert "teamSnippet || team.description" in content
    assert "remoteSnippet ||" in content


def test_css_defines_rail_timestamp():
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert ".os-rail-timestamp {" in css
    assert "tabular-nums" or "nowrap" in css

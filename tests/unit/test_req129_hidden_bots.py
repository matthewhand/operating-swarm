"""REQ-129: Hidden Bots footer row chrome — label + count, hover chevron, ghost until hover."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
AGENT_SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
BASE_HTML = REPO_ROOT / "src" / "swarm" / "templates" / "base.html"
AGENT_SIDEBAR_JS = REPO_ROOT / "src" / "swarm" / "static" / "js" / "agent_sidebar.js"


def test_agent_sidebar_tsx_has_hidden_bots_row_and_swap():
    tsx = AGENT_SIDEBAR_TSX.read_text(encoding="utf-8")
    # Terminology: the row reads 'Hidden Agents' (#873) — same chrome contract.
    assert "Hidden Agents" in tsx
    assert "os-hidden-bots-row" in tsx
    assert "os-hidden-bots-label" in tsx
    assert "os-hidden-bots-tail" in tsx
    assert "os-hidden-bots-count" in tsx
    assert "os-hidden-bots-chevron" in tsx
    assert "hoveringHidden" in tsx
    assert "os-hide-drop--has-hidden" in tsx


def test_index_css_hidden_bots_ghost_and_borderless():
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert ".os-hidden-bots-row" in css
    assert ".os-hide-drop--has-hidden" in css

    # Ghost / transparent resting state with no border
    assert "border: 0;" in css
    assert "background: transparent;" in css

    # Hover fill
    assert ".os-hidden-bots-row:hover" in css


def test_base_html_and_sidebar_js_updated_for_hidden_bots():
    html = BASE_HTML.read_text(encoding="utf-8")
    assert "Hidden Bots" in html
    assert "os-hidden-bots-row" in html

    js = AGENT_SIDEBAR_JS.read_text(encoding="utf-8")
    # Count updated cleanly without old parenthesis-wrapped style
    assert "String(hiddenTotal)" in js

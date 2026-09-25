from pathlib import Path


def test_req99_rail_scroll_fade_in_sidebar_and_css():
    repo_root = Path(__file__).resolve().parents[2]
    sidebar_tsx = repo_root / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
    rail_sections_tsx = repo_root / "webui" / "frontend" / "src" / "components" / "sidebar" / "RailSections.tsx"
    index_css = repo_root / "webui" / "frontend" / "src" / "index.css"

    assert sidebar_tsx.exists()
    assert rail_sections_tsx.exists()
    assert index_css.exists()

    tsx_content = sidebar_tsx.read_text(encoding="utf-8") + rail_sections_tsx.read_text(encoding="utf-8")
    css_content = index_css.read_text(encoding="utf-8")

    # Verifies fade element rendered with testid and class in sidebar
    assert 'data-testid="rail-scroll-fade"' in tsx_content
    assert "os-rail-scroll-fade" in tsx_content
    assert "pointer-events-none" in tsx_content

    # Verifies CSS gradient uses theme-aware sidebar chrome variable and pointer-events: none
    assert ".os-rail-scroll-fade" in css_content
    assert "linear-gradient(to bottom, transparent, var(--os-chrome-sidebar))" in css_content
    assert "pointer-events: none;" in css_content

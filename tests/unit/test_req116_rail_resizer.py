from pathlib import Path
from helpers.source_surface import sidebar_surface


def test_req116_rail_resize_module_and_helpers_exist():
    repo_root = Path(__file__).resolve().parents[2]
    module_ts = repo_root / "webui" / "frontend" / "src" / "lib" / "railResize.ts"
    assert module_ts.exists()
    content = module_ts.read_text(encoding="utf-8")

    assert "MIN_RAIL_WIDTH" in content
    assert "MAX_RAIL_WIDTH" in content
    assert "AVATAR_ONLY_THRESHOLD" in content
    assert "clampRailWidth" in content
    assert "loadRailWidth" in content
    assert "saveRailWidth" in content
    assert "isAvatarOnlyWidth" in content


def test_req116_agent_sidebar_and_css_wired():
    repo_root = Path(__file__).resolve().parents[2]
    sidebar_tsx = repo_root / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
    rail_resize_hook = (
        repo_root / "webui" / "frontend" / "src" / "components" / "sidebar" / "useRailResize.ts"
    )
    sidebar_content = sidebar_surface()

    assert 'data-testid="rail-resize-handle"' in sidebar_content
    assert 'data-avatar-only=' in sidebar_content
    assert "os-rail-resizer" in sidebar_content
    assert "os-agent-sidebar--avatar-only" in sidebar_content
    assert "clampRailWidth" in sidebar_content

    index_css = repo_root / "webui" / "frontend" / "src" / "index.css"
    assert index_css.exists()
    css_content = index_css.read_text(encoding="utf-8")

    assert ".os-rail-resizer" in css_content
    assert "cursor: col-resize;" in css_content
    assert ".os-agent-sidebar--avatar-only" in css_content

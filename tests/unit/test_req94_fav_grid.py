"""REQ-94 favourite grid: 2-up named large tiles, move not copy."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA_CSS = REPO / "webui/frontend/src/index.css"
SPA_SIDEBAR = REPO / "webui/frontend/src/components/AgentSidebar.tsx"
SPA_SIDEBAR_ROWS = SPA_SIDEBAR.parent / "sidebar" / "RailSections.tsx"
SPA_PINS = REPO / "webui/frontend/src/lib/pinnedAgents.ts"
DJANGO_CSS = REPO / "src/swarm/static/css/rest_mode_style.css"
DJANGO_PIN_JS = REPO / "src/swarm/static/js/agent_pin_grid.js"
DJANGO_SIDEBAR_JS = REPO / "src/swarm/static/js/agent_sidebar.js"


def test_spa_fav_grid_is_two_up_named_large_avatar():
    css = SPA_CSS.read_text(encoding="utf-8")
    sidebar = "\n".join(x.read_text(encoding="utf-8") for x in (SPA_SIDEBAR, SPA_SIDEBAR_ROWS))
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "repeat(4," not in css.split(".os-fav-grid")[1].split(".os-fav-grid--active")[0]
    assert ".os-fav-tile__name" in css
    assert ".os-fav-tile__badge" in css
    tile_block = css.split(".os-fav-tile {")[1].split("}")[0]
    assert "background: transparent" in tile_block
    assert ".os-fav-tile--active" in css
    assert ".os-fav-grid--bare" in css
    assert ".os-fav-grid__hint" in css
    assert 'data-fav-layout="2-up"' in sidebar
    assert 'size="lg"' in sidebar
    assert "os-fav-tile__name" in sidebar
    assert "os-fav-tile__badge" in sidebar
    assert "os-fav-tile--active" in sidebar
    assert "os-fav-grid--bare" in sidebar
    assert "fav-empty-hint" in sidebar
    assert "loadOrSeedPinnedAgents" in sidebar
    assert "Favourites" not in sidebar
    assert "Favorites" not in sidebar


def test_spa_pin_is_a_move_out_of_the_rail_list():
    pins = SPA_PINS.read_text(encoding="utf-8")
    sidebar = "\n".join(x.read_text(encoding="utf-8") for x in (SPA_SIDEBAR, SPA_SIDEBAR_ROWS))
    assert "excludePinnedFromList" in pins
    assert "excludePinnedFromList" in sidebar
    assert "move, not a copy" in pins
    assert "swarm_pinned_agents" in pins
    assert "movePinnedAgent" in pins
    assert "loadOrSeedPinnedAgents" in pins
    assert "DEFAULT_PINNED_SUPPORT" in pins
    assert "dropUnfavourite" in sidebar
    assert "dropPinReorder" in sidebar
    assert "agent-list-drop" in sidebar
    assert 'dropEffect = \'move\'' in sidebar or 'dropEffect = "move"' in sidebar


def test_django_mirror_matches_two_up_named_large_tiles():
    css = DJANGO_CSS.read_text(encoding="utf-8")
    js = DJANGO_PIN_JS.read_text(encoding="utf-8")
    sidebar = DJANGO_SIDEBAR_JS.read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert ".os-agent-tile__name" in css
    assert "os-agent-tile__avatar" in css
    assert "os-agent-tile__avatar" in js
    assert 'dropEffect = "move"' in js
    assert "swarm_pinned_agents" in sidebar
    assert "pinnedIds" in sidebar
    assert "Favourites" not in css
    assert "Favourites" not in js

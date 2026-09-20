"""REQ-858 / #213 — Plugins/tools & skills install UX (TrueForge catalog pattern).

Locks the Add tools / Add skills catalog in PluginsPopup: search + kind
filters, detail drawer, install states, already-installed Manage/Remove,
honest skills empty state, env-name-only display. Behaviour spec of record
(vitest): webui/frontend/src/components/__tests__/InstallCatalog.test.tsx
and webui/frontend/src/lib/__tests__/installCatalog.test.ts.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
POPUP = REPO / "webui" / "frontend" / "src" / "components" / "PluginsPopup.tsx"
CATALOG = REPO / "webui" / "frontend" / "src" / "components" / "InstallCatalog.tsx"
LIB = REPO / "webui" / "frontend" / "src" / "lib" / "installCatalog.ts"
CSS = REPO / "webui" / "frontend" / "src" / "index.css"
FEATURE_STATUS = REPO / "FEATURE_STATUS.md"
CHANGELOG = REPO / "CHANGELOG.md"


def test_req858_plugins_popup_has_add_tools_and_skills_panes():
    src = POPUP.read_text(encoding="utf-8")
    assert "Add tools" in src
    assert "Add skills" in src
    # #516 relabelled the scope pane to the agent seat.
    assert "This agent" in src
    assert "Toggles apply to this agent only." in src
    assert "<InstallCatalog" in src
    assert "surface={pane === 'skills' ? 'skills' : 'tools'}" in src
    assert "MarketplaceScanSection" not in src


def test_req858_catalog_has_search_filter_drawer_and_install_states():
    src = CATALOG.read_text(encoding="utf-8")
    lib = LIB.read_text(encoding="utf-8")
    assert 'data-testid="os-install-catalog"' in src
    assert 'data-testid="os-install-search"' in src
    assert 'aria-label="Kind filters"' in src
    assert 'data-testid="os-install-drawer"' in src
    assert 'data-testid="os-install-btn"' in src
    assert 'data-testid="os-manage-btn"' in src
    assert 'data-testid="os-remove-btn"' in src
    assert 'data-testid="os-health-dot"' in src
    assert "idle" in lib and "installing" in lib and "'ok'" in lib and "fail" in lib
    assert "progress progress-primary" in src


def test_req858_skills_empty_state_is_honest():
    lib = LIB.read_text(encoding="utf-8")
    src = CATALOG.read_text(encoding="utf-8")
    assert "No skill packs to install yet" in lib
    assert "honest" in lib.lower()
    assert "SKILLS_CATALOG_EMPTY_TITLE" in src
    assert "fake" not in src.lower()


def test_req858_env_names_only_and_no_html_injection():
    lib = LIB.read_text(encoding="utf-8")
    src = CATALOG.read_text(encoding="utf-8")
    assert "envNamesOnly" in lib
    assert "SECRETISH_RE" in lib
    assert "dangerouslySetInnerHTML" not in src
    assert "${" in lib
    css = CSS.read_text(encoding="utf-8")
    assert ".os-install-catalog" in css
    assert ".os-install-drawer" in css
    assert ".os-health-dot" in css


def test_req858_feature_status_and_changelog():
    status = FEATURE_STATUS.read_text(encoding="utf-8")
    log = CHANGELOG.read_text(encoding="utf-8")
    assert "REQ-858" in status
    assert "#213" in status
    assert "REQ-858" in log
    assert "#213" in log

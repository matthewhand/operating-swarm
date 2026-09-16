"""REQ-861 / #251 — left/right sidepane conceal buttons and click-outside dismissal."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QA = REPO / "docs" / "qa" / "REQ-861-sidepane-conceal-buttons.md"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
HEADER = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar" / "SidebarHeader.tsx"
MODAL = REPO / "webui" / "frontend" / "src" / "components" / "DaisyUI" / "Modal.tsx"
SETTINGS = REPO / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx"
GENERATIONS = REPO / "webui" / "frontend" / "src" / "components" / "GenerationsPanel.tsx"
TEAMS = REPO / "webui" / "frontend" / "src" / "components" / "overlays" / "TeamsSheet.tsx"
EDITOR = REPO / "webui" / "frontend" / "src" / "components" / "AgentEditorSheet.tsx"
BLUEPRINTS = REPO / "webui" / "frontend" / "src" / "components" / "overlays" / "BlueprintsSheet.tsx"
CONCEAL = REPO / "webui" / "frontend" / "src" / "components" / "SidepaneConceal.tsx"
BRAND_MARK = REPO / "webui" / "frontend" / "src" / "components" / "BrandMarkMono.tsx"
MONO = REPO / "assets" / "brand" / "webui-geometric-mono.svg"


def test_req861_docs_exist():
    assert QA.is_file()
    text = QA.read_text(encoding="utf-8")
    assert "Conceal sidebar" in text
    assert "Conceal sidepane" in text
    assert "webui-geometric-mono.svg" in text


def test_req861_left_sidebar_mono_conceal():
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    conceal = CONCEAL.read_text(encoding="utf-8")
    mark = BRAND_MARK.read_text(encoding="utf-8")
    mono = MONO.read_text(encoding="utf-8")
    assert "SidebarConcealButton" in sidebar
    assert "concealSidebar" in sidebar
    assert 'aria-label="Close agents sidebar"' in sidebar
    assert "SidebarConcealButton" in header
    assert 'aria-label="Conceal sidebar"' in conceal
    assert "BrandMarkMono" in conceal
    assert "currentColor" in mark
    assert "os-brand-mark-geometric" in mark
    assert "currentColor" in mono


def test_req861_right_sidepane_chevrons():
    modal = MODAL.read_text(encoding="utf-8")
    generations = GENERATIONS.read_text(encoding="utf-8")
    conceal = CONCEAL.read_text(encoding="utf-8")
    assert "SidepaneConcealButton" in modal
    assert "placement === 'end'" in modal
    assert "ChevronsRight" in conceal
    assert 'aria-label="Conceal sidepane"' in conceal
    assert "SidepaneConcealButton" in generations
    for path in (SETTINGS, TEAMS, EDITOR, BLUEPRINTS):
        src = path.read_text(encoding="utf-8")
        assert 'placement="end"' in src, path.name


def test_req861_settings_branding_unchanged():
    """REQ-861 must not replace the Settings sheet Operating Swarm mark."""
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "Open Swarm" in settings
    assert "/webui-geometric.svg" in settings
    assert "os-brand-mark-geometric" in settings


def test_req861_click_outside():
    modal = MODAL.read_text(encoding="utf-8")
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    generations = GENERATIONS.read_text(encoding="utf-8")
    assert "handleBackdropClick" in modal
    assert "modal-backdrop" in modal
    assert "Close agents sidebar" in sidebar
    assert "pointerdown" in generations

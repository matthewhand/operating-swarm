"""REQ-880 / #275: Model pill opens the model menu, never the CLI agent list."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PICKER = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "NavbarRoutingPicker.tsx"
TEST = (
    REPO_ROOT
    / "webui"
    / "frontend"
    / "src"
    / "components"
    / "__tests__"
    / "NavbarRoutingPicker.test.tsx"
)


def test_sheet_follows_explicit_dimension_not_families():
    picker = PICKER.read_text(encoding="utf-8")
    assert "sheetDim" in picker
    assert "openSheetAt" in picker
    # Keyboard items follow the remembered sheet level, not families.length.
    assert "open === 'sheet' ? sheetLevel : open" in picker
    assert "const sheetLevel: RoutingDimension = sheetDim ?? 'agent'" in picker
    # Old derived fallback that sent Model clicks to the agent list.
    assert "open === 'sheet' && families.length > 0 && previewAgent !== ''" not in picker
    # Face click must not blindly open agent when a pill was the target.
    assert "closest('[data-routing-pill]')" in picker


def test_picker_tests_cover_wide_and_narrow_empty_model_click():
    text = TEST.read_text(encoding="utf-8")
    assert "narrow sheet keeps an explicit Model request" in text
    assert "wide flyout keeps an explicit Model request" in text
    assert "routing-menu-model" in text
    assert "routing-menu-agent" in text
    assert "routing-pill-model" in text

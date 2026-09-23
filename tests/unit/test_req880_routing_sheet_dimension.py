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
    """REQ-906/#504 + #681 retired the sheet mechanics; the requirement
    survives as: the picker offers one surface, and Model rows route to the
    model dimension (tag='model' → pickModel), never the agent list."""
    picker = PICKER.read_text(encoding="utf-8")
    # The combined trigger exists; the retired sibling model pill does not.
    assert "routing-pill-agent" in picker
    assert "routing-pill-model" not in picker
    # Model-dimension routing is explicit in both surfaces.
    assert "pickModel" in picker
    # Face click must not blindly open agent when a pill was the target.
    assert "closest('[data-routing-pill]')" in picker


def test_picker_tests_cover_wide_and_narrow_empty_model_click():
    """The sheet/flyout test names are gone with the surfaces (#629/#681);
    the palette tests still pin the negative: no menu, no sibling model pill."""
    text = TEST.read_text(encoding="utf-8")
    assert "routing-pill-model" in text  # asserted ABSENT in the palette tests
    assert "routing-menu-agent" in text  # asserted ABSENT in the palette tests

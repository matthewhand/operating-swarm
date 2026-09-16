"""REQ-182: Alt+N hover tip — top-right of pin/card (Fixes #638)."""

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"


def test_alt_hotkey_tip_is_top_right():
    css = INDEX_CSS.read_text(encoding="utf-8")

    # Match .os-fav-tile__shortcut rule
    match = re.search(r"\.os-fav-tile__shortcut\s*\{([^}]+)\}", css)
    assert match, ".os-fav-tile__shortcut rule must exist in index.css"
    body = match.group(1)

    assert "top:" in body, "Shortcut chip must position from top, not bottom"
    assert "bottom:" not in body, "Shortcut chip must not position from bottom"
    assert "right:" in body, "Shortcut chip must position from right"

    # Hover reveal only — #57: leave the tile and the hint hides (no focus stick).
    assert ".os-fav-tile:hover .os-fav-tile__shortcut" in css
    assert ".os-fav-tile:focus-within .os-fav-tile__shortcut" not in css

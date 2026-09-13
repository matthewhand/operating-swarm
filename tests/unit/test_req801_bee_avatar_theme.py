"""#801 Bee avatar theme — enum, both locked variants, brand reuse, custom wins."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BEE_AVATAR_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "beeAvatar.ts"
BEE_AVATAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "BeeAvatar.tsx"
AGENT_AVATAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentAvatar.tsx"
THEME_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "avatarTheme.ts"
GEOMETRIC_SVG = REPO_ROOT / "assets" / "brand" / "webui-geometric.svg"


def test_req801_theme_enum_includes_bee():
    content = THEME_TS.read_text(encoding="utf-8")
    assert "'blobs', 'bland', 'default', 'bee'" in content
    assert "return 'blobs'" in content
    assert "defaultAvatarTheme" in content


def test_req801_bee_is_opt_in_not_forced_default():
    content = THEME_TS.read_text(encoding="utf-8")
    # Default remains Blobs; Bee is stored only when chosen.
    assert "function defaultAvatarTheme(): AvatarTheme {\n  return 'blobs'\n}" in content
    picker = (
        REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AvatarThemePicker.tsx"
    ).read_text(encoding="utf-8")
    # REQ-828 picker: Bee/Blobs are installable families rendered as checkboxes.
    assert "{ id: 'bee', label: 'Bee' }" in content
    assert "{ id: 'blobs', label: 'Blobs' }" in content
    picker = (
        REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AvatarThemePicker.tsx"
    ).read_text(encoding="utf-8")
    assert "AVATAR_THEME_FAMILIES.map" in picker
    assert "aria-label={theme.label}" in picker
    assert "toggleEnabledAvatarTheme(theme.id, event.target.checked)" in picker
    assert "optional installs" in picker
    assert "never auto-applied" in picker


def test_req801_both_locked_variants_are_assigned():
    content = BEE_AVATAR_TS.read_text(encoding="utf-8")
    assert "['side-on', 'face-only']" in content
    assert "beeSpecForAgent" in content
    assert "variant === 'face-only'" in content
    tsx = BEE_AVATAR_TSX.read_text(encoding="utf-8")
    assert 'data-bee-variant={spec.variant}' in tsx
    assert "spec.variant === 'side-on'" in tsx
    assert "FaceOnlyBee" in tsx
    assert "SideOnBee" in tsx
    assert 'data-googly="true"' in tsx


def test_req801_reuses_geometric_webui_paths_not_cyber_swarm():
    geometric = GEOMETRIC_SVG.read_text(encoding="utf-8")
    bee = BEE_AVATAR_TSX.read_text(encoding="utf-8")
    assert "M18 18 C8 8 4 22 16 28 C20 24 22 20 18 18 Z" in geometric
    assert "M18 18 C8 8 4 22 16 28 C20 24 22 20 18 18 Z" in bee
    assert "webui-geometric.svg" in bee
    assert not any("src=" in line and "marketing" in line for line in bee.splitlines())
    assert not any("href=" in line and "marketing" in line for line in bee.splitlines())


def test_req801_eye_wander_css_matches_blobs_spirit():
    css = (REPO_ROOT / "webui" / "frontend" / "src" / "index.css").read_text(encoding="utf-8")
    assert '.os-bee-avatar[data-eye-state="active"] .os-bee-pupils' in css
    assert "animation: os-bee-wander" in css
    assert "@keyframes os-bee-wander" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_req801_custom_still_wins_over_bee():
    content = AGENT_AVATAR_TSX.read_text(encoding="utf-8")
    custom_at = content.index("if (isCustom)")
    bee_at = content.index("if (theme === 'bee')")
    blobs_at = content.index("if (theme === 'blobs')")
    assert custom_at < bee_at < blobs_at

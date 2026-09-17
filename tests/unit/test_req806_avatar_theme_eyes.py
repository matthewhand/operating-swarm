"""REQ-806 / #111: every enabled avatar theme style has idle eyes + active wander."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
THEME_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "avatarTheme.ts"
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
AGENT_AVATAR = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentAvatar.tsx"
ROBOT_AVATAR = (
    REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar" / "RobotAvatar.tsx"
)
SIDEBAR_AVATAR = (
    REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar" / "AgentAvatar.tsx"
)
EYES_TEST = (
    REPO_ROOT
    / "webui"
    / "frontend"
    / "src"
    / "components"
    / "__tests__"
    / "AvatarThemeEyes.test.tsx"
)

PACK_IDS = (
    "chassis",
    "pixel",
    "glyph",
    "orb",
    "antenna",
    "cube",
    "mask",
    "beetle",
    "ghost",
    "crystal",
)


def _reduce_haystack(css: str) -> str:
    return "\n".join(css.split("@media (prefers-reduced-motion: reduce)")[1:])


def test_req806_catalog_and_packs_are_wired_for_eyes():
    theme = THEME_TS.read_text(encoding="utf-8")
    agent = AGENT_AVATAR.read_text(encoding="utf-8")
    sidebar = SIDEBAR_AVATAR.read_text(encoding="utf-8")
    robot = ROBOT_AVATAR.read_text(encoding="utf-8")
    css = INDEX_CSS.read_text(encoding="utf-8")

    for pack in PACK_IDS:
        assert f"'{pack}'" in theme

    assert "os-bland-eyes" in agent
    assert "'data-eye-state': eyeState" in agent
    assert "data-eye-state={active ? 'active' : 'idle'}" in agent
    assert "os-bland-eyes" in sidebar
    assert "GooglyPair" in robot
    assert "os-robot-pupils" in robot
    assert "data-eye-state={eyeState}" in robot

    assert '.os-blob-avatar[data-eye-state="active"] .os-blob-eyes' in css
    assert "animation: os-blob-wander" in css
    assert '.os-bee-avatar[data-eye-state="active"] .os-bee-pupils' in css
    assert "animation: os-bee-wander" in css
    assert '.os-bland-avatar[data-eye-state="active"] .os-bland-eyes' in css
    assert "animation: os-bland-wander" in css
    assert "animation: os-robot3d-wander" in css
    assert "animation: os-robot-wander" in css
    assert "@keyframes os-robot-wander" in css

    for pack in PACK_IDS:
        if pack == "chassis":
            continue
        assert f'[data-avatar-theme="{pack}"][data-eye-state="active"] .os-robot-pupils' in css
        assert f"@keyframes os-robot-wander-{pack}" in css


def test_req806_reduced_motion_kills_every_eye_loop():
    css = INDEX_CSS.read_text(encoding="utf-8")
    reduce = _reduce_haystack(css)
    assert '.os-blob-avatar[data-eye-state="active"] .os-blob-eyes' in reduce
    assert '.os-bee-avatar[data-eye-state="active"] .os-bee-pupils' in reduce
    assert '.os-bland-avatar[data-eye-state="active"] .os-bland-eyes' in reduce
    assert '.os-robot-avatar[data-eye-state="active"] .os-robot-pupils' in reduce
    assert '[data-avatar-theme][data-eye-state="active"] .os-robot-pupils' in reduce
    assert '.os-robot3d-fallback[data-eye-state="active"] .os-robot3d-pupils' in reduce
    assert "animation: none" in reduce


def test_req806_vitest_walks_the_settings_catalog():
    content = EYES_TEST.read_text(encoding="utf-8")
    assert "INSTALLABLE_AVATAR_THEMES" in content
    assert "ROBOT_PACK_THEME_IDS" in content
    assert "data-eye-state" in content
    assert "prefers-reduced-motion" in content

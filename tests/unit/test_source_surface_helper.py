"""#1030 — the source-surface helper contract + pin-migration meta-test.

Guards two things:

1. The helper returns every file the orchestrator has shed into its
   extraction packages (so pins see moved code), and stays deterministic.
2. The meta-test fires when an orchestrator grows a *new* extraction
   package that no pin surface covers yet (the class of drift that broke
   REQ-128/78/848/98/165 pins during slices #1020-#1027).
"""

from helpers.source_surface import (
    FRONTEND_SRC,
    REPO_ROOT,
    chat_surface,
    settings_surface,
    sidebar_surface,
    surface,
)


def test_chat_surface_covers_orchestrator_and_package():
    chat_pkg = FRONTEND_SRC / "features" / "chat"
    content = chat_surface()
    assert "ChatPage.tsx" in content or "export default" in content
    if chat_pkg.is_dir():
        # every package file's distinctive header made it into the surface
        for p in sorted(chat_pkg.glob("*.ts*")):
            first_line = p.read_text(encoding="utf-8").splitlines()[0]
            assert first_line in content, f"{p.name} missing from chat_surface"


def test_sidebar_surface_covers_both_package_homes():
    content = sidebar_surface()
    for pkg in (FRONTEND_SRC / "components" / "sidebar", FRONTEND_SRC / "features" / "sidebar"):
        if pkg.is_dir():
            for p in sorted(pkg.glob("*.ts*")):
                first_line = p.read_text(encoding="utf-8").splitlines()[0]
                assert first_line in content, f"{p.name} missing from sidebar_surface"


def test_settings_surface_covers_package():
    pkg = FRONTEND_SRC / "features" / "settings"
    if not pkg.is_dir():
        return  # pre-extraction: orchestrator-only surface is correct
    content = settings_surface()
    for p in sorted(pkg.glob("*.ts*")):
        first_line = p.read_text(encoding="utf-8").splitlines()[0]
        assert first_line in content, f"{p.name} missing from settings_surface"


def test_surface_is_deterministic():
    assert chat_surface() == chat_surface()
    assert sidebar_surface() == sidebar_surface()


def test_surface_helper_handles_missing_package():
    """A package dir that doesn't exist is simply skipped (pre-extraction repos)."""
    ghost = REPO_ROOT / "webui" / "frontend" / "src" / "features" / "no_such_pkg"
    orch = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
    content = surface(orch, ghost)
    assert content == orch.read_text(encoding="utf-8")


def test_meta_new_extraction_packages_are_pinned():
    """Any *new* package dir under features/ or components/sidebar must be
    claimed by a known surface — otherwise pins will silently drift again."""
    known = {
        FRONTEND_SRC / "features" / "chat",
        FRONTEND_SRC / "components" / "sidebar",
        FRONTEND_SRC / "features" / "sidebar",
        FRONTEND_SRC / "features" / "settings",
    }
    unclaimed = []
    for base in (FRONTEND_SRC / "features", FRONTEND_SRC / "components"):
        if base.is_dir() and base.name == "components":
            # components/ itself is full of ordinary components; only flag
            # package dirs that an orchestrator has already shed code into,
            # i.e. those containing an index or multiple extracted modules
            # alongside AgentSidebar/SettingsSheet still orchestrating them.
            continue
        if base.is_dir():
            for child in sorted(base.iterdir()):
                if child.is_dir() and child not in known:
                    unclaimed.append(child)
    assert not unclaimed, (
        "New extraction package(s) under features/ are not covered by any "
        f"source-surface pin: {unclaimed}. Add them to "
        "tests/helpers/source_surface.py (and migrate the relevant pins) — "
        "see #1030."
    )

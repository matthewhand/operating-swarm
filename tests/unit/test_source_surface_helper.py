"""#1030/#1055 — the source-surface helper contract + pin-migration meta-test.

Guards three things:

1. The helper returns every file the orchestrator has shed into its
   extraction packages (so pins see moved code), and stays deterministic.
2. The meta-test fires when an orchestrator grows a *new* extraction
   package that no pin surface covers yet (the class of drift that broke
   REQ-128/78/848/98/165 pins during slices #1020-#1027).
3. ``pin_source`` (#1055) asserts declaratively and its failure messages
   NAME the home each symbol lives in — no 6,000-line file dumps.
"""

from helpers.source_surface import (
    FRONTEND_SRC,
    REPO_ROOT,
    api_surface,
    chat_surface,
    pin_source,
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


def test_settings_surface_covers_real_package():
    # #1016 split SettingsSheet into components/settings/ — the surface must
    # read THAT package (an earlier draft pointed at features/settings/,
    # which does not exist, making the surface silently orchestrator-only).
    pkg = FRONTEND_SRC / "components" / "settings"
    assert pkg.is_dir(), "the #1016 settings package is missing"
    content = settings_surface()
    for p in sorted(pkg.glob("*.ts*")):
        first_line = p.read_text(encoding="utf-8").splitlines()[0]
        assert first_line in content, f"{p.name} missing from settings_surface"


def test_api_surface_covers_package():
    # #856 slice A made lib/api/ the single home; no orchestrator remains.
    pkg = FRONTEND_SRC / "lib" / "api"
    assert pkg.is_dir()
    content = api_surface()
    for p in sorted(pkg.glob("*.ts")):
        first_line = p.read_text(encoding="utf-8").splitlines()[0]
        assert first_line in content, f"{p.name} missing from api_surface"


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
    """Any *new* package dir under features/ must be claimed by a known surface
    — otherwise pins will silently drift again."""
    known = {
        FRONTEND_SRC / "features" / "chat",
        FRONTEND_SRC / "features" / "sidebar",
    }
    unclaimed = []
    base = FRONTEND_SRC / "features"
    if base.is_dir():
        for child in sorted(base.iterdir()):
            if child.is_dir() and child not in known:
                unclaimed.append(child)
    assert not unclaimed, (
        "New extraction package(s) under features/ are not covered by any "
        f"source-surface pin: {unclaimed}. Add them to "
        "tests/helpers/source_surface.py (and migrate the relevant pins) — "
        "see #1030/#1055."
    )


# ---------------------------------------------------------------------------
# pin_source (#1055)


class TestPinSource:
    def test_contains_passes_and_names_the_home(self):
        ok, msg = pin_source("chat", contains=["os-chat-header", "isWorking"])
        assert ok, msg
        assert "ChatHeader.tsx" in msg

    def test_missing_symbol_lists_every_searched_home(self):
        ok, msg = pin_source("chat", contains=["definitely-not-anywhere-xyz"])
        assert not ok
        assert "definitely-not-anywhere-xyz" in msg
        assert "ChatHeader.tsx" in msg
        assert "not found" in msg

    def test_not_contains_violation_names_the_offending_home(self):
        ok, msg = pin_source(
            "chat", contains=["os-chat-header"], not_contains=["os-chat-header"]
        )
        assert not ok
        assert "ChatHeader.tsx" in msg

    def test_count(self):
        ok, msg = pin_source("chat", count={"AgentAvatar": 1})
        assert ok, msg

    def test_count_failure_reports_actual(self):
        ok, msg = pin_source("chat", count={"AgentAvatar": 10_000})
        assert not ok
        assert "expected >= 10000" in msg

    def test_regex(self):
        ok, msg = pin_source("chat", regex=[r'className="os-chat-header[^"]*"'])
        assert ok, msg

    def test_regex_failure_names_homes(self):
        ok, msg = pin_source("chat", regex=[r"definitely-not-anywhere-\d+"])
        assert not ok
        assert "matched none of" in msg

    def test_multiple_problems_all_reported(self):
        ok, msg = pin_source(
            "chat",
            contains=["os-chat-header", "definitely-not-anywhere-xyz"],
            not_contains=["isWorking"],
        )
        assert not ok
        assert "definitely-not-anywhere-xyz" in msg
        assert "forbidden token" in msg
        # the passing token is not reported as missing
        assert "os-chat-header' not found" not in msg

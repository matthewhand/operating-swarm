"""Issue #163 — section internal-only talk (lock) source-lock.

Custom rail sections persist an internal-only flag. Locked members may
message only each other (team of one included). Unassigned is never
lockable. No secrets. No LiteLLM catalog. No Neon.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECTIONS = REPO / "webui" / "frontend" / "src" / "lib" / "railSections.ts"
MENU = REPO / "webui" / "frontend" / "src" / "lib" / "railContextMenu.ts"
HEADER = REPO / "webui" / "frontend" / "src" / "components" / "RailSectionHeader.tsx"
RAIL_MENU = REPO / "webui" / "frontend" / "src" / "components" / "RailContextMenu.tsx"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
MAILBOX = REPO / "src" / "swarm" / "core" / "agent_mailbox.py"
TALK = REPO / "src" / "swarm" / "core" / "section_talk.py"
DOCS = REPO / "docs" / "qa" / "ISSUE-163-section-internal-talk.md"
CHANGELOG = REPO / "CHANGELOG.md"
CI = REPO / ".github" / "workflows" / "issue163-section-talk.yml"


def _no_secrets(text: str) -> None:
    lowered = text.lower()
    assert "ghp_" not in lowered
    assert "github_pat_" not in lowered


def test_docs_name_lock_and_team_of_one():
    text = DOCS.read_text(encoding="utf-8")
    assert "internal-only" in text
    assert "team of one" in text.lower() or "team of 1" in text.lower()
    assert "Fixes #163" in text or "issue #163" in text.lower() or "#163" in text
    assert ":8001" not in text
    _no_secrets(text)


def test_section_state_persists_internal_only():
    text = SECTIONS.read_text(encoding="utf-8")
    assert "internalOnly" in text
    assert "toggleSectionInternalOnly" in text
    assert "canSectionTalk" in text
    assert "railSectionsParam" in text
    assert "swarm_rail_sections" in text
    _no_secrets(text)


def test_section_chrome_has_lock_control():
    header = HEADER.read_text(encoding="utf-8")
    assert "rail-section-talk-lock" in header
    assert "Talk internal only" in header
    assert "Talk externally" in header
    assert "LockOpen" in header or "Lock" in header
    menu = MENU.read_text(encoding="utf-8")
    assert "section-talk-lock" in menu
    assert "Talk internal only" in menu
    assert "Talk externally" in menu
    rail = RAIL_MENU.read_text(encoding="utf-8")
    assert "'section-talk-lock'" in rail
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert "toggleSectionInternalOnly" in sidebar
    assert "data-internal-only" in sidebar
    _no_secrets(header + menu + rail + sidebar)


def test_mailbox_enforces_section_lock_from_params():
    talk = TALK.read_text(encoding="utf-8")
    assert "can_section_talk" in talk
    assert "section_internal_only" in talk
    mailbox = MAILBOX.read_text(encoding="utf-8")
    assert "rail_sections" in mailbox
    assert "ERROR_SECTION_LOCKED" in mailbox
    assert "filter_talk_targets" in mailbox
    chat = CHAT.read_text(encoding="utf-8")
    assert "railSectionsParam" in chat
    _no_secrets(talk + mailbox + chat)


def test_changelog_and_ci():
    log = CHANGELOG.read_text(encoding="utf-8")
    added = log.split("## [Unreleased]", 1)[1].split("Fixes #163", 1)[0]
    assert "internal-only" in added
    assert "Fixes #163" in log
    ci = CI.read_text(encoding="utf-8")
    assert "issue163" in ci.lower() or "163" in ci
    assert "pytest" in ci
    assert "vitest" in ci
    assert ":8001" not in ci
    _no_secrets(ci)

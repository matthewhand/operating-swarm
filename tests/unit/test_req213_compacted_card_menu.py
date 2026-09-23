"""REQ-213 / #693 — compacted-card context menu is SPA chrome.

View-only Remove; DaisyUI menu shared with rail (#435); no disk rewrite,
no secrets, no live :8001 dump.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MENU = REPO / "webui" / "frontend" / "src" / "lib" / "compactedCardMenu.ts"
PILL = REPO / "webui" / "frontend" / "src" / "components" / "SystemPreloadPill.tsx"
CARD = REPO / "webui" / "frontend" / "src" / "components" / "CompactSummaryCard.tsx"
OVERLAY = REPO / "webui" / "frontend" / "src" / "components" / "CompactedCardContextMenu.tsx"
RAIL = REPO / "webui" / "frontend" / "src" / "components" / "RailContextMenu.tsx"
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
MSG_LIST = REPO / "webui" / "frontend" / "src" / "features" / "chat" / "ChatMessageList.tsx"
CI = REPO / ".github" / "workflows" / "req213-compacted-card-menu.yml"


def test_menu_contract_is_honest_about_view_only_delete():
    text = MENU.read_text(encoding="utf-8")
    assert "REQ-213" in text
    assert "Remove from view" in text
    assert "view-only" in text or "view only" in text.lower()
    assert "chat_store" in text
    assert "WAVE" not in text
    assert "ghp_" not in text
    assert ":8001" not in text


def test_shared_daisy_menu_matches_rail_chrome():
    overlay = OVERLAY.read_text(encoding="utf-8")
    assert "RailContextMenu" in overlay
    assert "compacted-card-context-menu" in overlay
    rail = RAIL.read_text(encoding="utf-8")
    assert "menu menu-sm rounded-box" in rail
    assert "expand" in rail
    assert "collapse" in rail


def test_pill_and_summary_chip_open_the_menu():
    pill = PILL.read_text(encoding="utf-8")
    assert "useCompactedCardMenu" in pill
    assert "onContextMenu" in pill
    card = CARD.read_text(encoding="utf-8")
    assert "useCompactedCardMenu" in card
    assert "chat-summary-chip" in card
    chat = CHAT.read_text(encoding="utf-8") + MSG_LIST.read_text(encoding="utf-8")
    assert "hiddenSummaryIds" in chat
    assert "hiddenMessageKeys" in chat
    assert "onRemoveCard" in chat


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "req213" in text.lower() or "REQ-213" in text
    assert "vitest" in text
    assert "pytest" in text
    assert ":8001" not in text

"""REQ-161: Restored session status for every agent kind (Fixes #572)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_RESTORE = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "sessionRestore.ts"
CHAT_PAGE = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
MSG_LIST = REPO_ROOT / "webui" / "frontend" / "src" / "features" / "chat" / "ChatMessageList.tsx"


def test_session_restore_covers_cli_api_remote_team():
    src = SESSION_RESTORE.read_text(encoding="utf-8")
    assert "export function withRestoredSession" in src
    assert "export function restoreKindForAgent" in src
    assert "Resumed CLI session" in src
    assert "Restored session" in src
    assert "Reconnected remote" in src
    assert "hasRestorableTurns" in src


def test_chat_page_hydrates_remote_threads_and_banners_restore():
    src = CHAT_PAGE.read_text(encoding="utf-8") + MSG_LIST.read_text(encoding="utf-8")
    assert 'fetchAgentThread(`remote:${remoteFromUrl}`' in src
    assert "restoredSessionNotice" in src
    assert "restoreNotice" in src
    assert "os-chat-status" in src

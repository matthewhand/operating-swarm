"""REQ-98: Per-agent rail notifications (Fixes #459)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTIFY_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "agentNotifications.ts"
RAIL_MENU_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "railContextMenu.ts"
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
CHAT_PAGE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CHAT_WS_HOOK = (
    REPO_ROOT / "webui" / "frontend" / "src" / "features" / "chat" / "useChatWebSocket.ts"
)
RAIL_ORDER_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "railOrder.ts"


def test_notify_store_is_local_swarm_key_not_neon():
    content = NOTIFY_TS.read_text(encoding="utf-8")
    assert "export const NOTIFY_AGENTS_STORAGE_KEY = 'swarm_notify_agents'" in content
    assert "localStorage" in content
    assert "/v1/preferences" not in content
    assert "Notification.requestPermission" in content
    assert "document.hidden" in content
    assert "new Notification(" in content
    assert "window.focus" in content
    assert "swarm:focus-agent" in content


def test_sidebar_menu_has_notifications_toggle():
    menu = RAIL_MENU_TS.read_text(encoding="utf-8")
    assert "id: 'notify'" in menu
    assert "Notifications: On" in menu
    assert "Notifications: Off" in menu
    content = SIDEBAR_TSX.read_text(encoding="utf-8")
    assert "maybeNotifyAgentTurn" in content
    assert "enableAgentNotifications" in content
    assert "notify-permission-hint" in content
    assert "remoteDisplayName" in content
    assert 'className="os-agent-edit"' not in content


def test_chat_page_notifies_on_assistant_final_and_failed_interrupt():
    content = CHAT_PAGE_TSX.read_text(encoding="utf-8") + CHAT_WS_HOOK.read_text(
        encoding="utf-8"
    )
    assert "maybeNotifyAgentTurn" in content
    assert "notifyGenerationComplete" in content
    assert "failed: true" in content
    assert "snippet: event.text" in content


def test_generation_complete_carries_snippet():
    content = RAIL_ORDER_TS.read_text(encoding="utf-8")
    assert "export interface GenerationCompleteDetail" in content
    assert "snippet?: string" in content
    assert "failed?: boolean" in content

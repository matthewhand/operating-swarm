"""Issue #88 — AnythingLLM list/search/resume/chat wiring locks."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CHAT_SEND = REPO / "webui" / "frontend" / "src" / "features" / "chat" / "useChatSend.ts"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
# #855 slice 2: per-harness dispatch moved verbatim into the stubs mixin.
STUBS = REPO / "src" / "swarm" / "chat" / "stubs_mixin.py"
API = REPO / "src" / "swarm" / "views" / "remotes_api.py"


def test_chat_sends_session_id_for_remote_resume():
    src = "\n".join(x.read_text(encoding="utf-8") for x in (CHAT, CHAT_SEND))
    assert "remoteChatTurnParams" in src
    assert "sessionFromUrl" in src
    assert "fetchRemoteThreadSessions" in src
    assert "os-session-picker" not in src or "SessionPicker" in src


def test_rail_opens_searchable_anythingllm_sessions():
    src = SIDEBAR.read_text(encoding="utf-8")
    # #748/#580: the rail's session affordance is the declared capability
    # (seatHasSessions) plus the menu-payload session rows; remote thread
    # listing lives in RemoteSessionSwitcher + lib/remoteSessions.
    assert "seatHasSessions" in src
    assert "openGroupPicker" in src


def test_operate_api_forwards_session_id():
    src = API.read_text(encoding="utf-8")
    assert "session_id" in src
    assert "query" in src


def test_consumers_route_anythingllm_remote():
    src = CONSUMERS.read_text(encoding="utf-8") + STUBS.read_text(encoding="utf-8")  # #855 slice 2: dispatch moved to the stubs mixin
    assert "anythingllm" in src
    assert "streamed_any" in src

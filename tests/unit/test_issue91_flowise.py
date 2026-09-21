"""Issue #91 — Flowise list/search/resume/chat wiring locks."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
API = REPO / "src" / "swarm" / "views" / "remotes_api.py"
REMOTE_SESSIONS = REPO / "webui" / "frontend" / "src" / "lib" / "remoteSessions.ts"


def test_chat_sends_session_id_for_remote_resume():
    src = CHAT.read_text(encoding="utf-8")
    assert "remoteChatTurnParams" in src
    assert "sessionFromUrl" in src
    assert "fetchRemoteThreadSessions" in src
    assert "os-session-picker" not in src or "SessionPicker" in src


def test_rail_opens_searchable_flowise_sessions():
    src = SIDEBAR.read_text(encoding="utf-8")
    # #748/#580: see test_issue88 — declared capability + menu payload rows.
    assert "seatHasSessions" in src
    assert "openGroupPicker" in src


def test_operate_api_forwards_session_id():
    src = API.read_text(encoding="utf-8")
    assert "session_id" in src
    assert "query" in src


def test_consumers_route_flowise_remote():
    src = CONSUMERS.read_text(encoding="utf-8")
    assert "flowise" in src
    assert "streamed_any" in src


def test_remote_sessions_treats_flowise_as_session_kind():
    src = REMOTE_SESSIONS.read_text(encoding="utf-8")
    assert "flowise" in src
    assert "remoteListsSessions" in src
    assert "remoteChatTurnParams" in src

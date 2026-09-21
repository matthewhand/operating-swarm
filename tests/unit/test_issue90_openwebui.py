"""Issue #90 — Open WebUI list/search/resume/chat wiring locks."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
API = REPO / "src" / "swarm" / "views" / "remotes_api.py"
ADAPTER = REPO / "src" / "swarm" / "core" / "openwebui_remote.py"
REMOTES = REPO / "src" / "swarm" / "core" / "remotes.py"
HARNESS = REPO / "src" / "swarm" / "core" / "remote_harness.py"


def test_chat_sends_session_id_for_remote_resume():
    src = CHAT.read_text(encoding="utf-8")
    assert "remoteChatTurnParams" in src
    assert "sessionFromUrl" in src
    assert "fetchRemoteThreadSessions" in src
    assert "SessionPicker" in src


def test_rail_opens_searchable_openwebui_sessions():
    src = SIDEBAR.read_text(encoding="utf-8")
    # #748/#580: see test_issue88 — declared capability + menu payload rows.
    assert "seatHasSessions" in src
    assert "openGroupPicker" in src


def test_operate_api_forwards_session_id_and_query():
    src = API.read_text(encoding="utf-8")
    assert "session_id" in src
    assert "query" in src


def test_consumers_route_openwebui_remote():
    src = CONSUMERS.read_text(encoding="utf-8")
    assert "openwebui" in src
    assert "streamed_any" in src


def test_adapter_is_external_open_webui_not_os_webui():
    src = ADAPTER.read_text(encoding="utf-8")
    assert "os-webui" in src.lower() or "own WebUI" in src
    assert "never replace" in src.lower() or "must never replace" in src
    remotes = REMOTES.read_text(encoding="utf-8")
    assert '"openwebui"' in remotes
    assert "OPENWEBUI_BASE_URL" in remotes
    assert "os-webui" in remotes
    harness = HARNESS.read_text(encoding="utf-8")
    assert "openwebui" in harness
    assert "sessions=rid in" in harness.replace(" ", "") or '"openwebui"' in harness

"""Issue #92 — n8n list/search/resume/chat wiring locks."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CHAT_SEND = REPO / "webui" / "frontend" / "src" / "features" / "chat" / "useChatSend.ts"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
API = REPO / "src" / "swarm" / "views" / "remotes_api.py"
REMOTES = REPO / "src" / "swarm" / "core" / "remotes.py"


def test_chat_sends_session_id_for_remote_resume():
    src = "\n".join(x.read_text(encoding="utf-8") for x in (CHAT, CHAT_SEND))
    assert "remoteChatTurnParams" in src
    assert "sessionFromUrl" in src
    assert "fetchRemoteThreadSessions" in src


def test_rail_opens_searchable_n8n_sessions():
    src = SIDEBAR.read_text(encoding="utf-8")
    # #748/#580: see test_issue88 — declared capability + menu payload rows.
    assert "seatHasSessions" in src
    assert "openGroupPicker" in src


def test_operate_api_forwards_session_id_and_query():
    src = API.read_text(encoding="utf-8")
    assert "session_id" in src
    assert "query" in src


def test_consumers_route_n8n_remote():
    src = CONSUMERS.read_text(encoding="utf-8")
    assert "n8n" in src


def test_n8n_adapter_does_not_mint_workflows():
    # #812 slice 5: the n8n impl body moved verbatim to remote_impls/n8n.py.
    src = "\n".join(
        (
            REMOTES.read_text(encoding="utf-8"),
            (REPO / "src" / "swarm" / "core" / "remote_impls" / "n8n.py").read_text(encoding="utf-8"),
        )
    )
    assert "n8n_workflow_required" in src
    assert "does not mint new" in src
    assert "N8N_BASE_URL" in src
    assert "N8N_API_KEY" in src

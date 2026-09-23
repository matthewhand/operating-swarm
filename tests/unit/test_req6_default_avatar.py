"""REQ-6: original Bert-like default agent avatar is wired as the fallback."""

from pathlib import Path

from helpers.source_surface import chat_surface

REPO = Path(__file__).resolve().parents[2]
AVATAR = REPO / "src" / "swarm" / "static" / "img" / "default-agent-avatar.svg"
SPA_AVATAR = REPO / "webui" / "frontend" / "src" / "assets" / "default-agent-avatar.svg"
SIDEBAR_JS = REPO / "src" / "swarm" / "static" / "js" / "agent_sidebar.js"
SPA_SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
SPA_AVATAR_TSX = REPO / "webui" / "frontend" / "src" / "components" / "AgentAvatar.tsx"
CARD = REPO / "src" / "swarm" / "templates" / "blueprint_card.html"


def test_original_svg_exists_and_is_not_a_raster_still():
    svg = AVATAR.read_text(encoding="utf-8")
    assert AVATAR.is_file()
    assert svg.lstrip().startswith("<svg")
    assert "png" not in svg.lower()
    # Cyan pear + white eyes + dark pupils — the small-size read.
    assert "#3deef5" in svg.lower()
    assert "#ffffff" in svg.lower()
    assert "#141414" in svg
    assert svg.count("<circle") >= 4
    assert "Not a copy of any film/TV still" in svg
    # SPA ships the same original drawing (Vite import), not a Trap Door still.
    assert SPA_AVATAR.read_text(encoding="utf-8") == svg


def test_django_sidebar_and_library_card_use_default_svg():
    js = SIDEBAR_JS.read_text(encoding="utf-8")
    # Django rail uses a colour-dot mark; library cards keep the SVG fallback.
    assert "os-agent-dot" in js
    card = CARD.read_text(encoding="utf-8")
    assert "img/default-agent-avatar.svg" in card
    assert "fa-robot" not in card


def test_spa_wires_agent_avatar_as_default():
    avatar = SPA_AVATAR_TSX.read_text(encoding="utf-8")
    sidebar = SPA_SIDEBAR.read_text(encoding="utf-8")
    # #1055: shared chat surface — the header and message list mount
    # AgentAvatar; the surface covers every extraction home.
    chat = chat_surface()
    # SPA fallback is an inline data-URI (REQ-60 bland default), not a static SVG path.
    assert "DEFAULT_AGENT_AVATAR_SRC" in avatar
    assert "data:image/svg+xml" in avatar
    assert "AgentAvatar" in sidebar
    assert "os-agent-dot" not in sidebar
    assert "agentMarkIndex" not in sidebar
    assert "AgentAvatar" in chat
    # Chat header uses the shared AgentAvatar; custom path wins, data-URI is fallback.
    assert "selectedAgent?.avatar_path" in chat
    assert chat.count("<AgentAvatar") >= 1


def test_blueprints_list_exposes_avatar_path_for_chat():
    api = (REPO / "src" / "swarm" / "views" / "api_views.py").read_text(encoding="utf-8")
    assert '"avatar_path": _metadata_avatar_path(meta)' in api
    assert "def _metadata_avatar_path" in api

"""REQ-78 (#423) chrome contracts: XOR update/info right of system name.

Locks placement, colours, public GitHub call-home (no tokens), and local-over-upstream
priority so a later rail rewrite cannot drop the slot or invent secrets.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
UPDATE = REPO / "webui" / "frontend" / "src" / "components" / "UpdateChrome.tsx"
CSS = REPO / "webui" / "frontend" / "src" / "index.css"
SPA_UPDATE = REPO / "webui" / "frontend" / "src" / "lib" / "spaUpdate.ts"
GITHUB = REPO / "webui" / "frontend" / "src" / "lib" / "githubRelease.ts"
CONSUMERS = REPO / "src" / "swarm" / "consumers.py"
CHAT_WS = REPO / "webui" / "frontend" / "src" / "lib" / "chatWs.ts"
CHAT_PAGE = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"


def test_update_chrome_sits_right_of_system_name_not_on_server_icon():
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert "import UpdateChrome from './UpdateChrome'" in sidebar
    assert "<UpdateChrome />" in sidebar
    hostname_idx = sidebar.index('id="os-rail-hostname"')
    chrome_idx = sidebar.index("<UpdateChrome />")
    server_idx = sidebar.index('data-testid="rail-server-icon"')
    assert server_idx < hostname_idx < chrome_idx
    assert "os-rail-update-chrome--local" in css
    assert "os-rail-update-chrome--upstream" in css
    assert "#d97706" in css
    assert "#38bdf8" in css
    assert "#d46a6a" in css  # #372 WS drop stays a different red


def test_xor_priority_and_click_targets():
    chrome = UPDATE.read_text(encoding="utf-8")
    logic = SPA_UPDATE.read_text(encoding="utf-8")
    assert "kind === 'local'" in chrome
    assert "kind === 'upstream'" in chrome
    assert "GITHUB_ISSUES_URL" in chrome
    assert "window.location.reload" in chrome or "reload()" in chrome
    assert "kind: 'local'" in logic
    assert "alsoUpstream" in logic
    assert "if (localMismatch)" in logic
    assert "if (upstreamNewer)" in logic


def test_github_call_home_is_public_and_tokenless():
    src = GITHUB.read_text(encoding="utf-8")
    assert "api.github.com/repos/" in src
    assert "releases/latest" in src
    # REQ-78: public repo default; VITE_SWARM_GITHUB_REPO may override the
    # repo name but the call-home stays unauthenticated either way.
    assert "GITHUB_REPO =" in src
    assert "matthewhand/open-swarm" in src
    assert "Authorization" not in src
    assert "GITHUB_TOKEN" not in src
    assert "Bearer" not in src
    assert "No tokens" in src


def test_backend_advertises_spa_hello_on_authenticated_connect():
    consumer = CONSUMERS.read_text(encoding="utf-8")
    ws = CHAT_WS.read_text(encoding="utf-8")
    page = CHAT_PAGE.read_text(encoding="utf-8")
    assert 'SPA_HELLO_TYPE = "spa_hello"' in consumer
    assert "_send_spa_hello" in consumer
    assert 'kind: \'spa_hello\'' in ws or 'kind: "spa_hello"' in ws
    assert "publishExpectedSpaVersion" in page

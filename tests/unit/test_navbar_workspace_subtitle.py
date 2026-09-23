"""Navbar workspace/folder/branch subtitle under the agent name (#65)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
CHAT_PAGE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
# #856 slice J: the navbar identity block moved verbatim into ChatHeader.
CHAT_HEADER_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "features" / "chat" / "ChatHeader.tsx"
WORKSPACE_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "agentWorkspace.ts"


def test_subtitle_renders_under_agent_name():
    tsx = CHAT_PAGE_TSX.read_text(encoding="utf-8") + CHAT_HEADER_TSX.read_text(encoding="utf-8")
    assert "os-navbar-identity-text" in tsx
    assert "os-navbar-identity-subtitle" in tsx
    assert "os-navbar-workspace-subtitle" in tsx
    assert "navbarWorkspaceSubtitle" in tsx
    assert "os-navbar-identity-label" in tsx
    # Name still uses the #255 fade mask class, not truncate.
    assert "os-navbar-identity-label min-w-0 flex-1" in tsx
    assert 'className="os-navbar-identity-subtitle"' in tsx


def test_subtitle_css_truncates_with_ellipsis_and_keeps_name_fade():
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert ".os-navbar-identity-subtitle" in css
    assert "text-overflow: ellipsis;" in css
    assert ".os-navbar-identity-label" in css
    assert (
        "mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent 100%)"
        in css
    )
    assert (
        "-webkit-mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent 100%)"
        in css
    )


def test_subtitle_formatter_uses_folder_emdash_branch():
    src = WORKSPACE_TS.read_text(encoding="utf-8")
    assert "formatNavbarWorkspaceSubtitle" in src
    assert "${path} — branch: ${branch}" in src
    assert "navbarWorkspaceSubtitle" in src

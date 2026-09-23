"""REQ-132: Remotes dropdown only on remote agents (not every agent)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAT_PAGE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CHAT_PAGE_TEST_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "__tests__" / "ChatPage.test.tsx"


def test_chat_page_guards_remotes_dropdown():
    tsx = CHAT_PAGE_TSX.read_text(encoding="utf-8")
    assert "isRemoteBackedTeam" in tsx
    assert "isRemoteAgent" in tsx
    assert "showRemotesControl" in tsx
    # Post-#749: remotes chrome is remote-only (agent or remote-backed team).
    # #736: product modes are retired — the guard is the seat kind alone.
    assert "Boolean(isRemoteAgent || isRemoteBackedTeam)" in tsx

    # Empty catalog shows Add remote; otherwise the REQ-200 picker; omitted when not remote.
    assert "showEmptyRemoteChrome" in tsx
    assert "{showEmptyRemoteChrome ? (" in tsx
    assert "showRemotesControl" in tsx
    assert "<RemoteSelect" not in tsx
    assert "NavbarRoutingPicker" in tsx
    assert 'seatKind="remote"' in tsx
    assert ") : null}" in tsx


def test_chat_page_test_covers_req132():
    test_tsx = CHAT_PAGE_TEST_TSX.read_text(encoding="utf-8")
    assert "hides the Remotes control on local API and CLI agents" in test_tsx
    assert "hides the Remotes control on local teams" in test_tsx
    assert "shows the Remotes control on remote-backed teams" in test_tsx

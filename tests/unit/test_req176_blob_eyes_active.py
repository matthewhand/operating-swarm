"""REQ-176: Blob eyes must wander while agent is working/streaming."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAT_PAGE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
MSG_LIST_TSX = (
    REPO_ROOT / "webui" / "frontend" / "src" / "features" / "chat" / "ChatMessageList.tsx"
)
# #856 slice J: the header mounts AgentAvatar active={isWorking}.
CHAT_HEADER_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "features" / "chat" / "ChatHeader.tsx"
BLOB_AVATAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "BlobAvatar.tsx"
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"


def test_chat_page_blob_eyes_active_when_streaming():
    content = (
        CHAT_PAGE_TSX.read_text(encoding="utf-8")
        + MSG_LIST_TSX.read_text(encoding="utf-8")
        + CHAT_HEADER_TSX.read_text(encoding="utf-8")
    )

    # Header passes active from the working state (stream OR queued await),
    # not merely because the ws status is open.
    assert "const isWorking = Boolean(streamingMessage) || awaitingAssistant" in content
    assert "active={isWorking}" in content
    assert "active={Boolean(streamingMessage || status === 'open')}" not in content

    # Composer / footer working indicator renders working avatar with active={true}
    assert 'data-testid="composer-working-indicator"' in content
    assert re.search(
        r'<AgentAvatar[^>]+active=\{true\}[^>]*size="xs"',
        content,
    )


def test_blob_avatar_sets_eye_state_active_or_idle():
    content = BLOB_AVATAR_TSX.read_text(encoding="utf-8")

    assert "const eyeState: BlobEyeState = active ? 'active' : 'idle'" in content
    assert 'data-eye-state={eyeState}' in content


def test_css_animates_active_blob_eyes():
    css = INDEX_CSS.read_text(encoding="utf-8")

    assert '.os-blob-avatar[data-eye-state="active"] .os-blob-eyes' in css
    assert "animation: os-blob-wander" in css
    assert "@keyframes os-blob-wander" in css

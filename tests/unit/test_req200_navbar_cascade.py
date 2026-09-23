"""REQ-200: one cascading navbar picker (Fixes #676)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAT_PAGE = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
PICKER = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "NavbarRoutingPicker.tsx"
PATH_LIB = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "routingPath.ts"
PALLETTE = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "ModelSearchPalette.tsx"
SETTINGS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "agentSettings.ts"
STATUS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "chatStatus.ts"


def test_navbar_uses_one_cascading_picker_not_sibling_selects():
    chat = CHAT_PAGE.read_text(encoding="utf-8")
    picker = PICKER.read_text(encoding="utf-8")
    path_lib = PATH_LIB.read_text(encoding="utf-8")
    settings = SETTINGS.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")

    assert "NavbarRoutingPicker" in chat
    assert "applyCliRoutingChange" in chat
    assert 'data-testid="cli-select"' not in chat
    assert 'data-testid="cli-model-select"' not in chat
    assert 'data-testid="api-select"' not in chat
    assert 'data-testid="api-model-select"' not in chat
    assert "availableApiAgents" not in chat
    assert 'data-testid="api-select"' not in picker
    assert "availableApiAgents" not in picker

    assert "navbar-routing-picker" in picker
    assert "routing-pill-agent" in picker
    # #629 superseded the sibling model pill: ONE combined trigger now.
    # #638 folded effort into the combined pill too — no sibling effort pill.
    # (test_req638 asserts 'routing-pill-effort' is absent; it is the authority.)
    assert "routing-pill-model" not in picker
    assert "routing-pill-effort" not in picker
    # REQ-906/#504 retired the flyout/sheet menus — the shared palette is the
    # successor surface and inherits the keyboard/rtl handling.
    assert "ArrowDown" in PALLETTE.read_text(encoding="utf-8")
    assert "rtl" in PALLETTE.read_text(encoding="utf-8")
    assert "routing-sheet" not in picker

    assert "HIDDEN_ROUTING_LABELS" in path_lib
    assert "you" in path_lib
    assert "gemini-3.8-flash" not in path_lib  # do not invent models
    assert "'effort'" in settings or '"effort"' in settings
    assert "effort" in status


def test_no_live_host_or_secrets_in_req200_surface():
    import re

    secret_key = re.compile(r"(?<![A-Za-z])sk-[A-Za-z0-9]{8,}")
    for path in (CHAT_PAGE, PICKER, PATH_LIB):
        text = path.read_text(encoding="utf-8")
        assert ":8001" not in text
        assert secret_key.search(text) is None, f"{path.name} looks like it embeds an API key"
        assert "OPENAI_API_KEY" not in text
        assert "localhost:8001" not in text

from pathlib import Path

from helpers.source_surface import chat_surface


def test_req192_chat_transcript_classes_and_tighter_margins():
    repo_root = Path(__file__).resolve().parents[2]
    chat_page_tsx = repo_root / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
    index_css = repo_root / "webui" / "frontend" / "src" / "index.css"

    assert chat_page_tsx.exists()
    assert index_css.exists()

    # #856 slice M: the os-chat-transcript container lives in ChatTranscriptShell.
    tsx_content = chat_surface()
    css_content = index_css.read_text(encoding="utf-8")

    # Verifies transcript container uses tightened padding and os-chat-transcript class
    assert "os-chat-transcript" in tsx_content
    assert "px-2 py-3 sm:px-3" in tsx_content
    assert "px-4 py-4" not in tsx_content

    # Verifies CSS rules tighten horizontal margins and column gaps
    assert ".os-chat-transcript" in css_content
    assert "column-gap: 0.25rem;" in css_content
    assert "max-width: 95%;" in css_content

    # Verifies status lines remain centered
    assert ".os-chat-status" in css_content
    assert "justify-content: center;" in css_content
    assert "text-align: center;" in css_content

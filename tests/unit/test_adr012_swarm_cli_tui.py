"""Lock ADR-012 Wave 0 TUI decision (REQ-111 / #481)."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "adr" / "012-swarm-cli-tui.md"
INDEX = REPO / "docs" / "adr" / "README.md"
REQ = REPO / "docs" / "requirements" / "REQ-111.md"
FEATURE_STATUS = REPO / "FEATURE_STATUS.md"
VISION = REPO / "docs" / "VISION.md"


def test_adr012_exists_and_picks_textual_not_herdr_or_go():
    text = ADR.read_text(encoding="utf-8")
    assert "ADR-012" in text
    assert "REQ-111" in text
    assert "#481" in text
    assert "Textual" in text
    assert "Wave 0" in text
    assert "127.0.0.1:8000" in text
    assert ":8001" in text  # named so we refuse it
    assert "Do **not** hardcode `:8001`" in text or "Do **not** hardcode :8001" in text
    assert "Herdr" in text
    assert "SSH" in text
    assert "Bubble Tea" in text
    assert "No secrets" in text
    assert "Neon" in text
    assert "sk-" not in text
    assert "W1a" in text and "W2b" in text and "W4b" in text


def test_adr012_is_indexed_and_req_pointer_exists():
    index = INDEX.read_text(encoding="utf-8")
    assert "012-swarm-cli-tui.md" in index
    assert "REQ-111" in index
    req = REQ.read_text(encoding="utf-8")
    assert "https://github.com/matthewhand/open-swarm/issues/481" in req
    assert "012-swarm-cli-tui.md" in req


def test_feature_status_and_vision_mark_tui_scaffolded():
    status = FEATURE_STATUS.read_text(encoding="utf-8")
    assert "REQ-111" in status
    assert "ADR-012" in status
    assert "os-cli tui" in status
    vision = VISION.read_text(encoding="utf-8")
    assert "#481" in vision
    assert "TUI" in vision

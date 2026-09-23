"""Lock ADR-011 Remote harness spec (REQ-203 / #680)."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "adr" / "011-remote-harness.md"
ADR_INDEX = REPO / "docs" / "adr" / "README.md"
REQ = REPO / "docs" / "requirements" / "REQ-203.md"
HARNESS_DOC = REPO / "docs" / "REMOTE_HARNESSES.md"


def test_adr011_exists_and_names_the_contract():
    text = ADR.read_text(encoding="utf-8")
    assert "REQ-203" in text
    assert "#680" in text
    assert "RemoteHarness" in text
    assert "Hermes" in text and "OpenMousBot" in text and "Rakazo" in text
    assert "Herdr" in text
    assert "not a fifth kind" in text.lower() or "not extra kinds" in text.lower()
    assert "CLI | API | Blueprint | Remote" in text or "CLI | API | Blueprint | Remote" in text.replace("**", "")
    assert "operate" in text.lower()
    assert "SSH" in text
    assert "10.0.0." not in text
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_"):
        assert needle not in lowered


def test_adr011_is_indexed_and_docs_table_exists():
    index = ADR_INDEX.read_text(encoding="utf-8")
    assert "011-remote-harness.md" in index
    assert "REQ-203" in index
    req = REQ.read_text(encoding="utf-8")
    assert "https://github.com/matthewhand/open-swarm/issues/680" in req
    table = HARNESS_DOC.read_text(encoding="utf-8")
    assert "RemoteHarness" in table
    assert "| **Hermes**" in table
    assert "| **OpenMousBot**" in table
    assert "| **Rakazo**" in table
    assert "| **Herdr**" in table
    assert "| **Slack (NemoHermes)**" in table
    assert "not a fifth kind" in table.lower()

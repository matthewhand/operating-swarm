"""Verify ADR numbering uniqueness and consistency across docs."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "adr"
ADR_INDEX = ADR_DIR / "README.md"


def test_adr_numbers_are_unique():
    adr_files = sorted(ADR_DIR.glob("[0-9][0-9][0-9]-*.md"))
    numbers = [f.name[:3] for f in adr_files]
    assert len(numbers) == len(set(numbers)), f"Duplicate ADR numbers found: {numbers}"


def test_adr011_and_adr012_distinct():
    adr011 = ADR_DIR / "011-remote-harness.md"
    adr012 = ADR_DIR / "012-swarm-cli-tui.md"
    assert adr011.exists(), "011-remote-harness.md must exist"
    assert adr012.exists(), "012-swarm-cli-tui.md must exist"

    text011 = adr011.read_text(encoding="utf-8")
    text012 = adr012.read_text(encoding="utf-8")
    assert "Remote is an abstract harness spec" in text011
    assert "swarm-cli TUI" in text012


def test_adr_index_references_all_adrs():
    index_text = ADR_INDEX.read_text(encoding="utf-8")
    adr_files = sorted(ADR_DIR.glob("[0-9][0-9][0-9]-*.md"))
    for f in adr_files:
        assert f.name in index_text, f"Missing index reference for {f.name}"

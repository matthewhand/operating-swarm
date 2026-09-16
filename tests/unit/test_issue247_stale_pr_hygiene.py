"""#247 — source-lock: CONTRIBUTING documents the rebase-or-close window.

Process/docs only. Not a product feature. The 48h nudge / 72h close
window must stay written down so stale-PR triage cannot silently drift.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTRIBUTING = REPO / "CONTRIBUTING.md"
NOTE = REPO / "docs" / "qa" / "ISSUE-247-stale-pr-hygiene.md"


def test_issue247_contributing_documents_rebase_or_close_window():
    text = CONTRIBUTING.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "**rebase-or-close window**" in lowered
    assert ">48h" in text
    assert ">72h" in text
    assert "conflicting" in lowered
    assert "nudge" in lowered
    assert "superseded" in lowered
    assert "check-if-fixed" in lowered
    assert "salvage" in lowered
    assert "base pr" in lowered
    assert "#247" in text
    assert "ISSUE-247-stale-pr-hygiene.md" in text


def test_issue247_workflow_note_locks_the_same_window():
    assert NOTE.is_file()
    text = NOTE.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "rebase-or-close" in lowered
    assert ">48h" in text
    assert ">72h" in text
    assert "nudge" in lowered
    assert "superseded" in lowered
    assert "check-if-fixed" in lowered
    assert "salvage" in lowered
    assert "base pr" in lowered
    assert "#247" in text
    assert "test_issue247_stale_pr_hygiene.py" in text
    assert "not a product change" in lowered

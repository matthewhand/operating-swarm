"""#250 — source-lock: CONTRIBUTING triages instant-fail/no-logs to Actions billing.

Process/docs only. Jobs that die in seconds with empty steps and no logs
are an account-level Actions block (usually the spending limit), not a
code regression. Keep that sentence in CONTRIBUTING so triage cannot
silently drift back to "debug the workflow YAML".
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTRIBUTING = REPO / "CONTRIBUTING.md"


def test_issue250_contributing_triages_instant_fail_to_actions_billing():
    text = CONTRIBUTING.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "instant-fail" in lowered
    assert "no job logs" in lowered
    assert "billing" in lowered
    assert "actions spending limit" in lowered
    assert "not code" in lowered
    assert "#250" in text

"""#238 — REQ-79 + Issue-136 own-diff workflows stay present and honest.

Local pytest of both selections is green. GitHub Actions currently fails
these jobs before step 1 with no logs (#250 billing/spend), which paints
every PR red and masks real regressions. Workflows must keep existing,
keep firing on pull_request, use concurrency, and if quarantined mention
#250 (no silent `if: false`).
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
REQ79 = REPO / ".github" / "workflows" / "req79-survival.yml"
KIND = REPO / ".github" / "workflows" / "issue136-kind-chat-e2e.yml"
WORKFLOWS = (REQ79, KIND)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(data: dict) -> dict:
    # PyYAML 1.1 treats the key `on` as boolean True.
    on = data.get("on", data.get(True))
    assert isinstance(on, dict), f"workflow on: must be a mapping, got {type(on)}"
    return on


def test_workflow_files_exist():
    for path in WORKFLOWS:
        assert path.is_file(), path


def test_workflows_run_on_pull_request():
    for path in WORKFLOWS:
        on = _on(_load(path))
        assert "pull_request" in on, f"{path.name} must run on pull_request"


def test_workflows_declare_concurrency():
    for path in WORKFLOWS:
        data = _load(path)
        conc = data.get("concurrency")
        assert isinstance(conc, dict), f"{path.name} must declare concurrency"
        assert conc.get("group"), f"{path.name} concurrency.group is required"


def test_quarantined_jobs_mention_issue_250():
    """Silent `if: false` is forbidden; tracking comment must cite #250."""
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8")
        job = _load(path)["jobs"]["own-diff"]
        skipped = job.get("if") is False or str(job.get("if")).lower() == "false"
        if skipped:
            assert "if: false" in text
            assert "#250" in text, f"{path.name} quarantine must cite #250"
            assert "#238" in text, f"{path.name} quarantine must cite #238"

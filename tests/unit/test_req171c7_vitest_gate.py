"""REQ-171C-7 / C-H9 / #616 — Vitest gates PRs; golden-journey stays HOLD.

This file locks CI *wiring*, not SPA behaviour. Chat/CLI/dropdown contracts
live in `webui/frontend` Vitest (`npm test`). Do not treat source-grep REQ
locks (or this YAML parse) as a substitute for that suite.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
PYTEST_WORKFLOW = REPO / ".github" / "workflows" / "python-pytest.yml"
VISUAL_WORKFLOW = REPO / ".github" / "workflows" / "visual-regression.yml"


def _load_workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _step_run(step: dict) -> str:
    run = step.get("run") or ""
    if isinstance(run, list):
        return "\n".join(str(part) for part in run)
    return str(run)


def _job_step_runs(job: dict) -> list[str]:
    return [_step_run(step) for step in job.get("steps") or [] if isinstance(step, dict)]


def test_vitest_job_runs_npm_test_after_npm_ci():
    """Sibling (or frontend) job must run `npm test` after `npm ci`."""
    data = _load_workflow(PYTEST_WORKFLOW)
    jobs = data["jobs"]
    assert "test" in jobs
    assert "frontend" in jobs

    candidates = []
    if "vitest" in jobs:
        candidates.append(("vitest", jobs["vitest"]))
    candidates.append(("frontend", jobs["frontend"]))

    gated = False
    for name, job in candidates:
        runs = _job_step_runs(job)
        ci_idx = next((i for i, run in enumerate(runs) if "npm ci" in run), None)
        test_idx = next(
            (i for i, run in enumerate(runs) if run.strip() == "npm test" or run.strip().endswith("\nnpm test")),
            None,
        )
        if ci_idx is not None and test_idx is not None and test_idx > ci_idx:
            gated = True
            assert name in {"vitest", "frontend"}
            break

    assert gated, (
        "python-pytest.yml must run `npm test` after `npm ci` in the "
        "frontend job or a sibling (REQ-171C-7 / #616)"
    )


def test_python_matrix_stays_off_browsers():
    """3.12 pytest stays keyless/SQLite — no Playwright, no npm test."""
    job = _load_workflow(PYTEST_WORKFLOW)["jobs"]["test"]
    matrix = job["strategy"]["matrix"]["python-version"]
    assert matrix == ["3.12"]
    blob = "\n".join(_job_step_runs(job)).lower()
    assert "playwright" not in blob
    assert "npm test" not in blob
    assert "npx playwright" not in blob
    assert "8001" not in blob
    assert "neon.tech" not in blob


def test_golden_journey_hold_stays_skipped():
    """REQ-89 HOLD: do not re-enable visual-regression.yml in this issue."""
    data = _load_workflow(VISUAL_WORKFLOW)
    journey = data["jobs"]["golden-journey"]
    assert journey.get("if") is False or str(journey.get("if")).lower() == "false"
    text = VISUAL_WORKFLOW.read_text(encoding="utf-8")
    assert "if: false" in text
    assert "REQ-89" in text
    assert "REQ-171C-7" in text or "#616" in text

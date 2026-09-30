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
    assert "vitest" in jobs

    candidates = []
    if "vitest" in jobs:
        candidates.append(("vitest", jobs["vitest"]))
    if "frontend" in jobs:
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
            assert name == "vitest" or name == "frontend"
            break

    assert gated, (
        "python-pytest.yml must run `npm test` after `npm ci` in the "
        "frontend job or a sibling (REQ-171C-7 / #616)"
    )


def test_python_matrix_stays_off_browsers():
    """3.12 pytest stays keyless/SQLite — no Playwright, no npm test."""
    job = _load_workflow(PYTEST_WORKFLOW)["jobs"]["test"]
    matrix = job["strategy"]["matrix"]["python-version"]
    assert matrix == ["3.12", "3.13"]  # #899/#1115: pyproject declares both
    blob = "\n".join(_job_step_runs(job)).lower()
    assert "playwright" not in blob
    assert "npm test" not in blob
    assert "npx playwright" not in blob
    assert "8001" not in blob
    assert "neon.tech" not in blob


def test_golden_journey_is_not_permanently_disabled():
    """#1730 claim B — the REQ-89 HOLD is lifted, and this pins the replacement.

    This test used to be ``test_golden_journey_hold_stays_skipped``, and its
    docstring read "REQ-89 HOLD: do not re-enable visual-regression.yml **in
    this issue**" -- a scoped, per-task instruction encoded as an assertion.
    #1730 owns the visual-gate claim, and the HOLD's stated reason turned out to
    be false in both halves: there are no golden images to recapture (the suite
    asserts computed styles, and the only PNGs are failure screenshots in a
    gitignored artifacts/), and the suite is green (5 passed, 1 skipped with a
    stated reason).

    An ``if: false`` job whose stated blocker no longer exists is worse than no
    job at all, so the gate now runs. What is pinned here is the *new* contract,
    and each part of it is something a future edit could quietly undo:

    1. the job is not switched off,
    2. it is reachable -- a disabled job with no trigger is a job that never
       runs, which is the original defect wearing a different hat,
    3. it still sets RUN_E2E_VISUAL=1, without which all six tests skip and the
       job goes green while checking nothing,
    4. and it still drives a real browser (Playwright Chromium), not a stub.
    """
    data = _load_workflow(VISUAL_WORKFLOW)
    journey = data["jobs"]["golden-journey"]
    assert journey.get("if") is not False, (
        "visual-regression.yml's golden-journey job is `if: false` again. The "
        "REQ-89 HOLD it was behind was for stale goldens that do not exist, and "
        "the suite is green; a disabled job reads as a gate to every future "
        "reader."
    )
    # Structural, not a grep for the literal: the job comment explains what
    # `if: false` used to be, so a substring search over the file text fails on
    # this test's own documentation. "No job in this workflow is switched off"
    # is the contract, and it is checked off the parsed YAML.
    disabled = sorted(
        name for name, job in data["jobs"].items() if str(job.get("if", "")).lower() == "false"
    )
    assert not disabled, (
        f"visual-regression.yml has job(s) permanently disabled: {disabled}. "
        f"Name the blocker in the job's own comment if one genuinely applies."
    )

    text = VISUAL_WORKFLOW.read_text(encoding="utf-8")

    # Reachable: `on:` must not be empty, or nothing can start the job.
    triggers = data.get("on", data.get(True))  # PyYAML parses bare `on:` as True
    assert triggers, "visual-regression.yml has no trigger, so the job can never run"

    blob = "\n".join(_job_step_runs(journey))
    assert "playwright" in blob.lower(), (
        "the job no longer installs a real browser, so the computed-style "
        "assertions it exists for cannot run"
    )
    # RUN_E2E_VISUAL lives in a step's `env:`, not its `run:`, so read the
    # parsed steps rather than the concatenated run scripts.
    step_envs = [
        dict(step.get("env") or {})
        for step in (journey.get("steps") or [])
        if isinstance(step, dict)
    ]
    assert any(str(env.get("RUN_E2E_VISUAL")) == "1" for env in step_envs), (
        "no step sets RUN_E2E_VISUAL=1, so every test in tests/e2e_visual skips "
        "and the job is green while asserting nothing -- the exact failure mode "
        "this gate exists to prevent"
    )
    # Provenance kept: REQ-89 placed the HOLD, and REQ-171C-7 / #616 is the
    # automatic SPA gate that this job must not be mistaken for a replacement
    # for.
    assert "REQ-89" in text
    assert "REQ-171C-7" in text or "#616" in text

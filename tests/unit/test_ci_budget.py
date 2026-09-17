"""Default PR CI is a thin suite — own-diff workflows are manual (#250)."""

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
WF = REPO / ".github" / "workflows"

# Workflows allowed to run on pull_request / push to main.
PR_OK = {
    "python-pytest.yml",
    "tsc-ratchet.yml",
    "docker-io-fly-deploy.yml",
    # #238 requires these two own-diff workflows to keep firing on
    # pull_request, and this test previously demanded the opposite for them —
    # so one of the two always failed. They are safe to list here: their only
    # job is quarantined (`if: false` citing #250/#238), so a run costs no
    # minutes, and both are path-filtered to a narrow file set. Keeping them
    # listed is what makes this file agree with
    # tests/unit/test_issue238_ci_honesty.py.
    "issue136-kind-chat-e2e.yml",
    "req79-survival.yml",
}


def _on(data: dict) -> dict | list | str:
    return data.get("on") or data.get(True) or {}


def test_own_diff_workflows_are_dispatch_only():
    extra = []
    for path in sorted(WF.glob("*.yml")):
        if path.name in PR_OK or path.name == "publish.yml":
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        on = _on(data)
        if isinstance(on, str):
            keys = {on}
        elif isinstance(on, list):
            keys = {str(x) for x in on}
        else:
            keys = set(on)
        if "pull_request" in keys or "push" in keys:
            extra.append(path.name)
    assert extra == [], extra


def test_python_tests_is_one_python_no_playwright_job():
    data = yaml.safe_load((WF / "python-pytest.yml").read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert "frontend" not in jobs
    assert "vitest" in jobs
    assert jobs["test"]["strategy"]["matrix"]["python-version"] == ["3.12"]

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

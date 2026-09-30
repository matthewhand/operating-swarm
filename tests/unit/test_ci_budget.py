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
    # #857: SDK doc gate — same quarantine pattern: only job is
    # `if: false` citing #250, path-filtered to the SDK docs surface,
    # so a run costs no minutes while #250 persists.
    "sdk-docs.yml",
    # #1334: barebones-install gate. Unlike the entries above this one is NOT
    # quarantined -- it is the only thing that catches a module-level import of
    # a package that has become an extra. CI installs --all-extras everywhere
    # (38 of 40 workflows), so such a bug resolves fine in CI and breaks only
    # in a clean container: `pytz` shipped undeclared that way, and
    # `gunicorn` stayed in base after being moved out. Both were found by hand.
    # Cost is two short jobs (a barebones and a deploy-profile `uv pip install`
    # plus a module walk). Reconsider if minutes get tight -- but note that
    # removing it reopens #1334, and a dispatch-only gate gates nothing.
    "barebones-install.yml",
}

# Workflows allowed to keep a `push` trigger even though they are NOT
# dispatch-only. These are POST-MERGE triggers, not own-diff PR gates: they fire
# once per merge instead of once per push inside a PR, so they cost no PR
# review minutes and are outside the #250 budget this file enforces.
#
# This is deliberately NOT a bare name allowlist. Each entry must satisfy the
# real invariant in `test_push_to_main_exemptions_keep_their_invariants` (push
# scoped to `main`, no `pull_request` trigger, manual retry still offered), and
# the specific workflow must still do its actual job — asserted in
# `test_on_main_sync_workflow_still_syncs_the_deployment_host`. Dropping a name
# here would silently re-open the CI-cost hole; a name that stops meeting these
# conditions fails the suite.
PUSH_TO_MAIN_ONLY = {
    # Deployment-host sync. Firing when main moves IS its purpose: it runs the
    # `sync-main` agent on the self-hosted `[self-hosted, windows, os-sync]`
    # runner, which pulls, resolves conflicts, and restarts the docker compose
    # stack (see .opencode/agent/sync-main.md). Making it dispatch-only would
    # stop the deployment box from ever updating after a merge — a silent
    # regression, not a CI saving. It is also not a cost risk: a single job,
    # job-level `if: github.repository == 'matthewhand/operating-swarm'` so it is
    # skipped in this private SoT, a `concurrency` group so two syncs can never
    # overlap, and a bounded `timeout-minutes`.
    "on-main.yml": {
        "push_branches": ["main"],
        "workflow_dispatch": True,
    },
}


def _on(data: dict) -> dict | list | str:
    return data.get("on") or data.get(True) or {}


def _triggers(data: dict) -> dict:
    """The `on:` block normalised to `{event: config-or-None}`."""
    on = _on(data)
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {str(x): None for x in on}
    return dict(on)


def _trigger_keys(data: dict) -> set[str]:
    return set(_triggers(data))


def test_own_diff_workflows_are_dispatch_only():
    extra = []
    for path in sorted(WF.glob("*.yml")):
        if path.name in PR_OK or path.name in PUSH_TO_MAIN_ONLY or path.name == "publish.yml":
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        keys = _trigger_keys(data)
        if "pull_request" in keys or "push" in keys:
            extra.append(path.name)
    assert extra == [], extra


def test_push_to_main_exemptions_keep_their_invariants():
    """A push-to-main exemption must stay the narrow shape it was granted as.

    Without this, adding a name to PUSH_TO_MAIN_ONLY would be a permanent,
    silent hole in the #250 CI budget: the workflow could grow a `pull_request`
    trigger, or widen `push` to every branch, and the budget test above would
    skip it without complaint.
    """
    for name, spec in PUSH_TO_MAIN_ONLY.items():
        path = WF / name
        assert path.is_file(), f"{name} has a push-to-main exemption but the workflow is missing"

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        triggers = _triggers(data)
        keys = set(triggers)

        # The budget this file protects is PR review minutes.
        assert "pull_request" not in keys, (
            f"{name} is exempt as post-merge, but it has a pull_request trigger — "
            "that is a PR-time cost and needs a PR_OK entry with a cost argument"
        )

        assert "push" in keys, (
            f"{name} is listed as PUSH_TO_MAIN_ONLY but no longer has a push trigger; "
            "remove the exemption instead of leaving a stale one"
        )
        push_cfg = triggers["push"] or {}
        assert push_cfg.get("branches") == spec["push_branches"], (
            f"{name} push trigger must stay scoped to {spec['push_branches']}, "
            f"got {push_cfg.get('branches')!r}"
        )
        assert ("workflow_dispatch" in keys) == spec["workflow_dispatch"], (
            f"{name} workflow_dispatch presence changed from {spec['workflow_dispatch']}; "
            "a manual retry path must be kept available for an operator-triggered restart"
        )


def test_on_main_sync_workflow_still_syncs_the_deployment_host():
    """on-main.yml's JOB is the invariant, not its trigger list.

    The exemption above permits `push: [main]` because that is the whole point
    of the workflow. If the mechanism it exists to drive is ever deleted, the
    trigger becomes a no-op that quietly stops the deployment host from ever
    updating — so assert the job is still wired up.
    """
    data = yaml.safe_load((WF / "on-main.yml").read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert set(jobs) == {"sync"}, f"on-main.yml job set changed: {sorted(jobs)}"

    job = jobs["sync"]
    body = yaml.safe_dump(job)

    # It must still run on the dedicated self-hosted runner, not ubuntu-latest.
    assert job["runs-on"] == ["self-hosted", "windows", "os-sync"], (
        f"on-main.yml must stay pinned to the os-sync self-hosted runner, got {job['runs-on']!r}"
    )

    # It must still drive the sync-main agent, or the workflow does nothing.
    assert "sync-main" in body, "on-main.yml no longer invokes the sync-main agent"

    # Cost guards: one sync at a time, and a bounded run.
    assert data.get("concurrency", {}).get("group") == "on-main-sync", (
        "on-main.yml must keep a concurrency group so two syncs never overlap"
    )
    assert data["concurrency"].get("cancel-in-progress") is False, (
        "on-main.yml must not cancel an in-flight sync"
    )
    assert 0 < job.get("timeout-minutes", 10**6) <= 60, (
        "on-main.yml must keep a bounded timeout-minutes"
    )

    # Private SoT guard: the job must not run here at all.
    assert "github.repository ==" in str(job.get("if", "")), (
        "on-main.yml must keep its job-level repository guard so it is skipped "
        "outside the deployment repo"
    )


def test_python_tests_is_one_python_no_playwright_job():
    data = yaml.safe_load((WF / "python-pytest.yml").read_text(encoding="utf-8"))
    jobs = data["jobs"]
    assert "frontend" not in jobs
    assert "vitest" in jobs
    assert jobs["test"]["strategy"]["matrix"]["python-version"] == ["3.12", "3.13"]  # #899/#1115

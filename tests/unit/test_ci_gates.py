"""Local CI runner must match the jobs it claims to reproduce (#1346)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ci_gates", REPO / "scripts" / "ci_gates.py")
assert _spec is not None and _spec.loader is not None
ci_gates = importlib.util.module_from_spec(_spec)
sys.modules["ci_gates"] = ci_gates
_spec.loader.exec_module(ci_gates)

# main() rewrites process env on purpose (#1335). Restore it so a test that
# drives main() cannot strip DATABASE_URL out from under the rest of the suite.
_MAIN_TOUCHED_ENV = (
    "SWARM_SKIP_DOTENV",
    "DJANGO_ALLOW_ASYNC_UNSAFE",
    "DATABASE_URL",
    "POSTGRES_HOST",
)


@pytest.fixture
def _main_env_restored():
    saved = {key: os.environ.get(key) for key in _MAIN_TOUCHED_ENV}
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_default_sequence_skips_frontend_and_quick_skips_the_suite():
    assert ci_gates.select_gates("", quick=False, with_frontend=False) == [
        "lock",
        "migration-graph",
        "sanitization",
        "tests",
        "py313",
        "barebones",
        "deploy-profile",
        "barebones-foreign",
        "postgres-migrate",
    ]
    assert ci_gates.select_gates("", quick=True, with_frontend=False) == [
        "lock",
        "migration-graph",
        "sanitization",
        "py313",
        "barebones",
        "deploy-profile",
        "barebones-foreign",
        "postgres-migrate",
    ]


def test_with_frontend_appends_the_frontend_gate():
    selected = ci_gates.select_gates("", quick=True, with_frontend=True)
    assert selected[-1] == "frontend"
    assert "tests" not in selected


def test_explicit_frontend_runs_without_the_flag():
    assert ci_gates.select_gates("frontend", quick=False, with_frontend=False) == ["frontend"]


def test_frontend_gate_runs_vitest_and_build_in_the_frontend_tree():
    gate = ci_gates.GATES["frontend"]
    assert gate.cwd_rel == "webui/frontend"
    assert gate.commands[0][:2] == ("npm", "test")
    assert gate.commands[1][:3] == ("npm", "run", "build")
    assert (REPO / gate.cwd_rel / "package.json").is_file()


def test_missing_npm_fails_the_frontend_gate(monkeypatch):
    monkeypatch.setattr(ci_gates.shutil, "which", lambda _name: None)
    rc, detail = ci_gates.run_named("frontend")
    assert rc == 1
    assert "npm" in detail


def test_barebones_reinstalls_even_when_the_venv_exists(tmp_path, monkeypatch):
    venv = tmp_path / "venv"
    py = venv / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(ci_gates.subprocess, "run", fake_run)
    argv = ci_gates.ensure_barebones(venv)
    # A warm tree must be thrown away. `uv pip install` of the same version
    # leaves a dependency that has moved into an extra still importable.
    assert calls[0][:2] == ["uv", "venv"]
    assert "--clear" in calls[0]
    assert calls[1][:3] == ["uv", "pip", "install"]
    assert calls[1][-1] == "."
    assert argv[0] == str(py)
    assert argv[1].endswith("import_all_swarm_modules.py")


def test_barebones_creates_a_missing_venv_before_install(tmp_path, monkeypatch):
    venv = tmp_path / "venv"
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        if list(argv)[:2] == ["uv", "venv"]:
            py = venv / "bin" / "python"
            py.parent.mkdir(parents=True, exist_ok=True)
            py.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(ci_gates.subprocess, "run", fake_run)
    ci_gates.ensure_barebones(venv)
    assert [cmd[:2] for cmd in calls] == [["uv", "venv"], ["uv", "pip"]]
    assert "--clear" in calls[0]


def test_barebones_install_failure_is_a_gate_failure(monkeypatch):
    def boom(_venv):
        raise subprocess.CalledProcessError(1, ["uv", "pip", "install"])

    monkeypatch.setattr(ci_gates, "ensure_barebones", boom)
    rc, detail = ci_gates.run_named("barebones")
    assert rc == 1
    assert "barebones install" in detail


def test_empty_selection_is_an_error():
    assert ci_gates.main(["--only", "tests", "--quick"]) == 2


def test_unknown_gate_is_an_error():
    assert ci_gates.main(["--only", "neon"]) == 2


def test_makefile_lists_the_targets():
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "ci-gates:" in text
    assert "ci-gates-quick:" in text
    assert ".PHONY:" in text
    phony = text.split(".PHONY:", 1)[1].split("\n", 1)[0]
    assert "ci-gates" in phony
    assert "ci-gates-quick" in phony
    # $(PY) is `uv run` and rewrites uv.lock before the script's lock gate.
    assert "$(PY) python scripts/ci_gates.py" not in text
    assert "\tuv run --frozen python scripts/ci_gates.py --with-frontend\n" in text
    assert "\tuv run --frozen python scripts/ci_gates.py --with-frontend --quick\n" in text


def test_local_ci_sequence_includes_the_frontend_gate():
    """#1730 claim C — `make ci-gates` is advertised as the local CI sequence.

    `ci_gates.select_gates` drops the `frontend` gate (vitest + the production
    build) unless `--with-frontend` is passed, and neither Make target passed
    it, so the one gate a developer most needs locally was the one that never
    ran. The no-frontend sequence is still reachable, but only by asking for it
    by name — so the opt-out is visible in review instead of being the default.
    """
    # ci_gates is imported at module scope, from the same scripts/ci_gates.py
    # the Makefile invokes.
    assert "frontend" in ci_gates.select_gates(with_frontend=True)
    assert "frontend" not in ci_gates.select_gates()
    # --quick drops the full suite; it must not drop the frontend half.
    quick = ci_gates.select_gates(with_frontend=True, quick=True)
    assert "frontend" in quick
    assert "tests" not in quick

    text = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "ci-gates-no-frontend:" in text
    phony = text.split(".PHONY:", 1)[1].split("\n", 1)[0]
    assert "ci-gates-no-frontend" in phony
    # The opt-out is the plain form; the default must not be.
    assert "\tuv run --frozen python scripts/ci_gates.py\n" in text


# ---------------------------------------------------------------------------
# #1671 — barebones-foreign must not abort on a uv too old to accept
# `uv python list <version>`. A tool that cannot answer the question skips the
# gate with a reason; it does not fail it and it does not crash.
# ---------------------------------------------------------------------------


def test_uv_version_key_reads_the_number_and_ignores_the_build_triple():
    assert ci_gates.uv_version_key("uv 0.12.5 (x86_64-unknown-linux-gnu)") == (0, 12, 5)
    # A local build's `+sha` suffix must not change the ordering.
    assert ci_gates.uv_version_key("uv 0.12.5+deadbeef") == (0, 12, 5)
    assert ci_gates.uv_version_key("uv 0.5.9 (aarch64-apple-darwin)") == (0, 5, 9)
    assert ci_gates.uv_version_key("uv 1.0") == (1, 0)
    assert ci_gates.uv_version_key("") is None
    assert ci_gates.uv_version_key("uv (unknown)") is None


def test_the_minimum_is_the_uv_that_actually_grew_the_positional_filter():
    # uv 0.6.0's `PythonListArgs` has no `request` field at all; 0.7.0 is the
    # first release documenting `uv python list [OPTIONS] [REQUEST]`. #1671 said
    # 0.6, one minor series too low — 0.6 rejects the argument too.
    assert ci_gates.UV_PYTHON_LIST_FILTER_MIN == (0, 7, 0)
    assert ci_gates.uv_python_list_skip_reason("uv 0.6.18 (x86_64-unknown-linux-gnu)")
    assert ci_gates.uv_python_list_skip_reason("uv 0.5.9 (x86_64-unknown-linux-gnu)")
    assert ci_gates.uv_python_list_skip_reason("uv 0.7.0 (x86_64-unknown-linux-gnu)") is None
    assert ci_gates.uv_python_list_skip_reason("uv 0.12.5 (x86_64-unknown-linux-gnu)") is None
    assert ci_gates.uv_python_list_skip_reason("uv 1.0.0 (x86_64-unknown-linux-gnu)") is None
    # `0.7` is `0.7.0` in semver, not an older uv: the comparison zero-pads.
    assert ci_gates.uv_python_list_skip_reason("uv 0.7") is None
    assert ci_gates.uv_python_list_skip_reason("uv 0.6") is not None
    assert ci_gates.uv_python_list_skip_reason("uv 1.0") is None


def test_the_skip_reason_names_the_version_and_the_remedy():
    reason = ci_gates.uv_python_list_skip_reason("uv 0.5.9 (x86_64-unknown-linux-gnu)")
    assert reason is not None
    assert "0.5.9" in reason
    assert "0.7.0" in reason
    assert "uv self update" in reason
    # An unreadable version is a skip too, never a silent pass.
    unreadable = ci_gates.uv_python_list_skip_reason("uv (no version here)")
    assert unreadable is not None
    assert "no uv version" in unreadable


def test_the_listing_still_passes_the_positional_version_filter(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="[]")

    monkeypatch.setattr(ci_gates.subprocess, "run", fake_run)
    assert ci_gates._cpython_rows() == []
    # The argv an old uv rejects. Dropping it would change what the gate asks.
    assert calls[0][:4] == ["uv", "python", "list", "3.12"]


def test_the_repo_uv_is_new_enough_to_run_the_listing():
    # Not mocked: the gate must actually work on the uv in this checkout.
    assert ci_gates.uv_python_list_skip_reason(ci_gates.uv_version_output()) is None


def test_barebones_foreign_skips_with_a_reason_on_an_old_uv(monkeypatch):
    monkeypatch.setattr(ci_gates, "uv_version_output", lambda: "uv 0.5.9 (x86_64-unknown-linux-gnu)")

    def unreachable(*_args, **_kwargs):
        raise AssertionError("an old uv must be answered before any preparation runs")

    # The qemu/sysroot precondition and the uv listing would both raise here.
    monkeypatch.setattr(ci_gates, "prepare_foreign_barebones", unreachable)
    rc, detail = ci_gates.run_barebones_foreign()
    assert rc == ci_gates.SKIP_RC
    assert rc != ci_gates.PASS_RC
    assert rc != ci_gates.FAIL_RC
    assert detail.startswith("SKIP ")
    assert "0.5.9" in detail


def test_barebones_foreign_runs_on_a_new_enough_uv(monkeypatch):
    monkeypatch.setattr(ci_gates, "uv_version_output", lambda: "uv 0.12.5 (x86_64-unknown-linux-gnu)")
    monkeypatch.setattr(ci_gates.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(ci_gates, "prepare_foreign_barebones", lambda _target: Path("/tmp/wrap/python"))
    monkeypatch.setattr(ci_gates, "_run", lambda *_a, **_k: (0, "PASS (0s)"))
    rc, detail = ci_gates.run_barebones_foreign()
    assert rc == ci_gates.PASS_RC
    assert detail.startswith("PASS ")
    assert "aarch64 barebones import" in detail


def test_a_missing_uv_is_still_a_failure_not_a_skip(monkeypatch):
    def boom():
        raise FileNotFoundError("uv")

    monkeypatch.setattr(ci_gates, "uv_version_output", boom)
    rc, detail = ci_gates.run_barebones_foreign()
    assert rc == ci_gates.FAIL_RC
    assert detail.startswith("FAIL ")


def test_a_skip_is_named_in_the_summary_and_is_not_counted_as_a_pass(
    monkeypatch, capsys, _main_env_restored
):
    monkeypatch.setattr(
        ci_gates,
        "run_named",
        lambda _name, **_kw: (ci_gates.SKIP_RC, "SKIP (0s) uv too old"),
    )
    assert ci_gates.main(["--only", "barebones-foreign"]) == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "barebones-foreign" in out
    # The old "all N gate(s) passed" line would have covered a gate that ran
    # nothing. The count must exclude the skip.
    assert "0 of 1 gate(s) passed" in out
    assert "all 1 gate(s) passed" not in out


def test_a_real_failure_still_fails_the_run_even_beside_a_skip(monkeypatch, _main_env_restored):
    def fake(name, **_kwargs):
        if name == "barebones-foreign":
            return ci_gates.SKIP_RC, "SKIP (0s) uv too old"
        return ci_gates.FAIL_RC, "FAIL (1s) boom"

    monkeypatch.setattr(ci_gates, "run_named", fake)
    assert ci_gates.main(["--only", "lock,barebones-foreign"]) == 1

"""#1730 claim A: there is exactly one coverage floor, and it can fail.

The defect: ``pyproject.toml`` declared ``[tool.coverage.report] fail_under =
70`` while ``pytest.ini``'s ``addopts`` passed ``--cov-fail-under=0``. The
command-line flag wins, so the declared 70% applied to nothing -- every run had
a 0% floor. The issue's proof: ``pytest tests/utils`` reported
``TOTAL 69471 66140 5%`` and exited 0.

Two things have to hold, and both are checked here as *behaviour*:

1. No second, contradictory knob exists. The CLI flag is read back out of the
   resolved pytest config (not grepped out of the file text -- a substring grep
   against a config file is the exact defect class that let this ship, see
   ``test_pytest_config_single_source``), and the pyproject key is read
   structurally with ``tomllib``.

2. The one floor that replaced them actually fails. A ratchet is worthless if
   it cannot fail, and the gate it is modelled on had exactly that bug: the old
   ``tsc-ratchet.mjs`` counted only ``error TS####`` lines, so a toolchain that
   never ran produced 0 diagnostics and printed ``PASS``. The tests below are
   the anti-vacuity tripwire: a missing report, a report with no ``totals``, and
   a report that measured zero statements must each be a FAILURE.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "coverage_ratchet.py"


def _load_ratchet():
    spec = importlib.util.spec_from_file_location("coverage_ratchet_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ratchet = _load_ratchet()


# --------------------------------------------------------------------------- #
# 1. one gate, not two
# --------------------------------------------------------------------------- #


def test_no_coverage_floor_is_smuggled_in_through_pytest_addopts(
    request: pytest.FixtureRequest,
) -> None:
    """The resolved run must not carry a coverage floor of its own.

    Read from the running pytest rather than from pytest.ini's text: what
    matters is what the run actually applies, and an ini key that is present
    but inert is indistinguishable from one that is absent by grep alone.

    Why this is the load-bearing assertion for claim A --
    ``pytest_cov/plugin.py`` resolves the floor like this::

        if self.options.cov_fail_under is None and hasattr(cov_config, 'fail_under'):
            self.options.cov_fail_under = cov_config.fail_under

    so ``--cov-fail-under=0`` in addopts set the option to 0, the ``is None``
    guard was False, and ``[tool.coverage.report] fail_under = 70`` was never
    even read. The declared 70% was not overridden so much as skipped.
    """
    if not request.config.pluginmanager.hasplugin("pytest_cov"):
        # Without pytest-cov there is no floor to smuggle; say so rather than
        # passing on an unexamined config.
        pytest.fail("pytest-cov is not installed, so there is no coverage run to gate")

    fail_under = request.config.getoption("cov_fail_under", default=None)
    assert fail_under in (None, 0, 0.0), (
        f"the run applies --cov-fail-under={fail_under!r}. A per-run floor takes "
        f"precedence over the config file's and would override "
        f"scripts/coverage_ratchet.py, which is the ONE authoritative gate. "
        f"pytest tests/utils measures ~5% on purpose (it is not the whole suite) "
        f"and must not fail on that number."
    )


def test_pyproject_declares_no_dead_coverage_floor() -> None:
    """`fail_under` in pyproject is dead config, the way it was dead before.

    Read structurally, so a renamed or nested spelling is still caught and a
    comment mentioning the key is not mistaken for one.
    """
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    report = data.get("tool", {}).get("coverage", {}).get("report", {})
    assert "fail_under" not in report, (
        f"[tool.coverage.report].fail_under={report['fail_under']!r} is a second "
        f"floor that only applies to whatever run happens not to pass a CLI "
        f"override -- i.e. it applied to nothing before, and would contradict the "
        f"ratchet now. The floor lives in scripts/coverage-ratchet-baseline.txt."
    )


# --------------------------------------------------------------------------- #
# 2. the baseline is real
# --------------------------------------------------------------------------- #


def test_a_pinned_baseline_exists_and_is_a_plausible_percentage() -> None:
    baseline_path = SCRIPT.parent / "coverage-ratchet-baseline.txt"
    assert baseline_path.is_file(), (
        f"{baseline_path.name} is missing, so the coverage ratchet has no floor. "
        f"Measure one (pytest tests/ --cov=src/swarm --cov-report=json) and pin it."
    )
    value = ratchet.read_baseline(baseline_path)
    assert 0.0 < value <= 100.0, f"baseline {value} is outside (0, 100]"
    # A baseline of 0 would pass for any measurement, including none. The old
    # effective floor was exactly that.
    assert value > 1.0, (
        f"baseline {value}% gates nothing meaningful; a floor that any run clears "
        f"is the same defect as --cov-fail-under=0"
    )


@pytest.mark.parametrize("raw", ["", "   ", "seventy", "0", "-3", "101", "nan", "inf"])
def test_an_unusable_baseline_is_an_error_not_a_default(tmp_path: Path, raw: str) -> None:
    path = tmp_path / "baseline.txt"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ratchet.RatchetError):
        ratchet.read_baseline(path)


def test_a_missing_baseline_is_an_error_not_zero(tmp_path: Path) -> None:
    with pytest.raises(ratchet.RatchetError):
        ratchet.read_baseline(tmp_path / "nope.txt")


# --------------------------------------------------------------------------- #
# 3. the measurement is read, and a run that measured nothing FAILS
# --------------------------------------------------------------------------- #


def _report(tmp_path: Path, **totals: object) -> Path:
    path = tmp_path / "coverage.json"
    payload: dict[str, object] = {"meta": {"branch_coverage": True}}
    if totals or True:
        payload["totals"] = dict(totals)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_full_run_measurement_is_read(tmp_path: Path) -> None:
    path = _report(tmp_path, percent_covered=61.23, num_statements=69471)
    percent, statements = ratchet.read_measured(path)
    assert percent == pytest.approx(61.23)
    assert statements == 69471


def test_a_report_with_no_totals_is_a_failure(tmp_path: Path) -> None:
    """The tsc-ratchet defect: nothing measured must not read as a pass."""
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    with pytest.raises(ratchet.RatchetError, match="totals"):
        ratchet.read_measured(path)


def test_a_report_that_measured_zero_statements_is_a_failure(tmp_path: Path) -> None:
    """`percent_covered` is 0.0 for an empty measurement.

    Compared against a baseline that reads as a catastrophic drop rather than
    as "the toolchain never ran" -- the same misreading #1730 caught in
    tsc-ratchet.mjs, so it is pinned here explicitly.
    """
    path = _report(tmp_path, percent_covered=0.0, num_statements=0)
    with pytest.raises(ratchet.RatchetError, match="statement"):
        ratchet.read_measured(path)


def test_a_missing_report_is_a_failure(tmp_path: Path) -> None:
    with pytest.raises(ratchet.RatchetError):
        ratchet.read_measured(tmp_path / "never-written.json")


def test_a_truncated_report_is_a_failure(tmp_path: Path) -> None:
    path = tmp_path / "coverage.json"
    path.write_text('{"totals": {"percent_cov', encoding="utf-8")
    with pytest.raises(ratchet.RatchetError):
        ratchet.read_measured(path)


# --------------------------------------------------------------------------- #
# 4. the CLI verdict, end to end
# --------------------------------------------------------------------------- #


def _cli(report: Path, baseline: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--report",
            str(report),
            "--baseline",
            str(baseline),
            *extra,
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_a_drop_below_the_baseline_fails(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("70.00\n", encoding="utf-8")
    result = _cli(_report(tmp_path, percent_covered=69.99, num_statements=69471), baseline)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FAIL" in result.stderr


def test_the_baseline_itself_passes(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("70.00\n", encoding="utf-8")
    result = _cli(_report(tmp_path, percent_covered=70.0, num_statements=69471), baseline)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "at baseline" in result.stdout


def test_a_run_exactly_on_the_baseline_is_reported_as_at_baseline(tmp_path: Path) -> None:
    """"At baseline" has to be reachable, or the ratchet nags to tighten forever.

    The stored baseline has 2 decimals; the measurement has more. Compared raw,
    79.490346 always beat 79.49, so the only reachable verdict was "PASS, go
    tighten" -- and following that advice would never converge.
    """
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("79.49\n", encoding="utf-8")
    result = _cli(
        _report(tmp_path, percent_covered=79.49034605476324, num_statements=75306), baseline
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "at baseline" in result.stdout
    assert "tighten" not in result.stdout


def test_improvement_passes_and_asks_to_tighten(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("70.00\n", encoding="utf-8")
    result = _cli(_report(tmp_path, percent_covered=70.5, num_statements=69471), baseline)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--update" in result.stdout, "an improved run must name the way to ratchet in"


def test_update_creates_a_baseline_that_did_not_exist(tmp_path: Path) -> None:
    """The first-ever run has to work.

    An earlier version of the script read the baseline before branching on
    --update, so pinning the very first number was impossible: the file did not
    exist, the read raised, and the run that was supposed to create it exited 1.
    Every other --update test pre-created the file, so nothing caught it.
    """
    baseline = tmp_path / "coverage-ratchet-baseline.txt"
    assert not baseline.exists()
    report = _report(tmp_path, percent_covered=79.49, num_statements=75306)
    result = _cli(report, baseline, "--update")
    assert result.returncode == 0, result.stdout + result.stderr
    assert baseline.read_text(encoding="utf-8").strip() == "79.49"
    assert "created" in result.stdout
    # And the number it just wrote is one the check accepts.
    assert _cli(report, baseline).returncode == 0


def test_update_writes_the_measured_value(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("70.00\n", encoding="utf-8")
    report = _report(tmp_path, percent_covered=73.456, num_statements=69471)
    result = _cli(report, baseline, "--update")
    assert result.returncode == 0, result.stdout + result.stderr
    assert baseline.read_text(encoding="utf-8").strip() == "73.46"


def test_update_written_baseline_then_passes(tmp_path: Path) -> None:
    """The two-flag path the update is for, checked end to end."""
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("99.00\n", encoding="utf-8")
    report = _report(tmp_path, percent_covered=42.0, num_statements=69471)
    assert _cli(report, baseline).returncode == 1
    assert _cli(report, baseline, "--update").returncode == 0
    assert _cli(report, baseline).returncode == 0


def test_a_nothing_measured_run_exits_nonzero_not_pass(tmp_path: Path) -> None:
    """The whole point: the gate must not be able to report green while blind."""
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("1.00\n", encoding="utf-8")
    empty = _report(tmp_path, percent_covered=0.0, num_statements=0)
    result = _cli(empty, baseline)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "PASS" not in result.stdout
    assert "measured" in result.stderr


def test_a_missing_report_exits_nonzero_not_pass(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("1.00\n", encoding="utf-8")
    result = _cli(tmp_path / "absent.json", baseline)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "PASS" not in result.stdout

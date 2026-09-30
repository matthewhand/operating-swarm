#!/usr/bin/env python3
"""Coverage floor ratchet (issue #1730, claim A).

Why this exists
---------------
``pyproject.toml`` declared ``[tool.coverage.report] fail_under = 70`` while
``pytest.ini``'s ``addopts`` passed ``--cov-fail-under=0``. The command-line
flag wins, so the declared 70% never applied to anything: a reader of
``pyproject.toml`` believed there was a floor and there was a 0% one. Proof
from the issue: ``pytest tests/utils`` reported ``TOTAL ... 5%`` and exited 0.

Both numbers are now GONE, and this script is the only place a coverage floor
is expressed:

* ``pytest.ini`` no longer passes ``--cov-fail-under`` at all, so nothing on a
  developer run can silently override a floor.
* ``pyproject.toml``'s ``[tool.coverage.report]`` no longer carries
  ``fail_under``.

Why not simply set ``fail_under`` to the measured number? Because
``fail_under`` is a single scalar with no notion of "was this a full run?". A
developer running ``pytest tests/utils`` would get a red exit code for a
coverage number that says nothing about the project. That is the same defect as
the one being fixed -- a gate whose number does not mean what a reader thinks it
means -- so the floor is enforced where the full-suite run actually happens.

The contract
------------
The baseline is pinned at the number a full-suite run measures *today* and may
only improve. A run that measures less fails; a run that measures more passes
and tells you to tighten the ratchet.

  # measure and check (what CI does)
  pytest tests/ --cov=src/swarm --cov-report=json      # writes coverage.json
  python scripts/coverage_ratchet.py

  # deliberately move the baseline, so the change shows in review
  python scripts/coverage_ratchet.py --update

Headroom discipline: a change that legitimately lowers coverage (dead code
removed from a measured path, a module moved out of ``src/swarm``) is a real
regression in the measured percentage and must be argued for in review, not
absorbed silently. Raise coverage or, with the reason in the commit body, run
``--update`` and say so in the same message.

Fails closed
------------
A coverage run that measured nothing must never read as a pass. The
``tsc-ratchet`` gate this is modelled on had exactly that bug (#1730): it
counted only ``error TS####`` lines, so a toolchain that never ran produced 0
diagnostics and ``PASS``. Here, a missing report, a report with no ``totals``,
and a report that measured zero statements are all failures that name the
cause. The check for zero statements matters: ``percent_covered`` is ``0.0`` for
an empty measurement, which would otherwise be compared against the baseline
and reported as a catastrophic drop rather than as "nothing was measured".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = REPO_ROOT / "coverage.json"
BASELINE_PATH = Path(__file__).resolve().parent / "coverage-ratchet-baseline.txt"

#: Below this, a "coverage" number is not a measurement of a Python project.
MIN_MEANINGFUL_STATEMENTS = 1

#: The baseline is stored to this many decimals, so the comparison is made at
#: the same precision. Without it the measured value (79.490346...) always
#: compares greater than the stored 79.49, and a run sitting exactly on the
#: baseline could never be reported as "at baseline" -- it would nag to tighten
#: forever, which is how a ratchet gets ignored.
BASELINE_PRECISION = 2


class RatchetError(RuntimeError):
    """The measurement or the baseline is unusable. Always a failure."""


def read_baseline(path: Path = BASELINE_PATH) -> float:
    """The pinned floor, as a percentage. Raises rather than defaulting."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RatchetError(f"coverage-ratchet: cannot read baseline {path.name}: {exc}") from exc
    if not raw:
        raise RatchetError(f"coverage-ratchet: baseline {path.name} is empty")
    try:
        value = float(raw)
    except ValueError as exc:
        raise RatchetError(
            f"coverage-ratchet: baseline {path.name} is not a number: {raw!r}"
        ) from exc
    if not 0.0 < value <= 100.0:
        raise RatchetError(
            f"coverage-ratchet: baseline {path.name}={value} is outside (0, 100]"
        )
    return value


def read_measured(report_path: Path = DEFAULT_REPORT) -> tuple[float, int]:
    """``(percent_covered, num_statements)`` from a coverage JSON report."""
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RatchetError(
            f"coverage-ratchet: cannot read coverage report {report_path.name}: {exc}. "
            f"Produce it with: pytest tests/ --cov=src/swarm --cov-report=json"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RatchetError(
            f"coverage-ratchet: {report_path.name} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RatchetError(f"coverage-ratchet: {report_path.name} is not a coverage report")
    totals = payload.get("totals")
    if not isinstance(totals, dict):
        raise RatchetError(
            f"coverage-ratchet: {report_path.name} has no 'totals' block, so nothing "
            f"was measured. A run that measured nothing is a failure, not a pass."
        )
    percent = totals.get("percent_covered")
    statements = totals.get("num_statements")
    if not isinstance(percent, (int, float)) or isinstance(percent, bool):
        raise RatchetError(
            f"coverage-ratchet: {report_path.name} totals.percent_covered is not a "
            f"number: {percent!r}"
        )
    if not isinstance(statements, int) or isinstance(statements, bool):
        raise RatchetError(
            f"coverage-ratchet: {report_path.name} totals.num_statements is not an "
            f"integer: {statements!r}"
        )
    if statements < MIN_MEANINGFUL_STATEMENTS:
        raise RatchetError(
            f"coverage-ratchet: {report_path.name} measured {statements} statement(s). "
            f"An empty measurement reports 0.0% and must not be read as a pass."
        )
    return float(percent), statements


def update_baseline(measured: float, path: Path = BASELINE_PATH) -> None:
    path.write_text(f"{measured:.{BASELINE_PRECISION}f}\n", encoding="utf-8")


def _at_baseline_precision(value: float) -> float:
    return round(value, BASELINE_PRECISION)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when full-suite coverage falls below the pinned baseline."
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="coverage JSON report (default: %(default)s)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=BASELINE_PATH,
        help="pinned baseline file (default: %(default)s)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="deliberately write the measured value as the new baseline",
    )
    args = parser.parse_args(argv)

    try:
        measured, statements = read_measured(args.report)
        if args.update:
            # --update is how the baseline is CREATED as well as moved, so a
            # missing baseline is not an error here. Reading it first (as an
            # earlier version of this did) meant the first-ever run could never
            # pin a number, which is the one run that has to work.
            previous = None
            try:
                previous = read_baseline(args.baseline)
            except RatchetError:
                previous = None
        else:
            previous = read_baseline(args.baseline)
    except RatchetError as exc:
        # Fail closed, and say why. Never a bare non-zero.
        print(str(exc), file=sys.stderr)
        return 1

    if args.update:
        update_baseline(measured, args.baseline)
        rounded = _at_baseline_precision(measured)
        if previous is None:
            print(
                f"coverage-ratchet: baseline created at {rounded:.2f}% "
                f"({statements} statements measured)"
            )
        else:
            moved = (
                "raised"
                if rounded > previous
                else "lowered"
                if rounded < previous
                else "unchanged"
            )
            print(
                f"coverage-ratchet: baseline {moved} {previous:.2f}% -> {rounded:.2f}% "
                f"({statements} statements measured)"
            )
        return 0

    baseline = _at_baseline_precision(previous)
    measured = _at_baseline_precision(measured)
    assert baseline is not None  # only reachable via the read above
    if measured < baseline:
        print(
            f"coverage-ratchet: FAIL — {measured:.2f}% over {statements} statements, "
            f"baseline {baseline:.2f}%.",
            file=sys.stderr,
        )
        print(
            "Add tests for the new code, or -- and say so in the commit body -- run:\n"
            "  python scripts/coverage_ratchet.py --update",
            file=sys.stderr,
        )
        return 1

    if measured > baseline:
        print(
            f"coverage-ratchet: PASS — {measured:.2f}% over {statements} statements, "
            f"baseline {baseline:.2f}%. "
            f'Run "python scripts/coverage_ratchet.py --update" to tighten the ratchet.'
        )
        return 0

    print(
        f"coverage-ratchet: PASS — {measured:.2f}% over {statements} statements, "
        f"at baseline {baseline:.2f}%."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

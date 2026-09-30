#!/usr/bin/env python
"""Parallel stress-test harness for the Operating Swarm test suite.

Ported from archive/local-main-2025-04 (swarm_nuclear_scale.py). Spawns many
concurrent, staggered pytest runs of the same target to flush out flaky tests,
shared-state bugs, and resource contention. Uses only the stdlib plus pytest.

Usage:
    python scripts/stress_test_suite.py [pytest-target ...]

The pytest target defaults to STRESS_TEST_TARGET (env var) or tests/unit.
Per-process logs land in swarm_stress_logs/ and an aggregate JSON report is
written to swarm_stress_final_report.json. Exit code is non-zero if any run
fails.
"""
import json
import multiprocessing
import os
import random
import subprocess
import sys
import time

NUM_PROCESSES = max(8, multiprocessing.cpu_count() * 2)
LOG_DIR = "swarm_stress_logs"
REPORT_FILE = "swarm_stress_final_report.json"
DEFAULT_TARGET = os.environ.get("STRESS_TEST_TARGET", "tests/unit")

os.makedirs(LOG_DIR, exist_ok=True)


def _pytest_args():
    targets = sys.argv[1:] or [DEFAULT_TARGET]
    return [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-cov", *targets]


def run_test_instance(proc_id):
    """Run one isolated pytest instance, capturing output, with staggered start."""
    # Staggered launch: random delay between 0.5 and 3 seconds
    delay = random.uniform(0.5, 3.0)
    time.sleep(delay)
    log_path = os.path.join(LOG_DIR, f"swarm_{proc_id}.log")
    try:
        result = subprocess.run(
            _pytest_args(),
            capture_output=True, text=True, timeout=600
        )
        with open(log_path, "w") as f:
            f.write(result.stdout)
            f.write("\n--- STDERR ---\n")
            f.write(result.stderr)
        return {"proc_id": proc_id, "exit_code": result.returncode, "log": log_path}
    except Exception as e:
        with open(log_path, "w") as f:
            f.write(f"Exception: {e}\n")
        return {"proc_id": proc_id, "exit_code": 99, "log": log_path}


def main():
    print(f"\nLaunching staggered stress swarm: {NUM_PROCESSES} parallel pytest runs of {sys.argv[1:] or [DEFAULT_TARGET]}\n")
    with multiprocessing.Pool(NUM_PROCESSES) as pool:
        results = pool.map(run_test_instance, range(NUM_PROCESSES))
    # Aggregate results
    all_logs = []
    all_green = True
    for res in results:
        with open(res["log"]) as f:
            log_content = f.read()
        all_logs.append({"proc_id": res["proc_id"], "exit_code": res["exit_code"], "log": log_content})
        if res["exit_code"] != 0:
            all_green = False
    with open(REPORT_FILE, "w") as f:
        json.dump(all_logs, f, indent=2)
    if all_green:
        print("\nAll stress runs passed.\n")
    else:
        print(f"\nSome stress runs FAILED. Check logs in {LOG_DIR}/ and the report file.\n")
    print(f"See {REPORT_FILE} for full results.")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Run Issue #136 kind-chat proofs (cheap local backends, no secrets).

Prints pytest output only. Does not echo API tokens, cookies, or .env values.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "tests/api/test_issue136_kind_chat_e2e.py",
    "tests/core/test_agent_kind.py",
    "tests/unit/test_issue136_csrf_bearer.py",
]


def main() -> int:
    env = os.environ.copy()
    env.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    env.setdefault("SWARM_TEST_MODE", "1")
    # Never inherit a real operator token into the proof process logs.
    for key in (
        "API_AUTH_TOKEN",
        "API_AUTH_TOKENS",
        "SWARM_API_KEY",
        "SWARM_API_KEYS",
        "OPENAI_API_KEY",
    ):
        env.pop(key, None)
    cmd = [sys.executable, "-m", "pytest", *TESTS, "-q"]
    print("prove_kind_chat_e2e:", " ".join(TESTS), flush=True)
    print("backends: SWARM_TEST_MODE + local python echo CLI (no paid providers)", flush=True)
    return subprocess.call(cmd, cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())

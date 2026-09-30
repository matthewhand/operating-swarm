#!/usr/bin/env python3
"""Grep-style lint: POSIX process-group calls stay in swarm.core.proc (#1438).

Direct ``os.getpgid``, ``os.killpg``, and ``os.setsid`` in product code crash
native Windows. Spawn and tree-kill go through ``swarm.core.proc``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOW = "src/swarm/core/proc.py"

PATTERNS = (
    re.compile(r"\bos\s*\.\s*(getpgid|killpg|setsid)\b"),
    re.compile(r"""getattr\(\s*os\s*,\s*['"](getpgid|killpg|setsid)['"]"""),
    re.compile(r"\bfrom\s+os\s+import\b[^\n]*\b(getpgid|killpg|setsid)\b"),
)


def violations(root: Path | None = None) -> list[str]:
    base = root or ROOT
    hits: list[str] = []
    src = base / "src"
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(base).as_posix()
        if rel == ALLOW:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(pat.search(line) for pat in PATTERNS):
                hits.append(f"{rel}:{lineno}: {line.strip()}")
    return hits


def main() -> int:
    hits = violations()
    if hits:
        print(
            "direct POSIX process-group calls (use swarm.core.proc):",
            file=sys.stderr,
        )
        for hit in hits:
            print(hit, file=sys.stderr)
        return 1
    print(f"ok: no direct os.getpgid/os.killpg/os.setsid outside {ALLOW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

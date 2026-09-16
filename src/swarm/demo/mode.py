"""REQ-882 / #279: public demo flags. No LLM, no local shells."""

from __future__ import annotations

import os


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def is_demo_mode() -> bool:
    """True when ``SWARM_DEMO_MODE`` is set. Implies anonymous preview."""
    return _flag("SWARM_DEMO_MODE")


def demo_stream_delay_s() -> float:
    """Per-chunk sleep. ``0`` under pytest unless ``SWARM_DEMO_STREAM_DELAY_MS`` is set."""
    raw = os.getenv("SWARM_DEMO_STREAM_DELAY_MS")
    if raw is None or not str(raw).strip():
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return 0.0
        return 0.04
    try:
        ms = float(raw)
    except ValueError:
        return 0.0
    return max(0.0, ms / 1000.0)

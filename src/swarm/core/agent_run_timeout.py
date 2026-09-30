"""#1264 — configurable timeout for openai-agents LLM runs.

Agent Router / specialist / coordinator paths wrap ``Runner.run`` in
``asyncio.wait_for``. A hardcoded 25s killed slow gateway routes (the
``orchestration`` profile is reported taking 300s+), so every designed/API
seat failed while the model was still thinking.

Resolution order:
1. ``SWARM_AGENT_LLM_TIMEOUT`` environment variable (seconds).
2. ``settings.agent_llm_timeout_s`` in ``swarm_config.json``.
3. :data:`DEFAULT_AGENT_RUN_TIMEOUT_S` (600s).
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_AGENT_RUN_TIMEOUT_S = 600.0


def agent_run_timeout(config: dict[str, Any] | None = None) -> float:
    """Seconds to allow one openai-agents LLM run. Never returns <= 0."""
    raw = str(os.environ.get("SWARM_AGENT_LLM_TIMEOUT", "") or "").strip()
    if not raw and isinstance(config, dict):
        settings = config.get("settings")
        if isinstance(settings, dict):
            raw = str(settings.get("agent_llm_timeout_s") or "").strip()
    try:
        value = float(raw)
        if value > 0:
            return value
    except (TypeError, ValueError):
        pass
    return DEFAULT_AGENT_RUN_TIMEOUT_S


__all__ = ["DEFAULT_AGENT_RUN_TIMEOUT_S", "agent_run_timeout"]

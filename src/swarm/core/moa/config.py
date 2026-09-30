"""MoA config helpers — default block + merge into swarm_config.json.

``moa`` block schema (known keys consumed by blueprints / resolve_moa_preset)
----------------------------------------------------------------------------
Top-level keys (panel / consensus only)::

    backend          fake | grok | acpx
    participants     list of read-only seat names
    permission       approve-reads | deny-all  (never approve-all)
    default_timeout  seconds (per participant)
    presets          named overlays; see below
    fake_responses   optional dict (usually under a ``ci`` preset)

Preset overlay keys (same panel fields; preset values win on resolve)::

    backend, participants, permission, fake_responses, timeout

Team / specialist mode is **not** a config or preset key. Select it via:

* CLI: ``swarm-cli moa --team --workdir … [--team-tasks …]``
* Models: ``hybrid_moa`` (one implementer write) or ``moa_orchestrator``
  (``params.tasks`` for purpose specialists)
* Python: ``run_moa_then_team`` / ``run_moa_consensus``

Do not invent preset fields for team; tasks stay on the request/CLI surface.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

# Default moa block for moa-init. Presets name panel/consensus settings only
# (backend + seats [+ fake_responses for CI]). Team mode is CLI/model-path, not
# a preset field — see module docstring.
DEFAULT_MOA_BLOCK: dict[str, Any] = {
    "backend": "grok",
    "participants": ["analyst", "critic"],
    "permission": "approve-reads",
    "default_timeout": 300,
    "presets": {
        # Live multi-seat Grok panel (same as top-level defaults).
        "default": {
            "backend": "grok",
            "participants": ["analyst", "critic"],
        },
        # Deterministic panel for CI / Open WebUI smoke (no live CLI).
        "ci": {
            "backend": "fake",
            "participants": ["analyst", "critic"],
            "fake_responses": {
                "analyst": (
                    '{"claim":"Prefer a simple safe option","confidence":0.85}'
                ),
                "critic": (
                    '{"claim":"Prefer a simple safe option with monitoring",'
                    '"confidence":0.8}'
                ),
            },
        },
        # Single Grok seat (cheaper live consensus).
        "single-grok": {
            "backend": "grok",
            "participants": ["grok"],
        },
    },
}

# Open WebUI / OpenAI-compatible client preset (document + export helper).
OPENWEBUI_MOA_CONNECTION: dict[str, Any] = {
    "name": "Operating Swarm MoA",
    "model": "moa",
    "base_url": "http://localhost:8000/v1",
    "api_key": "${SWARM_API_KEY}",
    "params": {
        "backend": "grok",
        "participants": ["analyst", "critic"],
    },
    "notes": (
        "Point Open WebUI (or any OpenAI client) at the swarm-api base URL. "
        "model id 'moa' (aliases: mixture_of_agents, cli_fusion, cli_ensemble). "
        "Use params.backend=fake + fake_responses for CI."
    ),
}


def merge_moa_config(
    existing: dict[str, Any] | None,
    *,
    overwrite: bool = False,
    backend: str | None = None,
    participants: list[str] | None = None,
) -> dict[str, Any]:
    """Return a full config dict with a ``moa`` block merged in."""
    cfg = deepcopy(existing) if existing else {}
    if "moa" in cfg and not overwrite:
        # Still allow field-level defaults for missing keys
        moa = dict(cfg["moa"])
        for k, v in DEFAULT_MOA_BLOCK.items():
            moa.setdefault(k, deepcopy(v))
    else:
        moa = deepcopy(DEFAULT_MOA_BLOCK)
    if backend:
        moa["backend"] = backend
    if participants:
        moa["participants"] = list(participants)
    cfg["moa"] = moa
    cfg.setdefault("llm", cfg.get("llm") or {})
    return cfg


def write_moa_config(
    path: Path,
    *,
    overwrite: bool = False,
    backend: str | None = None,
    participants: list[str] | None = None,
) -> Path:
    """Load-or-create swarm_config.json at ``path`` and merge MoA defaults."""
    path = Path(path)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except json.JSONDecodeError:
            existing = {}
    cfg = merge_moa_config(
        existing, overwrite=overwrite, backend=backend, participants=participants
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return path


def resolve_moa_preset(
    moa_cfg: dict[str, Any] | None, preset: str | None
) -> dict[str, Any]:
    """Flatten a named preset onto the moa config (preset fields win).

    Presets are panel overlays only (``backend``, ``participants``,
    ``fake_responses``, etc.). Team / specialist selection is not resolved
    here — use CLI ``--team`` or models ``hybrid_moa`` / ``moa_orchestrator``.
    """
    base = dict(moa_cfg or {})
    if not preset:
        return base
    presets = base.get("presets") or {}
    if preset not in presets:
        raise KeyError(f"unknown moa preset {preset!r}; known: {sorted(presets)}")
    overlay = dict(presets[preset] or {})
    out = {**base, **overlay}
    return out

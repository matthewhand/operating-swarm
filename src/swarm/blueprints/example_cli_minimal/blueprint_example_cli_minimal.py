"""example_cli_minimal — the smallest CLI-kind recipe, with the provider binding.

Read this file top-to-bottom; it is a worked tour of the CLI extension
point (REQ-920 / #539; SDK docs: REQ-921 / #540).

Base: CliKindBase (``swarm.core.kind_bases``). Why: the transcript lives
in a **host CLI process** (claude, codex, gemini, omp, …), not in Open
Swarm. A CLI recipe is an *adapter*: it selects which CLI and which
model/profile to invoke, keeps the session native, and optionally re-renders
output for the webui. openai-agents handoff edges DO NOT apply inside the
CLI process — if you need swarm-side graphs, that is an API recipe.

Hooks / attributes used here, and why:
    metadata                 discovery + catalog (see example_api_minimal).
    create_starting_agent    a CLI recipe does not need one — the kind
                             base's default run() shells out to the CLI
                             for the turn. Define it only when you opt
                             into an openai-agents *wrap* of the CLI.

What this example deliberately does NOT do:
    - no custom run(): the CliKindBase default handles session resume and
      the native print-mode invocation.
    - no cli_slash_commands or cli_compact declarations: those are
      provider-verified contracts (REQ-910 / #641) — a recipe only
      declares what the CLI actually supports, never aspirational
      commands. See omp's status-line work for the worked version.

Runnability: needs the referenced CLI installed and authenticated on the
host (``swarm config`` → cli_agents). Without it, the seat fails with a
friendly config error at run time — it still LOADS and is INSPECTABLE
with zero credentials, which is the contract for every example recipe.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.core.kind_bases import CliKindBase

logger = logging.getLogger(__name__)


class ExampleCliMinimalBlueprint(CliKindBase):
    """Smallest CLI recipe: bind one host CLI, keep the session native."""

    kind = CliKindBase.kind  # stamped by the base; restated for readers

    metadata: ClassVar[dict[str, Any]] = {
        "name": "example_cli_minimal",
        "title": "Example: minimal CLI recipe",
        "description": (
            "Teaching recipe: the smallest CliKindBase blueprint — binds one "
            "configured host CLI and keeps the session native. Read its "
            "source before copying it."
        ),
        "version": "1.0.0",
        "author": "Open Swarm Team",
        "tags": ["example", "teaching", "cli", "minimal"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    #: The provider binding — "which CLI, which model". This is the line a
    #: reader is here for. The id must match a cli_agents entry in swarm
    #: config (or a discovered CLI); the model/profile pass-through is
    #: forwarded per request by the API layer's params.
    #: HOW TO BIND A DIFFERENT CLI: copy this class, change DEFAULT_CLI_ID
    #: (e.g. "claude"), and adjust DEFAULT_MODEL to a model that CLI serves.
    DEFAULT_CLI_ID: ClassVar[str] = "omp"
    DEFAULT_MODEL: ClassVar[str] = "default"

    # Capability axes are inherited from CliKindBase (#551): attach/plugins/
    # routines are off with honest reasons, compact needs a default API
    # profile or a provider cli_compact hook. A recipe overrides a SINGLE
    # axis only when it genuinely changes the answer, e.g.:
    #     attach = {"enabled": True, "reason": "omp print-mode accepts files"}
    # (a dict with `enabled` + optional `reason` — see seat_capability()).

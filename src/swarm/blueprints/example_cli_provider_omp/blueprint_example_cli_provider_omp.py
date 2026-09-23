"""example_cli_provider_omp — the omp seat as the worked provider example.

Read this file top-to-bottom; it teaches the *provider surface* axis
(REQ-920 / #539; SDK docs: REQ-921 / #540): the provider-specific extras a
real CLI seat can declare beyond the minimal binding.

Base: CliKindBase. omp is the worked instance because it exercises the
most of the CLI contract; opencode / qwen / pi follow the IDENTICAL
pattern with their own ids — copy this file, change the binding, delete
the surface bits that CLI does not actually support (an example that
declares surface the provider lacks is worse than no example).

Provider surface taught here:
    1. session policy     — omp sessions persist provider-side; the seat
       resumes rather than restarting (the "started a new session" bug
       class, #640's lesson). Session handling is the kind base's job;
       a provider recipe only declares policy flags it needs.
    2. status line        — REQ-843: the composer can render an
       omp-inspired status line; the provider recipe opts in via params
       (status_line_preset), it does not reimplement rendering.
    3. slash commands     — declared via CliSlashCommand on
       cli_slash_commands, each with `available` reflecting what
       print-mode actually supports (REQ-910 / #641). The webui derives
       its slash popup from the published catalog — never hardcoded.

What this example deliberately does NOT do:
    - no invented slash commands: every declaration must be verified
      against the CLI's real behaviour; aspirational commands grey out
      with unavailable_reason at best and mislead at worst.
    - no custom run(): session resume + invocation stay in the kind base.

Runnability: needs `omp` installed and authenticated on the host
(``swarm config`` → cli_agents). Without it the seat fails with a
friendly config error — it still LOADS and is INSPECTABLE with zero
credentials, which is the contract for every example recipe.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.core.kind_bases import CliKindBase, CliSlashCommand

logger = logging.getLogger(__name__)


class ExampleCliProviderOmpBlueprint(CliKindBase):
    """Provider example: omp with its session/status/slash surface shown."""

    kind = CliKindBase.kind  # stamped by the base; restated for readers

    metadata: ClassVar[dict[str, Any]] = {
        "name": "example_cli_provider_omp",
        "title": "Example: provider CLI surface (omp)",
        "description": (
            "Teaching recipe: the provider-specific surface of a real CLI "
            "seat — session resume policy, status-line opt-in, and "
            "honestly-declared slash commands. Read its source before "
            "copying it."
        ),
        "version": "1.0.0",
        "author": "Open Swarm Team",
        "tags": ["example", "teaching", "cli", "provider", "omp"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    #: The provider binding (full tour in example_cli_minimal).
    DEFAULT_CLI_ID: ClassVar[str] = "omp"

    #: Status-line opt-in (REQ-843). "ascii" is the portable preset; the
    #: webui renders it from params — this file contains no ANSI art.
    STATUS_LINE_PRESET: ClassVar[str] = "ascii"

    #: Slash commands, declared honestly (REQ-910 / #641). The shape is the
    #: lesson: name + description + `available` per command. An unavailable
    #: command still declares itself so the popup can explain WHY it is
    #: greyed out instead of hiding it.
    cli_slash_commands: ClassVar[dict[str, CliSlashCommand]] = {
        "help": CliSlashCommand(
            name="help",
            description="Show the provider's own help.",
        ),
        # Example of an honest NOT-available declaration (keep the pattern;
        # only declare what your CLI actually supports):
        # "compress": CliSlashCommand(
        #     name="compress",
        #     description="Compress the session transcript.",
        #     available=False,
        #     unavailable_reason="omp print-mode cannot compress a resumed session",
        # ),
    }

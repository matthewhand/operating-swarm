"""example_cli_provider_agy — a provider-locked CLI recipe (Gemini-only).

Read this file top-to-bottom; it teaches the *provider-specific* CLI axis
(REQ-920 / #539; SDK docs: REQ-921 / #540): some host CLIs cannot use every
backend the platform offers, and a good recipe says so out loud.

Base: CliKindBase. Why this one exists: `agy` (the Gemini CLI) speaks
Gemini only. The platform's shared LiteLLM `orchestration` backend — the
free-window pool every other CLI can ride — is NOT reachable from agy, so
an agy recipe must never advertise orchestration, must not fall back to
it silently, and should document the exclusion where a reader will trip
over it: here.

The general lesson (the class of constraint, not just agy):
    A provider-locked CLI recipe declares:
      1. the lock         — which backend class it CANNOT use, in writing;
      2. the real backend — the provider's own auth (agy's Gemini login);
      3. the honest error — what the user sees when the provider is
         unauthenticated (a friendly hint, never raw JSON).

What this example deliberately does NOT do:
    - no silent provider fallback. A locked recipe that "falls back" to a
      different backend is lying about which brain answered.
    - no orchestration/LiteLLM wiring of any kind.

Runnability: needs `agy` installed and Gemini-authenticated on the host.
Without it the seat fails with the friendly config error — it still LOADS
and is INSPECTABLE with zero credentials, which is the contract for every
example recipe.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.core.kind_bases import CliKindBase

logger = logging.getLogger(__name__)


class ExampleCliProviderAgyBlueprint(CliKindBase):
    """Provider-locked CLI recipe: agy rides Gemini, never orchestration."""

    kind = CliKindBase.kind  # stamped by the base; restated for readers

    metadata: ClassVar[dict[str, Any]] = {
        "name": "example_cli_provider_agy",
        "title": "Example: provider-locked CLI (agy / Gemini-only)",
        "description": (
            "Teaching recipe: a CLI recipe locked to its provider's own "
            "backend. agy speaks Gemini only and cannot target the shared "
            "LiteLLM orchestration pool — documented here so the exclusion "
            "is visible before you copy the pattern."
        ),
        "version": "1.0.0",
        "author": "Open Swarm Team",
        "tags": ["example", "teaching", "cli", "provider", "agy", "gemini"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    #: THE LOCK, in writing. Docstring + metadata + this constant all say
    #: the same thing so a reader cannot miss it.
    PROVIDER_LOCK: ClassVar[str] = (
        "Gemini-only: this CLI cannot target LiteLLM orchestration. "
        "Schedule its work outside free orchestration windows."
    )

    #: The provider binding (see example_cli_minimal for the full tour).
    DEFAULT_CLI_ID: ClassVar[str] = "agy"
    DEFAULT_MODEL: ClassVar[str] = "gemini"

    # Capability note: compaction via a default API profile is exactly the
    # kind of thing a locked provider must re-think — an API-side summarizer
    # would produce a summary a Gemini-only CLI cannot itself continue from
    # in its own session format. Leave `compact` off unless you implement a
    # provider-native cli_compact for the locked CLI.

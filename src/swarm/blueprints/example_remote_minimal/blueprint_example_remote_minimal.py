"""example_remote_minimal — the smallest Remote-kind recipe (one harness).

Read this file top-to-bottom; it is a worked tour of the remote extension
point (REQ-920 / #539; SDK docs: REQ-921 / #540).

Base: RemoteKindBase (``swarm.core.kind_bases``). Why: the transcript and
the brain live on a REMOTE harness (OpenMausBot, Hermes, Rakazo, Herdr,
nested swarm, TrueForge, …). Per ADR-011 / REQ-203 these are all
implementations of ONE remote harness kind — Open Swarm sits in front and
consults them; it never impersonates them.

Hooks / helpers used here, and why:
    metadata                    discovery + catalog.
    swarm.core.remotes          the persisted-remote registry + HTTP ops
                                (health / list / send). A remote recipe is
                                a thin, honest wrapper over these — do not
                                hand-roll HTTP against a harness.

What this example deliberately does NOT do:
    - no custom run(): the RemoteKindBase default yields the turn against
      the bound remote using the registry entry below. Override run() only
      for multi-step remote workflows (see remote_harness for the
      deterministic-grammar worked version).
    - no credentials: connection details come from the remotes registry
      (settings → Remotes). This file never contains a host, token, or
      key — sanitization bans literals like that in tracked files, and the
      registry is the operator's single source of truth.

Runnability: needs the named remote configured and reachable. Without it
the seat reports the remote as DOWN honestly (never a fake answer) — it
still LOADS and is INSPECTABLE with zero credentials, which is the
contract for every example recipe.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.core.kind_bases import RemoteKindBase

logger = logging.getLogger(__name__)


class ExampleRemoteMinimalBlueprint(RemoteKindBase):
    """Smallest remote recipe: bind one registered harness, stay honest."""

    kind = RemoteKindBase.kind  # stamped by the base; restated for readers

    metadata: ClassVar[dict[str, Any]] = {
        "name": "example_remote_minimal",
        "title": "Example: minimal remote recipe",
        "description": (
            "Teaching recipe: the smallest RemoteKindBase blueprint — binds "
            "one configured remote harness (health / list / send) and stays "
            "honest when it is DOWN. Read its source before copying it."
        ),
        "version": "1.0.0",
        "author": "Open Swarm Team",
        "tags": ["example", "teaching", "remote", "minimal"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    #: The harness binding — the remote id in the Remotes registry
    #: (settings → Remotes, persisted by swarm.core.remotes). Point this at
    #: any registered harness id; the seat is reusable per registry entry.
    REMOTE_ID: ClassVar[str] = "example-remote"

    #: What this seat tells the operator when the remote is not configured.
    #: Honest, actionable, and never a dump of raw JSON (#663's friendly
    #: remote errors apply here too).
    CONFIG_ERROR_HINT: ClassVar[str] = (
        "Remote 'example-remote' is not configured yet. Add it under "
        "Settings → Remotes, then re-send."
    )

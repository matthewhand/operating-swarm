"""Agent Router blueprint package.

``AgentRouterBlueprint`` is re-exported **lazily** (PEP 562) instead of at
import time. Blueprint discovery does not import this package the normal way:
``swarm/core/blueprint_discovery.py`` builds a spec for
``blueprint_agent_router.py`` by file path, registers the *empty* module in
``sys.modules`` **before** executing it, and only then walks its imports. An
eager re-export here closed that loop::

    discover_blueprints()
      -> sys.modules["swarm.blueprints.agent_router.blueprint_agent_router"] = <empty>
      -> exec: blueprint_agent_router.py:31
               from swarm.blueprints.agent_router.engines import RouterEnginesMixin
             -> Python imports the parent package (this file)
                  -> from ...blueprint_agent_router import AgentRouterBlueprint
                       -> sys.modules hit on the half-built module: name not bound
                          -> ImportError: cannot import name 'AgentRouterBlueprint'

Discovery catches that, logs an error, drops the id from the map and moves on,
so ``agent_router`` silently vanished from the registry — and every seat that
resolves through it (designer personality / swarm / remote designs, via
``resolve_chat_blueprint_id``) then failed its turn with
``blueprint '<seat>' was not found``. Whether it reproduced depended on whether
something had already imported this package: ``import swarm.urls`` before
discovery succeeded, discovery first did not.

Deferring the attribute lookup makes importing the package side-effect free, so
the cycle cannot form in any import order. ``from swarm.blueprints.agent_router
import AgentRouterBlueprint`` still resolves, via ``__getattr__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only, never executed at runtime
    from swarm.blueprints.agent_router.blueprint_agent_router import (
        AgentRouterBlueprint,
    )

__all__ = ["AgentRouterBlueprint"]


def __getattr__(name: str) -> Any:
    if name != "AgentRouterBlueprint":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from swarm.blueprints.agent_router.blueprint_agent_router import (
        AgentRouterBlueprint,
    )

    return AgentRouterBlueprint


def __dir__() -> list[str]:
    return sorted(__all__)

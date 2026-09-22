"""#812 — adapter registry: kind → adapter class, with duplicate guard."""

from __future__ import annotations

from typing import Any, Type

from swarm.core.remotes import RemoteSpec
from swarm.remotes.base import RemoteAdapter

REMOTE_ADAPTER_REGISTRY: dict[str, Type[RemoteAdapter]] = {}


def register_remote_adapter(kind: str):
    """Class decorator: register an adapter under its remote kind."""

    def _wrap(cls: Type[RemoteAdapter]) -> Type[RemoteAdapter]:
        if kind in REMOTE_ADAPTER_REGISTRY:
            raise ValueError(f"remote adapter kind '{kind}' already registered")
        cls.kind = kind
        REMOTE_ADAPTER_REGISTRY[kind] = cls
        return cls

    return _wrap


def create_remote_adapter(
    spec: RemoteSpec, config: dict[str, Any] | None = None
) -> RemoteAdapter | None:
    """Build the adapter for ``spec.kind``; None for not-yet-migrated kinds."""
    from swarm.core.remotes import kind_of_instance

    kind = (spec.kind or kind_of_instance(spec.id, config) or "").strip().lower()
    cls = REMOTE_ADAPTER_REGISTRY.get(kind)
    if cls is None:
        return None
    return cls(spec, config)


# Slice 1 migrations — importing registers them. Later slices append their
# module here (and nowhere else has to change).
from swarm.remotes import letta, trueforge  # noqa: E402,F401  (registration)

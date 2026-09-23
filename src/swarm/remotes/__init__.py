"""#812 — polymorphic remote adapters (strangler slice 1).

``swarm.core.remotes`` remains the single source of truth for config
persistence and the legacy implementations; this package layers a registry
of per-harness adapters over it so ``operate()`` stops growing if/elif
branches. Each adapter forwards to the exact implementation the existing
per-harness suites pin — behavior unchanged, dispatch polymorphic.
"""


# #857: public SDK surface — adapters + registry; persistence stays in
# ``swarm.core.remotes``.
__all__ = [
    "RemoteAdapter",
    "create_remote_adapter",
    "register_remote_adapter",
]

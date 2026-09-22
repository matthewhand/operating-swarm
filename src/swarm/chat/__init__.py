"""#855 — swarm.chat package (consumers.py modularisation).

Slice 1 moved the module-level helpers (``helpers``); slice 2 moved cohesive
method clusters of ``DjangoChatConsumer`` into mixin classes that the kernel
class MRO-merges (advice pipeline, conversation persistence, stub responders).
The consumer class itself stays in :mod:`swarm.consumers` — the hot turn path
never leaves the kernel.
"""

__all__ = ["advice_mixin", "conversations_mixin", "helpers", "stubs_mixin"]

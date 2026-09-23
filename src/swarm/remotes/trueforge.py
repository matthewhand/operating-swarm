"""#812 — TrueForge adapter (strangler slice 1).

Forwards to the legacy implementations the ``test_trueforge_remote.py``
suite (47 tests) pins. Behavior unchanged; ``operate()`` now routes
trueforge list/send/routines through this adapter instead of the if/elif
chain.
"""

from __future__ import annotations

from typing import Any

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("trueforge")
class TrueForgeAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._trueforge_list(self.spec, timeout)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._trueforge_send(
            self.spec, prompt, target, timeout, session_id=session_id
        )

    def routines(self, timeout: float) -> OperateResult:
        from swarm.core import remotes

        return remotes._trueforge_routines(self.spec, timeout)

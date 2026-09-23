"""#812 — Hermes adapter (slice 2). Nous Hermes run dispatch + job polling.
List takes no query in the legacy impl; send is session-resumable.
"""

from __future__ import annotations

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("hermes")
class HermesAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._hermes_list(self.spec, timeout)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._hermes_send(
            self.spec, prompt, timeout, session_id=session_id
        )

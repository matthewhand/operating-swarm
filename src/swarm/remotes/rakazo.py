"""#812 — Rakazo adapter (slice 2). Simple list/send pair."""

from __future__ import annotations

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("rakazo")
class RakazoAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._rakazo_list(self.spec, timeout)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._rakazo_send(self.spec, prompt, target, timeout)

"""#1365 — Tencent Octop adapter.

One remote boundary. Octop AgentTeams are not OS teams; list/send forward
to the HTTP/WebSocket impl.
"""

from __future__ import annotations

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("octop")
class OctopAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._octop_list(self.spec, timeout, query=query)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._octop_send(
            self.spec, prompt, timeout, session_id=session_id, target=target
        )

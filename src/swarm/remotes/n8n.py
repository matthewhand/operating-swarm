"""#812 — n8n adapter (slice 2). Workflow list + execution send with the
legacy short-timeout floor (``_N8N_SEND_TIMEOUT_S``).
"""

from __future__ import annotations

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("n8n")
class N8nAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._n8n_list(self.spec, timeout, query=query)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        send_timeout = timeout if timeout >= 30 else remotes._N8N_SEND_TIMEOUT_S
        return remotes._n8n_send(
            self.spec, prompt, send_timeout, session_id=session_id, target=target
        )

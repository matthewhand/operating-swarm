"""#812 — AnythingLLM adapter (slice 2). Workspace/thread list + send with
the legacy short-timeout floor (``_ANYTHINGLLM_SEND_TIMEOUT_S``).
"""

from __future__ import annotations

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("anythingllm")
class AnythingLLMAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._anythingllm_list(self.spec, timeout, query=query)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        send_timeout = timeout if timeout >= 30 else remotes._ANYTHINGLLM_SEND_TIMEOUT_S
        return remotes._anythingllm_send(
            self.spec, prompt, send_timeout, session_id=session_id, target=target
        )

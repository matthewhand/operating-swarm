"""#812 — Open WebUI adapter (slice 2). Chat-completions streaming harness;
impls live in :mod:`swarm.core.openwebui_remote` with its own send-timeout
helper.
"""

from __future__ import annotations

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("openwebui")
class OpenWebUIAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core.openwebui_remote import openwebui_list

        return openwebui_list(self.spec, timeout, query=query)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core.openwebui_remote import openwebui_send, send_timeout

        return openwebui_send(
            self.spec,
            prompt,
            send_timeout(timeout),
            session_id=session_id,
            target=target,
        )

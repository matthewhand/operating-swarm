"""#812 — OpenMousBot adapter (slice 2). Simple list/send pair; the legacy
chain passed target positionally between the two.
"""

from __future__ import annotations

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("omb")
class OmbAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._omb_list(self.spec, timeout)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._omb_send(self.spec, prompt, target, timeout)

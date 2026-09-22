"""#812 — Letta adapter (strangler slice 1).

Forwards to the legacy implementations the ``test_letta_remote.py`` suite
pins, preserving the short-timeout floor (``_LETTA_SEND_TIMEOUT_S``) the
legacy chain applies before a real Letta turn is allowed to run long.
"""

from __future__ import annotations

from typing import Any

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("letta")
class LettaAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._letta_list(self.spec, timeout, query=query)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        send_timeout = timeout if timeout >= 30 else remotes._LETTA_SEND_TIMEOUT_S
        return remotes._letta_send(
            self.spec, prompt, send_timeout, session_id=session_id, target=target
        )

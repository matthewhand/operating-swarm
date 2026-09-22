"""#812 — Herdr adapter (slice 2). CLI/SSH multiplexer: pane list, send,
interrogate. Forwards to the legacy impls the herdr suites pin; ``config``
stays threaded because Herdr resolves its transport (local vs SSH) from it.
"""

from __future__ import annotations

from typing import Any

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("herdr")
class HerdrAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._herdr_list(self.spec, timeout, self.config)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._herdr_send(self.spec, prompt, target, timeout, self.config)

    def interrogate(
        self,
        target: str,
        timeout: float,
        config: dict[str, Any] | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._herdr_interrogate(
            self.spec, target, timeout, self.config if config is None else config
        )

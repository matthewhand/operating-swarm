"""#812 — Swarm-remote adapter (slice 2). Remote swarm-to-swarm list/send."""

from __future__ import annotations

from typing import Any

from swarm.core.remotes import HealthResult, OperateResult
from swarm.core.swarm_peer import peer_version_warning, version_string
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("swarm")
class SwarmAdapter(RemoteAdapter):
    def health(self, timeout: float, config: dict[str, Any] | None = None) -> HealthResult:
        """Add an advisory compatibility warning to a successful peer probe."""
        result = super().health(timeout, config)
        if result.ok:
            from swarm.core.app_version import get_app_version

            warning = peer_version_warning(version_string(result.version), get_app_version())
            if warning:
                result.warning = warning
                result.detail = f"{result.detail} · {warning}" if result.detail else warning
        return result

    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._swarm_list(self.spec, timeout)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._swarm_send(self.spec, prompt, target, timeout, session_id=session_id)

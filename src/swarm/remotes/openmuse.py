"""OpenMuse adapter — one OpenMuse task per OS remote session.

``operate()`` dispatches every declared kind through this registry, so the
adapter is what makes list / send / control reachable; the wire behavior
lives in :mod:`swarm.core.remote_impls.openmuse`.
"""

from __future__ import annotations

from typing import Any

from swarm.core.remotes import OperateResult
from swarm.remotes.base import RemoteAdapter
from swarm.remotes.registry import register_remote_adapter


@register_remote_adapter("openmuse")
class OpenMuseAdapter(RemoteAdapter):
    def list(self, timeout: float, query: str = "") -> OperateResult:
        from swarm.core import remotes

        return remotes._openmuse_list(self.spec, timeout, query=query)

    def health(self, timeout: float = 3.0, config: dict[str, Any] | None = None):
        """Mint a session, then probe ``GET /api/agent/``.

        The generic prober sends the configured key as a bearer, which OpenMuse
        never accepts (it wants a ``POST /api/session`` token), so it would
        only ever see a 401 and have to guess the endpoint was alive. This
        asks the real question instead. The token is cached, so repeat health
        checks cost one HTTP call, not one session mint each.
        """
        from swarm.core import remotes

        return remotes._openmuse_health(self.spec, timeout)

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._openmuse_send(
            self.spec, prompt, timeout, session_id=session_id, target=target
        )

    def control(self, action: str, task_id: str, timeout: float) -> OperateResult:
        """``pause`` / ``resume`` / ``cancel`` / ``retry`` on one task."""
        from swarm.core import remotes

        return remotes._openmuse_control(self.spec, action, task_id, timeout)

    def resume_with_answer(
        self,
        session_id: str,
        pending_action: dict[str, Any],
        answer: str,
        timeout: float,
    ) -> OperateResult:
        from swarm.core import remotes

        return remotes._openmuse_resume_pending(
            self.spec,
            session_id=session_id,
            pending_action=pending_action,
            content=answer,
            timeout=timeout,
        )

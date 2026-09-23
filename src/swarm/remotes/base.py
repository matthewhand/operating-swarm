"""#812 — the RemoteAdapter base contract.

Slice 1 ships the *dispatch seam*: the base declares the async protocol
surface the issue specifies (``check_health``, ``list_agents``, ``chat``,
``stream_chat``, ``list_routines``) plus the synchronous ``operate`` shape
``remotes.operate()`` routes through today. Concrete adapters start by
forwarding to the legacy implementations (zero behavior change) and fill in
the async surface per-adapter as the httpx migration lands — a missing
implementation is an explicit ``NotImplementedError``, never a silent
fallthrough.
"""

from __future__ import annotations

from typing import Any, Iterator

from swarm.core.remotes import OperateResult, RemoteSpec


class RemoteAdapter:
    """Per-harness adapter over one resolved :class:`RemoteSpec`.

    Subclasses set ``kind`` (the registry key) and override the sync
    ``list``/``send``/``routines`` operations as they are migrated. The
    async protocol methods are declared here and intentionally unimplemented
    until each harness moves onto the shared async client.
    """

    kind: str = ""

    def __init__(self, spec: RemoteSpec, config: dict[str, Any] | None = None) -> None:
        self.spec = spec
        self.config = config

    # ------------------------------------------------------------------
    # Sync operate surface — what remotes.operate() dispatches through.
    # ------------------------------------------------------------------
    def list(self, timeout: float, query: str = "") -> OperateResult:
        raise NotImplementedError(f"{type(self).__name__}.list")

    def send(
        self,
        prompt: str,
        timeout: float,
        *,
        target: str = "",
        session_id: str | None = None,
    ) -> OperateResult:
        raise NotImplementedError(f"{type(self).__name__}.send")

    def routines(self, timeout: float) -> OperateResult:
        raise NotImplementedError(f"{type(self).__name__}.routines")

    def interrogate(
        self,
        target: str,
        timeout: float,
        config: dict[str, Any] | None = None,
    ) -> OperateResult:
        raise NotImplementedError(f"{type(self).__name__}.interrogate")

    # ------------------------------------------------------------------
    # Async protocol surface (#812 target shape — filled in per harness).
    # ------------------------------------------------------------------
    async def check_health(self, timeout: float = 3.0):
        raise NotImplementedError(f"{type(self).__name__}.check_health")

    async def list_agents(self, timeout: float = 8.0, query: str = ""):
        raise NotImplementedError(f"{type(self).__name__}.list_agents")

    async def chat(
        self,
        prompt: str,
        target: str = "",
        session_id: str | None = None,
        timeout: float = 180.0,
    ):
        raise NotImplementedError(f"{type(self).__name__}.chat")

    async def stream_chat(
        self,
        prompt: str,
        target: str = "",
        session_id: str | None = None,
        timeout: float = 180.0,
    ):
        raise NotImplementedError(f"{type(self).__name__}.stream_chat")
        yield  # pragma: no cover — makes this an async generator

    async def list_routines(self, timeout: float = 8.0):
        raise NotImplementedError(f"{type(self).__name__}.list_routines")

    # ------------------------------------------------------------------
    # Streaming chat surface (#812 slice 3) — consumed polymorphically by
    # blueprint_remote_harness. Yields ``(delta, done, error)`` tuples,
    # matching the legacy ``iter_*_chat`` generators exactly.
    # ------------------------------------------------------------------
    def iter_chat(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        target: str = "",
    ) -> Iterator[tuple[str | None, bool, str | None]]:
        raise NotImplementedError(f"{type(self).__name__}.iter_chat")

    def empty_reply_hint(self) -> str:
        """Honest sentence when a stream finished without any delta."""
        raise NotImplementedError(f"{type(self).__name__}.empty_reply_hint")

    # ------------------------------------------------------------------
    # Health surface (#812 slice 4) — check_health dispatches through the
    # registry. The base forwards to the shared generic prober (HTTP kinds
    # unchanged); adapters with non-HTTP transports (Herdr) or alternate
    # probe paths (Letta) override the hooks instead of the prober growing
    # kind branches.
    # ------------------------------------------------------------------
    def health(self, timeout: float, config: dict[str, Any] | None = None):
        from swarm.core import remotes

        return remotes._check_health_spec(
            self.spec, timeout, config, extra_health_paths=self.extra_health_paths()
        )

    def extra_health_paths(self) -> list[str]:
        """Alternate health paths probed after the spec's own (Letta #489)."""
        return []

"""#1684 — the turn-phase ``tool_status`` producer.

The ``tool_status`` websocket frame has been fully understood by the client for
a long time (``webui/frontend/src/lib/chatWs.ts`` parses it into
``ChatWsEvent.kind === 'tool_status'``, ``useChatWsDispatcher`` routes it to
``upsertToolCall``, ``ToolCallPopup`` renders it). Nothing in ``src/`` ever
*produced* one outside demo replay: the only producer, ``tool_executor``'s
``handle_tool_calls``, has no caller anywhere in the package, and its emit path
bailed on ``uses_swarm_approval()`` — which is true for ``api`` channels only,
so CLI and remote seats could never report a tool in flight either.

This module is the live producer: an ``AgentHooksBase`` implementation, set on
the SDK ``Agent``'s ``hooks`` field, that turns tool start/end into the frame
the SPA already renders. It is the missing half of the "waiting on a model" vs
"a tool call is in flight" distinction.

Two facts about openai-agents 0.3.3 shape everything here. Both were read, not
remembered:

1. **The hook signature carries no id.** ``AgentHooksBase.on_tool_start(self,
   context, agent, tool)`` and ``AgentHooksBase.on_tool_end(self, context,
   agent, tool, result)`` — ``agents/lifecycle.py:110-127`` — receive no
   ``tool_call_id`` *argument*; only the ``Tool`` and a context. Meanwhile the
   client's ``ToolCallState.id`` (``webui/frontend/src/lib/safety.ts:11``) is
   used as an opaque upsert key inside ``upsertToolCall``, and the frame is
   dropped outright by the parser if ``id`` is empty
   (``chatWs.ts:267``). So a key must be minted here.

   Because the SDK fans a batch of parallel tool calls out through
   ``asyncio.gather`` (``agents/_run_impl.py:717-726`` and
   ``agents/_run_impl.py:809+``), two ``read_file`` calls in one turn genuinely
   overlap. A name-derived key would make the second call overwrite the first
   in the client's ``upsertToolCall`` reducer, and the first call would never
   reach a terminal status — its badge would hang forever. Hence
   ``agent_id + tool_name + monotonic counter``.

2. **Start and end share no back-reference.** ``on_tool_end`` fires from
   ``agents/_run_impl.py:787-796`` with the same ``tool_context`` object it was
   started with, but the *key we minted* is not recoverable from it, so
   :class:`ToolPhaseHooks` keeps a small in-flight map and pops it on end. A
   fresh key on end would create a second row in the client instead of
   updating the first.

   Corollary worth knowing (it is why the map falls back to object identity):
   the ``context`` the SDK passes is a real ``ToolContext`` carrying
   ``tool_call_id`` for *function* tools (``agents/tool_context.py:28``,
   built at ``agents/_run_impl.py:748-752``), but the plain
   ``RunContextWrapper`` for hosted computer / local-shell tools
   (``agents/_run_impl.py:1285`` and ``agents/_run_impl.py:1388``). The map
   therefore prefers the SDK's own call id and degrades to ``id(context)``,
   holding a reference to the context so the id cannot be recycled while the
   entry is live.

The hooks are a strict no-op when no :class:`~swarm.core.safety.SafetySession`
is installed, or when its ``emit_fn`` is ``None``, and they never raise: a
status frame must never be the reason a turn fails.
"""

from __future__ import annotations

import itertools
import json
import logging
from typing import Any

from agents.lifecycle import AgentHooksBase

from swarm.tool_executor import (
    COMMAND_DENIED_RESULT_PREFIX,
    DENIED_RESULT_PREFIX,
    ERROR_RESULT_KEY,
    emit_tool_status,
)

logger = logging.getLogger(__name__)

__all__ = ["ToolPhaseHooks", "attach_turn_phase_hooks", "terminal_status_for"]


def _tool_name(tool: Any) -> str:
    """The name the LLM saw. Every ``Tool`` in the SDK's union has ``.name``
    (``agents/tool.py:69`` for ``FunctionTool``; the hosted ones expose it as a
    property), but a bare callable can reach here, so fall back."""
    return str(getattr(tool, "name", None) or getattr(tool, "__name__", None) or "tool")


def _inflight_key(context: Any) -> tuple[str, str]:
    """A stable per-invocation identity used only to correlate start → end.

    Never used as the emitted id — the emitted id is minted from the counter so
    it is guaranteed non-empty and collision-free even for two same-named tools
    racing in the same turn.
    """
    call_id = getattr(context, "tool_call_id", None)
    if call_id:
        return ("call", str(call_id))
    return ("ctx", str(id(context)))


def _json_error_key(result: str) -> bool:
    try:
        parsed = json.loads(result)
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict) and ERROR_RESULT_KEY in parsed


def terminal_status_for(result: Any) -> str:
    """``done``, or ``error`` when ``result`` carries a terminal sentinel.

    The sentinels are the exact strings the repo already writes into tool
    results — this adds no new vocabulary:

    * ``DENIED_RESULT_PREFIX`` — the swarm-approval denial from
      ``tool_executor._maybe_deny_tool``, and the identical strings from
      ``core.safety._wrap_callable`` and ``core.tool_gate.gate_wrap_callable``
      (those two return the denial as the tool's *value*, so it reaches the
      SDK's ``on_tool_end`` verbatim).
    * ``COMMAND_DENIED_RESULT_PREFIX`` — the #1312 command-allowlist denial.
    * an ``error`` key — every failure result this repo appends is
      ``{"error": ...}`` (missing tool, malformed tool call, tool exception),
      which reaches the hook either as a ``dict`` (the SDK hands the raw
      Python return value to ``on_tool_end``; see
      ``agents/tool.py:445``) or as its JSON text.

    Both denial sentinels map to ``error`` rather than to the client's
    ``denied`` status: from the hooks' point of view both are "this call is
    over and produced no usable output". A caller that wants the finer
    distinction can read the sentinel off the result.
    """
    if isinstance(result, dict):
        return "error" if ERROR_RESULT_KEY in result else "done"
    if isinstance(result, str):
        head = result.lstrip()
        if head.startswith(DENIED_RESULT_PREFIX) or head.startswith(
            COMMAND_DENIED_RESULT_PREFIX
        ):
            return "error"
        return "error" if _json_error_key(result) else "done"
    return "done"


class ToolPhaseHooks(AgentHooksBase):
    """Emit the existing ``tool_status`` frame around each SDK tool call.

    Attach with :func:`attach_turn_phase_hooks` rather than constructing
    directly — that keeps the install idempotent and hooks any agent whose
    ``hooks`` another decorator already claimed.
    """

    def __init__(self, previous: AgentHooksBase | None = None) -> None:
        #: Chained ahead of every callback, so an existing hook still sees the
        #: run. ``None`` on every agent in ``src/`` today (nothing in the
        #: package assigns ``agent.hooks``); kept so that stops being
        #: load-bearing.
        self.previous = previous
        self._seq = itertools.count()
        # mapkey -> (context_ref, emitted_id). The context reference is pinned
        # so the ``id(context)`` fallback in ``_inflight_key`` cannot be
        # recycled by a later tool call while this entry is still open.
        self._inflight: dict[tuple[str, str], tuple[Any, str]] = {}

    # -- SDK callbacks ----------------------------------------------------
    # Signatures verified against agents/lifecycle.py:110-127.

    async def on_start(self, context: Any, agent: Any) -> None:
        await self._forward("on_start", context, agent)

    async def on_end(self, context: Any, agent: Any, output: Any) -> None:
        await self._forward("on_end", context, agent, output)

    async def on_handoff(self, context: Any, agent: Any, source: Any) -> None:
        await self._forward("on_handoff", context, agent, source)

    async def on_llm_start(
        self,
        context: Any,
        agent: Any,
        system_prompt: str | None,
        input_items: list[Any],
    ) -> None:
        await self._forward(
            "on_llm_start", context, agent, system_prompt, input_items
        )

    async def on_llm_end(self, context: Any, agent: Any, response: Any) -> None:
        await self._forward("on_llm_end", context, agent, response)

    async def on_tool_start(self, context: Any, agent: Any, tool: Any) -> None:
        if self.previous is not None:
            await self._forward("on_tool_start", context, agent, tool)
        try:
            session = self._session()
            if session is None:
                return
            name = _tool_name(tool)
            emitted_id = f"{session.agent_id or '-'}:{name}:{next(self._seq)}"
            self._inflight[_inflight_key(context)] = (context, emitted_id)
            await emit_tool_status(emitted_id, name, "running")
        except Exception:
            logger.debug("turn-phase on_tool_start emit skipped", exc_info=True)

    async def on_tool_end(
        self, context: Any, agent: Any, tool: Any, result: Any
    ) -> None:
        try:
            # Pop first: a terminal frame must be emitted even if the chained
            # hook below raises.
            pinned = self._inflight.pop(_inflight_key(context), None)
            if self.previous is not None:
                await self._forward("on_tool_end", context, agent, tool, result)
            session = self._session()
            if session is None:
                return
            name = _tool_name(tool)
            emitted_id = (
                pinned[1]
                if pinned is not None
                else f"{session.agent_id or '-'}:{name}:{next(self._seq)}"
            )
            await emit_tool_status(emitted_id, name, terminal_status_for(result))
        except Exception:
            logger.debug("turn-phase on_tool_end emit skipped", exc_info=True)

    # -- internals --------------------------------------------------------

    async def _forward(self, name: str, *args: Any) -> None:
        """Delegate one callback to a previously-installed hook, if any.

        A broken third-party hook must not be able to fail the run, and must
        not be able to fail *our* frame either.
        """
        hook = getattr(self.previous, name, None)
        if hook is None:
            return
        try:
            await hook(*args)
        except Exception:
            logger.debug("chained agent hook %s raised", name, exc_info=True)

    @staticmethod
    def _session() -> Any:
        from swarm.core.safety import current_safety_session

        return current_safety_session()


def attach_turn_phase_hooks(agent: Any) -> Any:
    """Give ``agent`` a :class:`ToolPhaseHooks`, chaining any existing hooks.

    ``Agent.hooks`` is an ordinary dataclass field (``agents/agent.py:204``,
    type-checked in ``__post_init__`` at ``agents/agent.py:339-346``), so this
    *sets* the attribute on the existing agent — it never wraps, proxies, or
    replaces the object, which would break the identity checks the SDK and the
    blueprint layers do on the agent.

    Idempotent: an agent that already carries our hooks is returned untouched,
    so a shared post-construction sequence can call it unconditionally.
    """
    if agent is None:
        return agent
    existing = getattr(agent, "hooks", None)
    if isinstance(existing, ToolPhaseHooks):
        return agent
    try:
        agent.hooks = ToolPhaseHooks(previous=existing)
    except Exception:
        # A frozen/slotted agent, or a stand-in object that is not a real SDK
        # Agent at all (persona_swarm's coordinator, test doubles). Losing a
        # status frame is always preferable to failing a turn here.
        logger.debug("turn-phase hook attach skipped for %r", agent, exc_info=True)
    return agent

"""#1181 — streaming with an honest non-stream fallback.

#1154: the upstream gateway's ``orchestration`` route intermittently never
sends response **headers** for ``stream=True`` requests while the same route
answers non-stream in under a second. #1156's per-phase read deadline turns
that stall into a ~45s failure — honest, but needless when a retry without
streaming succeeds immediately.

:func:`stream_with_fallback` is the shared seam: try streaming; if the
failure happens in the *headers* phase (no chunk was ever received), retry
once — against a configured fallback gateway as a stream (default
``SWARM_LLM_FALLBACK_BASE_URL``, empty disables it), otherwise against the
same client non-streaming. A failure after chunks flowed (mid-stream drop)
is **not** retried — partial delivery already happened, so the caller must
see the error instead of a duplicated reply.

Only header-phase transport failures (timeouts, connect errors) fall back;
HTTP errors (4xx/5xx raised at request time) are the route's honest answer
and propagate unchanged. A fallback gateway that rejects the request before
any byte (e.g. 401) is non-fatal: the reply degrades to the primary
non-stream path exactly as if no fallback were configured.

The header phase is independently bounded by ``SWARM_LLM_STREAM_HEADER_TIMEOUT_S``
(:func:`swarm.utils.env_utils.get_llm_stream_header_timeout_s`, default 20s) so
the degrade happens promptly instead of waiting out the longer per-chunk read
deadline. Chunks after the first are governed only by the client's read timeout
(#1155), so a slow but healthy stream is never prematurely aborted.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import openai

logger = logging.getLogger(__name__)

OnChunk = Callable[[str], Awaitable[None]]
# ``primary_client, fallback_base_url -> fallback client or None``.
FallbackClientFactory = Callable[[Any, str], Any | None]

_HEADER_PHASE_ERRORS: tuple[type[BaseException], ...] = (
    openai.APITimeoutError,
    openai.APIConnectionError,
)
_STREAM_ATTEMPT_ERRORS: tuple[type[BaseException], ...] = (
    *_HEADER_PHASE_ERRORS,
    TimeoutError,
)


class _HeaderPhaseStall(Exception):
    """No chunk arrived before the bounded header deadline (safe to retry)."""


class _StreamState:
    """Mutable flag so callers can tell a pre-byte failure from a mid-stream one."""

    __slots__ = ("received_any",)

    def __init__(self) -> None:
        self.received_any = False


async def _close_stream(stream: Any) -> None:
    """Best-effort release of a stream we are abandoning (timeout/error)."""
    if stream is None:
        return
    close = getattr(stream, "close", None)
    if callable(close):
        try:
            result = close()
            if asyncio.iscoroutine(result):
                await result
        except Exception:  # noqa: BLE001 - cleanup must never mask the fallback
            logger.debug("stream close failed", exc_info=True)
        return
    aclose = getattr(stream, "aclose", None)
    if callable(aclose):
        try:
            await aclose()
        except Exception:  # noqa: BLE001 - cleanup must never mask the fallback
            logger.debug("stream aclose failed", exc_info=True)


async def _stream_once(
    create: Callable[..., Awaitable[Any]],
    *,
    model: str,
    messages: list[dict[str, Any]],
    on_chunk: OnChunk | None,
    header_timeout: float,
    create_kwargs: dict[str, Any],
    state: _StreamState,
) -> str:
    """One streaming attempt. Raises :class:`_HeaderPhaseStall` pre-first-byte."""
    parts: list[str] = []
    stream = None
    try:
        # Bound the header phase (request start + first chunk). After the first
        # chunk we stop wrapping in wait_for: the client's per-chunk read
        # deadline (#1155) governs, so a healthy slow generation is not cut off.
        stream = await asyncio.wait_for(
            create(model=model, messages=messages, stream=True, **create_kwargs),
            timeout=header_timeout,
        )
        iterator = stream.__aiter__()
        try:
            chunk = await asyncio.wait_for(iterator.__anext__(), timeout=header_timeout)
        except StopAsyncIteration:
            return "".join(parts)
        while True:
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0].delta, "content", None)
                if delta:
                    state.received_any = True
                    parts.append(delta)
                    if on_chunk is not None:
                        await on_chunk(delta)
            try:
                chunk = await iterator.__anext__()
            except StopAsyncIteration:
                break
        return "".join(parts)
    except _STREAM_ATTEMPT_ERRORS as exc:
        if state.received_any:
            # Mid-stream transport drop after partial delivery: do not retry.
            raise
        raise _HeaderPhaseStall(str(exc)) from exc
    finally:
        await _close_stream(stream)


def _default_fallback_client(primary: Any, base_url: str) -> Any | None:
    """Build an ``AsyncOpenAI`` on ``base_url`` reusing the primary's auth."""
    api_key = getattr(primary, "api_key", None)
    if not api_key:
        return None
    from swarm.utils.env_utils import llm_http_timeout

    return openai.AsyncOpenAI(
        api_key=api_key, base_url=base_url, timeout=llm_http_timeout()
    )


def _build_fallback_client(
    primary: Any,
    factory: FallbackClientFactory | None,
) -> Any | None:
    """Fallback client when ``SWARM_LLM_FALLBACK_BASE_URL`` is set, else ``None``."""
    from swarm.utils.env_utils import get_llm_fallback_base_url

    base_url = get_llm_fallback_base_url()
    if not base_url:
        return None
    build = factory or _default_fallback_client
    try:
        return build(primary, base_url)
    except Exception:  # noqa: BLE001 - a bad fallback must not break the reply
        logger.warning("could not build fallback LLM client", exc_info=True)
        return None


async def stream_with_fallback(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    on_chunk: OnChunk | None = None,
    fallback_client_factory: FallbackClientFactory | None = None,
    **create_kwargs: Any,
) -> str:
    """Stream a completion; fall back on a header-phase stall.

    Returns the full reply text. ``on_chunk`` (when given) receives each
    streamed delta — and exactly one whole-reply chunk on the non-stream
    fallback path — so callers can render progressively without knowing
    which path ran. The reply is delivered exactly once.

    ``fallback_client_factory`` is injectable for tests; it receives
    ``(primary_client, base_url)`` and returns a fallback client or ``None``.
    """
    from swarm.utils.env_utils import get_llm_stream_header_timeout_s

    header_timeout = get_llm_stream_header_timeout_s()

    # --- attempt 1: streaming against the primary gateway ---
    primary_state = _StreamState()
    try:
        return await _stream_once(
            client.chat.completions.create,
            model=model,
            messages=messages,
            on_chunk=on_chunk,
            header_timeout=header_timeout,
            create_kwargs=create_kwargs,
            state=primary_state,
        )
    except _HeaderPhaseStall as exc:
        logger.warning(
            "streaming stalled in headers phase (%s); retrying fallback/non-stream for model=%s",
            type(exc.__cause__).__name__ if exc.__cause__ else exc,
            model,
        )
    # (HTTP and mid-stream failures propagate from the try above.)

    # --- attempt 2: streaming against the configured fallback gateway ---
    fallback_client = _build_fallback_client(client, fallback_client_factory)
    if fallback_client is not None:
        fallback_state = _StreamState()
        try:
            return await _stream_once(
                fallback_client.chat.completions.create,
                model=model,
                messages=messages,
                on_chunk=on_chunk,
                header_timeout=header_timeout,
                create_kwargs=create_kwargs,
                state=fallback_state,
            )
        except _HeaderPhaseStall as exc:
            logger.warning(
                "fallback stream stalled in headers phase (%s); retrying non-stream for model=%s",
                type(exc.__cause__).__name__ if exc.__cause__ else exc,
                model,
            )
        except Exception:
            if fallback_state.received_any:
                # Mid-stream drop on the fallback: partial delivery, never retry.
                raise
            logger.warning(
                "fallback stream failed before first byte; retrying non-stream for model=%s",
                model,
                exc_info=True,
            )

    # --- attempt 3: non-stream against the original client/base_url ---
    resp = await client.chat.completions.create(
        model=model, messages=messages, stream=False, **create_kwargs
    )
    choices = getattr(resp, "choices", None) or []
    text = ""
    if choices:
        text = getattr(choices[0].message, "content", None) or ""
    if on_chunk is not None and text:
        await on_chunk(text)
    return text

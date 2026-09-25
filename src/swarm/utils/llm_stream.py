"""#1181 — streaming with an honest non-stream fallback.

#1154: the upstream gateway's ``orchestration`` route intermittently never
sends response **headers** for ``stream=True`` requests while the same route
answers non-stream in under a second. #1156's per-phase read deadline turns
that stall into a ~45s failure — honest, but needless when a retry without
streaming succeeds immediately.

:func:`stream_with_fallback` is the shared seam: try streaming; if the
failure happens in the *headers* phase (no chunk was ever received), retry
once with ``stream=False`` and hand the whole reply to ``on_chunk`` as a
single chunk. A failure after chunks flowed (mid-stream drop) is **not**
retried — partial delivery already happened, so the caller must see the
error instead of a duplicated reply.

Only header-phase transport failures (timeouts, connect errors) fall back;
HTTP errors (4xx/5xx raised at request time) are the route's honest answer
and propagate unchanged.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

import openai

logger = logging.getLogger(__name__)

OnChunk = Callable[[str], Awaitable[None]]

_HEADER_PHASE_ERRORS: tuple[type[BaseException], ...] = (
    openai.APITimeoutError,
    openai.APIConnectionError,
)


async def stream_with_fallback(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    on_chunk: OnChunk | None = None,
    **create_kwargs: Any,
) -> str:
    """Stream a completion; fall back to non-stream when headers never arrive.

    Returns the full reply text. ``on_chunk`` (when given) receives each
    streamed delta — and exactly one whole-reply chunk on the fallback path —
    so callers can render progressively without knowing which path ran.
    """
    create = client.chat.completions.create

    # --- attempt 1: streaming ---
    received_any = False
    parts: list[str] = []
    try:
        stream = await create(model=model, messages=messages, stream=True, **create_kwargs)
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0].delta, "content", None)
            if delta:
                received_any = True
                parts.append(delta)
                if on_chunk is not None:
                    await on_chunk(delta)
        return "".join(parts)
    except _HEADER_PHASE_ERRORS as exc:
        if received_any:
            # Mid-stream transport drop after partial delivery: do not retry.
            raise
        logger.warning(
            "streaming stalled in headers phase (%s); retrying non-stream for model=%s",
            type(exc).__name__, model,
        )
    # (HTTP errors and mid-stream failures propagate from the try above.)

    # --- attempt 2: non-stream ---
    resp = await create(model=model, messages=messages, stream=False, **create_kwargs)
    choices = getattr(resp, "choices", None) or []
    text = ""
    if choices:
        text = getattr(choices[0].message, "content", None) or ""
    if on_chunk is not None and text:
        await on_chunk(text)
    return text

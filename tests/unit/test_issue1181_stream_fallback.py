"""#1181 — stall-prone gateway routes degrade to non-stream instead of dying.

#1154: the upstream gateway's `orchestration` route intermittently never sends
response **headers** when `stream=True` (non-stream answers in <1s). With
#1156's read deadline the stream attempt fails at ~45s — an honest failure,
but a needless one when the same route answers non-stream immediately.

`stream_with_fallback` is the seam: try streaming; if the failure happens in
the *headers* phase (no chunk was ever received), retry once with
`stream=False` and deliver the whole reply as a single chunk. A failure after
chunks flowed (mid-stream drop) is NOT retried — partial delivery already
happened; the caller sees the error.
"""

from __future__ import annotations

import asyncio

import openai
import pytest

from swarm.utils.llm_stream import stream_with_fallback


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        return self._agen()

    async def _agen(self):
        for c in self._chunks:
            yield c


def _chunk(text: str):
    ch = openai.types.chat.ChatCompletionChunk.model_construct(
        choices=[
            openai.types.chat.chat_completion_chunk.Choice.model_construct(
                delta=openai.types.chat.chat_completion_chunk.ChoiceDelta.model_construct(
                    content=text
                ),
                index=0,
            )
        ]
    )
    return ch


@pytest.mark.asyncio
async def test_stream_success_never_falls_back():
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return _FakeStream([_chunk("PI"), _chunk("NG")])

    client = type("C", (), {"chat": type("Chat", (), {"completions": type("CP", (), {"create": staticmethod(create)})()})()})()
    out = []

    async def on_chunk(t):
        out.append(t)

    text = await stream_with_fallback(client, model="m", messages=[], on_chunk=on_chunk)
    assert text == "PING"
    assert out == ["PI", "NG"]
    assert len(calls) == 1 and calls[0]["stream"] is True


@pytest.mark.asyncio
async def test_headers_phase_timeout_falls_back_to_nonstream():
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        if kwargs.get("stream"):
            raise openai.APITimeoutError(_timeout_req())
        resp = openai.types.chat.ChatCompletion.model_construct(
            choices=[
                openai.types.chat.chat_completion_chunk.Choice.model_construct(
                    message=openai.types.chat.ChatCompletionMessage.model_construct(
                        content="PING"
                    ),
                    index=0,
                )
            ]
        )
        return resp

    client = type("C", (), {"chat": type("Chat", (), {"completions": type("CP", (), {"create": staticmethod(create)})()})()})()
    out = []

    async def on_chunk(t):
        out.append(t)

    text = await stream_with_fallback(client, model="m", messages=[], on_chunk=on_chunk)
    assert text == "PING"
    assert out == ["PING"]  # whole reply as one chunk
    assert [c["stream"] for c in calls] == [True, False]


@pytest.mark.asyncio
async def test_midstream_failure_is_not_retried():
    calls = []

    async def _gen():
        yield _chunk("PI")
        raise RuntimeError("mid-stream drop")

    async def create(**kwargs):
        calls.append(kwargs)
        return _gen()

    client = type("C", (), {"chat": type("Chat", (), {"completions": type("CP", (), {"create": staticmethod(create)})()})()})()
    out = []

    async def on_chunk(t):
        out.append(t)

    with pytest.raises(RuntimeError):
        await stream_with_fallback(client, model="m", messages=[], on_chunk=on_chunk)
    assert out == ["PI"]  # partial delivery happened
    assert len(calls) == 1  # no non-stream retry


def _timeout_req():
    import httpx

    return httpx.Request("POST", "http://gw/v1/chat/completions")

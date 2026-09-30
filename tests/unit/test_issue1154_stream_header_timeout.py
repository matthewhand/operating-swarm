"""#1154 — bounded first-byte deadline; header-less streams degrade promptly.

The upstream gateway's ``orchestration`` route accepts ``stream=True`` but can
never send response headers. #1155 bounded the wait with a 45s per-chunk read
deadline and #1181 retries once non-stream on a header-phase failure. This
suite pins the additional contract: the *header / first-byte* phase is bounded
separately (``SWARM_LLM_STREAM_HEADER_TIMEOUT_S``, default 20s) so the degrade
happens promptly, while a slow-but-arriving stream is not prematurely aborted
and post-first-chunk gaps stay under the client's read deadline.

All fakes are in-process; no network.
"""

from __future__ import annotations

import asyncio

import openai
import pytest

from swarm.utils.env_utils import get_llm_stream_header_timeout_s
from swarm.utils.llm_stream import stream_with_fallback

ENV = "SWARM_LLM_STREAM_HEADER_TIMEOUT_S"


def _chunk(text: str):
    return openai.types.chat.ChatCompletionChunk.model_construct(
        choices=[
            openai.types.chat.chat_completion_chunk.Choice.model_construct(
                delta=openai.types.chat.chat_completion_chunk.ChoiceDelta.model_construct(
                    content=text
                ),
                index=0,
            )
        ]
    )


def _nonstream_response(text: str):
    return openai.types.chat.ChatCompletion.model_construct(
        choices=[
            openai.types.chat.chat_completion_chunk.Choice.model_construct(
                message=openai.types.chat.ChatCompletionMessage.model_construct(
                    content=text
                ),
                index=0,
            )
        ]
    )


def _client(create):
    completions = type("CP", (), {"create": staticmethod(create)})()
    chat = type("Chat", (), {"completions": completions})()
    return type("C", (), {"chat": chat})()


class _DelayedStream:
    """Async stream yielding ``texts`` after per-index ``delays``."""

    def __init__(self, delays, texts):
        self._delays = delays
        self._texts = texts
        self.closed = False

    def __aiter__(self):
        return self._agen()

    async def _agen(self):
        for delay, text in zip(self._delays, self._texts, strict=True):
            if delay:
                await asyncio.sleep(delay)
            yield _chunk(text)

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_headerless_stream_falls_back_to_nonstream(monkeypatch):
    monkeypatch.setenv(ENV, "0.05")
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        if kwargs.get("stream"):
            await asyncio.sleep(5)  # headers never arrive within the deadline
        return _nonstream_response("PING")

    out = []

    async def on_chunk(text):
        out.append(text)

    text = await stream_with_fallback(
        _client(create), model="m", messages=[], on_chunk=on_chunk
    )
    assert text == "PING"
    assert out == ["PING"]  # whole reply, delivered exactly once
    assert [c["stream"] for c in calls] == [True, False]


@pytest.mark.asyncio
async def test_slow_but_arriving_first_chunk_not_aborted(monkeypatch):
    monkeypatch.setenv(ENV, "1.0")
    calls = []
    stream = _DelayedStream(delays=[0.2, 0.2], texts=["PI", "NG"])

    async def create(**kwargs):
        calls.append(kwargs)
        return stream

    out = []

    async def on_chunk(text):
        out.append(text)

    text = await stream_with_fallback(
        _client(create), model="m", messages=[], on_chunk=on_chunk
    )
    assert text == "PING"
    assert out == ["PI", "NG"]
    assert len(calls) == 1, "first byte arrived in time; must not fall back"


@pytest.mark.asyncio
async def test_post_first_chunk_gap_uses_read_deadline_not_header_deadline(monkeypatch):
    """The header deadline must not become a mid-stream cap (#1155 governs there)."""
    monkeypatch.setenv(ENV, "0.05")
    calls = []
    stream = _DelayedStream(delays=[0.0, 0.3, 0.3], texts=["PI", "N", "G"])

    async def create(**kwargs):
        calls.append(kwargs)
        return stream

    out = []

    async def on_chunk(text):
        out.append(text)

    text = await stream_with_fallback(
        _client(create), model="m", messages=[], on_chunk=on_chunk
    )
    assert text == "PING"
    assert out == ["PI", "N", "G"]
    assert len(calls) == 1, "header deadline leaked past the first chunk"


def test_stream_header_timeout_env_default_and_override(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert get_llm_stream_header_timeout_s() == 20.0
    monkeypatch.setenv(ENV, "7.5")
    assert get_llm_stream_header_timeout_s() == 7.5
    monkeypatch.setenv(ENV, "garbage")
    assert get_llm_stream_header_timeout_s() == 20.0, "garbage falls back to default"
    monkeypatch.setenv(ENV, "0")
    assert get_llm_stream_header_timeout_s() == 20.0, "non-positive falls back to default"

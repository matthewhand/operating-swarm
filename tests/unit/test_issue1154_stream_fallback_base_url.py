"""#1154 — header-less primary stream retries a configurable fallback gateway.

When the primary gateway accepts ``stream=True`` but never sends headers
within the bounded first-byte deadline, :func:`stream_with_fallback` may retry
the *stream* once against ``SWARM_LLM_FALLBACK_BASE_URL`` before degrading to
the same-url non-stream call. This suite pins that contract hermetically —
every client is an in-process fake and the fallback client is injected, so no
network is touched.

Covered:
- header-less primary -> fallback stream runs and its reply is returned once;
- a primary stream that arrives is never rerouted;
- no fallback configured -> existing non-stream same-url degrade;
- fallback hangs / rejects pre-byte -> still degrade to the primary non-stream.
"""

from __future__ import annotations

import asyncio

import httpx
import openai
import pytest

from swarm.utils.env_utils import get_llm_fallback_base_url
from swarm.utils.llm_stream import stream_with_fallback

HEADER_ENV = "SWARM_LLM_STREAM_HEADER_TIMEOUT_S"
FALLBACK_ENV = "SWARM_LLM_FALLBACK_BASE_URL"


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


def _timeout_req():
    return httpx.Request("POST", "http://gw/v1/chat/completions")


@pytest.mark.asyncio
async def test_headerless_primary_retries_fallback_stream(monkeypatch):
    monkeypatch.setenv(HEADER_ENV, "0.05")
    monkeypatch.setenv(FALLBACK_ENV, "https://fb.example/v1")
    primary_calls = []
    fallback_calls = []

    async def primary_create(**kwargs):
        primary_calls.append(kwargs)
        if kwargs.get("stream"):
            await asyncio.sleep(5)  # headers never arrive
        return _nonstream_response("PRIMARY-NONSTREAM")  # must not be reached

    async def fallback_create(**kwargs):
        fallback_calls.append(kwargs)
        assert kwargs.get("stream") is True, "fallback must retry as a stream"
        return _DelayedStream(delays=[0.0, 0.0], texts=["PI", "NG"])

    factory_calls = []

    def factory(_primary, base_url):
        factory_calls.append(base_url)
        return _client(fallback_create)

    out = []

    async def on_chunk(text):
        out.append(text)

    text = await stream_with_fallback(
        _client(primary_create),
        model="m",
        messages=[],
        on_chunk=on_chunk,
        fallback_client_factory=factory,
    )
    assert text == "PING"
    assert out == ["PI", "NG"], "reply delivered exactly once, streamed"
    assert factory_calls == ["https://fb.example/v1"]
    assert [c["stream"] for c in fallback_calls] == [True]
    assert len(primary_calls) == 1, "primary stream tried once; no primary non-stream"


@pytest.mark.asyncio
async def test_primary_stream_that_arrives_is_not_rerouted(monkeypatch):
    monkeypatch.setenv(HEADER_ENV, "1.0")
    monkeypatch.setenv(FALLBACK_ENV, "https://fb.example/v1")
    calls = []
    stream = _DelayedStream(delays=[0.0, 0.0], texts=["PI", "NG"])

    async def primary_create(**kwargs):
        calls.append(kwargs)
        return stream

    factory_calls = []

    def factory(_primary, _base_url):
        factory_calls.append(_base_url)
        raise AssertionError("factory must not be consulted when primary streams")

    out = []

    async def on_chunk(text):
        out.append(text)

    text = await stream_with_fallback(
        _client(primary_create),
        model="m",
        messages=[],
        on_chunk=on_chunk,
        fallback_client_factory=factory,
    )
    assert text == "PING"
    assert out == ["PI", "NG"]
    assert factory_calls == [], "an arriving primary stream is never rerouted"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_no_fallback_configured_uses_nonstream_same_url(monkeypatch):
    monkeypatch.setenv(HEADER_ENV, "0.05")
    monkeypatch.delenv(FALLBACK_ENV, raising=False)
    calls = []

    async def primary_create(**kwargs):
        calls.append(kwargs)
        if kwargs.get("stream"):
            await asyncio.sleep(5)
        return _nonstream_response("PING")

    factory_calls = []

    def factory(_primary, _base_url):
        factory_calls.append(_base_url)
        raise AssertionError("no fallback configured; factory must not be called")

    out = []

    async def on_chunk(text):
        out.append(text)

    text = await stream_with_fallback(
        _client(primary_create),
        model="m",
        messages=[],
        on_chunk=on_chunk,
        fallback_client_factory=factory,
    )
    assert text == "PING"
    assert out == ["PING"], "whole reply as one chunk"
    assert [c["stream"] for c in calls] == [True, False], "same-url non-stream degrade"
    assert factory_calls == []


@pytest.mark.asyncio
async def test_fallback_also_hangs_degrades_to_nonstream(monkeypatch):
    monkeypatch.setenv(HEADER_ENV, "0.05")
    monkeypatch.setenv(FALLBACK_ENV, "https://fb.example/v1")
    calls = []
    fallback_calls = []

    async def primary_create(**kwargs):
        calls.append(kwargs)
        if kwargs.get("stream"):
            await asyncio.sleep(5)
        return _nonstream_response("PING")

    async def fallback_create(**_kwargs):
        fallback_calls.append(_kwargs)
        await asyncio.sleep(5)  # fallback stream never sends headers either

    out = []

    async def on_chunk(text):
        out.append(text)

    text = await stream_with_fallback(
        _client(primary_create),
        model="m",
        messages=[],
        on_chunk=on_chunk,
        fallback_client_factory=lambda _primary, _base_url: _client(fallback_create),
    )
    assert text == "PING"
    assert out == ["PING"]
    assert [c["stream"] for c in calls] == [True, False], "degrade to primary non-stream"
    assert len(fallback_calls) == 1, "fallback stream attempted once"


@pytest.mark.asyncio
async def test_fallback_rejected_pre_byte_degrades_to_nonstream(monkeypatch):
    """A 401/HTTP error from the fallback is non-fatal — no duplicated reply."""
    monkeypatch.setenv(HEADER_ENV, "0.05")
    monkeypatch.setenv(FALLBACK_ENV, "https://fb.example/v1")
    calls = []

    async def primary_create(**kwargs):
        calls.append(kwargs)
        if kwargs.get("stream"):
            await asyncio.sleep(5)
        return _nonstream_response("PING")

    async def fallback_create(**_kwargs):
        raise openai.AuthenticationError(
            "no key",
            response=httpx.Response(401, request=_timeout_req()),
            body=None,
        )

    out = []

    async def on_chunk(text):
        out.append(text)

    text = await stream_with_fallback(
        _client(primary_create),
        model="m",
        messages=[],
        on_chunk=on_chunk,
        fallback_client_factory=lambda _primary, _base_url: _client(fallback_create),
    )
    assert text == "PING"
    assert out == ["PING"]
    assert [c["stream"] for c in calls] == [True, False]


def test_fallback_base_url_env_default_and_override(monkeypatch):
    monkeypatch.delenv(FALLBACK_ENV, raising=False)
    assert get_llm_fallback_base_url() is None
    monkeypatch.setenv(FALLBACK_ENV, "   ")
    assert get_llm_fallback_base_url() is None, "blank disables the fallback"
    monkeypatch.setenv(FALLBACK_ENV, " https://open-litellm.fly.dev/v1 ")
    assert get_llm_fallback_base_url() == "https://open-litellm.fly.dev/v1"

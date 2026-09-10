"""Issue #152 — gawd live run() must not leak EOFError on closed stdin.

The matrix pass-2 CODE seat hit HTTP 500 because the non-SWARM_TEST_MODE path
called input() (EOFError when stdin is closed) and /v1/chat/completions
surfaced that as 500. These tests stay on the live path, mock the LLM client,
and fail if EOFError escapes run().
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from swarm.blueprints.gawd.blueprint_gawd import GAWDBlueprint


def _boom_input(*_a, **_k):
    raise EOFError("EOF when reading a line")


def _assistant_text(chunks) -> str:
    text = ""
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        message = chunk.get("message")
        if isinstance(message, dict) and message.get("content"):
            text = str(message["content"])
        messages = chunk.get("messages")
        if isinstance(messages, list) and messages and messages[0].get("content"):
            text = str(messages[0]["content"])
    return text.strip()


async def _collect(gen):
    return [c async for c in gen]


@pytest.fixture(autouse=True)
def _live_path_no_stdin(monkeypatch):
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    monkeypatch.setattr("builtins.input", _boom_input)
    monkeypatch.setattr(
        "swarm.blueprints.gawd.blueprint_gawd.GAWDBlueprint._stdin_is_interactive",
        staticmethod(lambda: False),
    )


@pytest.mark.asyncio
async def test_run_does_not_raise_eoferror_when_stdin_closed():
    """Reproduction: live path + closed stdin must yield a reply, not raise."""
    bp = GAWDBlueprint(blueprint_id="gawd")
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    assert chunks, "gawd live run() produced no chunks"
    text = _assistant_text(chunks)
    assert text, "gawd live run() yielded empty assistant content"
    assert "ping" in text


@pytest.mark.asyncio
async def test_run_uses_mocked_llm_not_stdin(monkeypatch):
    fake_run = AsyncMock(
        return_value=SimpleNamespace(final_output="mocked-gawd:ping", complete=True)
    )
    fake_agents = SimpleNamespace(Runner=SimpleNamespace(run=fake_run))
    monkeypatch.setitem(__import__("sys").modules, "agents", fake_agents)

    bp = GAWDBlueprint(blueprint_id="gawd")
    bp.coordinator = object()
    chunks = await _collect(bp.run([{"role": "user", "content": "ping"}]))
    text = _assistant_text(chunks)
    assert text == "mocked-gawd:ping"
    fake_run.assert_awaited()


@pytest.mark.asyncio
async def test_run_llm_eoferror_is_honest_reply_not_raise(monkeypatch):
    async def _eof(*_a, **_k):
        raise EOFError("incomplete stream")

    fake_agents = SimpleNamespace(Runner=SimpleNamespace(run=_eof))
    monkeypatch.setitem(__import__("sys").modules, "agents", fake_agents)

    bp = GAWDBlueprint(blueprint_id="gawd")
    bp.coordinator = object()
    chunks = await _collect(bp.run([{"role": "user", "content": "tiny"}]))
    text = _assistant_text(chunks)
    assert text
    assert "could not finish reading the model stream" in text
    assert "tiny" in text

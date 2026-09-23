"""DjangoChatConsumer demo-mode path never calls an LLM (REQ-882 / #279)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from swarm.consumers import DjangoChatConsumer


@pytest.fixture
def consumer():
    user = type("U", (), {"is_authenticated": True, "pk": 1})()
    c = DjangoChatConsumer()
    c.scope = {"user": user, "url_route": {"kwargs": {"conversation_id": "demo"}}}
    c.user = user
    c.messages = []
    c.ui_events = []
    c.conversation_id = "demo"
    return c


@pytest.mark.asyncio
async def test_demo_mode_streams_canned_sdlc_without_blueprint(consumer, monkeypatch):
    monkeypatch.setenv("SWARM_DEMO_MODE", "1")
    sent: list[str] = []

    async def capture(*, text_data=None, **_k):
        sent.append(text_data or "")

    consumer.send = capture  # type: ignore[method-assign]
    consumer._persist_completed_turn = AsyncMock()  # type: ignore[method-assign]
    consumer.emit_tool_event = AsyncMock()  # type: ignore[method-assign]
    with patch("swarm.consumers.render_to_string", return_value="<div>final</div>"):
        await consumer.respond_with_demo("message-response-demo", "Build a REST API with the SDLC team")

    blob = "".join(sent)
    assert "Product Owner" in blob
    assert "Skeptic" in blob
    assert consumer.messages[-1]["role"] == "assistant"
    assert "Product Owner" in consumer.messages[-1]["content"]


@pytest.mark.asyncio
async def test_serialised_turn_uses_demo_engine_not_llm(consumer, monkeypatch):
    monkeypatch.setenv("SWARM_DEMO_MODE", "1")
    consumer.default_blueprint = "jeeves"
    consumer._ensure_chat_turn_lock = lambda: _Lock()  # type: ignore[method-assign]
    consumer.send = AsyncMock()  # type: ignore[method-assign]
    consumer._emit_new_cli_session_notice = AsyncMock()  # type: ignore[method-assign]
    consumer.respond_with_blueprint = AsyncMock()  # type: ignore[method-assign]
    consumer.respond_with_default_model = AsyncMock()  # type: ignore[method-assign]

    with patch("swarm.consumers.render_to_string", return_value="<div></div>"):
        await consumer._run_serialised_chat_turn(
            {"message": "Ping the Hermes remote worker"},
            "Ping the Hermes remote worker",
        )

    consumer.respond_with_blueprint.assert_not_awaited()
    consumer.respond_with_default_model.assert_not_awaited()
    assistant = [m for m in consumer.messages if m.get("role") == "assistant"]
    assert assistant
    assert "Hermes" in assistant[-1]["content"]


class _Lock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

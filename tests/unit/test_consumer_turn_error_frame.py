"""A failed chat turn must surface as an error frame, not a dropped socket.

Provider-client construction (a missing ``OPENAI_API_KEY``, or a
``${LITELLM_BASE_URL}`` / ``${LITELLM_API_KEY}`` in ``swarm_config.json`` whose
env var was never set) used to raise straight out of ``websocket_receive``.
Uvicorn then aborted the socket with no close frame, so the SPA could only
report *"ASGI is not serving /ws/ or Origin does not match ALLOWED_HOSTS"* —
a credential problem shown to the user as a connection fault. Observed live
via a session-authenticated WebSocket probe against a dev stack.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from swarm.consumers import DjangoChatConsumer

SECRET_IN_EXCEPTION = "sk-do-not-echo-this-value"


def _consumer() -> DjangoChatConsumer:
    consumer = DjangoChatConsumer()
    consumer.messages = []
    consumer.ui_events = []
    consumer.user = MagicMock()
    consumer.user.is_authenticated = True
    consumer.conversation_id = "turn-error-frame-conv"
    consumer.default_blueprint = None
    consumer.active_agent = None
    consumer.send = AsyncMock()
    consumer.send_error_message = AsyncMock()
    consumer.save_conversation = AsyncMock()
    return consumer


async def test_model_client_failure_sends_error_frame_instead_of_raising(monkeypatch):
    # Production: client_safe_error_message returns only the public text.
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    consumer = _consumer()

    async def boom(_contents_div_id):
        # Mirrors openai.OpenAIError raised while building the client.
        raise RuntimeError(f"api_key missing; leaked {SECRET_IN_EXCEPTION}")

    consumer.respond_with_default_model = boom

    # An escape here is what aborts the websocket, so this must not raise.
    await consumer._run_serialised_chat_turn({"message": "hi"}, "hi")

    consumer.send_error_message.assert_awaited_once()
    div_id, text = consumer.send_error_message.await_args.args
    assert div_id.startswith("message-response-")
    assert text.strip(), "error frame must carry a message"
    assert SECRET_IN_EXCEPTION not in text
    assert "RuntimeError" not in text


async def test_debug_mode_appends_operator_detail_by_design(monkeypatch):
    """Documented trade-off, not a regression: debug echoes the exception.

    ``client_safe_error_message`` only appends detail when DJANGO_DEBUG is on,
    so a dev stack can read the provider's complaint from the chat pane. That
    means a provider body echoing a key would reach the UI in debug — hence
    production must never run with DJANGO_DEBUG=true.
    """
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    consumer = _consumer()

    async def boom(_contents_div_id):
        raise RuntimeError("provider rejected the request")

    consumer.respond_with_default_model = boom
    await consumer._run_serialised_chat_turn({"message": "hi"}, "hi")

    _div_id, text = consumer.send_error_message.await_args.args
    assert "RuntimeError" in text
    assert "provider rejected the request" in text


async def test_blueprint_failure_also_stays_on_the_socket():
    consumer = _consumer()

    async def boom(*_args, **_kwargs):
        raise RuntimeError("provider exploded")

    consumer.respond_with_blueprint = boom

    await consumer._run_serialised_chat_turn(
        {"message": "hi", "blueprint": "codey"}, "hi"
    )

    consumer.send_error_message.assert_awaited_once()


async def test_error_frame_is_not_appended_to_model_context():
    """Errors are transport chrome: they must not enter later turn context."""
    consumer = _consumer()

    async def boom(_contents_div_id):
        raise RuntimeError("provider exploded")

    consumer.respond_with_default_model = boom
    await consumer._run_serialised_chat_turn({"message": "hi"}, "hi")

    contents = [
        str(item.get("content", ""))
        for item in consumer.messages
        if isinstance(item, dict)
    ]
    assert not any("provider exploded" in item for item in contents)

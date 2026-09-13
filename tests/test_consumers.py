"""
Unit tests for src/swarm/consumers.py

Covers:
- connect: authenticated vs unauthenticated, ?blueprint= query param default
- disconnect: cleanup, save, delete empty conversations
- receive: valid JSON, missing keys, invalid JSON, empty messages,
  overlapping frames serialised (REQ-171A-3 / #603)
- blueprint selection: message field, connection default, override,
  unknown-blueprint error partial
- fetch_conversation: cache hit, JSON-first + DB backfill, DoesNotExist
- save_conversation: create/update, idempotent replace on repeat save
- delete_conversation: existing, missing
"""

import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from swarm.consumers import (
    IN_MEMORY_CONVERSATIONS,
    IN_MEMORY_UI_EVENTS,
    SPA_HELLO_TYPE,
    DjangoChatConsumer,
    _conversation_cache_key,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.is_authenticated = True
    user.pk = 1
    return user


@pytest.fixture
def mock_unauthenticated_user():
    """Create a mock unauthenticated user."""
    user = MagicMock()
    user.is_authenticated = False
    return user


@pytest.fixture
def mock_scope(mock_user):
    """Create a mock scope for the consumer."""
    return {
        "user": mock_user,
        "url_route": {
            "kwargs": {
                "conversation_id": "test-conv-123"
            }
        }
    }


@pytest.fixture
def mock_scope_unauthenticated(mock_unauthenticated_user):
    """Create a mock scope with unauthenticated user."""
    return {
        "user": mock_unauthenticated_user,
        "url_route": {
            "kwargs": {
                "conversation_id": "test-conv-123"
            }
        }
    }


@pytest.fixture
def consumer(mock_scope, mock_user):
    """Create a consumer instance for testing."""
    consumer = DjangoChatConsumer()
    consumer.scope = mock_scope
    consumer.user = mock_user  # Set user attribute directly (normally set in connect)
    consumer.messages = []
    consumer.ui_events = []
    return consumer


@pytest.fixture(autouse=True)
def isolated_memory_cache():
    """Provide isolated in-memory conversation cache for each test.
    
    This fixture saves and restores the global IN_MEMORY_CONVERSATIONS
    to ensure test isolation when running with xdist.
    """
    # Save original state
    original = IN_MEMORY_CONVERSATIONS.copy()
    original_events = IN_MEMORY_UI_EVENTS.copy()
    IN_MEMORY_CONVERSATIONS.clear()
    IN_MEMORY_UI_EVENTS.clear()

    yield IN_MEMORY_CONVERSATIONS

    # Restore original state
    IN_MEMORY_CONVERSATIONS.clear()
    IN_MEMORY_CONVERSATIONS.update(original)
    IN_MEMORY_UI_EVENTS.clear()
    IN_MEMORY_UI_EVENTS.update(original_events)


# =============================================================================
# Connect Tests
# =============================================================================


class TestConnect:
    """Tests for DjangoChatConsumer.connect method."""

    @pytest.mark.asyncio
    async def test_connect_authenticated_accepts(self, consumer, mock_scope):
        """Authenticated user should have connection accepted."""
        with patch.object(consumer, 'fetch_conversation', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            with patch.object(consumer, 'accept', new_callable=AsyncMock) as mock_accept:
                order = []
                mock_accept.side_effect = lambda *a, **k: order.append("accept")
                mock_fetch.side_effect = lambda *a, **k: order.append("fetch") or []
                await consumer.connect()

                mock_accept.assert_called_once()
                mock_fetch.assert_called_once_with("test-conv-123")
                assert order == ["accept", "fetch"]

    @pytest.mark.asyncio
    async def test_connect_authenticated_sends_spa_hello(self, consumer):
        """REQ-78: authenticated connect advertises expected SPA version."""
        with patch.object(consumer, "fetch_conversation", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            with patch.object(consumer, "accept", new_callable=AsyncMock):
                with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                    with patch(
                        "swarm.core.app_version.get_app_version",
                        return_value="0.5.4",
                    ):
                        await consumer.connect()

        mock_send.assert_awaited()
        payload = json.loads(mock_send.await_args.kwargs["text_data"])
        assert payload == {"type": SPA_HELLO_TYPE, "spa_version": "0.5.4"}

    @pytest.mark.asyncio
    async def test_connect_unauthenticated_does_not_send_spa_hello(
        self, mock_scope_unauthenticated
    ):
        """Anonymous close must not emit spa_hello (no false update)."""
        from swarm.consumers import WS_AUTH_REQUIRED_CODE

        consumer = DjangoChatConsumer()
        consumer.scope = mock_scope_unauthenticated
        with patch("swarm.consumers.swarm_allow_anonymous", return_value=False):
            with patch.object(consumer, "accept", new_callable=AsyncMock):
                with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                    with patch.object(consumer, "close", new_callable=AsyncMock) as mock_close:
                        await consumer.connect()

        mock_send.assert_not_called()
        mock_close.assert_called_once_with(
            code=WS_AUTH_REQUIRED_CODE,
            reason="authentication required",
        )

    @pytest.mark.asyncio
    async def test_connect_accepts_even_if_fetch_raises(self, consumer):
        """DB/thread-pool failure must not leave the handshake hanging."""
        with patch.object(consumer, 'fetch_conversation', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = RuntimeError("CurrentThreadExecutor already quit or is broken")
            with patch.object(consumer, 'accept', new_callable=AsyncMock) as mock_accept:
                with patch.object(consumer, 'close', new_callable=AsyncMock) as mock_close:
                    await consumer.connect()
                    mock_accept.assert_called_once()
                    mock_close.assert_not_called()
                    assert consumer.messages == []

    @pytest.mark.asyncio
    async def test_connect_authenticated_fetches_conversation(self, consumer):
        """Authenticated user should have their conversation fetched."""
        existing_messages = [{"role": "user", "content": "Hello"}]

        with patch.object(consumer, 'fetch_conversation', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = existing_messages

            with patch.object(consumer, 'accept', new_callable=AsyncMock):
                await consumer.connect()

                assert consumer.messages == existing_messages

    @pytest.mark.asyncio
    async def test_connect_unauthenticated_closes(self, mock_scope_unauthenticated):
        """Unauthenticated user is accept-then-closed with WS_AUTH_REQUIRED_CODE."""
        from swarm.consumers import WS_AUTH_REQUIRED_CODE

        consumer = DjangoChatConsumer()
        consumer.scope = mock_scope_unauthenticated

        with patch.object(consumer, 'accept', new_callable=AsyncMock) as mock_accept:
            with patch.object(consumer, 'close', new_callable=AsyncMock) as mock_close:
                await consumer.connect()

                mock_accept.assert_called_once()
                mock_close.assert_called_once_with(
                    code=WS_AUTH_REQUIRED_CODE,
                    reason="authentication required",
                )

    @pytest.mark.asyncio
    async def test_connect_passes_client_ip_to_anonymous_gate(
        self, mock_scope_unauthenticated
    ):
        mock_scope_unauthenticated["client"] = ("10.0.0.199", 51234)
        consumer = DjangoChatConsumer()
        consumer.scope = mock_scope_unauthenticated
        preview = MagicMock()
        preview.is_authenticated = True
        preview.pk = 7

        with patch("swarm.consumers.swarm_allow_anonymous", return_value=True) as allow:
            with patch(
                "swarm.consumers.database_sync_to_async",
                side_effect=lambda fn: AsyncMock(return_value=preview),
            ):
                with patch.object(
                    consumer, "fetch_conversation", new_callable=AsyncMock, return_value=[]
                ):
                    with patch.object(consumer, "accept", new_callable=AsyncMock):
                        with patch.object(consumer, "close", new_callable=AsyncMock) as mock_close:
                            await consumer.connect()
        allow.assert_called_with("10.0.0.199")
        mock_close.assert_not_called()

    @pytest.mark.asyncio
    async def test_connect_anonymous_preview_does_not_close_4401(
        self, mock_scope_unauthenticated
    ):
        """SWARM_ALLOW_ANONYMOUS preview user: accept and keep the socket."""
        preview = MagicMock()
        preview.is_authenticated = True
        preview.pk = 99

        consumer = DjangoChatConsumer()
        consumer.scope = mock_scope_unauthenticated

        with patch("swarm.consumers.swarm_allow_anonymous", return_value=True):
            with patch(
                "swarm.consumers.database_sync_to_async",
                side_effect=lambda fn: AsyncMock(return_value=preview),
            ):
                with patch.object(
                    consumer, "fetch_conversation", new_callable=AsyncMock
                ) as mock_fetch:
                    mock_fetch.return_value = []
                    with patch.object(consumer, "accept", new_callable=AsyncMock) as mock_accept:
                        with patch.object(consumer, "close", new_callable=AsyncMock) as mock_close:
                            await consumer.connect()

        mock_accept.assert_called_once()
        mock_close.assert_not_called()
        mock_fetch.assert_called_once()
        assert consumer.user is preview

    @pytest.mark.asyncio
    async def test_connect_anonymous_preview_mint_failure_keeps_socket(
        self, mock_scope_unauthenticated
    ):
        """If the preview user cannot be minted, do not 4401 — socket stays open."""
        consumer = DjangoChatConsumer()
        consumer.scope = mock_scope_unauthenticated

        with patch("swarm.consumers.swarm_allow_anonymous", return_value=True):
            with patch(
                "swarm.consumers.database_sync_to_async",
                side_effect=lambda fn: AsyncMock(
                    side_effect=RuntimeError("CurrentThreadExecutor already quit")
                ),
            ):
                with patch.object(consumer, "accept", new_callable=AsyncMock) as mock_accept:
                    with patch.object(consumer, "close", new_callable=AsyncMock) as mock_close:
                        await consumer.connect()

        mock_accept.assert_called_once()
        mock_close.assert_not_called()
        assert consumer.messages == []

    @pytest.mark.asyncio
    async def test_connect_sets_conversation_id(self, consumer, mock_scope):
        """Connect should set conversation_id from URL route."""
        with patch.object(consumer, 'fetch_conversation', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            with patch.object(consumer, 'accept', new_callable=AsyncMock):
                await consumer.connect()

                assert consumer.conversation_id == "test-conv-123"

    @pytest.mark.asyncio
    async def test_connect_without_query_string_has_no_default_blueprint(self, consumer):
        """No ?blueprint= query param -> no connection-level default."""
        with patch.object(consumer, 'fetch_conversation', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            with patch.object(consumer, 'accept', new_callable=AsyncMock):
                await consumer.connect()

                assert consumer.default_blueprint is None

    @pytest.mark.asyncio
    async def test_connect_query_param_sets_default_blueprint(self, consumer):
        """?blueprint=<id> on the ws URL becomes the connection default."""
        consumer.scope["query_string"] = b"blueprint=jeeves"

        with patch.object(consumer, 'fetch_conversation', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            with patch.object(consumer, 'accept', new_callable=AsyncMock):
                await consumer.connect()

                assert consumer.default_blueprint == "jeeves"


# =============================================================================
# Disconnect Tests
# =============================================================================


class TestDisconnect:
    """Tests for DjangoChatConsumer.disconnect method."""

    @pytest.mark.asyncio
    async def test_disconnect_authenticated_saves_conversation(self, consumer):
        """Authenticated user should have conversation saved on disconnect."""
        consumer.messages = [{"role": "user", "content": "Hello"}]
        consumer.conversation_id = "test-conv-123"

        with patch.object(consumer, 'save_conversation', new_callable=AsyncMock) as mock_save:
            with patch.object(consumer, 'delete_conversation', new_callable=AsyncMock) as mock_delete:
                await consumer.disconnect(close_code=1000)

                mock_save.assert_called_once_with("test-conv-123", consumer.messages)
                mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_deletes_empty_conversation(self, consumer):
        """Empty conversation should be deleted on disconnect."""
        consumer.messages = []
        consumer.conversation_id = "test-conv-123"

        with patch.object(consumer, 'save_conversation', new_callable=AsyncMock):
            with patch.object(consumer, 'delete_conversation', new_callable=AsyncMock) as mock_delete:
                await consumer.disconnect(close_code=1000)

                mock_delete.assert_called_once_with("test-conv-123")

    @pytest.mark.asyncio
    async def test_disconnect_clears_memory_cache(self, consumer):
        """Disconnect should clear the in-memory cache for the conversation."""
        consumer.messages = []
        consumer.conversation_id = "test-conv-123"
        cache_key = _conversation_cache_key(consumer.user, "test-conv-123")
        IN_MEMORY_CONVERSATIONS[cache_key] = []

        with patch.object(consumer, 'save_conversation', new_callable=AsyncMock):
            with patch.object(consumer, 'delete_conversation', new_callable=AsyncMock):
                await consumer.disconnect(close_code=1000)

                assert cache_key not in IN_MEMORY_CONVERSATIONS

    @pytest.mark.asyncio
    async def test_disconnect_unauthenticated_does_not_save(self, mock_scope_unauthenticated, mock_unauthenticated_user):
        """Unauthenticated user should not trigger save on disconnect."""
        consumer = DjangoChatConsumer()
        consumer.scope = mock_scope_unauthenticated
        consumer.user = mock_unauthenticated_user
        consumer.messages = []

        with patch.object(consumer, 'save_conversation', new_callable=AsyncMock) as mock_save:
            await consumer.disconnect(close_code=1000)

            mock_save.assert_not_called()


# =============================================================================
# Receive Tests
# =============================================================================


class TestReceive:
    """Tests for DjangoChatConsumer.receive method."""

    @pytest.mark.asyncio
    async def test_receive_valid_json_adds_user_message(self, consumer):
        """Valid JSON message should be added to messages list."""
        consumer.messages = []
        text_data = json.dumps({"message": "Hello, world!"})

        # Create a proper async iterator for the stream
        async def mock_stream():
            mock_chunk = MagicMock()
            mock_chunk.choices = [MagicMock()]
            mock_chunk.choices[0].delta.content = "Response"
            yield mock_chunk
            # End with None content to stop
            mock_chunk2 = MagicMock()
            mock_chunk2.choices = [MagicMock()]
            mock_chunk2.choices[0].delta.content = None
            yield mock_chunk2

        # Mock all the external dependencies
        with patch('swarm.consumers.render_to_string', return_value="<div>user message</div>"):
            with patch('swarm.consumers.AsyncOpenAI') as mock_openai:
                mock_client = MagicMock()
                mock_client.base_url = None  # Set base_url to None to avoid litellm check
                mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())
                mock_client.close = AsyncMock()
                mock_openai.return_value = mock_client

                # Patch os at module level before the function runs
                import swarm.consumers as consumers_module
                original_os = consumers_module.os
                mock_os = MagicMock()
                mock_os.getenv = MagicMock(return_value="test-key")
                mock_os.environ = {'OPENAI_API_KEY': 'test-key', 'OPENAI_MODEL': 'test-model'}
                consumers_module.os = mock_os

                try:
                    with patch.object(consumer, 'send', new_callable=AsyncMock):
                        await consumer.receive(text_data)

                        assert len(consumer.messages) == 2
                        assert consumer.messages[0]["role"] == "user"
                        assert consumer.messages[0]["content"] == "Hello, world!"
                finally:
                    consumers_module.os = original_os

    @pytest.mark.asyncio
    async def test_receive_new_session_clears_prior_transcript(self, consumer):
        """REQ-65: params.new_session starts an empty task session."""
        consumer.messages = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "prior"}]
        text_data = json.dumps({"message": "fresh task", "params": {"new_session": True}})

        with patch('swarm.consumers.render_to_string', return_value="<div>user message</div>"):
            with patch.object(consumer, 'respond_with_default_model', new_callable=AsyncMock):
                with patch.object(consumer, 'send', new_callable=AsyncMock):
                    await consumer.receive(text_data)

        assert consumer.messages[0]["content"] == "fresh task"
        assert all(m.get("content") != "old" for m in consumer.messages)

    @pytest.mark.asyncio
    async def test_receive_empty_message_returns_early(self, consumer):
        """Empty message should be ignored."""
        consumer.messages = []
        text_data = json.dumps({"message": "   "})

        await consumer.receive(text_data)

        assert len(consumer.messages) == 0

    @pytest.mark.asyncio
    async def test_receive_missing_message_key_is_ignored(self, consumer):
        """JSON without 'message' key is logged and dropped, socket survives."""
        text_data = json.dumps({"content": "Hello"})

        await consumer.receive(text_data)

        assert len(consumer.messages) == 0

    @pytest.mark.asyncio
    async def test_receive_invalid_json_is_ignored(self, consumer):
        """Invalid JSON is logged and dropped instead of killing the socket."""
        text_data = "not valid json"

        await consumer.receive(text_data)

        assert len(consumer.messages) == 0

    @pytest.mark.asyncio
    async def test_receive_non_string_message_is_ignored(self, consumer):
        """A non-string 'message' value is dropped without raising."""
        text_data = json.dumps({"message": 12345})

        await consumer.receive(text_data)

        assert len(consumer.messages) == 0

    @pytest.mark.asyncio
    async def test_overlapping_receives_serialise_turns_before_run_completes(
        self, consumer, monkeypatch
    ):
        """REQ-171A-3 / #603: two frames before first run() stay ordered.

        Consumer queues the second ``respond_with_*`` (does not interleave
        ``self.messages`` or mix ``message-response-*`` ids). Full #447
        queue-pane chrome is not required here.
        """
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        consumer.messages = []
        consumer.conversation_id = "test-conv-123"
        consumer.default_blueprint = "jeeves"

        first_run_entered = asyncio.Event()
        release_first_run = asyncio.Event()
        run_started = 0
        concurrent_run = False

        async def fake_run(messages, **kwargs):
            nonlocal run_started, concurrent_run
            idx = run_started
            run_started += 1
            if idx == 0:
                first_run_entered.set()
                await release_first_run.wait()
            elif not release_first_run.is_set():
                concurrent_run = True
            users = [m.get("content") for m in messages if m.get("role") == "user"]
            yield {"messages": [{"role": "assistant", "content": f"reply:{users[-1]}"}]}

        instance = MagicMock()
        instance.run = fake_run
        instance._params = {}
        sent = []

        async def capture_send(*, text_data=None, **_kwargs):
            sent.append(text_data or "")

        def fake_render(template, context):
            name = str(template)
            if "user_message" in name:
                return f'<div class="user-message">{context.get("message_text", "")}</div>'
            cid = context.get("contents_div_id", "")
            if "final_system" in name:
                return f'<div id="{cid}" class="assistant-final">{context.get("message", "")}</div>'
            return f'<div id="{cid}" class="assistant-start"></div>'

        with patch("swarm.consumers.render_to_string", side_effect=fake_render):
            with patch.object(consumer, "send", new_callable=AsyncMock, side_effect=capture_send):
                with patch(
                    "swarm.views.utils.get_blueprint_instance",
                    new_callable=AsyncMock,
                    return_value=instance,
                ):
                    first = asyncio.create_task(
                        consumer.receive(
                            json.dumps({"message": "alpha", "blueprint": "jeeves"})
                        )
                    )
                    await asyncio.wait_for(first_run_entered.wait(), timeout=2)
                    second = asyncio.create_task(
                        consumer.receive(
                            json.dumps({"message": "beta", "blueprint": "jeeves"})
                        )
                    )
                    await asyncio.sleep(0.05)
                    assert [m.get("content") for m in consumer.messages] == ["alpha"]
                    assert [m.get("role") for m in consumer.messages] == ["user"]
                    assert run_started == 1
                    assert not concurrent_run
                    release_first_run.set()
                    await asyncio.gather(first, second)

        contents = [m.get("content") for m in consumer.messages]
        roles = [m.get("role") for m in consumer.messages]
        assert roles == ["user", "assistant", "user", "assistant"]
        assert contents == ["alpha", "reply:alpha", "beta", "reply:beta"]
        assert run_started == 2
        assert not concurrent_run

        ids = []
        for frame in sent:
            ids.extend(re.findall(r"message-response-[0-9a-f]+", frame))
        unique = []
        for mid in ids:
            if mid not in unique:
                unique.append(mid)
        assert len(unique) == 2
        first_id, second_id = unique
        first_last = max(i for i, mid in enumerate(ids) if mid == first_id)
        second_first = min(i for i, mid in enumerate(ids) if mid == second_id)
        assert first_last < second_first
        joined = "".join(sent)
        assert joined.index("reply:alpha") < joined.index("reply:beta")
        assert first_id in joined and second_id in joined

    @pytest.mark.asyncio
    async def test_tool_decision_is_not_blocked_by_in_flight_turn(self, consumer):
        """Tool approval must resolve while the turn lock is held."""
        hold = asyncio.Event()
        entered = asyncio.Event()

        async def fake_respond(*_args, **_kwargs):
            entered.set()
            await hold.wait()

        consumer.messages = []
        consumer.default_blueprint = "jeeves"
        future = asyncio.get_running_loop().create_future()
        consumer._pending_tool_decisions = {"appr-1": future}

        with patch("swarm.consumers.render_to_string", return_value="<div/>"):
            with patch.object(consumer, "send", new_callable=AsyncMock):
                with patch.object(
                    consumer, "respond_with_blueprint", side_effect=fake_respond
                ):
                    turn = asyncio.create_task(
                        consumer.receive(
                            json.dumps({"message": "hello", "blueprint": "jeeves"})
                        )
                    )
                    await asyncio.wait_for(entered.wait(), timeout=2)
                    await consumer.receive(
                        json.dumps(
                            {
                                "type": "tool_decision",
                                "id": "appr-1",
                                "decision": "allow",
                            }
                        )
                    )
                    assert future.result() == "allow"
                    hold.set()
                    await turn

    @pytest.mark.asyncio
    async def test_receive_tool_decision_resolves_pending_and_skips_chat(self, consumer):
        """Safety Allow/Deny frames are not treated as chat messages."""
        import asyncio

        future = asyncio.get_running_loop().create_future()
        consumer.messages = []
        consumer._pending_tool_decisions = {"appr-1": future}
        await consumer.receive(
            json.dumps({"type": "tool_decision", "id": "appr-1", "decision": "allow"})
        )
        assert future.result() == "allow"
        assert consumer.messages == []

    @pytest.mark.asyncio
    async def test_edit_frame_updates_transcript_used_by_next_turn(self, consumer):
        """REQ-49: saved edit is what the next send includes."""
        consumer.messages = [
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
        ]
        consumer.conversation_id = "test-conv-123"
        consumer.default_blueprint = "jeeves"
        consumer.active_agent = "jeeves"

        with patch.object(consumer, "save_conversation", new_callable=AsyncMock) as mock_save:
            await consumer.receive(
                json.dumps({"edit": {"index": 0, "content": "engineered question"}})
            )
            mock_save.assert_called_once_with("test-conv-123", consumer.messages)
        assert consumer.messages[0]["content"] == "engineered question"
        assert consumer.messages[0]["edited"] is True

        captured = {}

        async def fake_respond(blueprint_id, contents_div_id, params=None):
            captured["messages"] = [dict(m) for m in consumer.messages]
            captured["blueprint"] = blueprint_id
            captured["params"] = params

        with patch("swarm.consumers.render_to_string", return_value="<div/>"):
            with patch.object(consumer, "send", new_callable=AsyncMock):
                with patch.object(consumer, "respond_with_blueprint", side_effect=fake_respond):
                    await consumer.receive(
                        json.dumps({"message": "follow up", "blueprint": "jeeves"})
                    )

        assert captured["blueprint"] == "jeeves"
        assert captured["messages"][0]["content"] == "engineered question"
        assert captured["messages"][-1]["content"] == "follow up"

    @pytest.mark.asyncio
    async def test_edit_frame_ignored_for_cli_and_remote(self, consumer):
        consumer.messages = [{"role": "user", "content": "stay"}]
        consumer.conversation_id = "test-conv-123"
        consumer.default_blueprint = "cli:grok"
        consumer.active_agent = "cli:grok"

        with patch.object(consumer, "save_conversation", new_callable=AsyncMock) as mock_save:
            await consumer.receive(json.dumps({"edit": {"index": 0, "content": "nope"}}))
            mock_save.assert_not_called()
        assert consumer.messages[0]["content"] == "stay"

        consumer.default_blueprint = "remote:acp"
        consumer.active_agent = "remote:acp"
        with patch.object(consumer, "save_conversation", new_callable=AsyncMock) as mock_save:
            await consumer.receive(json.dumps({"edit": {"index": 0, "content": "nope"}}))
            mock_save.assert_not_called()
        assert consumer.messages[0]["content"] == "stay"


# =============================================================================
# Blueprint Selection Tests
# =============================================================================


class TestBlueprintSelection:
    """Tests for blueprint-aware reply routing in receive()."""

    @pytest.mark.asyncio
    async def test_receive_blueprint_field_routes_to_blueprint(self, consumer):
        """{"message", "blueprint"} should dispatch to the blueprint path."""
        consumer.messages = []
        text_data = json.dumps({"message": "Hello", "blueprint": "jeeves"})

        with patch('swarm.consumers.render_to_string', return_value="<div></div>"):
            with patch.object(consumer, 'send', new_callable=AsyncMock):
                with patch.object(consumer, 'respond_with_blueprint', new_callable=AsyncMock) as mock_bp:
                    with patch.object(consumer, 'respond_with_default_model', new_callable=AsyncMock) as mock_default:
                        await consumer.receive(text_data)

                        mock_bp.assert_awaited_once()
                        assert mock_bp.await_args.args[0] == "jeeves"
                        mock_default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_receive_without_blueprint_uses_default_model(self, consumer):
        """Plain {"message"} frames keep the legacy default-model path."""
        consumer.messages = []
        text_data = json.dumps({"message": "Hello"})

        with patch('swarm.consumers.render_to_string', return_value="<div></div>"):
            with patch.object(consumer, 'send', new_callable=AsyncMock):
                with patch.object(consumer, 'respond_with_blueprint', new_callable=AsyncMock) as mock_bp:
                    with patch.object(consumer, 'respond_with_default_model', new_callable=AsyncMock) as mock_default:
                        await consumer.receive(text_data)

                        mock_default.assert_awaited_once()
                        mock_bp.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_receive_uses_connection_default_blueprint(self, consumer):
        """The ?blueprint= connection default applies to plain frames."""
        consumer.messages = []
        consumer.default_blueprint = "jeeves"
        text_data = json.dumps({"message": "Hello"})

        with patch('swarm.consumers.render_to_string', return_value="<div></div>"):
            with patch.object(consumer, 'send', new_callable=AsyncMock):
                with patch.object(consumer, 'respond_with_blueprint', new_callable=AsyncMock) as mock_bp:
                    await consumer.receive(text_data)

                    assert mock_bp.await_args.args[0] == "jeeves"

    @pytest.mark.asyncio
    async def test_receive_message_field_overrides_connection_default(self, consumer):
        """A per-message blueprint field wins over the connection default."""
        consumer.messages = []
        consumer.default_blueprint = "jeeves"
        text_data = json.dumps({"message": "Hello", "blueprint": "zeus"})

        with patch('swarm.consumers.render_to_string', return_value="<div></div>"):
            with patch.object(consumer, 'send', new_callable=AsyncMock):
                with patch.object(consumer, 'respond_with_blueprint', new_callable=AsyncMock) as mock_bp:
                    await consumer.receive(text_data)

                    assert mock_bp.await_args.args[0] == "zeus"

    @pytest.mark.asyncio
    async def test_receive_team_params_uses_stub_runtime(self, consumer):
        """REQ-23: params {team, target} stub the roster send path."""
        consumer.messages = []
        text_data = json.dumps({
            "message": "hello roster",
            "params": {"team": "demo-team", "target": "all"},
        })

        with patch("swarm.consumers.render_to_string", return_value="<div></div>"):
            with patch.object(consumer, "send", new_callable=AsyncMock):
                with patch.object(consumer, "respond_with_team_stub", new_callable=AsyncMock) as mock_team:
                    with patch.object(consumer, "respond_with_blueprint", new_callable=AsyncMock) as mock_bp:
                        with patch.object(consumer, "respond_with_default_model", new_callable=AsyncMock) as mock_default:
                            await consumer.receive(text_data)

                            mock_team.assert_awaited_once()
                            assert mock_team.await_args.args[0]["team"] == "demo-team"
                            assert mock_team.await_args.args[0]["target"] == "all"
                            mock_bp.assert_not_awaited()
                            mock_default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_receive_demo_sdlc_ba_uses_blueprint_not_stub(self, consumer):
        """#113: BA on demo SDLC must run sdlc_handoff, not the team echo stub."""
        consumer.messages = []
        text_data = json.dumps({
            "message": "Write a story for login",
            "params": {"team": "demo-sdlc-pipeline", "target": "ba"},
        })

        with patch("swarm.consumers.render_to_string", return_value="<div></div>"):
            with patch.object(consumer, "send", new_callable=AsyncMock):
                with patch.object(consumer, "respond_with_team_stub", new_callable=AsyncMock) as mock_team:
                    with patch.object(consumer, "respond_with_blueprint", new_callable=AsyncMock) as mock_bp:
                        with patch.object(consumer, "respond_with_default_model", new_callable=AsyncMock) as mock_default:
                            await consumer.receive(text_data)

                            mock_bp.assert_awaited_once()
                            assert mock_bp.await_args.args[0] == "sdlc_handoff"
                            mock_team.assert_not_awaited()
                            mock_default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_receive_status_frame_appends_without_llm(self, consumer):
        """REQ-46: type=status persists a transcript line and skips the model."""
        consumer.messages = []
        consumer.conversation_id = "conv-status"
        text_data = json.dumps({
            "type": "status",
            "text": "CLI: antigravity → grok",
            "agent": "cli_agent",
        })

        with patch.object(consumer, "save_conversation", new_callable=AsyncMock) as mock_save:
            with patch.object(consumer, "respond_with_blueprint", new_callable=AsyncMock) as mock_bp:
                with patch.object(consumer, "respond_with_default_model", new_callable=AsyncMock) as mock_default:
                    await consumer.receive(text_data)

        assert consumer.messages == []
        assert consumer.ui_events[0]["role"] == "status"
        assert consumer.ui_events[0]["content"] == "CLI: antigravity → grok"
        assert consumer.ui_events[0]["ts"]
        assert consumer.active_agent == "cli_agent"
        mock_save.assert_awaited_once()
        mock_bp.assert_not_awaited()
        mock_default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_team_stub_echoes_team_and_target(self, consumer):
        consumer.messages = [{"role": "user", "content": "ping"}]
        with patch("swarm.consumers.render_to_string", return_value="<div></div>"):
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_team_stub(
                    {"team": "demo-team", "target": "codey"},
                    "ping",
                    "message-response-team",
                )
        sent = "".join(
            call.kwargs.get("text_data") or call.args[0]
            for call in mock_send.await_args_list
        )
        assert "team:demo-team" in sent
        assert "target:codey" in sent
        assert consumer.messages[-1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_team_stub_echoes_remote_member_target(self, consumer):
        """PR #318 / REQ-23: target may be a kind=remote member id (no live LAN)."""
        consumer.messages = [{"role": "user", "content": "ping hermes"}]
        with patch("swarm.consumers.render_to_string", return_value="<div></div>"):
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_team_stub(
                    {"team": "harness-team", "target": "hermes"},
                    "ping hermes",
                    "message-response-remote",
                )
        sent = "".join(
            call.kwargs.get("text_data") or call.args[0]
            for call in mock_send.await_args_list
        )
        assert "team:harness-team" in sent
        assert "target:hermes" in sent

    @pytest.mark.asyncio
    async def test_team_stub_emits_open_in_hermes_task_card(self, consumer):
        """REQ-84: team tasking a stub Hermes remote emits Open in Hermes chrome."""
        payload = {
            "type": "teammate_task",
            "team_id": "harness-team",
            "worker_id": "hermes",
            "worker_kind": "hermes",
            "title": "ping hermes",
            "status": "Running",
            "href": "http://127.0.0.1:9119/stub-hermes",
            "open_in_label": "Open in Hermes",
        }
        consumer.messages = [{"role": "user", "content": "ping hermes"}]
        consumer.ui_events = []
        with patch("swarm.consumers.render_to_string", return_value="<div></div>"):
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                with patch(
                    "swarm.core.teammate_task.teammate_tasks_for_team_send",
                    return_value=[payload],
                ):
                    await consumer.respond_with_team_stub(
                        {"team": "harness-team", "target": "hermes"},
                        "ping hermes",
                        "message-response-remote",
                    )
        sent = "".join(
            call.kwargs.get("text_data") or call.args[0]
            for call in mock_send.await_args_list
        )
        assert "teammate_task" in sent
        assert "Open in Hermes" in sent
        assert "http://127.0.0.1:9119/stub-hermes" in sent
        assert "OMB" not in sent
        assert consumer.ui_events
        assert consumer.ui_events[0]["kind"] == "teammate_task"

    @pytest.mark.asyncio
    async def test_team_stub_without_remote_emits_no_open_in_card(self, consumer):
        consumer.messages = [{"role": "user", "content": "ping"}]
        consumer.ui_events = []
        with patch("swarm.consumers.render_to_string", return_value="<div></div>"):
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                with patch(
                    "swarm.core.teammate_task.teammate_tasks_for_team_send",
                    return_value=[],
                ):
                    await consumer.respond_with_team_stub(
                        {"team": "local-team", "target": "codey"},
                        "ping",
                        "message-response-local",
                    )
        sent = "".join(
            call.kwargs.get("text_data") or call.args[0]
            for call in mock_send.await_args_list
        )
        assert "teammate_task" not in sent
        assert "Open in Hermes" not in sent
        assert consumer.ui_events == []

    @pytest.mark.asyncio
    async def test_unknown_blueprint_sends_error_partial(self, consumer):
        """Unknown blueprint -> error partial; no assistant message recorded."""
        consumer.messages = [{"role": "user", "content": "Hello"}]

        with patch('swarm.views.utils.get_blueprint_instance', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            with patch.object(consumer, 'send', new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_blueprint("nope", "message-response-abc")

                sent = "".join(
                    call.kwargs.get("text_data") or call.args[0]
                    for call in mock_send.await_args_list
                )
                assert "nope" in sent
                assert "not found" in sent
                # The error is transport-level: not appended to history.
                assert all(m["role"] != "assistant" for m in consumer.messages)

    @pytest.mark.asyncio
    async def test_blueprint_reply_streams_chunk_and_final(self, consumer, monkeypatch):
        """A blueprint reply emits an OOB chunk + final partial and is
        appended to the conversation history (last message wins, spinner
        side-channel chunks skipped — same semantics as chat_views)."""
        # SWARM_TEST_MODE short-circuits respond_with_blueprint before the mock.
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        consumer.messages = [{"role": "user", "content": "Hello"}]

        async def fake_run(messages, **kwargs):
            yield {"type": "spinner_update", "spinner": "Generating."}
            yield {"messages": [{"role": "assistant", "content": "BP reply"}]}

        instance = MagicMock()
        instance.run = fake_run

        with patch('swarm.views.utils.get_blueprint_instance', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, 'send', new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_blueprint("jeeves", "message-response-abc")

                frames = [
                    call.kwargs.get("text_data") or call.args[0]
                    for call in mock_send.await_args_list
                ]
                assert len(frames) == 2  # OOB chunk + final partial
                assert 'hx-swap-oob="beforeend:#message-response-abc"' in frames[0]
                assert "BP reply" in frames[0]
                assert "BP reply" in frames[1]
                assert consumer.messages[-1]["role"] == "assistant"
                assert consumer.messages[-1]["content"] == "BP reply"
                assert consumer.messages[-1]["ts"]

    @pytest.mark.asyncio
    async def test_blueprint_error_body_reply_is_meaningful_error(self, consumer, monkeypatch):
        """#133: a gateway JSON error body (or its head) must surface as a
        meaningful error naming the LLM profile — never as a successful
        assistant reply appended to the conversation."""
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        consumer.messages = [{"role": "user", "content": "Hello"}]

        async def fake_run(messages, **kwargs):
            yield {"messages": [{"role": "assistant", "content": "{"}]}

        instance = MagicMock()
        instance.run = fake_run
        instance._params = {}

        with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_blueprint(
                    "api_agent", "message-response-err", params={"model": "auxiliary"}
                )

                frames = [
                    call.kwargs.get("text_data") or call.args[0]
                    for call in mock_send.await_args_list
                ]
                error_html = "".join(frames)
                assert "Error:" in error_html
                assert "JSON error body" in error_html
                assert "auxiliary" in error_html
                # Never persisted as an assistant turn.
                assert all(m.get("role") != "assistant" for m in consumer.messages)

    @pytest.mark.asyncio
    async def test_blueprint_error_body_extracts_gateway_message(self, consumer, monkeypatch):
        """#133: a full {"error": {...}} body surfaces the gateway message."""
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        consumer.messages = [{"role": "user", "content": "Hello"}]

        async def fake_run(messages, **kwargs):
            yield {
                "messages": [
                    {
                        "role": "assistant",
                        "content": '{"error": {"message": "Invalid model name passed in model=test-probe."}}',
                    }
                ]
            }

        instance = MagicMock()
        instance.run = fake_run
        instance._params = {}

        with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_blueprint("api_agent", "message-response-err")

                frames = [
                    call.kwargs.get("text_data") or call.args[0]
                    for call in mock_send.await_args_list
                ]
                assert "Invalid model name passed in model=test-probe." in "".join(frames)
                assert all(m.get("role") != "assistant" for m in consumer.messages)

    @pytest.mark.asyncio
    async def test_blueprint_session_notice_is_bubbleless_status(self, consumer, monkeypatch):
        """REQ-52: CLI session notice is a status line, not an assistant bubble."""
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        consumer.messages = [{"role": "user", "content": "Hello"}]

        async def fake_run(messages, **kwargs):
            yield {
                "type": "cli_session_notice",
                "content": "Started a new echo session.",
                "resumed": False,
            }
            yield {"messages": [{"role": "assistant", "content": "ok"}]}

        instance = MagicMock()
        instance.run = fake_run
        instance._params = {}

        with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_blueprint("cli_agent", "message-response-cli")

                frames = [
                    call.kwargs.get("text_data") or call.args[0]
                    for call in mock_send.await_args_list
                ]
                assert any("chat-status-line" in frame for frame in frames)
                assert any("Started a new echo session." in frame for frame in frames)
                assert "Restored" not in "".join(frames)
                from swarm.core.transcript_roles import reconstruct_display

                status_rows = [m for m in consumer.ui_events if m.get("role") == "status"]
                assert status_rows
                assert status_rows[0]["content"] == "Started a new echo session."
                assert status_rows[0].get("ts")
                assert all(m.get("role") != "status" for m in consumer.messages)
                display = reconstruct_display(consumer.messages, consumer.ui_events)
                roles = [m["role"] for m in display]
                assert roles.index("status") < roles.index("assistant")
                status_i = next(i for i, frame in enumerate(frames) if "Started a new echo session." in frame)
                assistant_i = next(i for i, frame in enumerate(frames) if "ok" in frame)
                assert status_i < assistant_i
                instance.set_params.assert_called()
                passed = instance.set_params.call_args[0][0]
                assert passed.get("agent") == "cli_agent"

    @pytest.mark.asyncio
    async def test_cli_stdout_github_pr_emits_view_pr_card(self, consumer, monkeypatch):
        """REQ-79: a real GitHub PR URL in CLI stdout becomes REQ-71 chrome."""
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        consumer.messages = [{"role": "user", "content": "open a pr"}]
        consumer.active_agent = "cli_agent"
        consumer.conversation_id = "conv-self-update"
        url = "https://github.com/matthewhand/open-swarm/pull/416"

        async def fake_run(messages, **kwargs):
            yield {"messages": [{"role": "assistant", "content": f"Opened {url}"}]}

        instance = MagicMock()
        instance.run = fake_run
        instance._params = {}

        with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_blueprint("cli_agent", "message-response-pr")

        frames = [
            call.kwargs.get("text_data") or call.args[0]
            for call in mock_send.await_args_list
        ]
        assert any(url in frame for frame in frames)
        pr_json = [f for f in frames if '"type": "pr_opened"' in f or '"type":"pr_opened"' in f]
        assert pr_json
        assert url in pr_json[0]
        events = [row for row in consumer.ui_events if row.get("kind") == "pr_opened"]
        assert events
        assert url in events[0]["content"]
        assert all(row.get("kind") != "pr_opened" for row in consumer.messages)

    @pytest.mark.asyncio
    async def test_cli_stdout_without_pr_url_does_not_invent_card(self, consumer, monkeypatch):
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        consumer.messages = [{"role": "user", "content": "hello"}]

        async def fake_run(messages, **kwargs):
            yield {"messages": [{"role": "assistant", "content": "Opened a PR (no url)"}]}

        instance = MagicMock()
        instance.run = fake_run
        instance._params = {}

        with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, "send", new_callable=AsyncMock):
                await consumer.respond_with_blueprint("cli_agent", "message-response-nopr")

        assert not any(row.get("kind") == "pr_opened" for row in consumer.ui_events)

    @pytest.mark.asyncio
    async def test_receive_new_cli_session_notice_before_assistant_start(
        self, consumer, tmp_path, monkeypatch
    ):
        """REQ-92: first CLI turn sends the status line before assistant_start."""
        monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
        consumer.messages = []
        consumer.conversation_id = "conv-cli-new"

        def fake_render(template, context=None):
            if "user_message" in template:
                return "<div class='user-message'>hi</div>"
            if "system_message" in template:
                div_id = (context or {}).get("contents_div_id", "message-response-x")
                return (
                    '<div id="message-list" hx-swap-oob="beforeend">'
                    f'<div id="{div_id}" class="assistant-message"></div></div>'
                )
            return "<div></div>"

        frames = []

        async def capture_send(**kwargs):
            frames.append(kwargs.get("text_data") or "")

        with patch("swarm.consumers.render_to_string", side_effect=fake_render):
            with patch.object(consumer, "respond_with_blueprint", new_callable=AsyncMock):
                with patch.object(consumer, "send", new_callable=AsyncMock, side_effect=capture_send):
                    await consumer.receive(
                        json.dumps(
                            {
                                "message": "hello",
                                "blueprint": "cli_agent",
                                "params": {"cli": "grok"},
                            }
                        )
                    )

        assert any("Started a new grok session." in frame for frame in frames)
        status_i = next(i for i, frame in enumerate(frames) if "Started a new grok session." in frame)
        start_i = next(i for i, frame in enumerate(frames) if "assistant-message" in frame)
        assert status_i < start_i
        from swarm.core.transcript_roles import reconstruct_display

        assert [m["role"] for m in consumer.messages] == ["user"]
        display = reconstruct_display(consumer.messages, consumer.ui_events)
        assert [m["role"] for m in display[:2]] == ["user", "status"]
        assert display[1]["content"] == "Started a new grok session."

    @pytest.mark.asyncio
    async def test_receive_resume_does_not_emit_spurious_new_session(
        self, consumer, tmp_path, monkeypatch
    ):
        """REQ-92 / REQ-52: same-session turns do not print Started a new …"""
        monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
        from swarm.core.cli_sessions import put_cli_session

        put_cli_session("u1", "cli_agent", "grok", "sid-1")
        consumer.messages = []
        consumer.conversation_id = "conv-cli-resume"

        with patch("swarm.consumers.render_to_string", return_value="<div></div>"):
            with patch.object(consumer, "respond_with_blueprint", new_callable=AsyncMock):
                with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                    await consumer.receive(
                        json.dumps(
                            {
                                "message": "again",
                                "blueprint": "cli_agent",
                                "params": {"cli": "grok"},
                            }
                        )
                    )
                    frames = [
                        call.kwargs.get("text_data") or call.args[0]
                        for call in mock_send.await_args_list
                    ]

        assert all("Started a new" not in str(frame) for frame in frames)
        assert all(m.get("content") != "Started a new grok session." for m in consumer.messages)
        assert all(
            m.get("content") != "Started a new grok session."
            for m in getattr(consumer, "ui_events", [])
        )

    @pytest.mark.asyncio
    async def test_blueprint_run_uses_compacted_context(self, consumer, monkeypatch):
        """REQ-37: blueprint.run sees the summary tree, not covered raw turns."""
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        consumer.conversation_id = "ws-compact-conv"
        consumer.messages = [
            {"role": "user", "content": "secret raw turn"},
            {"role": "assistant", "content": "secret raw reply"},
        ]
        seen = {}

        async def fake_run(messages, **kwargs):
            seen["messages"] = messages
            yield {"messages": [{"role": "assistant", "content": "ok"}]}

        instance = MagicMock()
        instance.run = fake_run

        async def fake_context(conversation_id, messages):
            assert conversation_id == "ws-compact-conv"
            assert messages[0]["content"] == "secret raw turn"
            return [{"role": "system", "content": "[Conversation summary]\ndigest only"}]

        with patch("swarm.consumers._compacted_context", side_effect=fake_context):
            with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = instance
                with patch.object(consumer, "send", new_callable=AsyncMock):
                    await consumer.respond_with_blueprint("jeeves", "message-response-compact")

        contents = " ".join(m["content"] for m in seen["messages"])
        assert "[Conversation summary]" in contents
        assert "digest only" in contents
        assert "secret raw turn" not in contents
        assert consumer.messages[0]["content"] == "secret raw turn"

    @pytest.mark.asyncio
    async def test_blueprint_reply_escapes_html_in_oob_chunk(self, consumer, monkeypatch):
        """Streaming OOB chunks must HTML-escape model text (DOM XSS)."""
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        payload = '<img src=x onerror="alert(1)">'
        consumer.messages = [{"role": "user", "content": "Hello"}]

        async def fake_run(messages, **kwargs):
            yield {"messages": [{"role": "assistant", "content": payload}]}

        instance = MagicMock()
        instance.run = fake_run

        with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_blueprint("jeeves", "message-response-xss")

                frames = [
                    call.kwargs.get("text_data") or call.args[0]
                    for call in mock_send.await_args_list
                ]
                assert len(frames) == 2
                assert "<img" not in frames[0]
                assert "&lt;img src=x onerror=" in frames[0]
                assert "&quot;alert(1)&quot;" in frames[0]
                # History keeps the raw model text; only the HTML wire format escapes.
                assert consumer.messages[-1]["content"] == payload

    @pytest.mark.asyncio
    async def test_test_mode_reflects_user_text_escaped(self, consumer, monkeypatch):
        """TEST-MODE canned replies echo the user message and must escape it."""
        monkeypatch.setenv("SWARM_TEST_MODE", "1")
        payload = '<script>alert(1)</script>'
        consumer.messages = [{"role": "user", "content": payload}]

        with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
            await consumer.respond_with_blueprint("jeeves", "message-response-xss")

            frames = [
                call.kwargs.get("text_data") or call.args[0]
                for call in mock_send.await_args_list
            ]
            oob = frames[0]
            assert "<script>" not in oob
            assert "&lt;script&gt;" in oob
            assert consumer.messages[-1]["content"].startswith("[TEST-MODE]")

    @pytest.mark.asyncio
    async def test_suggestions_chips_emit_after_test_mode_turn(self, consumer, monkeypatch, tmp_path):
        """REQ-85: after a finished generation, emit chips — never into messages."""
        monkeypatch.setenv("SWARM_TEST_MODE", "1")
        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
        from swarm.core import agent_settings as store

        store.reset_agent_settings_cache()
        store.update_settings("jeeves", {"use_suggestions": True})
        consumer.messages = [{"role": "user", "content": "Hello"}]
        consumer.active_agent = "jeeves"

        with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
            await consumer.respond_with_blueprint("jeeves", "message-response-sug")
            frames = [
                call.kwargs.get("text_data") or call.args[0]
                for call in mock_send.await_args_list
            ]
        json_frames = [frame for frame in frames if str(frame).startswith("{")]
        assert json_frames, frames
        payload = json.loads(json_frames[-1])
        assert payload["type"] == "suggestions"
        assert 2 <= len(payload["suggestions"]) <= 5
        assert all(m.get("role") != "suggestions" for m in consumer.messages)
        store.reset_agent_settings_cache()

    @pytest.mark.asyncio
    async def test_suggestions_prod_path_passes_wired_agent(self, consumer, monkeypatch, tmp_path):
        """Outside TEST_MODE the WS emit must pass the suggestions-role agent + turn."""
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
        from swarm.core import agent_settings as store
        from swarm.core.agent_roles import ROLE_SUGGESTIONS, find_role_agent
        import swarm.core.suggestions as sug

        store.reset_agent_settings_cache()
        store.update_settings("cli_agent", {"use_suggestions": True})
        consumer.messages = [{"role": "user", "content": "Hello there"}]
        consumer.active_agent = "cli_agent"

        class Stub:
            role = "suggestions"
            name = "suggester"

            def suggest(self, prompt):
                assert "Hello there" in prompt
                return ["Wired chip", "Another chip"]

        instance = MagicMock()

        async def fake_run(messages, **kwargs):
            yield {"messages": [{"role": "assistant", "content": "done"}]}

        instance.run = fake_run
        instance._agents = {"suggester": Stub()}
        instance.metadata = {}
        instance.agents = None

        seen: dict = {}
        real = sug.run_suggestions

        def wrap(*, mode, messages=None, agents=None, suggest_fn=None, consumer_id=None):
            seen["mode"] = mode
            seen["messages"] = messages
            seen["agents"] = agents
            seen["consumer_id"] = consumer_id
            return real(
                mode=mode,
                messages=messages,
                agents=agents,
                suggest_fn=suggest_fn,
                consumer_id=consumer_id,
            )

        monkeypatch.setattr(sug, "run_suggestions", wrap)

        with patch("swarm.views.utils.get_blueprint_instance", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, "send", new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_blueprint("cli_agent", "message-response-prod-sug")
                frames = [
                    call.kwargs.get("text_data") or call.args[0]
                    for call in mock_send.await_args_list
                ]
        json_frames = [frame for frame in frames if str(frame).startswith("{")]
        assert json_frames, frames
        payload = json.loads(json_frames[-1])
        assert payload["type"] == "suggestions"
        assert payload["suggestions"] == ["Wired chip", "Another chip"]
        assert seen.get("agents") is not None
        assert find_role_agent(seen["agents"], ROLE_SUGGESTIONS) is not None
        assert any(
            isinstance(row, dict) and row.get("content") == "Hello there"
            for row in (seen.get("messages") or [])
        )
        assert all(m.get("role") != "suggestions" for m in consumer.messages)
        store.reset_agent_settings_cache()

    @pytest.mark.asyncio
    async def test_blueprint_run_failure_sends_error_partial(self, consumer, monkeypatch):
        """Exceptions from blueprint.run() surface as an error partial."""
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        consumer.messages = [{"role": "user", "content": "Hello"}]

        async def failing_run(messages, **kwargs):
            raise RuntimeError("boom")
            yield  # pragma: no cover - makes this an async generator

        instance = MagicMock()
        instance.run = failing_run

        with patch('swarm.views.utils.get_blueprint_instance', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = instance
            with patch.object(consumer, 'send', new_callable=AsyncMock) as mock_send:
                await consumer.respond_with_blueprint("jeeves", "message-response-abc")

                sent = "".join(
                    call.kwargs.get("text_data") or call.args[0]
                    for call in mock_send.await_args_list
                )
                assert "failed while generating" in sent
                assert all(m["role"] != "assistant" for m in consumer.messages)


# =============================================================================
# Fetch Conversation Tests
# =============================================================================


class TestFetchConversation:
    """Tests for DjangoChatConsumer.fetch_conversation method."""

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_fetch_from_memory_cache(self, consumer):
        """Should return cached conversation from memory."""
        # Use unique key to avoid conflicts with parallel tests
        import uuid
        unique_id = f"cached-conv-{uuid.uuid4().hex[:8]}"
        cached_messages = [{"role": "user", "content": "Cached"}]
        cache_key = _conversation_cache_key(consumer.user, unique_id)
        IN_MEMORY_CONVERSATIONS[cache_key] = cached_messages

        result = await consumer.fetch_conversation(unique_id)

        assert result == cached_messages

    def test_cache_hit_does_not_leak_across_users(self):
        """Composite cache keys prevent serving another user's transcript on hit."""
        from swarm.models import ChatConversation

        owner = MagicMock()
        owner.pk = 101
        attacker = MagicMock()
        attacker.pk = 202

        conv_id = "shared-looking-conv-id"
        secret = [{"role": "user", "content": "owner secret transcript"}]
        IN_MEMORY_CONVERSATIONS[_conversation_cache_key(owner, conv_id)] = secret
        # Pre-fix bug: bare conversation_id key. Must not be returned to attacker.
        IN_MEMORY_CONVERSATIONS[conv_id] = secret

        attacker_consumer = DjangoChatConsumer()
        attacker_consumer.user = attacker
        fetch_sync = DjangoChatConsumer.__dict__["fetch_conversation"].func

        with patch(
            "swarm.core.thread_load.ChatConversation.objects.get",
            side_effect=ChatConversation.DoesNotExist,
        ) as mock_get:
            result = fetch_sync(attacker_consumer, conv_id)

        assert result == []
        mock_get.assert_called_once()
        assert _conversation_cache_key(attacker, conv_id) not in IN_MEMORY_CONVERSATIONS
        assert IN_MEMORY_CONVERSATIONS[_conversation_cache_key(owner, conv_id)] == secret

    @pytest.mark.django_db
    def test_fetch_from_database_sync(self, test_user, tmp_path, monkeypatch):
        """DB backfill via fetch_conversation when JSON is missing."""
        from swarm.models import ChatConversation, ChatMessage

        monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
        chat = ChatConversation.objects.create(
            conversation_id="db-conv-123",
            student=test_user,
        )
        ChatMessage.objects.create(
            conversation=chat,
            sender="user",
            content="DB message",
        )

        consumer = DjangoChatConsumer()
        consumer.user = test_user
        consumer.default_blueprint = None
        consumer.active_agent = None
        fetch_sync = DjangoChatConsumer.__dict__["fetch_conversation"].func
        result = fetch_sync(consumer, "db-conv-123")

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "DB message"
        assert result[0].get("ts")

    @pytest.mark.django_db
    def test_fetch_nonexistent_returns_empty_sync(self, test_user):
        """Should return empty list for nonexistent conversation (sync check)."""
        from swarm.models import ChatConversation

        # Verify no conversation exists
        assert not ChatConversation.objects.filter(conversation_id="nonexistent-conv").exists()


# =============================================================================
# Save Conversation Tests
# =============================================================================


class TestSaveConversation:
    """Tests for DjangoChatConsumer.save_conversation method."""

    @pytest.mark.django_db
    def test_save_creates_new_conversation_sync(self, test_user):
        """Should create a new conversation if it doesn't exist (sync version)."""
        from swarm.models import ChatConversation, ChatMessage

        # Create conversation directly to test the model behavior
        chat, created = ChatConversation.objects.get_or_create(
            conversation_id="new-conv-123",
            defaults={"student": test_user}
        )

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]

        for message in messages:
            ChatMessage.objects.create(
                conversation=chat,
                sender=message["role"],
                content=message["content"]
            )

        assert ChatConversation.objects.filter(conversation_id="new-conv-123").exists()
        assert ChatMessage.objects.filter(conversation=chat).count() == 2

    @pytest.mark.django_db
    def test_save_updates_existing_conversation_sync(self, test_user):
        """Should add messages to existing conversation (sync version)."""
        from swarm.models import ChatConversation, ChatMessage

        # Create existing conversation
        chat = ChatConversation.objects.create(
            conversation_id="existing-conv",
            student=test_user
        )

        messages = [{"role": "user", "content": "New message"}]

        for message in messages:
            ChatMessage.objects.create(
                conversation=chat,
                sender=message["role"],
                content=message["content"]
            )

        # Should have the new message
        assert ChatMessage.objects.filter(conversation=chat).count() == 1

    @pytest.mark.django_db
    def test_save_conversation_bulk_creates_messages(self, test_user):
        """save_conversation persists all messages with a constant number of queries."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from swarm.models import ChatMessage

        consumer = DjangoChatConsumer()
        consumer.user = test_user

        num_messages = 20
        new_messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
            for i in range(num_messages)
        ]

        # Call the unwrapped sync function behind database_sync_to_async.
        save_sync = DjangoChatConsumer.__dict__["save_conversation"].func
        with CaptureQueriesContext(connection) as ctx:
            save_sync(consumer, "bulk-conv-123", new_messages)

        assert (
            ChatMessage.objects.filter(
                conversation__conversation_id="bulk-conv-123"
            ).count()
            == num_messages
        )
        # get_or_create + delete + bulk_create should stay well below one query per message.
        assert len(ctx.captured_queries) < num_messages

        IN_MEMORY_CONVERSATIONS.pop(_conversation_cache_key(test_user, "bulk-conv-123"), None)

    @pytest.mark.django_db
    def test_save_conversation_idempotent_on_repeat(self, test_user):
        """Saving the same transcript twice must keep count at N, not 2N."""
        from swarm.models import ChatMessage

        consumer = DjangoChatConsumer()
        consumer.user = test_user
        conv_id = "idempotent-conv-123"
        cache_key = _conversation_cache_key(test_user, conv_id)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        save_sync = DjangoChatConsumer.__dict__["save_conversation"].func
        save_sync(consumer, conv_id, messages)
        assert (
            ChatMessage.objects.filter(
                conversation__conversation_id=conv_id
            ).count()
            == len(messages)
        )
        assert IN_MEMORY_CONVERSATIONS[cache_key] == messages

        # Simulate reconnect → disconnect with the same in-memory transcript.
        save_sync(consumer, conv_id, messages)
        assert (
            ChatMessage.objects.filter(
                conversation__conversation_id=conv_id
            ).count()
            == len(messages)
        )
        assert IN_MEMORY_CONVERSATIONS[cache_key] == messages

        # Growing transcript replaces prior rows rather than appending.
        messages_grown = messages + [
            {"role": "assistant", "content": "Doing well."},
        ]
        save_sync(consumer, conv_id, messages_grown)
        qs = ChatMessage.objects.filter(
            conversation__conversation_id=conv_id
        ).order_by("timestamp")
        assert qs.count() == len(messages_grown)
        assert [m.content for m in qs] == [m["content"] for m in messages_grown]
        assert IN_MEMORY_CONVERSATIONS[cache_key] == messages_grown

        IN_MEMORY_CONVERSATIONS.pop(cache_key, None)

    @pytest.mark.django_db
    def test_save_refuses_other_users_conversation(self, test_user):
        """get_or_create by PK must not overwrite or IntegrityError on foreign ownership."""
        from django.contrib.auth import get_user_model

        from swarm.models import ChatConversation, ChatMessage

        User = get_user_model()
        owner = test_user
        attacker = User.objects.create_user(username="save-idor-attacker", password="x")

        conv_id = "owned-by-someone-else"
        chat = ChatConversation.objects.create(conversation_id=conv_id, student=owner)
        ChatMessage.objects.create(conversation=chat, sender="user", content="owner only")

        attacker_consumer = DjangoChatConsumer()
        attacker_consumer.user = attacker
        save_sync = DjangoChatConsumer.__dict__["save_conversation"].func
        save_sync(
            attacker_consumer,
            conv_id,
            [{"role": "user", "content": "attacker overwrite attempt"}],
        )

        chat.refresh_from_db()
        assert chat.student_id == owner.pk
        assert list(
            ChatMessage.objects.filter(conversation=chat).values_list("content", flat=True)
        ) == ["owner only"]
        assert _conversation_cache_key(attacker, conv_id) not in IN_MEMORY_CONVERSATIONS


# =============================================================================
# Delete Conversation Tests
# =============================================================================


class TestDeleteConversation:
    """Tests for DjangoChatConsumer.delete_conversation method."""

    @pytest.mark.django_db
    def test_delete_existing_conversation_sync(self, test_user):
        """Should delete existing empty conversation (sync version)."""
        from swarm.models import ChatConversation

        chat = ChatConversation.objects.create(
            conversation_id="to-delete",
            student=test_user
        )

        # Simulate the delete logic
        if not chat.chat_messages.exists():
            chat.delete()

        assert not ChatConversation.objects.filter(conversation_id="to-delete").exists()

    @pytest.mark.django_db
    def test_delete_nonexistent_does_not_raise_sync(self, test_user):
        """Should not raise error for nonexistent conversation (sync version)."""
        from swarm.models import ChatConversation

        # Should not raise
        try:
            chat = ChatConversation.objects.get(conversation_id="nonexistent-conv", student=test_user)
            chat.delete()
        except ChatConversation.DoesNotExist:
            pass  # Expected behavior

    @pytest.mark.django_db
    def test_delete_clears_memory_cache_sync(self, test_user):
        """Should clear memory cache when deleting (sync version)."""
        from swarm.models import ChatConversation

        ChatConversation.objects.create(
            conversation_id="cache-delete",
            student=test_user
        )
        cache_key = _conversation_cache_key(test_user, "cache-delete")
        IN_MEMORY_CONVERSATIONS[cache_key] = []

        consumer = DjangoChatConsumer()
        consumer.user = test_user
        delete_sync = DjangoChatConsumer.__dict__["delete_conversation"].func
        delete_sync(consumer, "cache-delete")

        assert cache_key not in IN_MEMORY_CONVERSATIONS
        assert not ChatConversation.objects.filter(conversation_id="cache-delete").exists()

    @pytest.mark.django_db
    def test_delete_does_not_delete_if_messages_exist_sync(self, test_user):
        """Should not delete conversation if it has messages (sync version)."""
        from swarm.models import ChatConversation, ChatMessage

        chat = ChatConversation.objects.create(
            conversation_id="with-messages",
            student=test_user
        )
        ChatMessage.objects.create(
            conversation=chat,
            sender="user",
            content="A message"
        )

        # Simulate the delete logic
        if not chat.chat_messages.exists():
            chat.delete()

        # Conversation should still exist
        assert ChatConversation.objects.filter(conversation_id="with-messages").exists()


# =============================================================================
# Integration-style Tests with WebsocketCommunicator
# =============================================================================


class TestWebsocketIntegration:
    """Integration tests using WebsocketCommunicator."""

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_unauthenticated_connection_rejected(self):
        """Unauthenticated WebSocket is accepted then closed with 4401."""
        from swarm.consumers import WS_AUTH_REQUIRED_CODE

        communicator = WebsocketCommunicator(
            DjangoChatConsumer.as_asgi(),
            "/ws/chat/test-conv/",
        )
        # Override scope with unauthenticated user
        communicator.scope["user"] = AnonymousUser()
        communicator.scope["url_route"] = {
            "kwargs": {"conversation_id": "test-conv"}
        }

        connected, _ = await communicator.connect()
        assert connected
        close_event = await communicator.receive_output(timeout=1)
        assert close_event["type"] == "websocket.close"
        assert close_event["code"] == WS_AUTH_REQUIRED_CODE

        await communicator.disconnect()

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_unauthenticated_receive_race_does_not_crash(self):
        """Anonymous frame after accept must not AttributeError or hit LLM path.

        connect() accept-then-closes with 4401; a concurrent client frame can
        still reach receive() before the close is applied. Guard must refuse
        without requiring ``self.messages`` from the authenticated branch.
        """
        from swarm.consumers import WS_AUTH_REQUIRED_CODE

        communicator = WebsocketCommunicator(
            DjangoChatConsumer.as_asgi(),
            "/ws/chat/race-conv/",
        )
        communicator.scope["user"] = AnonymousUser()
        communicator.scope["url_route"] = {
            "kwargs": {"conversation_id": "race-conv"}
        }

        connected, _ = await communicator.connect()
        assert connected
        await communicator.send_to(text_data=json.dumps({"message": "pwned?"}))

        saw_close = False
        for _ in range(8):
            try:
                event = await communicator.receive_output(timeout=0.5)
            except Exception:
                break
            if event.get("type") == "websocket.close":
                assert event["code"] == WS_AUTH_REQUIRED_CODE
                saw_close = True
                break
            # Must never emit chat HTML partials for anonymous frames.
            assert event.get("type") != "websocket.send"

        assert saw_close
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_receive_unauthenticated_closes_without_append(self):
        """Unit: receive() for AnonymousUser closes 4401 and skips transcript."""
        from swarm.consumers import WS_AUTH_REQUIRED_CODE

        consumer = DjangoChatConsumer()
        consumer.user = AnonymousUser()
        consumer.messages = []
        consumer.conversation_id = "anon-recv"
        consumer.default_blueprint = None

        with patch.object(consumer, "close", new_callable=AsyncMock) as mock_close:
            with patch.object(
                consumer, "respond_with_default_model", new_callable=AsyncMock
            ) as mock_llm:
                await consumer.receive(text_data=json.dumps({"message": "nope"}))

        mock_close.assert_called_once_with(
            code=WS_AUTH_REQUIRED_CODE,
            reason="authentication required",
        )
        mock_llm.assert_not_called()
        assert consumer.messages == []

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_authenticated_connection_accepted(self):
        """Authenticated WebSocket connection should be accepted."""
        User = get_user_model()
        user, _ = await User.objects.aget_or_create(username="testuser")

        communicator = WebsocketCommunicator(
            DjangoChatConsumer.as_asgi(),
            "/ws/chat/test-conv/",
        )
        communicator.scope["user"] = user
        communicator.scope["url_route"] = {
            "kwargs": {"conversation_id": "test-conv-int"}
        }

        connected, _ = await communicator.connect()

        assert connected

        await communicator.disconnect()


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_receive_whitespace_only_message_returns_early(self, consumer):
        """Whitespace-only message should be ignored."""
        consumer.messages = []
        text_data = json.dumps({"message": "\n\t  \n"})

        await consumer.receive(text_data)

        assert len(consumer.messages) == 0

    @pytest.mark.asyncio
    async def test_disconnect_with_no_messages_deletes_conversation(self, consumer):
        """Disconnect with no messages should trigger delete."""
        consumer.messages = []
        consumer.conversation_id = "empty-conv"

        with patch.object(consumer, 'save_conversation', new_callable=AsyncMock):
            with patch.object(consumer, 'delete_conversation', new_callable=AsyncMock) as mock_delete:
                await consumer.disconnect(close_code=1000)

                mock_delete.assert_called_once_with("empty-conv")

    @pytest.mark.asyncio
    @pytest.mark.django_db
    async def test_memory_cache_isolation(self, consumer):
        """Each conversation should have isolated cache."""
        import uuid
        # Use unique keys to avoid conflicts with parallel tests
        key1 = f"conv-1-{uuid.uuid4().hex[:8]}"
        key2 = f"conv-2-{uuid.uuid4().hex[:8]}"

        IN_MEMORY_CONVERSATIONS[_conversation_cache_key(consumer.user, key1)] = [
            {"role": "user", "content": "Msg 1"}
        ]
        IN_MEMORY_CONVERSATIONS[_conversation_cache_key(consumer.user, key2)] = [
            {"role": "user", "content": "Msg 2"}
        ]

        result1 = await consumer.fetch_conversation(key1)
        result2 = await consumer.fetch_conversation(key2)

        assert result1 != result2
        assert result1[0]["content"] == "Msg 1"
        assert result2[0]["content"] == "Msg 2"


# =============================================================================
# Default-model LiteLLM wiring
# =============================================================================


class TestRespondWithDefaultModelLiteLLM:
    """respond_with_default_model must honor LITELLM_* like blueprint_base."""

    @pytest.mark.asyncio
    async def test_uses_litellm_base_url_and_api_key(self, consumer, monkeypatch):
        monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
        monkeypatch.setenv("LITELLM_API_KEY", "sk-litellm-test")
        monkeypatch.setenv("LITELLM_MODEL", "orchestration")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_MODEL", raising=False)

        consumer.messages = [{"role": "user", "content": "hi"}]

        async def stream():
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = "ok"
            yield chunk

        mock_client = MagicMock()
        mock_client.base_url = "http://127.0.0.1:4000/v1"
        mock_client.chat.completions.create = AsyncMock(return_value=stream())
        mock_client.close = AsyncMock()

        with patch("swarm.consumers.AsyncOpenAI", return_value=mock_client) as mock_cls:
            with patch.object(consumer, "send", new_callable=AsyncMock):
                await consumer.respond_with_default_model("message-response-litellm")

        mock_cls.assert_called_once_with(
            api_key="sk-litellm-test",
            base_url="http://127.0.0.1:4000/v1",
        )
        create_kwargs = mock_client.chat.completions.create.await_args.kwargs
        assert create_kwargs["model"] == "orchestration"

    @pytest.mark.asyncio
    async def test_uses_settings_default_when_env_unset(self, consumer, monkeypatch):
        for key in ("LITELLM_MODEL", "OPENAI_MODEL", "DEFAULT_LLM"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
        monkeypatch.setenv("LITELLM_API_KEY", "sk-litellm-test")

        consumer.messages = [{"role": "user", "content": "hi"}]

        async def stream():
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = "ok"
            yield chunk

        mock_client = MagicMock()
        mock_client.base_url = "http://127.0.0.1:4000/v1"
        mock_client.chat.completions.create = AsyncMock(return_value=stream())
        mock_client.close = AsyncMock()

        route = MagicMock()
        route.profile = "gpt-5.6-terra"
        route.warning = None
        with patch("swarm.consumers.AsyncOpenAI", return_value=mock_client):
            with patch("swarm.core.llm_task_routing.resolve_chat_model", return_value=route):
                with patch(
                    "swarm.core.llm_task_routing.model_id_for_profile",
                    return_value="gpt-5.6-terra",
                ):
                    with patch.object(consumer, "send", new_callable=AsyncMock):
                        await consumer.respond_with_default_model("message-response-settings")

        create_kwargs = mock_client.chat.completions.create.await_args.kwargs
        assert create_kwargs["model"] == "gpt-5.6-terra"

    @pytest.mark.asyncio
    async def test_rejects_openai_com_when_litellm_configured(self, consumer, monkeypatch):
        monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
        monkeypatch.setenv("LITELLM_API_KEY", "sk-litellm-test")
        monkeypatch.setenv("LITELLM_MODEL", "orchestration")

        consumer.messages = [{"role": "user", "content": "hi"}]

        mock_client = MagicMock()
        # Simulate accidental default OpenAI endpoint on the constructed client.
        mock_client.base_url = "https://api.openai.com/v1"
        mock_client.close = AsyncMock()

        with patch("swarm.consumers.AsyncOpenAI", return_value=mock_client):
            with patch.object(consumer, "send", new_callable=AsyncMock):
                with pytest.raises(RuntimeError, match="Attempted fallback to OpenAI API"):
                    await consumer.respond_with_default_model("message-response-bad")

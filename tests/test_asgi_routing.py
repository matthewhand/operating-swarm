"""
End-to-end tests for the ASGI websocket routing (ROADMAP §2).

Unlike tests/test_consumers.py — which instantiates DjangoChatConsumer
directly and hand-crafts the scope — these tests exercise the real
``swarm.asgi.application`` stack:

    ProtocolTypeRouter
      -> SwarmWebsocketOriginValidator
        -> AuthMiddlewareStack (session cookie -> scope["user"])
          -> URLRouter (ws/ai-demo/<conversation_id>/)
            -> DjangoChatConsumer

Covered:
- application structure / settings wiring
- anonymous connections are rejected
- origin not in ALLOWED_HOSTS is rejected before reaching the consumer
- unknown ws paths do not route
- authenticated session connects and completes a send -> stream -> receive
  round trip (OpenAI client mocked, real templates rendered)
- blueprint selection: a "blueprint" field in the JSON frame (or a
  ?blueprint= query param default) routes the reply through that
  blueprint's run() (SWARM_TEST_MODE canned answers); unknown blueprints
  produce an error partial without killing the socket
- plain HTTP still works through the same application
"""

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async
from channels.routing import ProtocolTypeRouter
from channels.testing import HttpCommunicator, WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.asgi import application
from swarm.consumers import SPA_HELLO_TYPE

WS_PATH = "/ws/ai-demo/asgi-test-conv/"
# Loopback Origin/Host; REQ-849 also allows same-origin LAN IPs.
VALID_ORIGIN_HEADERS = [
    (b"origin", b"http://localhost"),
    (b"host", b"localhost"),
]


# =============================================================================
# Helpers
# =============================================================================


async def make_authenticated_headers(username="asgi-ws-user"):
    """Create a user with a real DB-backed session and return ws headers."""
    User = get_user_model()
    user = await User.objects.acreate(username=username)
    client = Client()
    await sync_to_async(client.force_login)(user)
    session_cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
    cookie_header = f"{settings.SESSION_COOKIE_NAME}={session_cookie}".encode()
    return user, VALID_ORIGIN_HEADERS + [(b"cookie", cookie_header)]


def mock_openai_streaming(chunks=("Hello", " from", " mock")):
    """Patch swarm.consumers.AsyncOpenAI with a streaming mock."""

    async def stream():
        for text in chunks:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = text
            yield chunk

    mock_client = MagicMock()
    mock_client.base_url = None
    mock_client.chat.completions.create = AsyncMock(return_value=stream())
    mock_client.close = AsyncMock()
    patcher = patch("swarm.consumers.AsyncOpenAI", return_value=mock_client)
    return patcher, mock_client


# =============================================================================
# Application structure / settings wiring
# =============================================================================


class TestAsgiWiring:
    def test_application_is_protocol_type_router(self):
        assert isinstance(application, ProtocolTypeRouter)
        assert set(application.application_mapping) >= {"http", "websocket"}

    def test_settings_point_at_this_application(self):
        assert settings.ASGI_APPLICATION == "swarm.asgi.application"

    def test_channels_and_daphne_installed(self):
        assert "channels" in settings.INSTALLED_APPS
        # daphne must precede contrib apps for its runserver override
        assert settings.INSTALLED_APPS.index("daphne") == 0

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_http_requests_still_served(self):
        """The http branch of the router serves normal Django views."""
        communicator = HttpCommunicator(
            application, "GET", "/login/", headers=[(b"host", b"localhost")]
        )
        response = await communicator.get_response()
        assert response["status"] == 200


# =============================================================================
# Websocket connection gating
# =============================================================================


class TestWebsocketGating:
    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_anonymous_connection_rejected(self):
        """No session cookie -> accept then close with WS_AUTH_REQUIRED_CODE."""
        from swarm.consumers import WS_AUTH_REQUIRED_CODE

        communicator = WebsocketCommunicator(
            application, WS_PATH, headers=VALID_ORIGIN_HEADERS
        )
        # Accept-then-close so browsers see close code 4401 (not opaque 1006).
        connected, _ = await communicator.connect()
        assert connected
        close_event = await communicator.receive_output(timeout=1)
        assert close_event["type"] == "websocket.close"
        assert close_event["code"] == WS_AUTH_REQUIRED_CODE
        await communicator.disconnect()

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_disallowed_origin_rejected(self):
        """Cross-site Origin is denied even when debug ALLOWED_HOSTS has ``*``."""
        communicator = WebsocketCommunicator(
            application,
            WS_PATH,
            headers=[(b"origin", b"http://evil.example.com"), (b"host", b"localhost")],
        )
        connected, _ = await communicator.connect()
        assert not connected
        await communicator.disconnect()

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_lan_same_origin_connects(self):
        """Phone on http://10.x.x.x:port is same-origin; handshake is not denied."""
        communicator = WebsocketCommunicator(
            application,
            WS_PATH,
            headers=[
                (b"origin", b"http://10.0.0.30:8002"),
                (b"host", b"10.0.0.30:8002"),
            ],
        )
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_unknown_ws_path_does_not_route(self):
        communicator = WebsocketCommunicator(
            application, "/ws/no-such-route/", headers=VALID_ORIGIN_HEADERS
        )
        # URLRouter raises "No route found for path ..."; depending on timing
        # it surfaces from connect() or from draining the application task.
        connected = False
        with pytest.raises(ValueError, match="No route found"):
            connected, _ = await communicator.connect()
            await communicator.wait()
        assert not connected

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_authenticated_session_connects(self):
        _, headers = await make_authenticated_headers("asgi-ws-connect")
        communicator = WebsocketCommunicator(application, WS_PATH, headers=headers)
        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()


# =============================================================================
# Authenticated round trip through the full stack
# =============================================================================


class TestWebsocketRoundTrip:
    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_send_message_receives_streamed_reply(self, monkeypatch):
        """connect -> send user message -> receive user echo, placeholder,
        streamed chunks and final message — over the real ASGI stack."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_MODEL", "test-model")
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

        _, headers = await make_authenticated_headers("asgi-ws-roundtrip")
        patcher, _client = mock_openai_streaming(("Hi", " there"))

        communicator = WebsocketCommunicator(application, WS_PATH, headers=headers)
        with patcher:
            connected, _ = await communicator.connect()
            assert connected
            await expect_spa_hello(communicator)

            await communicator.send_to(text_data=json.dumps({"message": "Ping?"}))

            # 1) the user's own message echoed back as an HTML partial
            user_html = await communicator.receive_from()
            assert "Ping?" in user_html

            # 2) the system placeholder with a contents div id
            placeholder_html = await communicator.receive_from()
            match = re.search(r'id="(message-response-[0-9a-f]+)"', placeholder_html)
            assert match, f"no contents div in placeholder: {placeholder_html!r}"
            contents_div_id = match.group(1)

            # 3) one OOB-swap frame per streamed chunk
            chunk1 = await communicator.receive_from()
            chunk2 = await communicator.receive_from()
            assert contents_div_id in chunk1 and "Hi" in chunk1
            assert contents_div_id in chunk2 and " there" in chunk2

            # 4) the final rendered assistant message
            final_html = await communicator.receive_from()
            assert "Hi there" in final_html

            await communicator.disconnect()


# =============================================================================
# Blueprint selection over the websocket (SPA parity with /v1/chat/completions)
# =============================================================================


# jeeves' SWARM_TEST_MODE canned answer (see blueprint_jeeves.run):
#   "[TEST-MODE] Jeeves at your service. You said: '<instruction>'"
JEEVES_CANNED_MARKER = "Jeeves at your service"

# First blueprint round trip pays for discovery + instantiation; be generous.
BP_TIMEOUT = 30


def _unique_ws_path(suffix=""):
    """Per-test conversation id: the consumer persists a ChatConversation on
    disconnect and conversation_id is unique, so tests must not share one."""
    import uuid

    return f"/ws/ai-demo/bp-{uuid.uuid4().hex[:12]}/{('?' + suffix) if suffix else ''}"


@pytest.fixture
def swarm_test_mode(monkeypatch):
    """Run blueprints on their deterministic SWARM_TEST_MODE canned path."""
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    # Keyless CI: some blueprints construct an OpenAI client even on the
    # test-mode path; a dummy key keeps things deterministic everywhere.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-test-mode")


async def expect_spa_hello(communicator, timeout=1):
    """REQ-78: authenticated connect advertises spa_version before chat frames."""
    raw = await communicator.receive_from(timeout=timeout)
    payload = json.loads(raw)
    assert payload.get("type") == SPA_HELLO_TYPE
    assert payload.get("spa_version")
    return payload


async def _drain_reply(communicator, prompt):
    """Send a prompt dict and collect (user_echo, placeholder, frames-until-final)."""
    await communicator.send_to(text_data=json.dumps(prompt))
    user_html = await communicator.receive_from(timeout=BP_TIMEOUT)
    placeholder_html = await communicator.receive_from(timeout=BP_TIMEOUT)
    match = re.search(r'id="(message-response-[0-9a-f]+)"', placeholder_html)
    assert match, f"no contents div in placeholder: {placeholder_html!r}"
    contents_div_id = match.group(1)
    # Frames until the final partial (which replaces the container via
    # hx-swap-oob="true" on the container id).
    frames = []
    while True:
        frame = await communicator.receive_from(timeout=BP_TIMEOUT)
        frames.append(frame)
        if f'id="{contents_div_id}"' in frame and 'hx-swap-oob="true"' in frame:
            break
    return user_html, contents_div_id, frames


class TestWebsocketBlueprintSelection:
    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_blueprint_field_selects_that_blueprints_reply(
        self, swarm_test_mode
    ):
        """{"message", "blueprint": "jeeves"} -> jeeves' canned test-mode answer."""
        _, headers = await make_authenticated_headers("asgi-ws-bp-field")
        communicator = WebsocketCommunicator(
            application, _unique_ws_path(), headers=headers
        )
        connected, _ = await communicator.connect()
        assert connected
        await expect_spa_hello(communicator)

        user_html, contents_div_id, frames = await _drain_reply(
            communicator, {"message": "ping", "blueprint": "jeeves"}
        )
        assert "ping" in user_html
        # Both the streamed chunk and the final partial carry jeeves' answer.
        assert any(JEEVES_CANNED_MARKER in frame for frame in frames[:-1])
        assert JEEVES_CANNED_MARKER in frames[-1]
        assert "ping" in frames[-1]

        await communicator.disconnect()

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_blueprint_query_param_sets_connection_default(
        self, swarm_test_mode
    ):
        """?blueprint=jeeves on the ws URL applies to plain {"message"} frames."""
        _, headers = await make_authenticated_headers("asgi-ws-bp-query")
        communicator = WebsocketCommunicator(
            application, _unique_ws_path("blueprint=jeeves"), headers=headers
        )
        connected, _ = await communicator.connect()
        assert connected
        await expect_spa_hello(communicator)

        _, _, frames = await _drain_reply(communicator, {"message": "ping"})
        assert JEEVES_CANNED_MARKER in frames[-1]

        await communicator.disconnect()

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_unknown_blueprint_returns_error_partial(self, swarm_test_mode):
        """An unknown blueprint id yields an error partial, not a crash, and
        the same socket still answers a follow-up with a valid blueprint."""
        _, headers = await make_authenticated_headers("asgi-ws-bp-unknown")
        communicator = WebsocketCommunicator(
            application, _unique_ws_path(), headers=headers
        )
        connected, _ = await communicator.connect()
        assert connected
        await expect_spa_hello(communicator)

        _, _, frames = await _drain_reply(
            communicator, {"message": "hello", "blueprint": "no-such-blueprint"}
        )
        assert "no-such-blueprint" in frames[-1]
        assert "not found" in frames[-1]

        # The socket survived: a valid blueprint still answers afterwards.
        _, _, frames = await _drain_reply(
            communicator, {"message": "still alive?", "blueprint": "jeeves"}
        )
        assert JEEVES_CANNED_MARKER in frames[-1]

        await communicator.disconnect()

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_no_blueprint_still_uses_default_model(self, monkeypatch):
        """Backward compat: frames without a blueprint keep the legacy
        OpenAI-client path (no blueprint involved)."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_MODEL", "test-model")
        monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

        _, headers = await make_authenticated_headers("asgi-ws-bp-compat")
        patcher, client = mock_openai_streaming(("legacy", " path"))
        communicator = WebsocketCommunicator(
            application, _unique_ws_path(), headers=headers
        )
        with patcher:
            connected, _ = await communicator.connect()
            assert connected
            await expect_spa_hello(communicator)
            _, _, frames = await _drain_reply(communicator, {"message": "ping"})
            assert "legacy path" in frames[-1]
            client.chat.completions.create.assert_awaited_once()
            await communicator.disconnect()

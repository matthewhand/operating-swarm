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
- the CLI seat (#424): the frame ChatPage sends — a `cli_agent` blueprint
  default plus `params: {mode, cli, model}` — reaches the cli seat, emits the
  REQ-92 "Started a new <cli> session." status frame, and answers; the socket
  then serves a differently-shaped turn
- the remote seat (#424): `params: {remote, target}` alone routes to the
  remote_harness blueprint, and a remote that was never configured is answered
  with a sentence rather than a JSON dump (issue #129 / REQ-890)
"""

import html
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

    def test_http_branch_has_no_debug_only_static_handler(self):
        from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

        # #423: this branch used to be wrapped in ASGIStaticFilesHandler, which
        # only served /static/ when DEBUG was on — production behind uvicorn
        # answered every asset with a Django 404 instead.
        http_app = application.application_mapping["http"]
        assert not isinstance(http_app, ASGIStaticFilesHandler)
        assert "whitenoise.middleware.WhiteNoiseMiddleware" in settings.MIDDLEWARE

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
                (b"origin", b"http://198.51.100.30:8002"),
                (b"host", b"198.51.100.30:8002"),
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


# =============================================================================
# The CLI and Remote kinds over the websocket (#424)
# =============================================================================
#
# This suite proved the blueprint kind and nothing else, so the two seats the
# SPA spends most of its time in were unproven: /v1/chat/completions is the
# curl / os-cli door, and a green PONG there exercises neither the session
# cookie, the Origin validator, nor the consumer's per-kind dispatch. These
# tests drive the frames ChatPage actually sends.

# ChatPage sends the CLI seat's binary/model in `params`, with the seat itself
# as the connection's blueprint default (?blueprint=cli_agent).
CLI_SEAT = "cli_agent"
CLI_FRAME_PARAMS = {
    "mode": "cli",
    "cli": "agy",
    "model": "gemini-3.8-flash-medium",
}

# A remote seat is selected by `params.remote` alone — no `blueprint` field.
REMOTE_SEAT = "remote_harness"


def _canned_for(blueprint_id: str, instruction: str) -> str:
    """The reply respond_with_blueprint returns in SWARM_TEST_MODE."""
    return f"[TEST-MODE] {blueprint_id} at your service. You said: '{instruction}'"


def _enable_canned_blueprints(monkeypatch) -> None:
    """Same environment as the `swarm_test_mode` fixture, applied explicitly.

    The fixture is requested by the blueprint tests for its side effect alone;
    naming the variables here keeps the dependency visible and adds no new
    unused-argument findings.
    """
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-test-mode")


async def _drain_turn(communicator, prompt):
    """Drive one turn and return every class of frame it puts on the wire.

    ``_drain_reply`` assumes the reply is the only thing a turn sends. The CLI
    and remote seats are not that simple, and the SPA has to render all of it:

    * ``notices`` — status frames before the assistant placeholder. A CLI turn
      adds the REQ-92 ``Started a new <cli> session.`` line here, which is also
      the proof that ``params.cli`` was read.
    * ``frames`` — the placeholder, the stream, and the final partial that
      replaces the container.
    * ``trailing`` — frames emitted after the reply, e.g. the ``context_usage``
      telemetry JSON. Explicitly drained: leaving them queued shifts every
      later turn on the same socket by one frame.
    """
    await communicator.send_to(text_data=json.dumps(prompt))
    user_html = await communicator.receive_from(timeout=BP_TIMEOUT)

    notices: list[str] = []
    placeholder_html = await communicator.receive_from(timeout=BP_TIMEOUT)
    while 'id="message-response-' not in placeholder_html:
        notices.append(placeholder_html)
        placeholder_html = await communicator.receive_from(timeout=BP_TIMEOUT)
    match = re.search(r'id="(message-response-[0-9a-f]+)"', placeholder_html)
    assert match, f"no contents div in placeholder: {placeholder_html!r}"
    contents_div_id = match.group(1)

    frames = [placeholder_html]
    while True:
        frame = await communicator.receive_from(timeout=BP_TIMEOUT)
        frames.append(frame)
        if f'id="{contents_div_id}"' in frame and 'hx-swap-oob="true"' in frame:
            break

    trailing: list[str] = []
    while not await communicator.receive_nothing(timeout=0.5):
        trailing.append(await communicator.receive_from(timeout=BP_TIMEOUT))
    return user_html, notices, frames, trailing


class TestWebsocketCliKind:
    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_params_cli_reaches_the_cli_seat_and_replies(self, monkeypatch):
        """The CLI frame shape answers, and the socket stays usable.

        #424's success criterion for this kind: a frame carrying ``params.cli``
        returns a reply, or a *named* error — never a socket abort. The caller
        learns which seat answered from the reply, so a dispatch regression
        (silently falling through to the default model) fails here.
        """
        _enable_canned_blueprints(monkeypatch)
        _, headers = await make_authenticated_headers("asgi-ws-cli-kind")
        communicator = WebsocketCommunicator(
            application, _unique_ws_path(f"blueprint={CLI_SEAT}"), headers=headers
        )
        connected, _ = await communicator.connect()
        assert connected
        await expect_spa_hello(communicator)

        instruction = "run the tests"
        user_html, notices, frames, trailing = await _drain_turn(
            communicator, {"message": instruction, "params": dict(CLI_FRAME_PARAMS)}
        )
        assert instruction in user_html
        # `params.cli` was read: the status line names the binary the session
        # was started for. This frame is unique to a CLI turn, so it is asserted
        # rather than tolerated.
        assert any("Started a new agy session." in notice for notice in notices), notices
        # The cli seat answered — not the default model, and not no one.
        assert _canned_for(CLI_SEAT, instruction) in html.unescape(frames[-1])
        # Anything after the reply is telemetry JSON, never more markup.
        assert all(frame.startswith("{") for frame in trailing), trailing

        # No abort: the same socket serves a second, differently-shaped turn.
        _, _, frames, _ = await _drain_turn(
            communicator, {"message": "still there?", "blueprint": "jeeves"}
        )
        assert JEEVES_CANNED_MARKER in frames[-1]

        await communicator.disconnect()


class TestWebsocketRemoteKind:
    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_params_remote_selects_the_remote_harness(self, monkeypatch):
        """`params: {remote, target}` is enough — no blueprint field needed.

        The SPA's remote seats send exactly this. The consumer has to translate
        it to the remote_harness blueprint itself, so falling back to the
        default model here would be invisible to the operator.
        """
        _enable_canned_blueprints(monkeypatch)
        _, headers = await make_authenticated_headers("asgi-ws-remote-kind")
        communicator = WebsocketCommunicator(
            application, _unique_ws_path(), headers=headers
        )
        connected, _ = await communicator.connect()
        assert connected
        await expect_spa_hello(communicator)

        instruction = "status?"
        user_html, notices, frames, _ = await _drain_turn(
            communicator,
            {"message": instruction, "params": {"remote": "hermes", "target": "w1:p1"}},
        )
        assert instruction in user_html
        # Replies are HTML; the canned text carries the prompt in &#x27; quotes.
        assert _canned_for(REMOTE_SEAT, instruction) in html.unescape(frames[-1])
        assert notices == [], f"a remote turn adds no status notice: {notices}"

        await communicator.disconnect()

    @pytest.mark.django_db(transaction=True)
    @pytest.mark.asyncio
    async def test_a_remote_that_was_never_added_fails_as_a_sentence(self, monkeypatch):
        """Without test mode the real harness runs: an unconfigured remote must
        come back as a sentence, not a JSON dump and not a dropped socket.

        This is the state a fresh install is in when the SPA offers every
        catalog seat (issue #129 / REQ-890), so the seat has to explain itself
        rather than answer with an internal identifier.
        """
        monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
        from swarm.core import remotes as remotes_core

        def _not_configured(*_args, **_kwargs):
            raise remotes_core.RemoteError("Remote 'hermes' is not configured")

        # Deterministic: do not depend on the developer's own remotes config.
        monkeypatch.setattr(remotes_core, "load_remote", _not_configured)

        _, headers = await make_authenticated_headers("asgi-ws-remote-unadded")
        communicator = WebsocketCommunicator(
            application, _unique_ws_path(), headers=headers
        )
        connected, _ = await communicator.connect()
        assert connected
        await expect_spa_hello(communicator)

        _, _, frames, _ = await _drain_turn(
            communicator,
            {"message": "hello", "params": {"remote": "hermes", "target": "w1:p1"}},
        )
        reply = html.unescape(frames[-1])
        # A sentence that names the remote and what is wrong with it.
        assert "hermes" in reply
        assert "not configured" in reply
        # Not a dump: no upstream JSON body and no raw gap identifier.
        assert "{" not in reply
        assert '"json"' not in reply

        # The socket survived: a second turn still gets an answer.
        _, _, frames, _ = await _drain_turn(
            communicator, {"message": "and now?", "params": {"remote": "hermes"}}
        )
        assert "hermes" in html.unescape(frames[-1])

        await communicator.disconnect()

    @pytest.mark.django_db
    @pytest.mark.asyncio
    async def test_server_managed_context_remote_submits_only_latest_turn(self, monkeypatch):
        """#851: Server-managed context remotes receive only the latest user turn."""
        from unittest.mock import AsyncMock, patch

        _, headers = await make_authenticated_headers("asgi-ws-server-managed")
        communicator = WebsocketCommunicator(
            application, _unique_ws_path(), headers=headers
        )
        connected, _ = await communicator.connect()
        assert connected
        await expect_spa_hello(communicator)

        captured_messages = []

        class _MockBlueprint:
            server_managed_context = True

            async def run(self, messages, **kwargs):
                captured_messages.append(list(messages))
                yield {"content": "server managed reply"}

        with patch("swarm.views.utils.get_blueprint_instance", new=AsyncMock(return_value=_MockBlueprint())):
            # 1. First turn
            await _drain_turn(
                communicator,
                {"message": "turn 1", "params": {"remote": "letta", "target": "c1:t1"}},
            )
            assert len(captured_messages) == 1
            assert captured_messages[-1] == [{"role": "user", "content": "turn 1"}]

            # 2. Second turn: should receive ONLY turn 2, omitting prior history
            await _drain_turn(
                communicator,
                {"message": "turn 2", "params": {"remote": "letta", "target": "c1:t1"}},
            )
            assert len(captured_messages) == 2
            assert len(captured_messages[-1]) == 1
            assert captured_messages[-1][0]["content"] == "turn 2"

        await communicator.disconnect()


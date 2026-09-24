"""ADR-017 PR-3 — the SPA multiplex websocket contracts (REQ-925 / #1118).

Hermetic: WebsocketCommunicator drives the real mux against real headless
``DjangoChatConsumer`` workers. The reply boundary is stubbed at the same
seams ``tests/test_consumers.py`` uses (``render_to_string``, demo-mode
responder), so no test touches the network while the auth path (4401 /
preview user) and the frame-tagging transport are exercised for real.

Harness warning: asgiref's ``receive_output`` **cancels the application
task when its timeout expires** (it assumes a quiet app means a finished
one). Never drain with retry-until-timeout loops — read exactly the frames
the protocol owes you, or use ``receive_nothing()`` for quiet assertions.
"""

from __future__ import annotations

import json
import uuid
from unittest import mock

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User

from swarm.consumers import SPA_HELLO_TYPE, WS_AUTH_REQUIRED_CODE, DjangoChatConsumer
from swarm.models import ChatMessage
from swarm.spa_multiplex import MAX_SESSIONS_PER_SOCKET, SpaMultiplexConsumer


def _mux_communicator(user=None):
    communicator = WebsocketCommunicator(SpaMultiplexConsumer.as_asgi(), "/ws/spa/")
    communicator.scope["user"] = user
    communicator.scope["url_route"] = {"kwargs": {}}
    return communicator


async def _authorized_mux():
    # Unique username: database_sync_to_async runs on a separate connection,
    # so rows commit outside pytest-django's per-test transaction rollback.
    user = await database_sync_to_async(User.objects.create_user)(
        username=f"spa-mux-{uuid.uuid4().hex[:10]}", email="s@x.io", password="pw"
    )
    return _mux_communicator(user)


async def _read(communicator, n, timeout=3.0):
    """Read exactly n socket events — never a drain-to-timeout loop."""
    out = []
    for _ in range(n):
        out.append(await communicator.receive_output(timeout=timeout))
    return out


async def _read_ack(communicator, conversation_id, max_events=3, timeout=3.0):
    """Read until the mux ack for ``conversation_id`` arrives (bounded).

    The worker's best-effort ``spa_hello`` may precede or follow the ack (or
    fail silently), so the ack's position isn't fixed; early-exit on the ack
    guarantees we never read past what the protocol owes us.
    """
    seen = []
    for _ in range(max_events):
        event = await communicator.receive_output(timeout=timeout)
        seen.extend(_parse([event]))
        if any(
            f.get("kind") == "spa.subscribed" and f.get("conversationId") == conversation_id
            for f in seen
        ):
            return seen
    raise AssertionError(f"no spa.subscribed ack for {conversation_id} within {seen}")


def _parse(events):
    frames = []
    for event in events:
        if event.get("type") != "websocket.send":
            continue
        try:
            frames.append(json.loads(event.get("text") or "{}"))
        except ValueError:
            continue
    return frames


def _spa_frames(events):
    return [f for f in _parse(events) if f.get("kind") == "spa.frame"]


def _tagged_types(events, conversation_id):
    return [
        (f.get("data") or {}).get("type")
        for f in _spa_frames(events)
        if f.get("conversationId") == conversation_id
    ]


async def _read_until_finished(communicator, conversation_ids, limit=48, timeout=5.0):
    """Collect events until every conversation's turn_finished arrived."""
    events, finished = [], set()
    while len(events) < limit and finished != set(conversation_ids):
        event = await communicator.receive_output(timeout=timeout)
        events.append(event)
        for frame in _parse([event]):
            if (
                frame.get("kind") == "spa.frame"
                and frame.get("conversationId") in conversation_ids
                and (frame.get("data") or {}).get("type") == "turn_finished"
            ):
                finished.add(frame["conversationId"])
    return events


@pytest.mark.django_db
class TestSpaMultiplexAuth:
    @pytest.mark.asyncio
    async def test_unauthenticated_socket_closed_4401(self, settings):
        settings.SWARM_ALLOW_ANONYMOUS = False
        communicator = _mux_communicator()
        connected, _ = await communicator.connect()
        assert connected
        event = await communicator.receive_output(timeout=1)
        assert event["type"] == "websocket.close"
        assert event["code"] == WS_AUTH_REQUIRED_CODE
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_anonymous_allowed_gets_preview_session(self):
        communicator = _mux_communicator()
        with mock.patch("swarm.spa_multiplex.swarm_allow_anonymous", return_value=True):
            connected, _ = await communicator.connect()
            assert connected
            await communicator.send_to(
                json.dumps({"kind": "subscribe", "conversationId": "conv-anon"})
            )
            seen = await _read_ack(communicator, "conv-anon")
        # the session actually started: the mux acknowledged the subscription
        assert any(f.get("kind") == "spa.subscribed" for f in seen), seen
        await communicator.disconnect()


@pytest.mark.django_db
class TestSpaMultiplexProtocol:
    @pytest.mark.asyncio
    async def test_subscribe_ack_and_tagged_hello(self):
        communicator = await _authorized_mux()
        await communicator.connect()
        await communicator.send_to(
            json.dumps({"kind": "subscribe", "conversationId": "conv-1"})
        )
        seen = await _read_ack(communicator, "conv-1")
        assert any(
            f.get("kind") == "spa.subscribed" and f.get("conversationId") == "conv-1"
            for f in seen
        )
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_missing_conversation_id_yields_spa_error(self):
        communicator = await _authorized_mux()
        await communicator.connect()
        await communicator.send_to(json.dumps({"kind": "subscribe"}))
        frames = _parse(await _read(communicator, 1))
        assert frames[0]["kind"] == "spa.error"
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_unknown_kind_yields_spa_error(self):
        communicator = await _authorized_mux()
        await communicator.connect()
        await communicator.send_to(json.dumps({"kind": "wat", "conversationId": "conv-1"}))
        frames = _parse(await _read(communicator, 1))
        assert frames[0]["kind"] == "spa.error"
        assert "wat" in frames[0]["error"]
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_subscription_cap(self):
        communicator = await _authorized_mux()
        await communicator.connect()
        for i in range(MAX_SESSIONS_PER_SOCKET):
            await communicator.send_to(
                json.dumps({"kind": "subscribe", "conversationId": f"conv-{i}"})
            )
        # each subscribe owes exactly one mux ack (see _read_ack re: the
        # best-effort hello's unstable position)
        acks = []
        for i in range(MAX_SESSIONS_PER_SOCKET):
            seen = await _read_ack(communicator, f"conv-{i}")
            acks.extend(f for f in seen if f.get("kind") == "spa.subscribed")
        assert len(acks) == MAX_SESSIONS_PER_SOCKET
        await communicator.send_to(
            json.dumps({"kind": "subscribe", "conversationId": "conv-overflow"})
        )
        frames = _parse(await _read(communicator, 1))
        assert frames[0]["kind"] == "spa.error"
        assert frames[0]["conversationId"] == "conv-overflow"
        await communicator.disconnect()


async def _echo_responder(self, contents_div_id, message_text, params=None):
    """Stand-in for the demo responder: one HTML partial + REQ-171A-2 persist.

    The real ``respond_with_demo`` ends by calling
    ``_persist_completed_turn``; the stand-in must honour that contract or
    the store assertion below would be testing a responder that never
    existed.
    """
    await self.send(text_data=f"<div id='{contents_div_id}'>echo {message_text}</div>")
    await self._persist_completed_turn()


def _turn_patches():
    return (
        mock.patch("swarm.consumers.render_to_string", return_value="<div>partial</div>"),
        mock.patch("swarm.demo.is_demo_mode", return_value=True),
        mock.patch.object(DjangoChatConsumer, "respond_with_demo", _echo_responder),
    )


@pytest.mark.django_db
class TestSpaMultiplexTurns:
    @pytest.mark.asyncio
    async def test_turn_streams_tagged_and_persists_conversation(self):
        communicator = await _authorized_mux()
        await communicator.connect()
        await communicator.send_to(
            json.dumps({"kind": "subscribe", "conversationId": "conv-turn"})
        )
        await _read_ack(communicator, "conv-turn")

        patches = _turn_patches()
        with patches[0], patches[1], patches[2]:
            await communicator.send_to(
                json.dumps(
                    {"kind": "chat.send", "conversationId": "conv-turn", "message": "hi"}
                )
            )
            events = await _read_until_finished(communicator, {"conv-turn"})

        tagged = _spa_frames(events)
        assert tagged, "expected tagged frames from the turn"
        for frame in tagged:
            assert frame["conversationId"] == "conv-turn"
        types = _tagged_types(events, "conv-turn")
        assert "turn_started" in types
        assert "turn_finished" in types
        # the responder's HTML partial rode through as a tagged text frame
        assert any(
            isinstance(f.get("data"), dict) and f["data"].get("text") and "hi" in f["data"]["text"]
            for f in tagged
        )
        # the worker is the real consumer: the turn landed in the store
        count = await ChatMessage.objects.filter(
            conversation__conversation_id="conv-turn"
        ).acount()
        assert count > 0
        await communicator.disconnect()

    @pytest.mark.asyncio
    async def test_two_conversations_interleave_on_one_socket(self):
        communicator = await _authorized_mux()
        await communicator.connect()
        for cid in ("conv-A", "conv-B"):
            await communicator.send_to(
                json.dumps({"kind": "subscribe", "conversationId": cid})
            )
        await _read(communicator, 4)  # 2× (hello frame + ack)

        patches = _turn_patches()
        with patches[0], patches[1], patches[2]:
            for cid, text in (("conv-A", "aa"), ("conv-B", "bb")):
                await communicator.send_to(
                    json.dumps({"kind": "chat.send", "conversationId": cid, "message": text})
                )
            events = await _read_until_finished(communicator, {"conv-A", "conv-B"})

        for cid, text in (("conv-A", "aa"), ("conv-B", "bb")):
            frames = [f for f in _spa_frames(events) if f["conversationId"] == cid]
            assert frames, f"no tagged frames for {cid}"
            types = _tagged_types(events, cid)
            assert "turn_started" in types and "turn_finished" in types
            assert any(
                (f.get("data") or {}).get("text") and text in str(f["data"].get("text"))
                for f in frames
            ), f"{cid} missing its own reply payload"
        await communicator.disconnect()

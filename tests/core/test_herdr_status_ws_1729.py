"""#1729 — the Herdr status websocket (the push transport).

Herdr seat status rides its **own** socket, not the SPA multiplex: the mux is
a strict per-conversation transport whose contract is that every frame is a
reply to something the client asked for, so unsolicited seat status would
interleave frames nobody requested. These tests pin that separation as much as
the forwarding itself — a status frame arriving on a chat socket is the defect
this design exists to prevent.

NEW file for #1729; it does not edit ``tests/test_spa_multiplex.py``, which
another agent may own.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from channels.testing import WebsocketCommunicator

from swarm.core import herdr_status_watch as watch
from swarm.herdr_status_ws import HerdrStatusConsumer


@pytest.fixture(autouse=True)
def _clean_status_registry():
    watch.reset_status_consumers_for_tests()
    watch.reset_monitor_for_tests()
    yield
    watch.reset_status_consumers_for_tests()
    watch.reset_monitor_for_tests()


async def _wait_for_consumer_count(expected: int, timeout: float = 2.0) -> None:
    """Wait for the registry to reach ``expected`` consumers.

    Registration resolves the user key through `database_sync_to_async`, so it
    lands on a later turn of the loop than `connect()` returns on. Polling here
    is not a sleep-and-hope: it fails loudly if the count never arrives.
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while watch.registered_consumer_count() != expected:
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(
                f"consumer count never reached {expected} "
                f"(is {watch.registered_consumer_count()})"
            )
        await asyncio.sleep(0.01)


@pytest.fixture
def no_live_poller(monkeypatch):
    """Registration arms the watcher, whose client is this host's real Herdr.

    A transport test must never inherit a background thread talking to a live
    TUI, so the monitor is replaced with a non-autostarting stub.
    """
    stub = watch.HerdrStatusMonitor(autostart=False)
    monkeypatch.setattr(watch, "get_monitor", lambda: stub)
    return stub


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_a_status_event_reaches_a_connected_socket(no_live_poller):
    communicator = WebsocketCommunicator(HerdrStatusConsumer.as_asgi(), "/ws/herdr-status/")
    communicator.scope["user"] = None
    # Anonymous is refused with 4401 unless the host allows it; mint a user the
    # same way the app does so the happy path is what is under test.
    from channels.db import database_sync_to_async
    from django.contrib.auth.models import User

    user = await database_sync_to_async(User.objects.create_user)(
        username="herdr-status-ws", password="pw"
    )
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected

    watch._publish_to_consumers(
        {
            "type": "herdr_status",
            "seat_id": "herdr:w3:p1",
            "target": "w3:p1",
            "status": "waiting",
            "herdr_status": "blocked",
            "needs_input": True,
            "mark_unread": False,
        }
    )
    event = await asyncio.wait_for(communicator.receive_output(timeout=3.0), timeout=5.0)
    assert event["type"] == "websocket.send"
    frame = json.loads(event["text"])
    assert frame["type"] == "herdr_status"
    assert frame["seat_id"] == "herdr:w3:p1"
    assert frame["status"] == "waiting"
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_a_closing_socket_stops_receiving(no_live_poller):
    """A leaked registration would keep a dead queue filling, and the watcher
    would hold that buffer forever."""
    from channels.db import database_sync_to_async
    from django.contrib.auth.models import User

    user = await database_sync_to_async(User.objects.create_user)(
        username="herdr-status-ws-gone", password="pw"
    )
    # Counted BEFORE connecting, or the leak has already happened by the time
    # the baseline is taken and the assertion is vacuous.
    baseline = watch.registered_consumer_count()
    communicator = WebsocketCommunicator(HerdrStatusConsumer.as_asgi(), "/ws/herdr-status/")
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected
    # Registration crosses a `database_sync_to_async` hop, so it lands on a
    # later turn of the loop than `connect()` returns on. Poll for it rather
    # than assuming it is already there.
    await _wait_for_consumer_count(baseline + 1)

    await communicator.disconnect()

    # Asserted on the registry, not on "nothing arrived": a leak is invisible
    # to a receive-nothing check, because the dead socket is nobody left to
    # notice the queue still filling.
    assert watch.registered_consumer_count() == baseline


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_registration_failure_does_not_close_the_socket(monkeypatch):
    """Status is an enhancement. A failing feed must leave a usable socket."""
    from channels.db import database_sync_to_async
    from django.contrib.auth.models import User

    user = await database_sync_to_async(User.objects.create_user)(
        username="herdr-status-ws-boom", password="pw"
    )
    import swarm.core.herdr_status_watch as registry

    original = registry.register_status_consumer

    def boom(*_args, **_kwargs):
        raise RuntimeError("channel layer unavailable")

    monkeypatch.setattr(registry, "register_status_consumer", boom)
    communicator = WebsocketCommunicator(HerdrStatusConsumer.as_asgi(), "/ws/herdr-status/")
    communicator.scope["user"] = user
    connected, _ = await communicator.connect()
    assert connected, "a failed status feed took the socket down with it"
    # Restored only for the assertion's own clarity; the socket is already up.
    monkeypatch.setattr(registry, "register_status_consumer", original)
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_the_socket_ignores_inbound_frames(no_live_poller):
    """Push-only. Answering a client frame would imply a request/response
    contract this socket does not have."""
    from channels.db import database_sync_to_async
    from django.contrib.auth.models import User

    user = await database_sync_to_async(User.objects.create_user)(
        username="herdr-status-ws-oneway", password="pw"
    )
    communicator = WebsocketCommunicator(HerdrStatusConsumer.as_asgi(), "/ws/herdr-status/")
    communicator.scope["user"] = user
    await communicator.connect()
    await communicator.send_to(text_data=json.dumps({"type": "please-status"}))
    await asyncio.sleep(0.05)
    # Nothing is owed, so nothing is answered.
    assert await communicator.receive_nothing(timeout=0.2)
    await communicator.disconnect()


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_status_does_not_arrive_on_the_chat_multiplex(no_live_poller):
    """The separation, asserted. A status frame on the mux would interleave
    with chat frames the client never asked for."""
    from channels.db import database_sync_to_async
    from django.contrib.auth.models import User

    from swarm.spa_multiplex import SpaMultiplexConsumer

    user = await database_sync_to_async(User.objects.create_user)(
        username="herdr-status-mux-guard", password="pw"
    )
    mux = WebsocketCommunicator(SpaMultiplexConsumer.as_asgi(), "/ws/spa/")
    mux.scope["user"] = user
    mux.scope["url_route"] = {"kwargs": {}}
    await mux.connect()

    watch._publish_to_consumers(
        {"type": "herdr_status", "seat_id": "herdr:w3:p1", "status": "waiting"}
    )
    assert await mux.receive_nothing(timeout=0.3)
    await mux.disconnect()

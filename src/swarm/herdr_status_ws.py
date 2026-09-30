"""#1729 — the Herdr status websocket.

A Herdr pane's status belongs to **no conversation**, and that is exactly why
it does not ride the SPA multiplex socket
(:mod:`swarm.spa_multiplex`). That socket is a strict per-conversation
transport: its tests read an exact number of frames, because every frame on it
is a reply to something the client asked for. Pushing unsolicited seat status
down it interleaves frames nobody requested and breaks that contract — and it
would open a *chat* socket on a page that has no chat, which is its own lie.

So this is a small, dedicated socket:

    ws(s)://<host>/ws/herdr-status/

It sends exactly one thing — ``{"type": "herdr_status", ...}`` per transition —
and accepts nothing. Registration and teardown mirror the mux's
``register_consumer`` pattern so the two share the watcher without either
owning it.

Auth mirrors the mux: session cookie via ``AuthMiddlewareStack``, and an
anonymous socket closes with 4401. Status is per-user; an unminted socket must
not collect anyone else's.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from channels.generic.websocket import AsyncWebsocketConsumer

from swarm.consumers import WS_AUTH_REQUIRED_CODE
from swarm.middleware import client_ip_from_scope, swarm_allow_anonymous

logger = logging.getLogger(__name__)

#: One frame of headroom past the watcher's own per-tick cap, so a slow reader
#: loses frames rather than growing memory without bound.
QUEUE_MAXSIZE = 200


class HerdrStatusConsumer(AsyncWebsocketConsumer):
    """Pushes Herdr seat-status transitions to one user."""

    async def connect(self) -> None:
        self.user = self.scope.get("user")
        self._queue: Optional[asyncio.Queue] = None
        self._task: Optional[asyncio.Task] = None
        await self.accept()

        if not getattr(self.user, "is_authenticated", False):
            if swarm_allow_anonymous(client_ip_from_scope(self.scope)):
                from channels.db import database_sync_to_async

                from swarm.consumers import get_or_create_preview_user

                try:
                    self.user = await database_sync_to_async(get_or_create_preview_user)()
                    self.scope["user"] = self.user
                except Exception:
                    logger.exception(
                        "herdr status preview user mint failed; closing with 4401"
                    )
                    await self.close(
                        code=WS_AUTH_REQUIRED_CODE, reason="authentication required"
                    )
                    return
            else:
                await self.close(
                    code=WS_AUTH_REQUIRED_CODE, reason="authentication required"
                )
                return

        await self._start_feed()

    async def _start_feed(self) -> None:
        """Best-effort. A status feed must never stop the socket accepting."""
        try:
            from channels.db import database_sync_to_async

            from swarm.core import chat_store, herdr_status_watch

            self._queue = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
            user_key = await database_sync_to_async(chat_store.user_key_for)(self.user)
            herdr_status_watch.register_status_consumer(
                user_key,
                self._queue,
                loop=asyncio.get_running_loop(),
            )
            self._task = asyncio.ensure_future(self._drain())
        except Exception:
            logger.debug("herdr status feed registration failed", exc_info=True)

    async def _drain(self) -> None:
        queue = self._queue
        if queue is None:
            return
        while True:
            try:
                event = await queue.get()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("herdr status queue read failed", exc_info=True)
                return
            try:
                await self.send(json.dumps(event))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("herdr status send failed", exc_info=True)
                return

    async def receive(self, text_data=None, bytes_data=None) -> None:
        """This socket is one-way. Anything sent is a protocol error, ignored.

        Not closed: the client library may probe. Refusing to answer is the
        honest contract for a push-only channel.
        """
        return

    async def disconnect(self, close_code) -> None:
        if self._task is not None:
            self._task.cancel()
        if self._queue is not None:
            try:
                from swarm.core import herdr_status_watch

                herdr_status_watch.unregister_status_consumer(self._queue)
            except Exception:
                logger.debug("herdr status feed cleanup failed", exc_info=True)
        self._task = None
        self._queue = None

"""ADR-017 PR-3 — the SPA multiplex websocket (REQ-925 / #1118).

Today the SPA opens **one websocket per mounted chat**
(``/ws/ai-demo/<conversation_id>/``). Switching agents tears the old socket
down, so an in-flight turn on agent A stops streaming the moment the user
looks at agent B — and the ADR-017 turn bookends (#1113/#1117) die with it.
That is the root cause of #1118 and the wall in front of concurrent
per-agent turns (#1097 / ADR-017).

This module adds a **single multiplexed socket** for the whole SPA:

    ws(s)://<host>/ws/spa/

Client -> server frames (JSON):

    {"kind": "subscribe",   "conversationId": "<id>"}
    {"kind": "unsubscribe", "conversationId": "<id>"}
    {"kind": "chat.send",   "conversationId": "<id>", ...legacy frame fields}

Server -> client frames are the legacy consumer's frames **tagged** with the
conversation they belong to:

    {"kind": "spa.frame", "conversationId": "<id>", "data": <legacy frame>}

Lifecycle:

- ``subscribe`` binds the conversation to a **sticky session** — a headless
  :class:`~swarm.consumers.DjangoChatConsumer` whose ``base_send`` is
  redirected into the multiplex socket. The session outlives its
  subscriptions, so background turn output (including turn bookends) keeps
  flowing after an ``unsubscribe``; sessions are disposed when their socket
  closes. Cross-tab session adoption is ADR-017 PR-4 / #1097 territory.
- ``chat.send`` drives the session's real ``websocket_receive`` handler, so
  per-conversation turn locks, transcripts, bookends and elicitations keep
  working unchanged — the worker *is* the real consumer.
- The legacy endpoint stays untouched — it is the per-socket escape hatch
  and keeps the Django-template HTMx UI working.

Auth mirrors the legacy consumer: session cookie via ``AuthMiddlewareStack``;
anonymous sockets are allowed only when ``swarm_allow_anonymous`` says so,
and the mux closes them with 4401 otherwise.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from channels.generic.websocket import AsyncWebsocketConsumer

from swarm.consumers import DjangoChatConsumer, WS_AUTH_REQUIRED_CODE
from swarm.middleware import client_ip_from_scope, swarm_allow_anonymous

logger = logging.getLogger(__name__)

SPA_FRAME_TAG = "spa.frame"
MAX_SESSIONS_PER_SOCKET = 8


class SpaSession:
    """One sticky per-conversation worker inside a multiplex socket."""

    def __init__(
        self, mux: "SpaMultiplexConsumer", conversation_id: str, blueprint: Optional[str] = None
    ) -> None:
        self.mux = mux
        self.conversation_id = conversation_id
        self.blueprint = blueprint
        self.subscriptions = 0
        self.worker: Optional[DjangoChatConsumer] = None
        self.lock = asyncio.Lock()
        # Set by the collector when the worker's connect() ends the
        # headless lifecycle (e.g. 4401 auth rejection).
        self.rejected_code: Optional[int] = None

    def _make_collector(self):
        """Return a ``base_send`` replacement that tags worker output.

        Every generic-consumer reply (``accept`` / ``send`` / ``close``)
        funnels through ``base_send`` — capturing it intercepts the whole
        outbound side of the legacy consumer without touching its code.
        """

        async def collector(event: Dict[str, Any]) -> None:
            kind = event.get("type")
            if kind == "websocket.send":
                text = event.get("text")
                try:
                    inner = json.loads(text) if isinstance(text, str) else {}
                except ValueError:
                    inner = {"text": text}
                await self.mux.tagged_send(self.conversation_id, inner)
            elif kind == "websocket.close":
                self.rejected_code = int(event.get("code") or 1000)
            # websocket.accept is meaningless headless — swallow it.

        return collector

    async def ensure_worker(self) -> DjangoChatConsumer:
        async with self.lock:
            if self.worker is not None:
                return self.worker
            worker = DjangoChatConsumer({})
            worker.channel_name = f"spa-mux:{id(self)}"
            worker.channel_layer = None
            worker.scope = dict(self.mux.scope)
            worker.scope["url_route"] = {"kwargs": {"conversation_id": self.conversation_id}}
            worker.scope["spa_headless"] = True
            if self.blueprint:
                worker.scope["query_string"] = f"blueprint={self.blueprint}".encode()
            worker.base_send = self._make_collector()  # type: ignore[method-assign]
            self.worker = worker
            try:
                await worker.connect()
            except Exception:
                logger.exception(
                    "spa session %s worker connect failed", self.conversation_id
                )
                self.worker = None
                raise
            if self.rejected_code is not None:
                # Worker refused (auth). Surface as an error frame; caller
                # drops the session.
                await self.mux.send(
                    json.dumps(
                        {
                            "kind": "spa.error",
                            "conversationId": self.conversation_id,
                            "error": "session rejected",
                            "code": self.rejected_code,
                        }
                    )
                )
            return worker

    async def dispatch(self, text: str) -> None:
        worker = self.worker
        if worker is None:
            return
        try:
            await worker.websocket_receive({"type": "websocket.receive", "text": text})
        except Exception:
            logger.exception(
                "spa session %s failed to handle frame; disposing", self.conversation_id
            )
            await self.dispose()

    async def dispose(self) -> None:
        async with self.lock:
            worker, self.worker = self.worker, None
        if worker is None:
            return
        try:
            await worker.disconnect(1001)
        except Exception:
            logger.exception("spa session %s dispose failed", self.conversation_id)


class SpaMultiplexConsumer(AsyncWebsocketConsumer):
    """Whole-SPA socket; every frame tagged with its conversation."""

    async def connect(self) -> None:
        self.user = self.scope.get("user")
        self.sessions: Dict[str, SpaSession] = {}
        await self.accept()

        authenticated = bool(getattr(self.user, "is_authenticated", False))
        if not authenticated:
            if swarm_allow_anonymous(client_ip_from_scope(self.scope)):
                from channels.db import database_sync_to_async

                from swarm.consumers import get_or_create_preview_user

                try:
                    self.user = await database_sync_to_async(get_or_create_preview_user)()
                    self.scope["user"] = self.user
                except Exception:
                    logger.exception("mux preview user mint failed; closing with 4401")
                    await self.close(code=WS_AUTH_REQUIRED_CODE, reason="authentication required")
            else:
                await self.close(code=WS_AUTH_REQUIRED_CODE, reason="authentication required")

    async def disconnect(self, close_code: int) -> None:
        for session in list(getattr(self, "sessions", {}).values()):
            await session.dispose()
        self.sessions = {}

    async def receive(self, text_data: Optional[str] = None, bytes_data=None) -> None:
        try:
            frame = json.loads(text_data or "{}")
        except (TypeError, ValueError):
            await self._send_error("frame is not valid JSON")
            return
        kind = frame.get("kind")
        conversation_id = str(frame.get("conversationId") or "").strip()
        if not conversation_id:
            await self._send_error("frame missing conversationId")
            return

        if kind == "subscribe":
            await self._subscribe(conversation_id, frame.get("blueprint"))
        elif kind == "unsubscribe":
            session = self.sessions.get(conversation_id)
            if session is not None:
                # Sticky: keep the worker alive at zero subscriptions so
                # background turns keep streaming (#1118). Disposal happens
                # when the socket closes.
                session.subscriptions = max(0, session.subscriptions - 1)
        elif kind == "chat.send":
            session = self.sessions.get(conversation_id)
            if session is None:
                # Implicit sticky subscribe — a turn addressed to an unknown
                # conversation spins its session up rather than erroring.
                session = await self._create_session(
                    conversation_id, frame.get("blueprint")
                )
                if session is None:
                    return
            await session.dispatch(json.dumps(frame))
        else:
            await self._send_error(f"unknown frame kind: {kind!r}", conversation_id)

    async def _subscribe(self, conversation_id: str, blueprint: Optional[str] = None) -> None:
        if (
            len(self.sessions) >= MAX_SESSIONS_PER_SOCKET
            and conversation_id not in self.sessions
        ):
            await self._send_error("too many concurrent subscriptions", conversation_id)
            return
        session = self.sessions.get(conversation_id)
        if session is None:
            session = await self._create_session(conversation_id, blueprint)
            if session is None:
                return
        session.subscriptions += 1
        await self.send(
            json.dumps({"kind": "spa.subscribed", "conversationId": conversation_id})
        )

    async def _create_session(
        self, conversation_id: str, blueprint: Optional[str] = None
    ) -> Optional[SpaSession]:
        if (
            len(self.sessions) >= MAX_SESSIONS_PER_SOCKET
            and conversation_id not in self.sessions
        ):
            await self._send_error("too many concurrent subscriptions", conversation_id)
            return None
        session = SpaSession(self, conversation_id, blueprint)
        self.sessions[conversation_id] = session
        try:
            await session.ensure_worker()
        except Exception:
            self.sessions.pop(conversation_id, None)
            await self._send_error("session failed to start", conversation_id)
            return None
        if session.rejected_code is not None:
            self.sessions.pop(conversation_id, None)
            await session.dispose()
            return None
        return session

    async def tagged_send(self, conversation_id: str, inner: Dict[str, Any]) -> None:
        await self.send(
            json.dumps({"kind": SPA_FRAME_TAG, "conversationId": conversation_id, "data": inner})
        )

    async def _send_error(self, message: str, conversation_id: str = "") -> None:
        await self.send(
            json.dumps({"kind": "spa.error", "error": message, "conversationId": conversation_id})
        )

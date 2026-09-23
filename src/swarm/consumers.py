import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.template.loader import render_to_string
from django.utils.html import escape

from swarm.models import ChatConversation, ChatMessage
from swarm.middleware import (
    client_ip_from_scope,
    get_or_create_preview_user,
    swarm_allow_anonymous,
)

logger = logging.getLogger(__name__)

# Lazy sentinel — replaced on first use so the module-level name is patchable in tests.
AsyncOpenAI = None

# In-memory conversation storage (populated lazily).
# Keys are (user_id, conversation_id) to prevent cross-user cache IDOR.
IN_MEMORY_CONVERSATIONS = {}
# Side-channel UI chrome keyed the same way as IN_MEMORY_CONVERSATIONS.
IN_MEMORY_UI_EVENTS = {}

# Custom close code for anonymous connects (HTTP 401 analogue). Accept-then-close
# so browsers receive a CloseEvent with this code instead of opaque 1006.
WS_AUTH_REQUIRED_CODE = 4401

# #198: client -> server turn-cancel request ({"type": "cancel_turn"});
# server -> client acknowledgement {"type": "turn_cancelled"}. The ack is
# consumed by the WS parser as a status line, not a new event kind.
TURN_CANCELLED_TYPE = "turn_cancelled"
# #818: auxiliary/background LLM inference visibility.
AUX_START_TYPE = "aux_task_started"
AUX_UPDATE_TYPE = "aux_task_update"
AUX_CANCEL_TYPE = "cancel_auxiliary"

# REQ-78 / #423 — advertise the backend's expected SPA bake on connect.
SPA_HELLO_TYPE = "spa_hello"


from .chat.advice_mixin import AdviceMixin  # noqa: E402
from .chat.conversations_mixin import ConversationsMixin  # noqa: E402
from .chat.stubs_mixin import StubsMixin  # noqa: E402


class DjangoChatConsumer(AdviceMixin, ConversationsMixin, StubsMixin, AsyncWebsocketConsumer):
    """Websocket chat consumer.

    Client -> server frames are JSON: ``{"message": "<text>"}`` with an
    optional ``"blueprint": "<id>"`` field selecting which discovered
    blueprint generates the reply. A connection-level default can also be
    set via the ws URL query string (``?blueprint=<id>``); a per-message
    ``blueprint`` field overrides it. When neither is given, the legacy
    behaviour (server-configured OpenAI model) is preserved.

    Team compose (REQ-23) sends ``params: {team, target: "all"|memberId}``.
    Runtime for that path is stubbed until a real roster executor exists.

    Auth is Django **session** only (``AuthMiddlewareStack`` cookie). A
    Settings-page API bearer token does not authenticate this socket.

    Chat turns (``{"message": ...}``) are serialised per connection
    (REQ-171A-3 / #603). Overlapping frames queue on ``_chat_turn_lock``
    so ``self.messages`` and HTML frames cannot interleave. SPA composer
    queue chrome is REQ-90 / #447 — this lock is the transcript-correctness
    boundary. ``tool_decision``, ``question_answer``, ``status``, and
    ``edit`` frames stay off that lock so an in-flight ``respond_with_*``
    can still elicit tool approval or an ``ask_user`` question.
    """

    def _ensure_chat_turn_lock(self):
        lock = getattr(self, "_chat_turn_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            self._chat_turn_lock = lock
        return lock

    async def connect(self):
        self._ensure_chat_turn_lock()
        self.user = self.scope["user"]
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        # Optional connection-level default blueprint (?blueprint=<id>).
        query_params = parse_qs(self.scope.get("query_string", b"").decode())
        self.default_blueprint = (query_params.get("blueprint") or [None])[0]
        self.messages = []
        self.ui_events = []
        # Accept before any DB/thread work. A wedged CurrentThreadExecutor
        # used to hang handshake (HANDSHAKING, never CONNECT) and loop /chat.
        await self.accept()

        try:
            if (not getattr(self.user, "is_authenticated", False)) and swarm_allow_anonymous(
                client_ip_from_scope(self.scope)
            ):
                try:
                    self.user = await database_sync_to_async(get_or_create_preview_user)()
                except Exception:
                    logger.exception(
                        "Preview user mint failed for conversation %s; keeping socket open",
                        self.conversation_id,
                    )
                    return
            if getattr(self.user, "is_authenticated", False):
                await self._send_spa_hello()
                self.active_agent = self.default_blueprint
                self._pending_tool_decisions = {}
                self._pending_question_answers = {}
                try:
                    self.messages = await self.fetch_conversation(self.conversation_id)
                    if getattr(self, "ui_events", None) is None:
                        self.ui_events = []
                except Exception:
                    logger.exception(
                        "fetch_conversation failed after accept; continuing with empty transcript"
                    )
                    self.messages = []
                    self.ui_events = []
                await self._emit_suggestions_if_enabled(self.default_blueprint)
                self._start_omb_session_watch()
                self._maybe_start_herdr_session_watch(query_params)
            else:
                # Close after accept so the client sees 4401 (not 1006).
                # receive() re-checks auth so anonymous clients cannot hit the LLM.
                await self.close(
                    code=WS_AUTH_REQUIRED_CODE,
                    reason="authentication required",
                )
        except Exception:
            logger.exception("post-accept websocket setup failed; socket stays open")

    async def _send_spa_hello(self):
        """Tell the tab which SPA bake this backend expects (REQ-78)."""
        try:
            from swarm.core.app_version import get_app_version

            await self.send(
                text_data=json.dumps(
                    {
                        "type": SPA_HELLO_TYPE,
                        "spa_version": get_app_version(),
                    }
                )
            )
        except Exception:
            logger.debug("spa_hello advertise failed", exc_info=True)

    def _start_omb_session_watch(self):
        """Register this socket for OpenMousBot follow-up assistant turns (#125)."""
        try:
            from swarm.core import chat_store, omb_session_watch

            self._omb_watch_queue = asyncio.Queue(maxsize=200)
            user_key = chat_store.user_key_for(self.user)
            omb_session_watch.register_consumer(
                user_key,
                self._omb_watch_queue,
                loop=asyncio.get_running_loop(),
            )
            self._omb_watch_drain_task = asyncio.ensure_future(self._drain_omb_followups())
        except Exception:
            logger.debug("omb session watch registration failed", exc_info=True)

    async def _drain_omb_followups(self):
        queue = getattr(self, "_omb_watch_queue", None)
        if queue is None:
            return
        while True:
            payload = await queue.get()
            try:
                await self._emit_omb_followup(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("omb follow-up emit failed", exc_info=True)

    async def _emit_omb_followup(self, payload):
        """Append a later OpenMousBot bot text as its own assistant bubble."""
        if not isinstance(payload, dict):
            return
        cid = str(payload.get("conversation_id") or "")
        if cid and cid != str(getattr(self, "conversation_id", "") or ""):
            return
        text = str(payload.get("text") or "").strip()
        if not text:
            events = payload.get("events") or []
            if events and isinstance(events[0], dict):
                text = str(events[0].get("text") or "").strip()
        if not text:
            return
        for row in self.messages or []:
            if row.get("role") == "assistant" and str(row.get("content") or "").strip() == text:
                return
        message_id = uuid.uuid4().hex
        contents_div_id = f"message-response-{message_id}"
        start_html = render_to_string(
            "websocket_partials/system_message.html",
            {"contents_div_id": contents_div_id},
        )
        await self.send(text_data=start_html)
        await self.send(text_data=_oob_append_html(contents_div_id, text))
        final_html = render_to_string(
            "websocket_partials/final_system_message.html",
            {"contents_div_id": contents_div_id, "message": text},
        )
        await self.send(text_data=final_html)
        _record_turn(self, "assistant", text, ts=_message_ts())
        await self._persist_completed_turn()

    def _maybe_start_herdr_session_watch(self, query_params):
        """Watch the focused Herdr pane for externally started turns (#794).

        Registers this socket for pane frames and arms a track for the
        ``?session=<target>`` pane. Only Herdr seats watch — the query
        blueprint must be ``herdr`` (the remote_harness rewrite in receive()
        keeps ``self.default_blueprint`` as the original seat).
        """
        try:
            from swarm.core import chat_store, herdr_session_watch

            if str(getattr(self, "default_blueprint", None) or "").strip().lower() != "herdr":
                return
            params = query_params or {}
            target = str(
                (params.get("session") or params.get("target") or [""])[0]
            ).strip()
            if not target:
                return

            self._herdr_watch_queue = asyncio.Queue(maxsize=200)
            user_key = chat_store.user_key_for(self.user)
            herdr_session_watch.register_consumer(
                user_key,
                self._herdr_watch_queue,
                loop=asyncio.get_running_loop(),
            )
            herdr_session_watch.watch_session(
                user_key=user_key,
                agent_id="herdr",
                conversation_id=str(getattr(self, "conversation_id", "") or ""),
                target=target,
            )
            self._herdr_watch_drain_task = asyncio.ensure_future(
                self._drain_herdr_frames()
            )
        except Exception:
            logger.debug("herdr session watch registration failed", exc_info=True)

    async def _drain_herdr_frames(self):
        queue = getattr(self, "_herdr_watch_queue", None)
        if queue is None:
            return
        # #794: partial deltas coalesce — the harness mirrors the *turn*
        # (prompt immediately, final assistant text once), not every poll
        # delta, which would render one bubble per snapshot tick.
        pending_stream = None
        while True:
            payload = await queue.get()
            try:
                if isinstance(payload, dict) and payload.get("type") == "herdr_stream":
                    if payload.get("final"):
                        payload["text"] = str(payload.get("text") or "")
                        await self._emit_herdr_frame(payload)
                        pending_stream = None
                    else:
                        pending_stream = payload
                    continue
                await self._emit_herdr_frame(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("herdr frame emit failed", exc_info=True)

    async def _emit_herdr_frame(self, payload):
        """Render an external Herdr turn as chat bubbles (#794).

        ``herdr_external_turn`` mirrors the user's typed prompt as a user
        bubble; ``herdr_stream`` appends assistant output (the final frame
        replaces intermediate deltas via dedup on identical content).
        """
        if not isinstance(payload, dict):
            return
        cid = str(payload.get("conversation_id") or "")
        if cid and cid != str(getattr(self, "conversation_id", "") or ""):
            return
        from swarm.core.model_text import sanitize_model_text

        if payload.get("type") == "herdr_external_turn":
            text = sanitize_model_text(str(payload.get("text") or "")).strip()
            if not text:
                return
            for row in self.messages or []:
                if row.get("role") == "user" and str(row.get("content") or "").strip() == text:
                    return
            user_message_html = render_to_string(
                "websocket_partials/user_message.html",
                {"message_text": text},
            )
            await self.send(text_data=user_message_html)
            _record_turn(self, "user", text, ts=_message_ts())
            await self._persist_completed_turn()
            return
        if payload.get("type") != "herdr_stream":
            return
        text = sanitize_model_text(str(payload.get("text") or "")).strip()
        if not text:
            return
        if not payload.get("final"):
            for row in self.messages or []:
                if row.get("role") == "assistant" and str(row.get("content") or "").strip() == text:
                    return
        message_id = uuid.uuid4().hex
        contents_div_id = f"message-response-{message_id}"
        start_html = render_to_string(
            "websocket_partials/system_message.html",
            {"contents_div_id": contents_div_id},
        )
        await self.send(text_data=start_html)
        await self.send(text_data=_oob_append_html(contents_div_id, text))
        final_html = render_to_string(
            "websocket_partials/final_system_message.html",
            {"contents_div_id": contents_div_id, "message": text},
        )
        await self.send(text_data=final_html)
        _record_turn(self, "assistant", text, ts=_message_ts())
        await self._persist_completed_turn()

    async def disconnect(self, close_code):
        task = getattr(self, "_omb_watch_drain_task", None)
        if task is not None:
            task.cancel()
        herdr_task = getattr(self, "_herdr_watch_drain_task", None)
        if herdr_task is not None:
            herdr_task.cancel()
        try:
            from swarm.core import chat_store, omb_session_watch

            if getattr(self, "_herdr_watch_queue", None) is not None:
                from swarm.core import herdr_session_watch

                herdr_session_watch.unregister_consumer(self._herdr_watch_queue)
                if getattr(self.user, "is_authenticated", False):
                    herdr_session_watch.unwatch_conversation(
                        chat_store.user_key_for(self.user),
                        getattr(self, "conversation_id", "") or "",
                    )
            if getattr(self, "_omb_watch_queue", None) is not None:
                omb_session_watch.unregister_consumer(self._omb_watch_queue)
                if getattr(self.user, "is_authenticated", False):
                    omb_session_watch.unwatch_conversation(
                        chat_store.user_key_for(self.user),
                        getattr(self, "conversation_id", "") or "",
                    )
        except Exception:
            logger.debug("omb session watch cleanup failed", exc_info=True)
        if self.user.is_authenticated:
            from swarm.core.cli_session_error import is_uncontinued_fatal_init

            # A first-turn CLI/config failure is not a history thread (#274).
            if not is_uncontinued_fatal_init(self.messages):
                await self.save_conversation(self.conversation_id, self.messages)

            # Delete conversation from DB and memory if empty
            if not self.messages and not getattr(self, "ui_events", None):
                await self.delete_conversation(self.conversation_id)

            # Clean up in-memory cache to avoid leaks
            cache_key = _conversation_cache_key(self.user, self.conversation_id)
            if cache_key in IN_MEMORY_CONVERSATIONS:
                del IN_MEMORY_CONVERSATIONS[cache_key]
            if cache_key in IN_MEMORY_UI_EVENTS:
                del IN_MEMORY_UI_EVENTS[cache_key]

    async def receive(self, text_data):
        # Auth gate: accept-then-close 4401 leaves a race where a frame can
        # land before the close is applied. Refuse unauthenticated receives
        # (do not append to transcript or invoke blueprints / LLM).
        if not getattr(self.user, "is_authenticated", False):
            if swarm_allow_anonymous(client_ip_from_scope(getattr(self, "scope", None))):
                self.user = await database_sync_to_async(get_or_create_preview_user)()
            else:
                await self.close(
                    code=WS_AUTH_REQUIRED_CODE,
                    reason="authentication required",
                )
                return
            if not getattr(self.user, "is_authenticated", False):
                await self.close(
                    code=WS_AUTH_REQUIRED_CODE,
                    reason="authentication required",
                )
                return

        # Tolerate malformed frames without killing the socket: log and drop.
        try:
            text_data_json = json.loads(text_data)
            if not isinstance(text_data_json, dict):
                raise ValueError("frame must be a JSON object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Ignoring malformed chat frame (%s): %.200r", exc, text_data)
            return

        if text_data_json.get("type") == "tool_decision":
            await self.resolve_tool_decision(text_data_json)
            return

        if text_data_json.get("type") == "question_answer":
            await self.resolve_question_answer(text_data_json)
            return

        # #198: enter-to-interrupt — a queued-send promote cancels the turn
        # in flight before the new message runs.
        if text_data_json.get("type") == "cancel_turn":
            await self._cancel_current_turn()
            return

        # #818: kill one background task from the activity dialog.
        if text_data_json.get("type") == AUX_CANCEL_TYPE:
            task_id = text_data_json.get("task_id")
            if isinstance(task_id, str) and task_id:
                cancelled = self.auxiliary_tasks.cancel(task_id)
                await self.send(
                    text_data=json.dumps(
                        {"type": AUX_UPDATE_TYPE, "task_id": task_id, "cancelled": cancelled}
                    )
                )
            return

        if text_data_json.get("type") == "status":
            status_text = text_data_json.get("text")
            if not isinstance(status_text, str) or not status_text.strip():
                return
            agent = text_data_json.get("agent")
            if isinstance(agent, str) and agent.strip():
                self.active_agent = agent.strip()
            _record_status(self, status_text, ts=_message_ts())
            conversation_id = getattr(self, "conversation_id", None)
            if conversation_id:
                await self.save_conversation(conversation_id, self.messages)
            return

        if "edit" in text_data_json:
            await self.apply_message_edit(text_data_json.get("edit"))
            return

        try:
            message_text = text_data_json["message"]
            if not isinstance(message_text, str):
                raise ValueError("'message' must be a string")
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Ignoring malformed chat frame (%s): %.200r", exc, text_data)
            return

        from swarm.core import chat_attachments

        attachment_ids = chat_attachments.parse_attachment_ids(
            text_data_json.get("attachments")
        )
        if not message_text.strip() and not attachment_ids:
            return

        await self._run_serialised_chat_turn(text_data_json, message_text)

    def _cancel_event(self) -> asyncio.Event:
        """Lazily create the single cancel event shared by this socket."""
        event = getattr(self, "_turn_cancel_event", None)
        if event is None:
            event = asyncio.Event()
            self._turn_cancel_event = event
        return event

    @property
    def auxiliary_tasks(self):
        """#818: per-connection registry of background LLM tasks."""
        reg = getattr(self, "_auxiliary_tasks", None)
        if reg is None:
            from swarm.core.auxiliary_tasks import AuxiliaryTaskRegistry

            reg = AuxiliaryTaskRegistry()
            self._auxiliary_tasks = reg
        return reg

    async def _cancel_current_turn(self):
        """#198: cooperative cancel — request the active turn to stop.

        The running turn polls ``self._cancel_event`` between streamed chunks
        (blueprint and default-model paths) and bails with an "Interrupted"
        note instead of persisting a partial reply. Safe when nothing runs:
        the next turn clears the flag at entry.
        """
        self._cancel_event().set()
        pending_questions = getattr(self, "_pending_question_answers", {}) or {}
        for future in list(pending_questions.values()):
            if future is not None and not future.done():
                future.set_result("interrupted")
        try:
            await self.send(text_data=json.dumps({"type": TURN_CANCELLED_TYPE}))
        except Exception:
            logger.debug("turn_cancelled ack send failed", exc_info=True)

    async def _run_serialised_chat_turn(self, text_data_json, message_text):
        """One ``respond_with_*`` at a time on this socket (REQ-171A-3 / #603)."""
        async with self._ensure_chat_turn_lock():
            # #198: a fresh turn always starts un-cancelled.
            self._cancel_event().clear()
            # Per-message blueprint selection wins over the connection default.
            blueprint_id = text_data_json.get("blueprint") or getattr(
                self, "default_blueprint", None
            )
            params = text_data_json.get("params")
            if not isinstance(params, dict):
                params = None

            if params and params.get("remote") and not blueprint_id:
                blueprint_id = "remote_harness"
                params.setdefault("name", str(params["remote"]))
                params.setdefault("op", "send")
            elif blueprint_id and (
                str(blueprint_id).startswith("remote:")
                or str(blueprint_id).lower() in (
                    "hermes",
                    "anythingllm",
                    "letta",
                    "openwebui",
                    "flowise",
                    "n8n",
                    "omb",
                    "rakazo",
                    "herdr",
                    "swarm",
                    "trueforge",
                )
            ):
                remote_name = str(blueprint_id).replace("remote:", "")
                blueprint_id = "remote_harness"
                if params is None:
                    params = {}
                params.setdefault("name", remote_name)
                params.setdefault("remote", remote_name)
                params.setdefault("op", "send")

            self.active_agent = blueprint_id or getattr(self, "active_agent", None)

            # #794: a send toward a Herdr pane arms the "this turn is ours"
            # attribution so the session watch will not mirror our own prompt
            # back as an external user turn.
            if str((params or {}).get("remote") or "").strip().lower() == "herdr":
                try:
                    from swarm.core import chat_store, herdr_session_watch

                    herdr_session_watch.note_swarm_send(
                        user_key=chat_store.user_key_for(self.user),
                        conversation_id=str(getattr(self, "conversation_id", "") or ""),
                        target=str((params or {}).get("session") or ""),
                    )
                except Exception:
                    logger.debug("herdr swarm-send attribution failed", exc_info=True)

            if params and params.get("new_session"):
                # REQ-65: CoS/user task asked for an empty session on this socket.
                self.messages = []
                self.ui_events = []

            from swarm.core import chat_attachments

            attachment_ids = chat_attachments.parse_attachment_ids(
                text_data_json.get("attachments")
            )
            # #744: user text is a paste boundary — terminal transcripts carry
            # mangled CSI leftovers (``[13;28;13;1;0;1_``) that would otherwise
            # be persisted, rendered, and re-copied forever. Same sanitizer the
            # model-output path uses; plain text is untouched.
            from swarm.core.model_text import sanitize_model_text

            display_text = sanitize_model_text(message_text)
            if not display_text and attachment_ids:
                display_text = chat_attachments.caption([])
            _record_turn(
                self,
                "user",
                display_text,
                ts=_message_ts(),
                attachments=attachment_ids or None,
            )

            user_message_html = render_to_string(
                "websocket_partials/user_message.html",
                {"message_text": display_text},
            )
            await self.send(text_data=user_message_html)

            # REQ-92: new-session status must precede the assistant bubble on the wire.
            await self._emit_new_cli_session_notice(blueprint_id, params)

            message_id = uuid.uuid4().hex
            contents_div_id = f"message-response-{message_id}"
            system_message_html = render_to_string(
                "websocket_partials/system_message.html",
                {"contents_div_id": contents_div_id},
            )
            await self.send(text_data=system_message_html)

            # Guard the dispatch itself. The respond_* paths handle their own
            # generation failures, but anything raised before/around them —
            # e.g. constructing the model client when OPENAI_API_KEY is unset
            # or a config ${VAR} never expanded — used to escape
            # websocket_receive. Uvicorn then aborted the socket with no close
            # frame, leaving the SPA to report "ASGI is not serving /ws/ or
            # Origin does not match ALLOWED_HOSTS": a credential/config fault
            # presented as a connection fault. Surface it as an error partial.
            try:
                from swarm.demo import is_demo_mode

                if is_demo_mode():
                    await self.respond_with_demo(
                        contents_div_id, message_text, params=params
                    )
                elif params and params.get("team"):
                    from swarm.core.team_rosters import blueprint_id_for_team_target

                    team_blueprint = blueprint_id_for_team_target(
                        params.get("team"), params.get("target")
                    )
                    if team_blueprint:
                        await self.respond_with_blueprint(
                            team_blueprint, contents_div_id, params=params
                        )
                    else:
                        await self.respond_with_team_stub(
                            params, message_text, contents_div_id
                        )
                elif blueprint_id and _is_bootstrap_turn(blueprint_id, params):
                    await self.respond_with_bootstrap(
                        blueprint_id, contents_div_id, message_text, params=params
                    )
                elif blueprint_id:
                    await self.respond_with_blueprint(
                        blueprint_id, contents_div_id, params=params
                    )
                else:
                    await self.respond_with_default_model(contents_div_id)
            except Exception as e:
                logger.exception("Chat turn raised outside the respond_* handlers")
                from swarm.utils.env_utils import client_safe_error_message

                public = (
                    "Error: the reply could not be started — the server's "
                    "model provider is unusable (missing or invalid "
                    "credentials?)."
                )
                hint = _credential_hint()
                if hint:
                    public = f"{public} {hint}"

                try:
                    await self.send_error_message(
                        contents_div_id,
                        client_safe_error_message(e, public=public),
                    )
                except Exception:
                    logger.debug(
                        "turn error partial send failed; socket likely gone",
                        exc_info=True,
                    )




    async def _emit_teammate_task_cards(self, params, message_text):
        """REQ-84: Open-in-{remote} chrome when a team tasks a remote member."""
        try:
            from swarm.core.teammate_task import teammate_tasks_for_team_send

            team = str((params or {}).get("team") or "")
            target = str((params or {}).get("target") or "all")
            op = str((params or {}).get("op") or "")
            for payload in teammate_tasks_for_team_send(
                team_id=team,
                target=target,
                title=str(message_text or ""),
                op=op,
            ):
                await self.emit_tool_event(payload)
        except Exception:
            logger.debug("teammate_task emit skipped", exc_info=True)










    async def _emit_pr_opened_from_text(self, text):
        """REQ-79: CLI/API stdout with a real GitHub PR URL → REQ-71 View PR card.

        Never invents a URL. Markdown-only chatter without a pull link is ignored.
        """
        try:
            from swarm.core.self_update import parse_cli_pr_opened

            payload = parse_cli_pr_opened(
                text,
                agent_id=str(
                    getattr(self, "active_agent", None)
                    or getattr(self, "default_blueprint", None)
                    or ""
                ),
                conversation_id=str(getattr(self, "conversation_id", "") or ""),
            )
            if payload:
                await self.emit_tool_event(payload)
        except Exception:
            logger.debug("CLI PR-opened parse skipped", exc_info=True)

    async def _persist_completed_turn(self):
        """REQ-171A-2: write JSON + Django rows after a finished assistant turn.

        Disconnect still saves (idempotent replace). Status and edit keep
        their own immediate save. Load order is unchanged (H5).
        A first-turn fatal CLI/config failure is not persisted as history
        unless the user continues (#274).
        """
        if not getattr(self.user, "is_authenticated", False):
            return
        conversation_id = getattr(self, "conversation_id", None)
        if not conversation_id:
            return
        from swarm.core.cli_session_error import is_uncontinued_fatal_init

        if is_uncontinued_fatal_init(self.messages):
            return
        try:
            await self.save_conversation(conversation_id, self.messages)
        except Exception:
            logger.exception(
                "Failed to persist completed chat turn %s", conversation_id
            )
        await self._emit_context_usage()

    async def _emit_context_usage(self):
        """#215: JSON context_usage frame after a finished turn (read-only)."""
        try:
            from swarm.core.context_usage import usage_snapshot

            conversation_id = getattr(self, "conversation_id", None) or ""
            agent_id = str(
                getattr(self, "active_agent", None)
                or getattr(self, "default_blueprint", None)
                or ""
            )
            params = getattr(self, "_last_chat_params", None)
            model_id = None
            if isinstance(params, dict):
                raw = params.get("model") or params.get("llm_profile")
                if isinstance(raw, str) and raw.strip():
                    model_id = raw.strip()
            payload = await database_sync_to_async(usage_snapshot)(
                conversation_id=str(conversation_id),
                agent_id=agent_id,
                turns=list(getattr(self, "messages", None) or []),
                model_id=model_id,
                blueprint=getattr(self, "_blueprint_instance", None),
            )
            await self.send(text_data=json.dumps(payload))
        except Exception:
            logger.debug("context usage emit skipped", exc_info=True)

    async def _emit_suggestions_if_enabled(self, agent_id, blueprint=None):
        """REQ-85: JSON chips after a finished turn (never mid-token, never in LLM context)."""
        try:
            from swarm.core.suggestions import (
                resolve_suggestions_agents,
                suggestions_payload_for_turn,
            )

            target = (
                agent_id
                or getattr(self, "active_agent", None)
                or getattr(self, "default_blueprint", None)
            )
            instance = blueprint if blueprint is not None else getattr(self, "_blueprint_instance", None)
            agents = resolve_suggestions_agents(target, blueprint=instance)
            payload = suggestions_payload_for_turn(
                target,
                getattr(self, "messages", None),
                agents=agents,
            )
            if payload:
                await self.emit_tool_event(payload)
        except Exception:
            logger.debug("suggestions emit skipped", exc_info=True)

    async def emit_tool_event(self, payload: dict) -> None:
        """JSON tool-status / approval / user_question / PR-opened / teammate-task / suggestions frames."""
        try:
            from swarm.core.pr_opened import persist_pr_opened_message
            from swarm.core.teammate_task import persist_teammate_task_message

            if isinstance(payload, dict) and payload.get("type") == "pr_opened":
                opener = payload.get("opener")
                if not isinstance(opener, dict):
                    opener = {}
                    payload["opener"] = opener
                agent_id = (
                    opener.get("agent_id")
                    or getattr(self, "active_agent", None)
                    or getattr(self, "default_blueprint", None)
                    or ""
                )
                if agent_id and not opener.get("agent_id"):
                    opener["agent_id"] = str(agent_id)
                conversation_id = getattr(self, "conversation_id", None) or ""
                if conversation_id and not opener.get("conversation_id"):
                    opener["conversation_id"] = str(conversation_id)
                if getattr(self, "ui_events", None) is None:
                    self.ui_events = []
                persist_pr_opened_message(self.messages, payload, events=self.ui_events)
            if isinstance(payload, dict) and payload.get("type") == "teammate_task":
                if getattr(self, "ui_events", None) is None:
                    self.ui_events = []
                persist_teammate_task_message(self.messages, payload, events=self.ui_events)
            await self.send(text_data=json.dumps(payload))
        except Exception:
            logger.debug("tool event send failed", exc_info=True)

    async def elicit_tool_approval(self, tool_name: str, arguments: dict) -> str:
        """Pause the API-agent run until the chat sends Allow / Always / Deny."""
        approval_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        pending = getattr(self, "_pending_tool_decisions", None)
        if pending is None:
            pending = {}
            self._pending_tool_decisions = pending
        pending[approval_id] = future
        await self.emit_tool_event(
            {
                "type": "tool_approval",
                "id": approval_id,
                "name": tool_name,
                "agent_id": getattr(self, "active_agent", None) or "",
                "arguments": arguments or {},
            }
        )
        try:
            decision = await asyncio.wait_for(future, timeout=300)
        except TimeoutError:
            decision = "deny"
        finally:
            pending.pop(approval_id, None)
        return str(decision or "deny")

    async def elicit_user_question(self, question: dict) -> str:
        """Pause the API-agent run until the chat sends a ``question_answer``."""
        from swarm.core.ask_user import (
            INTERRUPTED_RESULT,
            TIMEOUT_RESULT,
            TIMEOUT_SEC,
            normalize_answer,
            question_event,
        )

        question_id = str(question.get("id") or uuid.uuid4().hex)
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        pending = getattr(self, "_pending_question_answers", None)
        if pending is None:
            pending = {}
            self._pending_question_answers = pending
        pending[question_id] = future
        event = question_event(question, agent_id=getattr(self, "active_agent", None) or "")
        event["id"] = question_id
        await self.emit_tool_event(event)
        try:
            answer = await asyncio.wait_for(future, timeout=TIMEOUT_SEC)
        except TimeoutError:
            answer = TIMEOUT_RESULT
        finally:
            pending.pop(question_id, None)
        if self._cancel_event().is_set():
            return INTERRUPTED_RESULT
        return normalize_answer(answer) or TIMEOUT_RESULT

    async def resolve_question_answer(self, payload: dict) -> None:
        from swarm.core.ask_user import normalize_answer

        question_id = str(payload.get("id") or "")
        answer = normalize_answer(payload.get("answer"))
        pending = getattr(self, "_pending_question_answers", {}) or {}
        future = pending.get(question_id)
        if future is None or future.done():
            return
        future.set_result(answer)

    async def resolve_tool_decision(self, payload: dict) -> None:
        approval_id = str(payload.get("id") or "")
        decision = str(payload.get("decision") or "deny")
        pending = getattr(self, "_pending_tool_decisions", {}) or {}
        future = pending.get(approval_id)
        if future is None or future.done():
            return
        future.set_result(decision)

    async def send_error_message(self, contents_div_id, error_text):
        """Replace the streaming placeholder with an error partial.

        Transport-level errors (unknown blueprint, execution failure) are
        shown to the user but deliberately NOT appended to ``self.messages``
        so they never pollute the model context of later turns.
        """
        error_html = render_to_string(
            "websocket_partials/final_system_message.html",
            {
                "contents_div_id": contents_div_id,
                "message": error_text,
            },
        )
        await self.send(text_data=error_html)

    async def _maybe_run_default_sandbox_agent(
        self, client, model, model_messages, contents_div_id
    ):
        """REQ-863: when a sandbox provider is enabled, run the default chat
        turn through openai-agents so ``sandbox_run_*`` tools are callable.
        Returns the assistant text, or None to keep the completions stream.
        """
        try:
            from swarm.core.sandbox import sandbox_function_tools

            tools = sandbox_function_tools()
        except Exception:
            logger.debug("sandbox tools lookup failed", exc_info=True)
            return None
        if not tools:
            return None
        try:
            from agents import Agent, Runner
            from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
        except Exception:
            logger.debug("openai-agents unavailable for sandbox default chat", exc_info=True)
            return None
        user_text = ""
        for message in reversed(model_messages or []):
            if isinstance(message, dict) and message.get("role") == "user":
                user_text = str(message.get("content") or "")
                break
        if not user_text:
            return None
        try:
            model_instance = OpenAIChatCompletionsModel(model=model, openai_client=client)
            agent = Agent(
                name="Chat",
                model=model_instance,
                instructions=(
                    "You are a helpful assistant. Use sandbox tools when the user "
                    "asks you to run code, a shell command, or read/write files."
                ),
                tools=tools,
            )
            result = await Runner.run(agent, user_text)
            text = str(getattr(result, "final_output", result) or "")
        except Exception:
            logger.warning("sandbox-enabled default chat failed; falling back", exc_info=True)
            return None
        if not text:
            return None
        await self.send(text_data=_oob_append_html(contents_div_id, text))
        return text

    async def respond_with_default_model(self, contents_div_id):
        """Legacy reply path: server-configured model via LiteLLM/OpenAI env."""
        import swarm.consumers as _self_mod
        _cls = _self_mod.AsyncOpenAI
        if _cls is None:
            from openai import AsyncOpenAI as _cls
            _self_mod.AsyncOpenAI = _cls

        # Mirror blueprint_base.configure_openai_client_from_env / LITELLM_* patterns.
        from swarm.utils.env_utils import get_llm_base_url, openai_client_kwargs

        base_url = get_llm_base_url()
        client_kwargs = openai_client_kwargs()
        model = (
            os.environ.get("LITELLM_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or os.environ.get("DEFAULT_LLM")
        )
        if not model:
            from swarm.core.llm_task_routing import (
                load_swarm_config,
                model_id_for_profile,
                resolve_chat_model,
            )

            config = load_swarm_config()
            route = resolve_chat_model(config)
            model = model_id_for_profile(route.profile, config)
            if route.warning:
                logger.warning("Default chat model: %s", route.warning)
        client = _cls(**client_kwargs)

        if base_url:
            logging.getLogger("openai.agents").setLevel(logging.CRITICAL)
            try:
                import openai.agents.tracing
                openai.agents.tracing.TracingClient = lambda *a, **kw: None
            except Exception:
                pass

        def _enforce_litellm_only(client):
            """Reject openai.com fallback when a custom LiteLLM gateway is configured."""
            expected = get_llm_base_url()
            if not expected:
                return
            actual = str(getattr(client, "base_url", "") or "")
            if not actual or "openai.com" in actual:
                import traceback
                raise RuntimeError(
                    "Attempted fallback to OpenAI API when custom base_url is set! "
                    f"base_url={actual!r} expected={expected!r}\n{traceback.format_stack()}"
                )

        _enforce_litellm_only(client)

        full_message = ""
        try:
            compact_result = await _auto_compress_before_send(self, model_id=model)
            if compact_result is not None and compact_result.context and (
                compact_result.acted or getattr(compact_result, "strategy", "") == "cull"
            ):
                model_messages = compact_result.context
            else:
                model_messages = await _compacted_context(
                    self,
                    getattr(self, "conversation_id", ""),
                    self.messages,
                )
            model_messages = await _expand_model_messages(self, model_messages)
            sandbox_reply = await self._maybe_run_default_sandbox_agent(
                client, model, model_messages, contents_div_id
            )
            if sandbox_reply is not None:
                full_message = sandbox_reply
            else:
                stream = await client.chat.completions.create(
                    model=model,
                    messages=model_messages,
                    stream=True,
                )
                async for chunk in stream:
                    # #198: same cooperative cancel as the blueprint path.
                    if self._cancel_event().is_set():
                        break
                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue
                    message_chunk = choices[0].delta.content
                    if message_chunk:
                        full_message += message_chunk
                        await self.send(
                            text_data=_oob_append_html(contents_div_id, message_chunk)
                        )
        except Exception as e:
            logger.error("Default-model chat stream failed: %s", e, exc_info=True)
            await self.send_error_message(
                contents_div_id,
                "Error: the default model failed while generating a reply. "
                "Check the server's LLM configuration (LITELLM_* / OPENAI_*).",
            )
            return

        from swarm.core.model_text import sanitize_model_text

        # #198: default-model interrupt — no partial reply, no persistence.
        if self._cancel_event().is_set():
            await self.send_error_message(contents_div_id, "Interrupted.")
            return

        full_message = sanitize_model_text(full_message)
        if not full_message:
            await self.send_error_message(
                contents_div_id,
                "Error: the model returned no usable text (empty or tokenizer leftovers).",
            )
            return

        _record_turn(self, "assistant", full_message, ts=_message_ts())

        final_message = render_to_string(
            "websocket_partials/final_system_message.html",
            {
                "contents_div_id": contents_div_id,
                "message": full_message,
            },
        )
        await client.close()
        await self.send(text_data=final_message)
        await self._persist_completed_turn()
        await self._emit_suggestions_if_enabled(None)






# #855 slice 1 — module-level helpers moved verbatim to swarm.chat.helpers
# (patch-safe: the moved bodies resolve names through a late-bound
# swarm.consumers handle, so monkeypatch targets on this module keep
# landing; the binding defers to first use, avoiding a circular import).
from .chat import helpers as _chat_helpers  # noqa: E402

_apply_pending_api_hop = _chat_helpers._apply_pending_api_hop
_auto_compress_before_send = _chat_helpers._auto_compress_before_send
_compacted_context = _chat_helpers._compacted_context
_conversation_cache_key = _chat_helpers._conversation_cache_key
_credential_hint = _chat_helpers._credential_hint
_display_rows = _chat_helpers._display_rows
_expand_model_messages = _chat_helpers._expand_model_messages
_gate_provider_rate_limit = _chat_helpers._gate_provider_rate_limit
_is_bootstrap_turn = _chat_helpers._is_bootstrap_turn
_load_agent_json = _chat_helpers._load_agent_json
_load_agent_record = _chat_helpers._load_agent_record
_message_ts = _chat_helpers._message_ts
_oob_append_html = _chat_helpers._oob_append_html
_rate_limit_status_html = _chat_helpers._rate_limit_status_html
_record_status = _chat_helpers._record_status
_record_turn = _chat_helpers._record_turn
_save_agent_json = _chat_helpers._save_agent_json
_status_line_html = _chat_helpers._status_line_html
_user_key_for_hop = _chat_helpers._user_key_for_hop

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

# REQ-78 / #423 — advertise the backend's expected SPA bake on connect.
SPA_HELLO_TYPE = "spa_hello"


def _message_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_agent_json(user, agent_id, messages, *, conversation_id="", ui_events=None):
    """Best-effort write of the per-agent JSON thread (Settings + reload)."""
    if not getattr(user, "is_authenticated", False) or not (messages or ui_events):
        return
    try:
        from swarm.core import chat_store
        from swarm.core.agent_settings import is_new_chat_per_task

        session_id = ""
        default_cid = chat_store.conversation_id_for(user, agent_id) if agent_id else ""
        if conversation_id and (
            conversation_id != default_cid
            or (agent_id and is_new_chat_per_task(agent_id))
        ):
            session_id = conversation_id
        chat_store.save(
            chat_store.user_key_for(user),
            agent_id,
            messages,
            conversation_id=conversation_id,
            session_id=session_id,
            ui_events=ui_events,
        )
    except Exception:
        logger.exception("Failed to persist agent chat JSON")


def _load_agent_record(user, agent_id, *, conversation_id=""):
    """Best-effort load of the per-agent JSON thread (turns + ui_events)."""
    empty = {"messages": [], "ui_events": []}
    if not getattr(user, "is_authenticated", False):
        return empty
    try:
        from swarm.core import chat_store
        from swarm.core.agent_settings import is_new_chat_per_task

        session_id = ""
        default_cid = chat_store.conversation_id_for(user, agent_id) if agent_id else ""
        if conversation_id and (
            conversation_id != default_cid
            or (agent_id and is_new_chat_per_task(agent_id))
        ):
            session_id = conversation_id
        record = chat_store.load(
            chat_store.user_key_for(user),
            agent_id,
            conversation_id=conversation_id,
            session_id=session_id,
        )
    except Exception:
        logger.exception("Failed to load agent chat JSON")
        return empty
    if not record:
        return empty
    from swarm.core.thread_load import public_message

    return {
        "messages": [public_message(m) for m in record.get("messages") or []],
        "ui_events": list(record.get("ui_events") or []),
    }


def _load_agent_json(user, agent_id, *, conversation_id=""):
    """Best-effort load of model turns from the per-agent JSON thread."""
    return _load_agent_record(user, agent_id, conversation_id=conversation_id)["messages"]


def _display_rows(consumer):
    from swarm.core.transcript_roles import reconstruct_display

    return reconstruct_display(
        getattr(consumer, "messages", None) or [],
        getattr(consumer, "ui_events", None) or [],
    )


def _record_turn(consumer, role, content, **extra):
    from swarm.core.transcript_roles import append_turn

    if getattr(consumer, "messages", None) is None:
        consumer.messages = []
    if getattr(consumer, "ui_events", None) is None:
        consumer.ui_events = []
    return append_turn(consumer.messages, consumer.ui_events, role, content, **extra)


def _record_status(consumer, content, **extra):
    from swarm.core.transcript_roles import append_event

    if getattr(consumer, "messages", None) is None:
        consumer.messages = []
    if getattr(consumer, "ui_events", None) is None:
        consumer.ui_events = []
    return append_event(
        consumer.messages,
        consumer.ui_events,
        extra.pop("role", "status"),
        content,
        **extra,
    )


def _conversation_cache_key(user, conversation_id):
    """Composite cache key so one user's transcript never leaks to another."""
    user_id = getattr(user, "pk", None)
    if user_id is None:
        user_id = getattr(user, "id", None)
    return (user_id, conversation_id)


async def _gate_provider_rate_limit(consumer, params=None, blueprint_id=""):
    """REQ-88: wait on the shared provider queue before a send (including test mode)."""
    emitted = {"done": False}

    async def on_wait(decision):
        if emitted["done"]:
            return
        emitted["done"] = True
        from swarm.core.provider_rate_limit import format_wait_text

        meta = decision.public_dict()
        text = format_wait_text(decision)
        try:
            await consumer.send(text_data=_rate_limit_status_html(text, meta))
        except Exception:
            logger.debug("rate-limit status send skipped", exc_info=True)
        _record_status(
            consumer,
            text,
            role="info",
            kind="rate_limit",
            rate_limit=meta,
            ts=_message_ts(),
        )

    try:
        from swarm.core.provider_rate_limit import gate_provider_send

        messages = getattr(consumer, "messages", None) or []
        return await gate_provider_send(
            params=params if isinstance(params, dict) else None,
            blueprint_id=str(blueprint_id or ""),
            messages=messages,
            on_wait=on_wait,
        )
    except Exception:
        logger.debug("provider rate-limit gate skipped", exc_info=True)
        return None


async def _auto_compress_before_send(consumer, params=None, model_id=None):
    """REQ-87: compact older span when estimated tokens hit N% of known max."""
    try:
        from swarm.core.context_cull_policy import prepare_context_before_send

        inference_entry = None
        mid = model_id
        if isinstance(params, dict):
            if not mid:
                raw_model = params.get("model") or params.get("llm_profile")
                if isinstance(raw_model, str) and raw_model.strip():
                    mid = raw_model.strip()
            seats = params.get("inference_list")
            if isinstance(seats, list) and seats and isinstance(seats[0], dict):
                inference_entry = seats[0]
        result = await database_sync_to_async(prepare_context_before_send)(
            user=getattr(consumer, "user", None),
            conversation_id=getattr(consumer, "conversation_id", "") or "",
            agent_id=str(
                getattr(consumer, "active_agent", None)
                or getattr(consumer, "default_blueprint", "")
                or ""
            ),
            messages=getattr(consumer, "messages", None) or [],
            model_id=str(mid).strip() if isinstance(mid, str) and mid.strip() else None,
            inference_entry=inference_entry,
        )
        if result.info:
            await consumer.send(text_data=_status_line_html(result.info))
            _record_status(consumer, result.info, ts=_message_ts())
        return result
    except Exception:
        logger.debug("auto-compress hook skipped", exc_info=True)
        return None


def _apply_pending_api_hop(conversation_id, messages):
    """#531: seed an API backend hop with the carried blob (same conversation)."""
    try:
        from swarm.core.cli_session_hop import apply_api_hop_messages

        cid = str(conversation_id or "")
        return apply_api_hop_messages("u0", cid or "api_agent", messages, conversation_id=cid)
    except Exception:
        logger.debug("API hop inject skipped", exc_info=True)
        return list(messages or [])


async def _compacted_context(conversation_id, messages):
    """Model context: summary tree replaces covered raw turns (REQ-37).

    Raw ``messages`` stay on the consumer and on disk. Failures fall back
    to the filtered list (status/info never reach the model — REQ-70).
    """
    try:
        from swarm.core.chat_compact import context_for_conversation

        compacted = await database_sync_to_async(context_for_conversation)(
            conversation_id, messages
        )
        return _apply_pending_api_hop(conversation_id, compacted)
    except Exception:
        logger.debug("compact context unavailable; using filtered transcript", exc_info=True)
        from swarm.core.speaker_identity import apply_speaker_identity
        from swarm.core.transcript_roles import messages_for_model

        filtered = apply_speaker_identity(messages_for_model(messages), adapter_id="openai_compat")
        return _apply_pending_api_hop(conversation_id, filtered)


def _status_line_html(text: str) -> str:
    """Bubble-less transcript line (CLI session notice; related to #362)."""
    return (
        '<div id="message-list" hx-swap-oob="beforeend">'
        f'<div class="chat-status-line os-chat-status">{escape(text)}</div>'
        "</div>"
    )


def _rate_limit_status_html(text: str, meta: dict) -> str:
    """Clickable rate-limit countdown chrome (REQ-88). Not a model bubble."""
    provider = escape(str(meta.get("provider") or ""))
    rule = escape(str(meta.get("reason") or ""))
    remaining = escape(str(meta.get("remaining_seconds") or 0))
    wait_until = escape(str(meta.get("wait_until_ms") or ""))
    field_id = ""
    settings = meta.get("settings") if isinstance(meta.get("settings"), dict) else {}
    if settings.get("field_id"):
        field_id = escape(str(settings["field_id"]))
    return (
        '<div id="message-list" hx-swap-oob="beforeend">'
        f'<div class="chat-status-line os-chat-status os-chat-status--rate-limit"'
        f' data-rate-limit="1" data-provider="{provider}" data-rule="{rule}"'
        f' data-remaining="{remaining}" data-wait-until="{wait_until}"'
        f' data-field-id="{field_id}" role="button" tabindex="0">'
        f"{escape(text)}</div>"
        "</div>"
    )


def _oob_append_html(contents_div_id: str, text: str) -> str:
    """HTMX OOB append chunk with HTML-escaped body text.

    Streaming replies previously interpolated model/user text into raw HTML,
    so a payload like ``<img onerror=…>`` executed before the final escaped
    template swap replaced the node.
    """
    return (
        f'<div hx-swap-oob="beforeend:#{contents_div_id}">'
        f"{escape(text)}</div>"
    )


class DjangoChatConsumer(AsyncWebsocketConsumer):
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
    boundary. ``tool_decision``, ``status``, and ``edit`` frames stay off
    that lock so an in-flight ``respond_with_*`` can still elicit tool
    approval.
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

    async def disconnect(self, close_code):
        if self.user.is_authenticated:
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

        if not message_text.strip():
            return

        await self._run_serialised_chat_turn(text_data_json, message_text)

    async def _run_serialised_chat_turn(self, text_data_json, message_text):
        """One ``respond_with_*`` at a time on this socket (REQ-171A-3 / #603)."""
        async with self._ensure_chat_turn_lock():
            # Per-message blueprint selection wins over the connection default.
            blueprint_id = text_data_json.get("blueprint") or getattr(
                self, "default_blueprint", None
            )
            self.active_agent = blueprint_id or getattr(self, "active_agent", None)
            params = text_data_json.get("params")
            if not isinstance(params, dict):
                params = None

            if params and params.get("new_session"):
                # REQ-65: CoS/user task asked for an empty session on this socket.
                self.messages = []
                self.ui_events = []

            _record_turn(self, "user", message_text, ts=_message_ts())

            user_message_html = render_to_string(
                "websocket_partials/user_message.html",
                {"message_text": message_text},
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

            if params and params.get("team"):
                from swarm.core.team_rosters import blueprint_id_for_team_target

                team_blueprint = blueprint_id_for_team_target(
                    params.get("team"), params.get("target")
                )
                if team_blueprint:
                    await self.respond_with_blueprint(
                        team_blueprint, contents_div_id, params=params
                    )
                else:
                    await self.respond_with_team_stub(params, message_text, contents_div_id)
            elif blueprint_id:
                await self.respond_with_blueprint(blueprint_id, contents_div_id, params=params)
            else:
                await self.respond_with_default_model(contents_div_id)

    async def _emit_new_cli_session_notice(self, blueprint_id, params):
        """REQ-92: send ``Started a new {cli} session.`` before assistant_start.

        Resume / same-session turns stay quiet here. The blueprint still yields
        the honest resumed/fallback line after it knows the outcome.
        """
        try:
            from swarm.core import chat_store
            from swarm.core.chat_transcript import (
                new_cli_session_notice_if_needed,
                transcript_already_has_notice,
            )

            user_key = None
            if getattr(self.user, "is_authenticated", False):
                user_key = chat_store.user_key_for(self.user)
            thread_params = dict(params or {})
            thread_params.setdefault("agent", blueprint_id)
            thread_params.setdefault("agent_id", blueprint_id)
            thread_params.setdefault(
                "conversation_id", getattr(self, "conversation_id", "") or ""
            )
            notice = new_cli_session_notice_if_needed(
                blueprint_id=blueprint_id,
                params=thread_params,
                user_key=user_key,
            )
            if not notice or transcript_already_has_notice(_display_rows(self), notice):
                return
            await self.send(text_data=_status_line_html(notice))
            _record_status(self, notice, ts=_message_ts())
        except Exception:
            logger.debug("CLI new-session notice pre-emit skipped", exc_info=True)

    async def respond_with_team_stub(self, params, message_text, contents_div_id):
        """Stub team send-to-all / member-target runtime (REQ-23).

        Echoes ``[team:<id> target:<all|memberId>]`` so the compose path is
        exercisable without a multi-agent roster executor.
        """
        team = str(params.get("team") or "")
        target = str(params.get("target") or "all")
        from swarm.core.team_cos import team_run_context
        from swarm.core.team_rosters import get_roster

        roster = get_roster(team) if team else None
        ctx = team_run_context(
            roster,
            target,
            messages=[{"role": "user", "content": message_text}],
        )
        # REQ-107: CoS brief is injected into model context only (not the
        # user-visible transcript). Stub still echoes so the compose path
        # stays exercisable without a live host.
        canned = f"[team:{team} target:{target}] {message_text}"
        if ctx.get("brief_applied"):
            canned = f"[team:{team} target:{target} cos:{ctx.get('chief_of_staff_id')}] {message_text}"
        await self.send(text_data=_oob_append_html(contents_div_id, canned))
        _record_turn(self, "assistant", canned)
        await self._emit_teammate_task_cards(params, message_text)
        final_html = render_to_string(
            "websocket_partials/final_system_message.html",
            {"contents_div_id": contents_div_id, "message": canned},
        )
        await self.send(text_data=final_html)
        await self._persist_completed_turn()
        await self._emit_suggestions_if_enabled(None)

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

    async def respond_with_blueprint(self, blueprint_id, contents_div_id, params=None):
        """Generate the assistant reply by running a discovered blueprint."""
        await _gate_provider_rate_limit(self, params=params, blueprint_id=blueprint_id)
        # In test mode, skip slow blueprint instantiation and return canned output.
        if os.environ.get("SWARM_TEST_MODE"):
            from pathlib import Path as _Path

            from django.conf import settings as _settings
            bp_dir = _Path(getattr(_settings, "BLUEPRINT_DIRECTORY", "src/swarm/blueprints"))
            known = {d.name for d in bp_dir.iterdir() if d.is_dir() and not d.name.startswith("_")} if bp_dir.is_dir() else set()
            from swarm.core.cli_catalog import cli_from_rail_id
            if blueprint_id not in known and not cli_from_rail_id(blueprint_id):
                await self.send_error_message(
                    contents_div_id,
                    f"Error: blueprint '{blueprint_id}' not found.",
                )
                return
            instruction = self.messages[-1]["content"] if self.messages else ""
            canned = f"[TEST-MODE] Jeeves at your service. You said: '{instruction}'" if blueprint_id == "jeeves" else f"[TEST-MODE] {blueprint_id} at your service. You said: '{instruction}'"
            await self.send(text_data=_oob_append_html(contents_div_id, canned))
            _record_turn(self, "assistant", canned, ts=_message_ts())
            final_html = render_to_string(
                "websocket_partials/final_system_message.html",
                {"contents_div_id": contents_div_id, "message": canned},
            )
            await self.send(text_data=final_html)
            await self._persist_completed_turn()
            await self._emit_suggestions_if_enabled(blueprint_id)
            return

        from swarm.views.chat_views import (
            _chunk_is_final,
            _extract_message_from_chunk,
        )

        try:
            from swarm.core.cli_catalog import cli_from_rail_id
            from swarm.views.utils import get_blueprint_instance

            from swarm.core.inference_list import (
                failover_notice,
                is_config_failure,
                is_rate_limit,
                normalize_inference_list,
                pick_scale_out,
                seat_id,
                seat_kind,
            )

            cli_name = None
            if isinstance(params, dict):
                raw_cli = params.get("cli")
                if isinstance(raw_cli, str) and raw_cli.strip():
                    cli_name = raw_cli.strip()
            if not cli_name:
                cli_name = cli_from_rail_id(blueprint_id)
            inference_seats = normalize_inference_list(
                params.get("inference_list") if isinstance(params, dict) else None
            )
            scale_out = bool(params and params.get("scale_out"))
            if scale_out and inference_seats:
                raw_idx = params.get("inference_index") if isinstance(params, dict) else 0
                try:
                    idx = int(raw_idx or 0)
                except (TypeError, ValueError):
                    idx = 0
                chosen = pick_scale_out(inference_seats, idx)
                inference_seats = [chosen] if chosen else []
            from swarm.core.agent_kind import API_AGENT_RAIL_ID, resolve_chat_blueprint_id

            profile = None
            if isinstance(params, dict):
                raw_model = params.get("model") or params.get("llm_profile")
                if isinstance(raw_model, str) and raw_model.strip() and raw_model.strip() != "default":
                    profile = raw_model.strip()
            # An explicit dropdown pick (params.model / params.cli) wins over
            # the inference list (#849 regression: a scale-out seat list cycled
            # claude → codex → gemini even when the user pinned agy/qwen in
            # the chat dropdown). Seats only fill values the user left open.
            explicit_model = bool(profile)
            explicit_cli = bool(cli_name)
            if inference_seats and not explicit_model:
                first = inference_seats[0]
                if seat_kind(first) == "llm":
                    profile = seat_id(first)
            if str(blueprint_id).strip().lower() == API_AGENT_RAIL_ID:
                run_id = resolve_chat_blueprint_id(blueprint_id)
                blueprint_instance = await get_blueprint_instance(run_id)
            else:
                run_id = "cli_agent" if cli_name else blueprint_id
                if (
                    inference_seats
                    and not explicit_cli
                    and seat_kind(inference_seats[0]) == "cli"
                ):
                    cli_name = seat_id(inference_seats[0])
                    run_id = "cli_agent"
                blueprint_instance = await get_blueprint_instance(run_id)
                if blueprint_instance is not None and cli_name and hasattr(
                    blueprint_instance, "set_params"
                ):
                    blueprint_instance.set_params({"cli": cli_name})
            if blueprint_instance is not None and profile:
                blueprint_instance.llm_profile_name = profile
        except Exception:
            logger.error(
                f"Error loading blueprint '{blueprint_id}'", exc_info=True
            )
            blueprint_instance = None

        if blueprint_instance is None:
            await self.send_error_message(
                contents_div_id,
                f"Error: blueprint '{blueprint_id}' was not found or could not be initialized.",
            )
            return

        self._blueprint_instance = blueprint_instance

        thread_params = {
            "conversation_id": getattr(self, "conversation_id", ""),
            "agent": blueprint_id,
            "agent_id": blueprint_id,
        }
        if getattr(self.user, "is_authenticated", False):
            try:
                from swarm.core import chat_store

                thread_params["user_key"] = chat_store.user_key_for(self.user)
            except Exception:
                logger.exception("Could not resolve chat user_key for CLI session")
        if isinstance(params, dict):
            thread_params.update(params)
        if hasattr(blueprint_instance, "set_params") and callable(blueprint_instance.set_params):
            existing = getattr(blueprint_instance, "_params", None)
            if not isinstance(existing, dict):
                existing = {}
            blueprint_instance.set_params({**existing, **thread_params})
        if isinstance(params, dict) and isinstance(params.get("enabled_tools"), list):
            from swarm.core.mcp_plugins import apply_plugin_mcp_runtime, swarm_config

            cfg = getattr(blueprint_instance, "config", None)
            if not isinstance(cfg, dict):
                cfg = swarm_config()
            apply_plugin_mcp_runtime(blueprint_instance, cfg, params.get("enabled_tools"))
        try:
            from swarm.core.agent_mailbox import install_mailbox_for_runtime

            install_mailbox_for_runtime(
                blueprint_instance,
                caller_id=str(blueprint_id or ""),
                user=getattr(self, "user", None),
                params=params if isinstance(params, dict) else {},
            )
        except Exception:
            logger.exception("Failed to install peer mailbox tools")
        try:
            from swarm.core.agent_lifecycle import install_lifecycle_for_runtime

            install_lifecycle_for_runtime(
                blueprint_instance,
                caller_id=str(blueprint_id or ""),
                user=getattr(self, "user", None),
                params=params if isinstance(params, dict) else {},
            )
        except Exception:
            logger.exception("Failed to install Support/CoS lifecycle tools")

        final_message = None
        token = None
        try:
            from swarm.core.safety import (
                SafetySession,
                channel_for_runtime,
                install_safety_session,
                safety_role_assigned,
            )

            channel = channel_for_runtime(blueprint_id=blueprint_id)
            metadata = getattr(blueprint_instance, "metadata", None)
            if not isinstance(metadata, dict):
                metadata = {}
            session = SafetySession(
                agent_id=str(blueprint_id),
                channel=channel,
                safety_assigned=safety_role_assigned(
                    getattr(blueprint_instance, "agents", None),
                    metadata=metadata,
                ),
                elicit_fn=self.elicit_tool_approval,
                emit_fn=self.emit_tool_event,
            )
            token = install_safety_session(session)
            compact_result = await _auto_compress_before_send(self, params=params)
            if compact_result is not None and compact_result.context and (
                compact_result.acted or getattr(compact_result, "strategy", "") == "cull"
            ):
                model_messages = compact_result.context
            else:
                model_messages = await _compacted_context(
                    getattr(self, "conversation_id", ""),
                    self.messages,
                )
            from swarm.core.skill_attach import (
                apply_skills_to_messages,
                blueprint_applies_own_skills,
            )

            skill_owner = run_id if "run_id" in locals() else blueprint_id
            if (
                isinstance(params, dict)
                and not blueprint_applies_own_skills(str(skill_owner))
            ):
                model_messages, applied_skills, missing_skills = apply_skills_to_messages(
                    model_messages, params
                )
                for name in applied_skills:
                    await self.send(
                        text_data=_oob_append_html(
                            contents_div_id,
                            f"_Applying skill `{name}` (`skills/{name}/SKILL.md`)…_",
                        )
                    )
                for name in missing_skills:
                    await self.send(
                        text_data=_oob_append_html(
                            contents_div_id,
                            f"_Skill `{name}` not found — running without it._",
                        )
                    )
            async for chunk in blueprint_instance.run(model_messages):
                if isinstance(chunk, dict) and chunk.get("type") == "cli_session_notice":
                    notice = str(chunk.get("content") or "").strip()
                    if notice:
                        from swarm.core.chat_transcript import (
                            transcript_already_has_notice,
                        )

                        if not transcript_already_has_notice(_display_rows(self), notice):
                            await self.send(text_data=_status_line_html(notice))
                            _record_status(self, notice, ts=_message_ts())
                    continue
                message = _extract_message_from_chunk(chunk)
                if message is None:
                    continue
                final_message = message
                if _chunk_is_final(chunk):
                    break
        except Exception as e:
            logger.error(
                f"Error running blueprint '{blueprint_id}': {e}", exc_info=True
            )
            from swarm.core.inference_list import (
                failover_notice,
                is_config_failure,
                is_rate_limit,
                normalize_inference_list,
                retry_params,
                should_failover,
            )

            seats = normalize_inference_list(
                params.get("inference_list") if isinstance(params, dict) else None
            )
            rest = seats[1:] if seats else []
            scale_out = bool(params and params.get("scale_out"))
            if should_failover(e, rest, scale_out=scale_out):
                notice = failover_notice(seats[0], rest[0])
                await self.send(text_data=_status_line_html(notice))
                _record_status(self, notice, ts=_message_ts())
                await self.respond_with_blueprint(
                    blueprint_id,
                    contents_div_id,
                    params=retry_params(params, rest),
                )
                return
            if (
                seats
                and not rest
                and not scale_out
                and is_config_failure(e)
                and not is_rate_limit(e)
            ):
                notice = failover_notice(seats[0], None, exhausted=True)
                await self.send(text_data=_status_line_html(notice))
                _record_status(self, notice, ts=_message_ts())
            from swarm.utils.env_utils import client_safe_error_message

            await self.send_error_message(
                contents_div_id,
                client_safe_error_message(
                    e,
                    public=f"Error: blueprint '{blueprint_id}' failed while generating a reply.",
                ),
            )
            return
        finally:
            if token is not None:
                from swarm.core.safety import reset_safety_session

                reset_safety_session(token)

        if not isinstance(final_message, dict) or final_message.get("content") is None:
            await self.send_error_message(
                contents_div_id,
                f"Error: blueprint '{blueprint_id}' did not return a reply.",
            )
            return

        from swarm.core.model_text import (
            error_body_message,
            sanitize_model_text,
        )

        full_message = sanitize_model_text(final_message["content"])
        if not full_message:
            await self.send_error_message(
                contents_div_id,
                "Error: the model returned no usable text (empty or tokenizer leftovers).",
            )
            return

        # #133: gateways answer HTTP 200 with an OpenAI-compatible JSON error
        # body (or its head) instead of raising; never persist that as a
        # "successful" assistant reply. Name the LLM profile so the user knows
        # which profile's model/base_url to check in Settings. Check the
        # sanitized text so ANSI/special-token-prefixed bodies are caught too.
        error_text = error_body_message(full_message)
        if error_text:
            profile_hint = ""
            if isinstance(params, dict):
                raw = params.get("model") or params.get("llm_profile")
                if isinstance(raw, str) and raw.strip():
                    profile_hint = f" (LLM profile '{raw.strip()}')"
            await self.send_error_message(
                contents_div_id,
                "Error: "
                + error_text
                + profile_hint
                + ". Check the profile's model/base_url in Settings → LLM profiles.",
            )
            return
        await self.send(text_data=_oob_append_html(contents_div_id, full_message))

        _record_turn(self, "assistant", full_message, ts=_message_ts())
        await self._emit_pr_opened_from_text(full_message)

        final_message_html = render_to_string(
            "websocket_partials/final_system_message.html",
            {
                "contents_div_id": contents_div_id,
                "message": full_message,
            },
        )
        await self.send(text_data=final_message_html)
        await self._persist_completed_turn()
        await self._emit_suggestions_if_enabled(blueprint_id, blueprint=blueprint_instance)
        await self._emit_advisor_followup(blueprint_id, full_message, params=params)
        # Wired skeptic audits the reply and can auto-prompt bounded rework.
        user_prompt = ""
        for row in reversed(self.messages or []):
            if row.get("role") == "user":
                user_prompt = str(row.get("content") or "")
                break
        await self._run_skeptic_rework_loop(blueprint_id, user_prompt, full_message, params=params)

    async def _emit_advisor_followup(self, agent_blueprint_id, reply_text, params=None):
        """Wired advisor posts one concise follow-up advice note.

        After the advised agent's turn completes, the advisor reviews the
        transcript slice and posts a single advice line — styled as a status
        line, never persisted as a model turn, so later context stays clean.
        Multiple advisors in a roster resolve to the first (no double-fire);
        failure to reach the advisor degrades to a quiet status note.
        """
        try:
            from swarm.core.team_rosters import advisor_blueprint_for_agent

            team_id = params.get("team") if isinstance(params, dict) else None
            advisor_id = advisor_blueprint_for_agent(team_id, agent_blueprint_id)
            if not advisor_id:
                return

            advice = await self._generate_advice_note(advisor_id, agent_blueprint_id, reply_text)
            if advice:
                await self.send(text_data=_status_line_html(f"Advisor: {advice}"))
            else:
                await self.send(
                    text_data=_status_line_html(
                        f"Advisor ({advisor_id}) had no advice for this turn."
                    )
                )
        except Exception:
            logger.exception("Advisor follow-up failed")
            try:
                await self.send(text_data=_status_line_html("Advisor follow-up failed."))
            except Exception:
                pass

    async def _generate_advice_note(self, advisor_id, agent_id, reply_text):
        """One bounded advice generation against the default chat model.

        Deliberately NOT a full re-answer: a compact transcript slice plus a
        strict advisor prompt, non-streaming, short answer. Returns None when
        the advisor produces nothing usable.
        """
        from swarm.core.blueprint_discovery import discover_blueprints

        advisor_name = advisor_id
        for row in discover_blueprints():
            if getattr(row, "id", None) == advisor_id:
                advisor_name = getattr(row, "name", None) or advisor_id
                break

        slice_text = "\n".join(
            f"{row.get('role')}: {row.get('content')}" for row in _display_rows(self)[-6:]
        )
        prompt = (
            f"You are {advisor_name}, an advisor wired to agent '{agent_id}'. "
            "Review the exchange below and reply with ONE concise follow-up "
            "advice note (max 2 sentences). Do not re-answer the task. "
            "If there is nothing to improve, reply exactly: none\n\n"
            f"{slice_text}"
        )

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
            model = model_id_for_profile(resolve_chat_model(config).profile, config)

        from openai import AsyncOpenAI

        client = AsyncOpenAI(**client_kwargs)
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Be terse. One advice note, max 2 sentences."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=120,
            )
            text = str(
                getattr(getattr(completion, "choices", [None])[0], "message", None)
                and completion.choices[0].message.content
                or ""
            ).strip()
        except Exception as exc:
            logger.warning("Advisor LLM call failed: %s", exc)
            return None
        if not text or text.lower() in {"none", "n/a", "nothing"}:
            return None
        return text[:400]

    async def _run_skeptic_rework_loop(self, blueprint_id, prompt, first_output, params=None):
        """Adversarial audit + bounded rework when a skeptic is wired.

        After the worker's first reply completes, the roster-wired skeptic
        (role='skeptic' + team wires, resolved like the advisor) audits
        the exchange. FAIL verdicts auto-prompt the worker with the findings
        (rework rounds, default 2, cap 5 — never unbounded). Each round is
        surfaced as a status line and recorded, so the transcript shows the
        rework honestly. FAIL-closed holds: an unusable verdict counts as
        not accomplished.
        """
        try:
            from swarm.core.team_rosters import skeptic_blueprint_for_agent

            team_id = params.get("team") if isinstance(params, dict) else None
            skeptic_id = skeptic_blueprint_for_agent(team_id, blueprint_id)
            if not skeptic_id:
                return

            from swarm.core.skeptic_loop import (
                DEFAULT_SKEPTIC_ROUNDS,
                normalize_skeptic_rounds,
                run_skeptic_rework_loop,
            )

            max_rounds = normalize_skeptic_rounds(
                os.environ.get("SKEPTIC_MAX_ROUNDS", DEFAULT_SKEPTIC_ROUNDS)
            )

            async def _review(_orig_prompt, output):
                return await self._skeptic_verdict(skeptic_id, blueprint_id, prompt, output)

            async def _worker(rework_prompt):
                return await self._skeptic_worker_reply(blueprint_id, rework_prompt, params)

            async def _on_round(round_i, _rework_prompt, _output):
                await self.send(
                    text_data=_status_line_html(
                        f"Skeptic rework {round_i}/{max_rounds}: addressing findings…"
                    )
                )
                return True

            result = await run_skeptic_rework_loop(
                prompt=prompt,
                first_output=first_output,
                worker_fn=_worker,
                review_fn=_review,
                max_rounds=max_rounds,
                on_round=_on_round,
            )
            if result.rounds:
                verdict_note = (
                    "skeptic PASS"
                    if result.accomplished
                    else "skeptic verdict pending" if result.accomplished is None else "skeptic FAIL"
                )
                await self.send(
                    text_data=_status_line_html(
                        f"Skeptic: {result.rounds} rework round(s) — {verdict_note}."
                    )
                )
                # Persist the reworked answer over the failed first draft.
                _record_turn(self, "assistant", result.output, ts=_message_ts())
                await self._persist_completed_turn()
        except Exception:
            logger.exception("Skeptic rework loop failed")
            try:
                await self.send(text_data=_status_line_html("Skeptic review failed."))
            except Exception:
                pass

    async def _skeptic_verdict(self, skeptic_id, agent_id, original_prompt, output):
        """One skeptic review call against the default chat model.

        Returns a plain string; ``parse_skeptic_verdict`` does the FAIL-closed
        parsing ("YES"/"NO ..." first token, prose → not accomplished).
        """
        slice_text = "\n".join(
            f"{row.get('role')}: {row.get('content')}" for row in _display_rows(self)[-8:]
        )
        review_prompt = (
            f"You are {skeptic_id}, the skeptic wired to agent '{agent_id}'. "
            "Audit whether the agent accomplished the original task with doubt: "
            "test claims, inspect the transcript below.\n\n"
            f"Original prompt:\n{original_prompt}\n\n"
            f"Agent output:\n{output}\n\n"
            "Transcript tail:\n"
            f"{slice_text}\n\n"
            "Reply with a first token verdict: YES (accomplished) or NO (not "
            "accomplished), then on NO one concise line of actionable findings."
        )
        return await self._short_default_model_call(review_prompt, max_tokens=200)

    async def _skeptic_worker_reply(self, agent_id, rework_prompt, params=None):
        """One worker rework generation (non-streaming) for the loop."""
        system = f"You are {agent_id}. Address the skeptic's findings completely."
        return (
            await self._short_default_model_call(
                rework_prompt, max_tokens=1400, system=system
            )
            or ""
        )

    async def _short_default_model_call(self, prompt, *, max_tokens, system=None):
        """Single non-streaming default-model completion (advisor follow-up pattern)."""
        from swarm.core.blueprint_discovery import discover_blueprints
        from swarm.utils.env_utils import get_llm_base_url, openai_client_kwargs

        base_url = get_llm_base_url()
        client_kwargs = openai_client_kwargs()
        model = (
            os.environ.get("LITELLM_MODEL")
            or os.environ.get("OPENAI_MODEL")
            or os.environ.get("DEFAULT_LLM")
        )
        if not model:
            from swarm.core.llm_task_routing import model_id_for_profile, resolve_chat_model

            model = model_id_for_profile(resolve_chat_model().profile)

        from openai import AsyncOpenAI

        client = AsyncOpenAI(**client_kwargs)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
            )
            text = str(
                getattr(getattr(completion, "choices", [None])[0], "message", None)
                and completion.choices[0].message.content
                or ""
            ).strip()
        except Exception as exc:
            logger.warning("Skeptic LLM call failed: %s", exc)
            return None
        if not text or text.lower() in {"none", "n/a", "nothing"}:
            return None
        return text

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
        """
        if not getattr(self.user, "is_authenticated", False):
            return
        conversation_id = getattr(self, "conversation_id", None)
        if not conversation_id:
            return
        try:
            await self.save_conversation(conversation_id, self.messages)
        except Exception:
            logger.exception(
                "Failed to persist completed chat turn %s", conversation_id
            )

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
        """JSON tool-status / approval / PR-opened / teammate-task / suggestions frames."""
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
            from swarm.core.llm_task_routing import model_id_for_profile, resolve_chat_model

            route = resolve_chat_model()
            model = model_id_for_profile(route.profile)
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
                    getattr(self, "conversation_id", ""),
                    self.messages,
                )
            stream = await client.chat.completions.create(
                model=model,
                messages=model_messages,
                stream=True,
            )
            async for chunk in stream:
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

    async def apply_message_edit(self, edit):
        """Replace one transcript turn and persist it (REQ-49)."""
        from swarm.core.agent_kind import can_edit_agent_messages

        agent = getattr(self, "active_agent", None) or getattr(self, "default_blueprint", None)
        if not can_edit_agent_messages(agent):
            logger.info("Ignoring message edit on non-API agent %s", agent)
            return
        if not isinstance(edit, dict):
            logger.warning("Ignoring malformed chat edit frame: %.200r", edit)
            return
        index = edit.get("index")
        content = edit.get("content")
        if type(index) is not int or not isinstance(content, str):
            logger.warning("Ignoring malformed chat edit frame: %.200r", edit)
            return
        if index < 0 or index >= len(self.messages):
            logger.warning(
                "Ignoring chat edit index %s (transcript length %s)",
                index,
                len(self.messages),
            )
            return
        current = dict(self.messages[index])
        current["content"] = content
        current["edited"] = True
        self.messages[index] = current
        conversation_id = getattr(self, "conversation_id", None)
        if conversation_id:
            await self.save_conversation(conversation_id, self.messages)

    @database_sync_to_async
    def fetch_conversation(self, conversation_id):
        """Fetch transcript: cache, then JSON, then Django backfill.

        Load order matches ``GET /chat/thread/`` (``swarm.core.thread_load``):

        0. On-mode mint (REQ-171C-4) — refuse reuse before any row load.
        1. In-memory cache keyed by ``(user_id, conversation_id)``.
        2. JSON disk (source of truth) — keeps ``ts`` / ``edited``.
        3. Django ``ChatMessage`` rows when the JSON file is missing.

        Always returns a COPY: two tabs sharing a conversation must not mutate
        each other's in-flight transcript list (interleaved appends previously
        corrupted both and double-persisted merged turns on disconnect).
        """
        from swarm.core import chat_store
        from swarm.core.session_policy import resolve_on_mode_conversation
        from swarm.core.thread_load import load_thread

        agent_id = getattr(self, "default_blueprint", None) or getattr(
            self, "active_agent", None
        )
        # REQ-171C-4 / C-H7: mint or refuse reuse before loading the old Django row.
        if agent_id:
            minted = resolve_on_mode_conversation(self.user, agent_id, conversation_id)
            if minted is not None:
                self.conversation_id = minted.conversation_id
                conversation_id = minted.conversation_id
                cache_key = _conversation_cache_key(self.user, conversation_id)
                IN_MEMORY_CONVERSATIONS[cache_key] = []
                IN_MEMORY_UI_EVENTS[cache_key] = []
                self.ui_events = []
                return []

        cache_key = _conversation_cache_key(self.user, conversation_id)
        if cache_key in IN_MEMORY_CONVERSATIONS:
            self.ui_events = list(IN_MEMORY_UI_EVENTS.get(cache_key, []))
            return list(IN_MEMORY_CONVERSATIONS[cache_key])

        on_mode = False
        default_cid = ""
        try:
            from swarm.core.agent_settings import is_new_chat_per_task

            if agent_id:
                default_cid = chat_store.conversation_id_for(self.user, agent_id)
                on_mode = bool(is_new_chat_per_task(agent_id))
        except Exception:
            logger.debug("new-chat-per-task check failed; using reuse fallback", exc_info=True)

        session_id = ""
        if conversation_id and (conversation_id != default_cid or on_mode):
            session_id = conversation_id

        loaded = load_thread(
            self.user,
            agent_id or "",
            requested_cid=conversation_id,
            session_id=session_id,
            default_cid=default_cid,
            fresh_task=on_mode,
        )
        if loaded.turns or loaded.events:
            IN_MEMORY_CONVERSATIONS[cache_key] = list(loaded.turns)
            IN_MEMORY_UI_EVENTS[cache_key] = list(loaded.events)
            self.ui_events = list(loaded.events)
            return list(loaded.turns)
        self.ui_events = []
        return []

    @database_sync_to_async
    def save_conversation(self, conversation_id, new_messages):
        """Replace DB messages with the current in-memory transcript.

        Disconnect always persists the full transcript. Without clearing
        prior rows, reconnect → disconnect would bulk_create duplicates.

        Lookup is by conversation_id PK only (avoids IntegrityError when the
        row exists for another student); ownership is then validated.
        """
        from swarm.core.transcript_roles import is_ui_only_role, split_store

        cache_key = _conversation_cache_key(self.user, conversation_id)
        from swarm.core.agent_sessions import get_or_create_session, touch_session

        agent_id = getattr(self, "active_agent", None) or getattr(self, "default_blueprint", None)
        events = list(getattr(self, "ui_events", None) or [])
        turns, events = split_store(new_messages, events, stamp_seq=False)
        self.messages = list(turns)
        self.ui_events = list(events)
        try:
            chat = get_or_create_session(
                self.user,
                conversation_id,
                agent_id=str(agent_id or ""),
            )
        except PermissionError:
            logger.warning(
                "Refusing to save conversation %s: owned by another user (requested by %s)",
                conversation_id,
                self.user,
            )
            return

        chat_messages = [
            ChatMessage(
                conversation=chat,
                sender=message["role"],
                content=message["content"],
            )
            for message in turns
            if not is_ui_only_role(message.get("role"))
        ]
        # Idempotent replace: delete then insert current transcript.
        ChatMessage.objects.filter(conversation=chat).delete()
        ChatMessage.objects.bulk_create(chat_messages)
        try:
            touch_session(chat, turns, agent_id=str(agent_id or ""))
        except Exception:
            logger.exception("Failed to touch Django session %s", conversation_id)

        IN_MEMORY_CONVERSATIONS[cache_key] = list(turns)
        IN_MEMORY_UI_EVENTS[cache_key] = list(events)
        _save_agent_json(
            self.user,
            getattr(self, "active_agent", None) or getattr(self, "default_blueprint", None),
            turns,
            conversation_id=conversation_id,
            ui_events=events,
        )

    @database_sync_to_async
    def delete_conversation(self, conversation_id):
        """
        Delete the conversation from DB if empty.
        """
        cache_key = _conversation_cache_key(self.user, conversation_id)
        try:
            chat = ChatConversation.objects.get(conversation_id=conversation_id, student=self.user)
            if not chat.messages.exists():  # Check if there are any messages before deleting
                chat.delete()
                if cache_key in IN_MEMORY_CONVERSATIONS:
                    del IN_MEMORY_CONVERSATIONS[cache_key]  # Cleanup memory cache
                IN_MEMORY_UI_EVENTS.pop(cache_key, None)
        except ChatConversation.DoesNotExist:
            logger.warning(f"Attempted to delete non-existent conversation: {conversation_id} for user: {self.user}")

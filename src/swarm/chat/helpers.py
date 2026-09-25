"""#855 slice 1 — consumers.py module-level helpers, moved verbatim.

``R`` is a late-bound handle to the ``swarm.consumers`` module: every
reference to a kernel import, head constant, or sibling helper routes
through it at call time, so ``patch("swarm.consumers.<name>")`` keeps
landing even when the caller lives here (same doctrine as the #1000
remote_impls move). The binding is deferred to first attribute access
so either module can be imported first — no circular import.
consumers.py rebinds these names eagerly after its class.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import time
from datetime import datetime, timezone  # noqa: F401 — _message_ts (R._message_ts)


class _ConsumersRef:
    """Late-bound swarm.consumers handle (import deferred)."""

    def __getattr__(self, name):
        return getattr(importlib.import_module("swarm.consumers"), name)


R = _ConsumersRef()

# #1170: the chat-side provider gate must not hold a turn (and its agent lock)
# forever when a bucket stays saturated. Past this cap the gate aborts the turn
# honestly; override with SWARM_CHAT_GATE_WAIT_CAP_S.
_PROVIDER_GATE_CAP_ENV = "SWARM_CHAT_GATE_WAIT_CAP_S"
_DEFAULT_GATE_CAP_S = 60.0


class ProviderGateTimeout(RuntimeError):
    """The provider gate exceeded its wait cap; the turn must fail honestly."""


def _chat_gate_wait_cap_s() -> float:
    raw = os.environ.get(_PROVIDER_GATE_CAP_ENV, "")
    try:
        value = float(raw) if raw.strip() else _DEFAULT_GATE_CAP_S
    except ValueError:
        value = _DEFAULT_GATE_CAP_S
    return max(1.0, value)


def _is_bootstrap_turn(blueprint_id: str, params) -> bool:
    """True when this turn should be served by the Bootstrap provider (#893)."""
    try:
        from swarm.core.bootstrap_provider import is_bootstrap_active

        return is_bootstrap_active(blueprint_id, params)
    except Exception:
        return False


async def _expand_model_messages(consumer, messages):
    """Inline image attachment bytes as OpenAI ``image_url`` parts (REQ-811)."""
    if not any(
        isinstance(msg, dict) and msg.get("attachments") for msg in (messages or [])
    ):
        return messages
    from swarm.core import chat_attachments

    return await R.database_sync_to_async(chat_attachments.expand_messages_for_model)(
        getattr(consumer, "user", None), messages
    )


def _message_ts() -> str:
    return datetime.now(R.timezone.utc).isoformat()


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
        R.logger.exception("Failed to persist agent chat JSON")


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
        R.logger.exception("Failed to load agent chat JSON")
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
    return R._load_agent_record(user, agent_id, conversation_id=conversation_id)["messages"]


def _credential_hint() -> str:
    """Best-effort naming of the config knob a failed turn is missing.

    Empty when credentials look fine, so a non-credential failure is not blamed
    on a key that is present (see ``swarm.core.llm_diagnostics``).
    """
    try:
        from swarm.core.llm_diagnostics import llm_credential_hint

        return llm_credential_hint()
    except Exception:
        R.logger.debug("LLM credential diagnosis failed", exc_info=True)
        return ""


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
    """REQ-88: wait on the shared provider queue before a send (including test mode).

    #1170: the gate's verdict is now *honored*, visibly, with a cap.

    1. The wait status is emitted the moment the wait **starts** — the old
       ``on_wait`` hook only fired from inside ``acquire``'s retry loop, so a
       long first wait left the composer animating with no copy.
    2. The total wait is capped (``SWARM_CHAT_GATE_WAIT_CAP_S``, default 60s).
       Past the cap, ``ProviderGateTimeout`` is raised so the responder fails
       the turn honestly instead of holding the per-agent lock indefinitely.
    3. The gate's ``WaitDecision`` is returned so ``respond_with_blueprint``
       proceeds exactly when the gate allowed it.
    """
    emitted = {"done": False}
    wait_started = {"done": False}
    cap_s = _chat_gate_wait_cap_s()
    deadline = time.monotonic() + cap_s

    async def on_wait(decision):
        if not wait_started["done"]:
            # #1170: copy on the wire the moment waiting begins.
            wait_started["done"] = True
            from swarm.core.provider_rate_limit import format_wait_text

            meta = decision.public_dict()
            text = format_wait_text(decision)
            try:
                await consumer.send(text_data=R._rate_limit_status_html(text, meta))
            except Exception:
                R.logger.debug("rate-limit status send skipped", exc_info=True)
            R._record_status(
                consumer,
                text,
                role="info",
                kind="rate_limit",
                rate_limit=meta,
                ts=R._message_ts(),
            )
        if emitted["done"]:
            return
        emitted["done"] = True

    async def _run_gate():
        try:
            from swarm.core.provider_rate_limit import gate_provider_send
        except Exception:
            R.logger.debug("provider rate-limit gate import skipped", exc_info=True)
            return None
        messages = getattr(consumer, "messages", None) or []
        return await gate_provider_send(
            params=params if isinstance(params, dict) else None,
            blueprint_id=str(blueprint_id or ""),
            messages=messages,
            on_wait=on_wait,
        )

    try:
        gate_task = asyncio.ensure_future(_run_gate())
        try:
            decision = await asyncio.wait_for(gate_task, timeout=cap_s)
        except asyncio.TimeoutError:
            gate_task.cancel()
            try:
                await gate_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            if not wait_started["done"]:
                # The wait never even announced itself — say why the turn died.
                from swarm.core.provider_rate_limit import format_wait_text

                text = (
                    f"Provider gate: still waiting for capacity after {cap_s:.0f}s — "
                    "the message was not sent. Try again shortly, or raise the "
                    "provider's rate limits in Settings."
                )
                try:
                    await consumer.send(text_data=R._rate_limit_status_html(text, {}))
                except Exception:
                    R.logger.debug("gate cap status send skipped", exc_info=True)
            seat = ""
            if isinstance(params, dict):
                seat = str(
                    params.get("remote") or params.get("remote_id") or params.get("cli") or ""
                ).strip()
            raise ProviderGateTimeout(
                f"Provider gate: {seat or blueprint_id or 'this seat'} is throttled — "
                f"still waiting for capacity after {cap_s:.0f}s; the message was not sent. "
                "Try again shortly or raise the provider's limits in Settings."
            ) from None
        return decision
    except ProviderGateTimeout:
        raise
    except Exception:
        R.logger.debug("provider rate-limit gate skipped", exc_info=True)
        return None


async def _auto_compress_before_send(consumer, params=None, model_id=None):
    """REQ-87: compact older span when estimated tokens hit N% of known max."""
    try:
        from swarm.core.agent_kind import classify_agent_kind
        from swarm.core.context_cull_policy import prepare_context_before_send

        active_id = str(
            getattr(consumer, "active_agent", None)
            or getattr(consumer, "default_blueprint", "")
            or ""
        )
        if classify_agent_kind(active_id) != "api":
            return None

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
        result = await R.database_sync_to_async(prepare_context_before_send)(
            user=getattr(consumer, "user", None),
            conversation_id=getattr(consumer, "conversation_id", "") or "",
            agent_id=active_id,
            messages=getattr(consumer, "messages", None) or [],
            model_id=str(mid).strip() if isinstance(mid, str) and mid.strip() else None,
            inference_entry=inference_entry,
        )
        if result.info:
            await consumer.send(text_data=R._status_line_html(result.info))
            R._record_status(consumer, result.info, ts=R._message_ts())
        return result
    except Exception:
        R.logger.debug("auto-compress hook skipped", exc_info=True)
        return None


def _apply_pending_api_hop(consumer, conversation_id, messages):
    """Seed a pending hop at turn assembly (#531 CLI, #900 api/remote).

    The hop API stores pending hops under the **agent id** record; the
    previous lookup keyed by conversation id (and a hardcoded "u0"), so the
    seed never matched and cross-backend hops silently carried nothing.
    """
    try:
        from swarm.core.agent_kind import classify_agent_kind
        from swarm.core.cli_session_hop import apply_cross_kind_hop_messages

        agent_id = str(
            getattr(consumer, "active_agent", None)
            or getattr(consumer, "default_blueprint", "")
            or ""
        )
        if not agent_id:
            return list(messages or [])
        kind = classify_agent_kind(agent_id)
        if kind not in ("cli", "api", "remote"):
            return list(messages or [])
        if kind == "cli":
            # CLI turn injection happens in prepare_cli_turn (blueprint).
            return list(messages or [])
        user_key = R._user_key_for_hop(getattr(consumer, "user", None))
        return apply_cross_kind_hop_messages(
            user_key,
            agent_id,
            messages,
            to_kind=kind,
            to_id=agent_id,
            conversation_id=str(conversation_id or ""),
        )
    except Exception:
        R.logger.debug("cross-kind hop inject skipped", exc_info=True)
        return list(messages or [])


def _user_key_for_hop(user):
    """Same user_key convention the hop API persists under."""
    try:
        from swarm.core.chat_store import user_key_for

        if user is not None and getattr(user, "is_authenticated", False):
            return user_key_for(user)
    except Exception:
        pass
    return "u0"


async def _compacted_context(consumer, conversation_id, messages):
    """Model context: summary tree replaces covered raw turns (REQ-37).

    Raw ``messages`` stay on the consumer and on disk. Failures fall back
    to the filtered list (status/info never reach the model — REQ-70).
    ``consumer`` is required: the #900 cross-kind hop seed reads the
    active agent off it, and this function used to NameError on exactly
    that call (regression pin: tests/unit/test_consumers_hop_seed.py).
    """
    try:
        from swarm.core.chat_compact import context_for_conversation

        compacted = await R.database_sync_to_async(context_for_conversation)(
            conversation_id, messages
        )
        return R._apply_pending_api_hop(consumer, conversation_id, compacted)
    except Exception:
        R.logger.debug("compact context unavailable; using filtered transcript", exc_info=True)
        from swarm.core.speaker_identity import apply_speaker_identity
        from swarm.core.transcript_roles import messages_for_model

        filtered = apply_speaker_identity(messages_for_model(messages), adapter_id="openai_compat")
        return R._apply_pending_api_hop(consumer, conversation_id, filtered)


def _status_line_html(text: str) -> str:
    """Bubble-less transcript line (CLI session notice; related to #362)."""
    return (
        '<div id="message-list" hx-swap-oob="beforeend">'
        f'<div class="chat-status-line os-chat-status">{R.escape(text)}</div>'
        "</div>"
    )


def _rate_limit_status_html(text: str, meta: dict) -> str:
    """Clickable rate-limit countdown chrome (REQ-88). Not a model bubble."""
    provider = R.escape(str(meta.get("provider") or ""))
    rule = R.escape(str(meta.get("reason") or ""))
    remaining = R.escape(str(meta.get("remaining_seconds") or 0))
    wait_until = R.escape(str(meta.get("wait_until_ms") or ""))
    field_id = ""
    settings = meta.get("settings") if isinstance(meta.get("settings"), dict) else {}
    if settings.get("field_id"):
        field_id = R.escape(str(settings["field_id"]))
    return (
        '<div id="message-list" hx-swap-oob="beforeend">'
        f'<div class="chat-status-line os-chat-status os-chat-status--rate-limit"'
        f' data-rate-limit="1" data-provider="{provider}" data-rule="{rule}"'
        f' data-remaining="{remaining}" data-wait-until="{wait_until}"'
        f' data-field-id="{field_id}" role="button" tabindex="0">'
        f"{R.escape(text)}</div>"
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
        f"{R.escape(text)}</div>"
    )



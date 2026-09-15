"""SPA chat thread restore + Settings-only retention actions.

``GET /chat/thread/`` hydrates an agent thread after reload / agent switch.
Load order is JSON first, then Django backfill — same helper as WS
``fetch_conversation`` (``swarm.core.thread_load``).
``POST /chat/compact/`` summarises a span (REQ-37). Retention (archive,
restore, empty trash) lives on ``/settings/`` only.
"""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from swarm.core import chat_attachments, chat_store
from swarm.core.agent_kind import can_edit_agent_messages, classify_agent_kind
from swarm.core.chat_compact import (
    CompactError,
    compact_backlog,
    list_summaries,
    summary_to_dict,
)
from swarm.core.thread_load import load_thread
from swarm.core.thread_load import public_messages as _public_messages
from swarm.models import ChatAttachment, ChatMessage, ConversationSummary

logger = logging.getLogger(__name__)

_ALLOWED_ACTIONS = frozenset({"archive", "archive_all", "restore", "empty_trash"})


def _user_key(user) -> str:
    return chat_store.user_key_for(user)


def _json_body(request) -> dict:
    content_type = request.content_type or ""
    if "application/json" in content_type:
        try:
            payload = json.loads(request.body.decode() or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _summaries_for(*conversation_ids: str) -> tuple[str, list[dict]]:
    """Return ``(conversation_id, summaries)`` for the first id that has rows."""
    seen: list[str] = []
    for cid in conversation_ids:
        text = (cid or "").strip()
        if not text or text in seen:
            continue
        seen.append(text)
        rows = [summary_to_dict(row) for row in list_summaries(text)]
        if rows:
            return text, rows
    return (seen[0] if seen else ""), []


def _thread_payload_messages(turns, events) -> list[dict]:
    from swarm.core.transcript_roles import reconstruct_display

    return _public_messages(reconstruct_display(turns, events))


def _sync_django_and_memory(
    user, messages, conversation_ids: list[str], *, agent_id: str = ""
) -> None:
    from swarm.consumers import IN_MEMORY_CONVERSATIONS, _conversation_cache_key
    from swarm.core.agent_sessions import get_or_create_session, touch_session

    seen: set[str] = set()
    for cid in conversation_ids:
        if not cid or cid in seen:
            continue
        seen.add(cid)
        try:
            chat = get_or_create_session(user, cid, agent_id=agent_id)
        except PermissionError:
            continue
        ChatMessage.objects.filter(conversation=chat).delete()
        ChatMessage.objects.bulk_create(
            [
                ChatMessage(
                    conversation=chat,
                    sender=item.get("role", "user"),
                    content=item.get("content", ""),
                )
                for item in messages
            ]
        )
        mem_rows: list[dict] = []
        for item in messages:
            row = {
                "role": item.get("role", "user"),
                "content": item.get("content", ""),
            }
            ts = item.get("ts") or item.get("timestamp")
            if isinstance(ts, str) and ts:
                row["ts"] = ts
            if item.get("edited"):
                row["edited"] = True
            mem_rows.append(row)
        IN_MEMORY_CONVERSATIONS[_conversation_cache_key(user, cid)] = mem_rows
        try:
            touch_session(chat, messages, agent_id=agent_id)
        except Exception:
            logger.exception("Failed to touch Django session %s", cid)


@login_required
@ensure_csrf_cookie
@require_http_methods(["GET", "POST", "PATCH"])
def chat_thread(request):
    """Hydrate (GET), append (POST), or edit (PATCH) the persisted transcript for one agent."""
    from swarm.core.agent_settings import is_new_chat_per_task
    from swarm.core.session_policy import list_active_task_sessions, resolve_on_mode_conversation

    agent_raw = request.GET.get("agent")
    agent = chat_store.normalize_agent_id(agent_raw)
    if agent_raw and str(agent_raw).startswith(("remote:", "remote-")):
        # Remote rail seats ('remote:<kind>' from hydrate, 'remote-<kind>' from
        # SPA status appends) persist their transcripts under the remote_harness
        # blueprint agent — the id the chat websocket send frame uses — not the
        # rail id. Map here so GET hydrate / POST append land on the same thread
        # file the websocket reads and writes (issue #131).
        agent = "remote_harness"
    user_key = _user_key(request.user)
    default_cid = chat_store.conversation_id_for(request.user, agent)
    conversation_id = default_cid
    requested_cid = (request.GET.get("conversation_id") or "").strip()
    if request.method in ("PATCH", "POST"):
        body = _json_body(request)
        if isinstance(body.get("conversation_id"), str) and body["conversation_id"].strip():
            requested_cid = body["conversation_id"].strip()
    fresh_task = is_new_chat_per_task(agent)
    # REQ-171C-4 / C-H7: mint or refuse reuse before loading the old Django row.
    minted = resolve_on_mode_conversation(request.user, agent, requested_cid)
    session_id = ""
    session_missing = False
    if minted is not None:
        conversation_id = minted.conversation_id
        session_id = minted.conversation_id
        requested_for_load = conversation_id
    else:
        if requested_cid and requested_cid != default_cid:
            session_id = requested_cid
        requested_for_load = requested_cid
    # JSON first, Django backfill — same order as WS fetch_conversation.
    loaded = load_thread(
        request.user,
        agent,
        requested_cid=requested_for_load,
        session_id=session_id,
        default_cid=default_cid,
        fresh_task=fresh_task,
    )
    record = loaded.record
    turns, events = loaded.turns, loaded.events
    if (
        minted is None
        and requested_cid
        and record is None
        and not turns
        and requested_cid.startswith(("cli-", "sess-", "task-"))
    ):
        # Select-minted / on-mode ids — honest miss, no swap.
        session_missing = True
        turns, events = [], []
    if minted is None and requested_cid:
        conversation_id = requested_cid
    elif minted is None and record and record.get("conversation_id") and not fresh_task:
        conversation_id = record["conversation_id"]
    # REQ-105: never fall back to another conversation's compact tree.
    if minted is not None:
        summaries = [summary_to_dict(row) for row in list_summaries(conversation_id)]
    elif requested_cid:
        summaries = [summary_to_dict(row) for row in list_summaries(requested_cid)]
    else:
        conversation_id, summaries = _summaries_for(
            (record or {}).get("conversation_id") if record else "",
            conversation_id,
        )
    if not conversation_id:
        conversation_id = requested_cid or (record or {}).get("conversation_id") or default_cid
    sessions = list_active_task_sessions(user_key, agent) if fresh_task else []
    kind = classify_agent_kind(agent_raw or agent)
    session_title = ""
    if not session_missing:
        try:
            from swarm.core.agent_sessions import get_or_create_session

            row = get_or_create_session(request.user, conversation_id, agent_id=agent)
            session_title = row.title or ""
        except Exception:
            session_title = ""
    payload = {
        "agent_id": agent,
        "conversation_id": conversation_id,
        "session_title": session_title,
        "kind": kind,
        "editable": kind == "api",
        "new_chat_per_task": fresh_task,
        "active_sessions": sessions,
        "session_missing": session_missing,
        "messages": _thread_payload_messages(turns, events),
        "turns": _public_messages(turns),
        "ui_events": _public_messages(events),
        "summaries": summaries if not (fresh_task and not requested_cid) else [],
        "context_meta": {},
    }
    try:
        from swarm.core.context_cull_policy import last_context_event_for_popup, load_context_meta

        meta = load_context_meta(conversation_id)
        if not meta.get("last_event"):
            meta["last_event"] = last_context_event_for_popup(conversation_id)
        payload["context_meta"] = meta
    except Exception:
        payload["context_meta"] = {"start_offset": 0, "last_event": None}
    if request.method == "GET":
        return JsonResponse(payload)

    if request.method == "POST":
        body = _json_body(request)
        msg = body.get("message")
        if isinstance(msg, dict) and msg.get("content"):
            from swarm.core.transcript_roles import (
                append_event,
                append_turn,
                is_chrome_message,
                stamp_ui_event,
            )

            current_turns = list(turns)
            current_events = list(events)
            new_row = {
                "role": str(msg.get("role") or "status"),
                "content": str(msg.get("content") or ""),
            }
            ts = msg.get("ts") or msg.get("timestamp") or msg.get("created_at")
            if isinstance(ts, str) and ts.strip():
                new_row["ts"] = ts.strip()
            if is_chrome_message(new_row):
                if not new_row.get("ts"):
                    new_row = stamp_ui_event(new_row)
                append_event(
                    current_turns,
                    current_events,
                    new_row["role"],
                    new_row["content"],
                    ts=new_row.get("ts"),
                    kind=msg.get("kind"),
                )
            else:
                append_turn(
                    current_turns,
                    current_events,
                    new_row["role"],
                    new_row["content"],
                    ts=new_row.get("ts"),
                )
            try:
                chat_store.save(
                    user_key,
                    agent,
                    current_turns,
                    conversation_id=conversation_id,
                    session_id=conversation_id if conversation_id != default_cid else "",
                    ui_events=current_events,
                )
            except OSError:
                logger.exception("Failed to append chat JSON for %s/%s", user_key, agent)
            _sync_django_and_memory(
                request.user,
                current_turns,
                [conversation_id],
                agent_id=agent,
            )
            payload["messages"] = _thread_payload_messages(current_turns, current_events)
            payload["turns"] = _public_messages(current_turns)
            payload["ui_events"] = _public_messages(current_events)
            return JsonResponse(payload)
        return JsonResponse({"error": "message must be provided."}, status=400)

    if not can_edit_agent_messages(agent_raw or agent):
        return JsonResponse(
            {"error": "Edits are only allowed on API-agent threads."},
            status=403,
        )
    body = _json_body(request)
    index = body.get("index")
    content = body.get("content")
    if type(index) is not int:
        return JsonResponse({"error": "index must be an integer."}, status=400)
    if not isinstance(content, str):
        return JsonResponse({"error": "content must be a string."}, status=400)
    current_turns = list(turns)
    if index < 0 or index >= len(current_turns):
        return JsonResponse({"error": "No message at that index."}, status=404)
    updated = dict(current_turns[index])
    updated["content"] = content
    updated["edited"] = True
    current_turns[index] = updated
    try:
        chat_store.save(
            user_key,
            agent,
            current_turns,
            conversation_id=conversation_id,
            session_id=conversation_id if conversation_id != default_cid else "",
            ui_events=events,
        )
    except OSError:
        logger.exception("Failed to persist edited chat JSON for %s/%s", user_key, agent)
        return JsonResponse(
            {"error": "Could not persist the edit. See server logs."},
            status=500,
        )
    # REQ-808: CLI-thread edit → clear cli_sessions + settings mirror + watch
    from swarm.core.cli_sessions import clear_cli_session, put_cli_session
    from swarm.core import chat_store as cs

    # Clear any stored CLI session ids for the edited thread
    user_key_local = _user_key(request.user)
    # Determine which CLIs were involved in the thread (from turns)
    involved_clis: set[str] = set()
    for turn in current_turns:
        role = turn.get("role", "")
        # Check for cli_name in turn metadata or content
        if isinstance(turn.get("content"), dict):
            cli = turn["content"].get("cli_name") or turn["content"].get("name")
            if cli:
                involved_clis.add(cli)
        # Also check top-level cli_name
        cli = turn.get("cli_name")
        if cli:
            involved_clis.add(cli)

    # Clear cli_sessions for each involved CLI
    for cli_name in involved_clis:
        clear_cli_session(
            user_key=user_key_local,
            agent_id=agent,
            cli_name=cli_name,
        )

    # Mirror: also clear any session-level flags that should reset on edit
    # (e.g. session_reset status line, cli_session_reset toast)
    # The frontend will read these from the response payload
    payload["session_reset"] = True
    payload["cli_session_reset"] = True

    _sync_django_and_memory(
        request.user,
        current_turns,
        [conversation_id],
        agent_id=agent,
    )
    payload["messages"] = _thread_payload_messages(current_turns, events)
    payload["turns"] = _public_messages(current_turns)
    payload["ui_events"] = _public_messages(events)
    return JsonResponse(payload)


@require_http_methods(["POST"])
def chat_attachment_upload(request):
    """Store one composer file and return its id (REQ-38).

    Session cookie required (same gate as the chat websocket). Bytes go to
    the local attachment store; sqlite holds metadata. Multipart field
    ``file``; optional ``conversation_id``.
    """
    if not getattr(request.user, "is_authenticated", False):
        return JsonResponse({"error": "authentication required"}, status=401)

    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"error": "file is required"}, status=400)

    size = int(getattr(uploaded, "size", 0) or 0)
    if size <= 0:
        return JsonResponse({"error": "empty file"}, status=400)
    if size > chat_attachments.MAX_ATTACHMENT_BYTES:
        return JsonResponse(
            {
                "error": (
                    f"file too large (max {chat_attachments.MAX_ATTACHMENT_BYTES} bytes)"
                ),
            },
            status=413,
        )

    name = chat_attachments.safe_display_name(getattr(uploaded, "name", "") or "file")
    content_type = (getattr(uploaded, "content_type", None) or "").strip()[:255]
    conversation_id = (request.POST.get("conversation_id") or "").strip()[:255]
    data = uploaded.read()
    if len(data) > chat_attachments.MAX_ATTACHMENT_BYTES:
        return JsonResponse(
            {
                "error": (
                    f"file too large (max {chat_attachments.MAX_ATTACHMENT_BYTES} bytes)"
                ),
            },
            status=413,
        )

    row = ChatAttachment.objects.create(
        owner=request.user,
        conversation_id=conversation_id,
        original_name=name,
        content_type=content_type,
        size=len(data),
    )
    try:
        chat_attachments.write_bytes(request.user, row.id, data)
    except OSError:
        logger.exception("Failed to store chat attachment %s", row.id)
        row.delete()
        return JsonResponse({"error": "could not store file"}, status=500)

    return JsonResponse(
        {
            "id": str(row.id),
            "name": row.original_name,
            "size": row.size,
            "content_type": row.content_type,
        },
        status=201,
    )


@login_required
@require_http_methods(["POST"])
def chat_compact(request):
    """LLM-summarise the current backlog (or a selected span) into a nested summary."""
    payload = _json_body(request)
    agent = chat_store.normalize_agent_id(
        payload.get("agent") or payload.get("agent_id") or request.POST.get("agent_id")
    )
    conversation_id = (
        (payload.get("conversation_id") or request.POST.get("conversation_id") or "")
        .strip()
    )
    if not conversation_id:
        conversation_id = chat_store.conversation_id_for(request.user, agent)
    messages = payload.get("messages")
    span_start = payload.get("span_start", payload.get("start"))
    span_end = payload.get("span_end", payload.get("end"))
    through_message_id = (
        payload.get("through_message_id")
        or payload.get("message_id")
        or payload.get("through")
    )
    try:
        start = int(span_start) if span_start is not None and span_start != "" else None
        end = int(span_end) if span_end is not None and span_end != "" else None
    except (TypeError, ValueError):
        return JsonResponse({"error": "span_start / span_end must be integers."}, status=400)
    try:
        row, raw = compact_backlog(
            user=request.user,
            conversation_id=conversation_id,
            agent_id=agent,
            messages=messages if isinstance(messages, list) else None,
            span_start=start,
            span_end=end,
            through_message_id=through_message_id,
        )
    except CompactError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
    summaries = [summary_to_dict(item) for item in list_summaries(conversation_id)]
    from swarm.core.chat_compact import build_model_context
    from swarm.core.context_cull_policy import EVENT_COMPRESS, record_context_event

    try:
        record_context_event(
            conversation_id,
            EVENT_COMPRESS,
            user=request.user,
            agent_id=agent,
        )
    except Exception:
        logger.debug("compress last-event stamp skipped", exc_info=True)

    return JsonResponse(
        {
            "summary": summary_to_dict(row),
            "summaries": summaries,
            "context": build_model_context(raw, list_summaries(conversation_id)),
            "raw_count": len(raw),
        }
    )


@login_required
@require_http_methods(["POST"])
def chat_summary_toggle_context(request):
    """#214: toggle a summary's include_in_context (default True keeps today's behavior).

    Unticked = the summary (and the raw span it replaced) stops feeding model
    context — a lightweight "new chat". The transcript row is untouched.
    """
    payload = _json_body(request)
    summary_id = payload.get("summary_id")
    try:
        summary_id = int(summary_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "summary_id must be an integer."}, status=400)
    include = payload.get("include_in_context")
    if not isinstance(include, bool):
        return JsonResponse({"error": "include_in_context must be a boolean."}, status=400)
    try:
        row = ConversationSummary.objects.select_related("conversation").get(pk=summary_id)
    except ConversationSummary.DoesNotExist:
        return JsonResponse({"error": "Summary not found."}, status=404)
    owner = row.conversation.student
    if owner is not None and request.user.pk != owner.pk:
        return JsonResponse({"error": "Not your conversation."}, status=403)
    row.include_in_context = include
    row.save(update_fields=["include_in_context"])
    return JsonResponse({"summary": summary_to_dict(row)})


@login_required
@require_http_methods(["POST"])
def chat_context_start(request):
    """REQ-121: start chat context from a chosen message (cull mode)."""
    payload = _json_body(request)
    agent = chat_store.normalize_agent_id(
        payload.get("agent") or payload.get("agent_id") or request.POST.get("agent_id")
    )
    conversation_id = (
        (payload.get("conversation_id") or request.POST.get("conversation_id") or "")
        .strip()
    )
    if not conversation_id:
        conversation_id = chat_store.conversation_id_for(request.user, agent)
    messages = payload.get("messages")
    start_offset = payload.get("start_offset", payload.get("start"))
    through_message_id = (
        payload.get("through_message_id")
        or payload.get("message_id")
        or payload.get("through")
    )
    confirm = payload.get("confirm") in (True, "true", "1", 1)
    model_id = payload.get("model_id") or payload.get("model")
    inference_entry = None
    for key in ("context_length", "context_window", "max_context"):
        raw_max = payload.get(key)
        try:
            value = int(raw_max)
        except (TypeError, ValueError):
            continue
        if value > 0:
            inference_entry = {key: value}
            break
    try:
        start = int(start_offset) if start_offset is not None and start_offset != "" else None
    except (TypeError, ValueError):
        return JsonResponse({"error": "start_offset must be an integer."}, status=400)

    from swarm.core.context_cull_policy import preview_start_from_here

    result = preview_start_from_here(
        user=request.user,
        conversation_id=conversation_id,
        agent_id=agent,
        messages=messages if isinstance(messages, list) else None,
        start_offset=start,
        through_message_id=through_message_id,
        model_id=str(model_id).strip() if isinstance(model_id, str) and model_id.strip() else None,
        inference_entry=inference_entry,
        confirm=confirm,
    )
    body = {
        "applied": result.acted,
        "warning": result.warning,
        "reason": result.reason,
        "info": result.info,
        "start_offset": result.start_offset,
        "estimated_tokens": result.estimated_tokens,
        "estimated_pct": result.estimated_pct,
        "cull_trigger_pct": result.threshold_pct,
        "max_context": result.max_context,
        "context": result.context,
        "last_event": result.last_event,
        "context_meta": {
            "start_offset": result.start_offset,
            "last_event": result.last_event,
        },
    }
    if result.reason == "unknown_message":
        return JsonResponse({"error": result.info or "Unknown message id.", **body}, status=400)
    if result.reason == "missing_start":
        return JsonResponse({"error": result.info or "start_offset required.", **body}, status=400)
    return JsonResponse(body)


@login_required
@require_http_methods(["POST"])
def chat_retention_action(request):
    """Archive / restore / empty-trash for the signed-in user's JSON threads."""
    action = (request.POST.get("action") or "").strip()
    if action not in _ALLOWED_ACTIONS:
        return JsonResponse({"success": False, "error": "Unknown action."}, status=400)

    user_key = _user_key(request.user)
    agent = chat_store.normalize_agent_id(request.POST.get("agent_id"))

    try:
        if action == "archive":
            path = chat_store.archive(user_key, agent)
            if path is None:
                return JsonResponse(
                    {"success": False, "error": "No active chat to archive."},
                    status=404,
                )
            return JsonResponse({"success": True, "archived": agent})
        if action == "archive_all":
            archived = chat_store.archive_all(user_key)
            return JsonResponse({"success": True, "archived": archived})
        if action == "restore":
            path = chat_store.restore(user_key, agent)
            if path is None:
                return JsonResponse(
                    {"success": False, "error": "No trashed chat to restore."},
                    status=404,
                )
            return JsonResponse({"success": True, "restored": agent})
        removed = chat_store.empty_trash(user_key)
        return JsonResponse({"success": True, "removed": removed})
    except OSError:
        logger.exception("Chat retention action %s failed", action)
        return JsonResponse(
            {"success": False, "error": "Could not update chat files. See server logs."},
            status=500,
        )

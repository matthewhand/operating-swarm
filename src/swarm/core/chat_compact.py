"""Nested conversation compact / summaries (REQ-37 / #672).

Raw transcripts stay on disk (JSON) and in ``ChatMessage``. Django/sqlite
stores summary rows. Serving model context walks the summary tree — later
compacts may summarise a mix of raw turns and earlier summaries.

Compact **body** is an LLM-written digest (agent profile or Settings default),
not a concatenated transcript dump. Auto-threshold (#444) should call
:func:`compact_backlog` so it gets the same summariser when wired.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Iterable

from swarm.core.speaker_identity import apply_speaker_identity
from swarm.core.transcript_roles import is_ui_only_item, messages_for_model
from swarm.models import ChatConversation, ChatMessage, ConversationSummary

logger = logging.getLogger(__name__)

COMPACT_SYSTEM = (
    "Write a concise conversation summary for later context. "
    "Preserve names, decisions, and open tasks. "
    "Do not answer the user or continue the task. "
    "Do not invent secrets, tokens, or credentials. "
    "Return only the summary text."
)

_SECRET_IN_TEXT = re.compile(
    r"(?i)(?:sk-[A-Za-z0-9]+|Bearer\s+\S+|api[_-]?key\s*[:=]\s*\S+)"
)


class CompactError(ValueError):
    """User-facing compact failure (empty span, tenancy, …)."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


def normalize_span(raw: Any) -> dict[str, int]:
    """Coerce ``span`` to ``{"start": int, "end": int}`` inclusive offsets."""
    if not isinstance(raw, dict):
        return {"start": 0, "end": 0}
    start = raw.get("start", raw.get("from", 0))
    end = raw.get("end", raw.get("to", start))
    try:
        start_i = int(start)
        end_i = int(end)
    except (TypeError, ValueError):
        return {"start": 0, "end": 0}
    if end_i < start_i:
        start_i, end_i = end_i, start_i
    return {"start": start_i, "end": end_i}


def _span_bounds(summary) -> tuple[int, int]:
    span = normalize_span(getattr(summary, "span", None) or {})
    return span["start"], span["end"]


def _as_summary_rows(summaries: Iterable[Any]) -> list[Any]:
    return [row for row in summaries if row is not None]


def _includes_in_context(row: Any) -> bool:
    """#214: rows without the flag (legacy fakes/rows) default to included."""
    value = getattr(row, "include_in_context", True)
    return value is not False


def excluded_summary_ids(summaries: Iterable[Any]) -> set[int]:
    """#214: ids of excluded summaries **plus their nested descendants**.

    Excluding a parent implicitly excludes the summaries nested inside it:
    an excluded row contributes nothing, and a child's tree would otherwise
    re-render the excluded parent via ``_format_summary_tree``.
    """
    rows = _as_summary_rows(summaries)
    by_id = {
        getattr(row, "id"): row
        for row in rows
        if getattr(row, "id", None) is not None
    }
    excluded: set[int] = set()

    def _row_excluded(row: Any) -> bool:
        seen: set[int] = set()
        current = row
        while current is not None:
            current_id = getattr(current, "id", None)
            if current_id in excluded or _includes_in_context(current) is False:
                return True
            if current_id is None or current_id in seen:
                return False
            seen.add(current_id)
            current = by_id.get(getattr(current, "parent_summary_id", None))
        return False

    for row in rows:
        row_id = getattr(row, "id", None)
        if row_id is not None and _row_excluded(row):
            excluded.add(row_id)
    return excluded


def outermost_summaries(summaries: Iterable[Any]) -> list[Any]:
    """Summaries that are not nested inside a later compact (no child points at them)."""
    rows = _as_summary_rows(summaries)
    nested_ids = {
        getattr(row, "parent_summary_id", None)
        for row in rows
        if getattr(row, "parent_summary_id", None) is not None
    }
    outers = [row for row in rows if getattr(row, "id", None) not in nested_ids]
    outers.sort(key=lambda row: (_span_bounds(row)[0], -_span_bounds(row)[1], getattr(row, "id", 0)))
    return outers


def choose_parent(summaries: Iterable[Any], span_start: int, span_end: int):
    """Latest outermost summary fully inside the new span becomes the nested parent."""
    candidates = []
    for row in outermost_summaries(summaries):
        start, end = _span_bounds(row)
        if start >= span_start and end <= span_end:
            candidates.append(row)
    if not candidates:
        return None
    candidates.sort(key=lambda row: getattr(row, "id", 0))
    return candidates[-1]


def _clip(text: str, limit: int = 240) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def summarize_items(items: list[dict[str, Any]]) -> str:
    """Deterministic extractive dump of a span (prompt material / tests).

    Not the compact bubble. UI-only status/info rows are skipped so chrome
    never re-enters the summary prompt. No secrets, no network.
    """
    lines: list[str] = []
    real: list[dict[str, Any]] = []
    for item in items:
        if item.get("kind") == "summary":
            real.append(item)
            lines.append(f"- [summary] {_clip(str(item.get('body') or ''))}")
            continue
        role = item.get("role") or "user"
        if is_ui_only_item(item):
            continue
        real.append(item)
        content = item.get("content") or item.get("text") or ""
        lines.append(f"- {role}: {_clip(str(content))}")
    count = len(real)
    noun = "item" if count == 1 else "items"
    return f"Summary of {count} {noun}:\n" + "\n".join(lines)


def build_compact_prompt(items: list[dict[str, Any]]) -> str:
    """Transcript the compact LLM sees. Chrome skipped; bodies clipped."""
    lines: list[str] = []
    for item in items:
        if item.get("kind") == "summary":
            lines.append(f"[summary]: {_clip(str(item.get('body') or ''), 800)}")
            continue
        if is_ui_only_item(item):
            continue
        role = item.get("role") or "user"
        content = item.get("content") or item.get("text") or ""
        lines.append(f"{role}: {_clip(str(content), 800)}")
    return (
        "Write a concise conversation summary for later context. "
        "Preserve names, decisions, and open tasks. "
        "Do not answer the user or continue the task.\n"
        "Transcript:\n" + "\n".join(lines)
    )


def _public_llm_error(exc: BaseException) -> str:
    raw = str(exc) or type(exc).__name__
    cleaned = _SECRET_IN_TEXT.sub("[REDACTED]", raw)
    try:
        from swarm.utils.redact import redact_uri_credentials

        cleaned = redact_uri_credentials(cleaned)
    except Exception:
        pass
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > 200:
        cleaned = cleaned[:199].rstrip() + "…"
    return f"Compact summary failed: {cleaned}"


def _blueprint_section_model(agent_id: str, config: dict[str, Any]) -> str | None:
    """Model slug from ``blueprints.<agent>.llm_profile`` — names only, no secrets."""
    agent = (agent_id or "").strip()
    if not agent or agent.startswith("_"):
        return None
    blueprints = config.get("blueprints")
    if not isinstance(blueprints, dict):
        return None
    bp = blueprints.get(agent)
    if not isinstance(bp, dict):
        return None
    profile_name = (
        bp.get("llm_profile") or bp.get("default_model") or bp.get("default_profile")
    )
    if not isinstance(profile_name, str) or not profile_name.strip():
        return None
    from swarm.core.llm_task_routing import model_id_for_profile

    return model_id_for_profile(profile_name.strip(), config) or None


def resolve_compact_model(agent_id: str = "") -> str:
    """Agent LLM profile, else Settings / env default. Raises if none configured."""
    env_model = (
        (os.environ.get("LITELLM_MODEL") or "").strip()
        or (os.environ.get("OPENAI_MODEL") or "").strip()
        or (os.environ.get("DEFAULT_LLM") or "").strip()
    )
    config: dict[str, Any] | None = None
    try:
        from swarm.core.llm_task_routing import load_swarm_config

        config = load_swarm_config()
    except Exception:
        logger.debug("compact model: swarm config unavailable")
        config = None

    if isinstance(config, dict):
        agent_model = _blueprint_section_model(agent_id, config)
        if agent_model:
            return agent_model

    if env_model:
        return env_model

    if isinstance(config, dict):
        try:
            from swarm.core.llm_task_routing import model_id_for_profile, resolve_chat_model

            route = resolve_chat_model(config)
            model = model_id_for_profile(route.profile, config)
            if model:
                return model
        except Exception:
            logger.debug("compact model: settings default unavailable")

    raise CompactError(
        "No default LLM is configured. Set a model in Settings → LLM profiles.",
        status=400,
    )


def llm_summarize_items(items: list[dict[str, Any]], *, agent_id: str = "") -> str:
    """Call the agent / Settings-default LLM. No secrets in logs. Fail closed."""
    model = resolve_compact_model(agent_id)
    prompt = build_compact_prompt(items)
    logger.info("compact LLM summarise model=%s items=%s", model, len(items))
    try:
        from openai import OpenAI

        from swarm.core.model_text import sanitize_model_text
        from swarm.utils.env_utils import openai_client_kwargs

        client = OpenAI(**openai_client_kwargs())
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": COMPACT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=600,
        )
    except CompactError:
        raise
    except Exception as exc:
        logger.warning("compact LLM failed: %s", type(exc).__name__)
        raise CompactError(_public_llm_error(exc), status=502) from exc

    content = ""
    choices = getattr(resp, "choices", None) or []
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) or ""
        if isinstance(choices[0], dict):
            content = ((choices[0].get("message") or {}).get("content")) or content
    text = sanitize_model_text(str(content or "")).strip()
    if not text:
        raise CompactError(
            "Compact summary failed: the model returned an empty summary.",
            status=502,
        )
    return text


def _message_item(message: dict[str, Any], offset: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "kind": "message",
        "role": (message.get("role") or message.get("sender") or "user"),
        "content": message.get("content") or message.get("text") or "",
        "offset": offset,
    }
    name = message.get("name") or message.get("speaker") or message.get("agent")
    if isinstance(name, str) and name.strip():
        item["name"] = name.strip()
    src_kind = message.get("kind")
    if isinstance(src_kind, str) and src_kind.strip():
        item["source_kind"] = src_kind.strip()
    return item


def build_context_items(
    messages: list[dict[str, Any]],
    summaries: Iterable[Any],
) -> list[dict[str, Any]]:
    """Walk the raw transcript, substituting outermost summaries for covered spans.

    #214: summaries with ``include_in_context=False`` are skipped — the
    summary is omitted AND its span's raw turns stay out of context (the
    operator archived this stretch of the conversation; the transcript row
    itself is untouched).
    """
    raw = list(messages or [])
    rows = _as_summary_rows(summaries)
    if not rows:
        return [
            _message_item(m, idx)
            for idx, m in enumerate(raw)
        ]

    cover: list[Any | None] = [None] * len(raw)
    excluded = excluded_summary_ids(rows)
    for row in outermost_summaries(rows):
        # #214: excluded rows still *cover* their span — the summarised raw
        # turns stay archived from context — they just emit nothing.
        start, end = _span_bounds(row)
        start = max(0, start)
        end = min(len(raw) - 1, end) if raw else -1
        for idx in range(start, end + 1):
            if cover[idx] is None:
                cover[idx] = row

    items: list[dict[str, Any]] = []
    emitted: set[int] = set()
    idx = 0
    while idx < len(raw):
        row = cover[idx]
        if row is not None:
            row_id = getattr(row, "id", None)
            if row_id is not None and row_id in excluded:
                # #214: archived from context — emit nothing, skip the span.
                idx = min(len(raw) - 1, _span_bounds(row)[1]) + 1
                continue
            if row_id not in emitted:
                items.append(
                    {
                        "kind": "summary",
                        "id": row_id,
                        "body": getattr(row, "body", "") or "",
                        "parent_summary_id": getattr(row, "parent_summary_id", None),
                        "span": normalize_span(getattr(row, "span", None)),
                    }
                )
                emitted.add(row_id)
            idx = min(len(raw) - 1, _span_bounds(row)[1]) + 1
            continue
        message = raw[idx]
        items.append(_message_item(message, idx))
        idx += 1
    return items


def _format_summary_tree(summary, by_id: dict[int, Any], *, depth: int = 0) -> str:
    body = (getattr(summary, "body", "") or "").strip()
    indent = "  " * depth
    lines = [f"{indent}{body}"] if depth == 0 else [f"{indent}[nested summary]", f"{indent}{body}"]
    parent_id = getattr(summary, "parent_summary_id", None)
    parent = by_id.get(parent_id) if parent_id is not None else None
    if parent is not None:
        lines.append(_format_summary_tree(parent, by_id, depth=depth + 1))
    return "\n".join(lines)


def build_model_context(
    messages: list[dict[str, Any]],
    summaries: Iterable[Any],
) -> list[dict[str, str]]:
    """Context the model sees: summary tree + uncovered raw turns. Raw file is untouched.

    #214: rows with ``include_in_context=False`` contribute nothing — and
    because ``build_context_items`` keeps their spans covered by no row, the
    raw turns they summarised do not silently reappear either.
    """
    rows = _as_summary_rows(summaries)
    excluded = excluded_summary_ids(rows)
    by_id = {
        row_id: row
        for row in rows
        for row_id in (getattr(row, "id", None),)
        if row_id is not None and row_id not in excluded
    }
    out: list[dict[str, str]] = []
    for item in build_context_items(messages, rows):
        if item.get("kind") == "summary":
            row = by_id.get(item.get("id"))
            tree = _format_summary_tree(row, by_id) if row is not None else (item.get("body") or "")
            out.append({"role": "system", "content": f"[Conversation summary]\n{tree}"})
            continue
        if is_ui_only_item(item):
            continue
        role = item.get("role") or "user"
        role_s = str(role)
        if role_s not in ("system", "assistant", "tool", "developer"):
            role_s = "user"
        row: dict[str, str] = {"role": role_s, "content": str(item.get("content") or "")}
        name = item.get("name") or item.get("speaker") or item.get("agent")
        if isinstance(name, str) and name.strip():
            row["name"] = name.strip()
        out.append(row)
    return apply_speaker_identity(out, adapter_id="openai_compat")


def context_for_conversation(
    conversation_id: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Load sqlite summaries for ``conversation_id`` and build model context."""
    if not conversation_id:
        return apply_speaker_identity(messages_for_model(messages), adapter_id="openai_compat")
    try:
        rows = list(
            ConversationSummary.objects.filter(conversation_id=conversation_id).order_by("id")
        )
    except Exception:
        return apply_speaker_identity(messages_for_model(messages), adapter_id="openai_compat")
    return build_model_context(messages, rows)


def list_summaries(conversation_id: str) -> list[ConversationSummary]:
    if not conversation_id:
        return []
    return list(
        ConversationSummary.objects.filter(conversation_id=conversation_id).order_by("id")
    )


def summary_to_dict(row: ConversationSummary) -> dict[str, Any]:
    span = normalize_span(row.span)
    replaced = span["end"] - span["start"] + 1
    created = row.created_at.isoformat() if getattr(row, "created_at", None) else ""
    return {
        "id": row.id,
        "conversation_id": row.conversation_id,
        "span": span,
        "parent_summary_id": row.parent_summary_id,
        "body": row.body,
        "created_at": created,
        "replaced_count": max(0, replaced),
        "include_in_context": bool(getattr(row, "include_in_context", True)),
    }


def _normalize_client_messages(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role") or item.get("sender") or "user"
        content = item.get("content")
        if content is None:
            content = item.get("text") or ""
        if not isinstance(content, str):
            content = str(content)
        role_raw = str(role)
        if role_raw == "assistant":
            role_s = "assistant"
        elif role_raw in ("status", "info", "system", "tool"):
            role_s = role_raw
        else:
            role_s = "user"
        row = {"role": role_s, "content": content}
        ts = item.get("ts") or item.get("timestamp") or item.get("created_at")
        if isinstance(ts, str) and ts:
            row["ts"] = ts
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            row["name"] = name.strip()
        out.append(row)
    return out


def ensure_transcript(
    user,
    conversation_id: str,
    agent_id: str,
    client_messages: list[dict[str, Any]] | None = None,
) -> tuple[ChatConversation, list[dict[str, str]]]:
    """Resolve the raw transcript without deleting originals.

    JSON on disk is the restore source of truth. Django ``ChatMessage`` rows
    are a mirror: we only create missing rows, never delete.
    """
    from swarm.core import chat_store

    if not conversation_id:
        raise CompactError("conversation_id is required.")
    if not getattr(user, "is_authenticated", False):
        raise CompactError("Sign in required.", status=403)

    from swarm.core.transcript_roles import is_ui_only_role, split_store

    user_key = chat_store.user_key_for(user)
    record = chat_store.load(user_key, agent_id)
    stored: list[dict[str, str]] = []
    if record:
        stored, _stored_events = split_store(
            _normalize_client_messages(record.get("messages") or []),
            record.get("ui_events") or [],
            stamp_seq=False,
        )
        del _stored_events

    chat, _created = ChatConversation.objects.get_or_create(
        conversation_id=conversation_id,
        defaults={"student": user},
    )
    if chat.student_id is None:
        chat.student = user
        chat.save(update_fields=["student"])
    if chat.student_id is not None and chat.student_id != getattr(user, "pk", None):
        raise CompactError("Conversation owned by another user.", status=403)

    db_rows = list(chat.chat_messages.all())
    if not stored and db_rows:
        stored, _db_events = split_store(
            [{"role": row.sender, "content": row.content} for row in db_rows],
            [],
            stamp_seq=False,
        )
        del _db_events

    client, _client_events = split_store(
        _normalize_client_messages(client_messages),
        [],
        stamp_seq=False,
    )
    del _client_events
    raw = stored if stored else client
    if client and len(client) > len(raw):
        raw = client
    raw = [item for item in raw if not is_ui_only_role(item.get("role"))]
    if not raw:
        raise CompactError("Nothing to compact.")

    # Rewrite JSON with the full raw turn list — chrome stays in ui_events.
    chat_store.save(user_key, agent_id, raw, conversation_id=conversation_id)

    if db_rows:
        if len(raw) > len(db_rows):
            extras = raw[len(db_rows) :]
            ChatMessage.objects.bulk_create(
                [
                    ChatMessage(conversation=chat, sender=item["role"], content=item["content"])
                    for item in extras
                    if not is_ui_only_role(item.get("role"))
                ]
            )
    else:
        ChatMessage.objects.bulk_create(
            [
                ChatMessage(conversation=chat, sender=item["role"], content=item["content"])
                for item in raw
                if not is_ui_only_role(item.get("role"))
            ]
        )
    return chat, raw


def resolve_through_offset(
    raw: list[dict[str, Any]],
    conversation: ChatConversation | None,
    through_message_id: Any,
) -> int:
    """Map a ChatMessage pk, client id/key, or raw offset to an inclusive end."""
    if through_message_id is None or through_message_id == "":
        raise CompactError("through_message_id is required.")
    pk: int | None
    try:
        pk = int(through_message_id)
    except (TypeError, ValueError):
        pk = None
    if pk is not None and conversation is not None:
        rows = list(conversation.chat_messages.all())
        for idx, row in enumerate(rows):
            if row.pk == pk:
                return idx
    needle = str(through_message_id).strip()
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        mid = item.get("id") or item.get("key") or item.get("message_id")
        if mid is not None and str(mid) == needle:
            return idx
    if pk is not None and 0 <= pk < len(raw):
        return pk
    raise CompactError("Unknown message id.")


def compact_backlog(
    *,
    user,
    conversation_id: str,
    agent_id: str,
    messages: list[dict[str, Any]] | None = None,
    span_start: int | None = None,
    span_end: int | None = None,
    through_message_id: Any = None,
    summarizer: Callable[..., str] | None = None,
) -> tuple[ConversationSummary, list[dict[str, str]]]:
    """Create a summary row covering ``span`` of the raw transcript.

    Does not delete JSON or ``ChatMessage`` rows. Nested compact sets
    ``parent_summary_id`` to the previous outermost summary inside the span.

    The compact body is an LLM summary (``summarizer`` or
    :func:`llm_summarize_items`). LLM failure raises :class:`CompactError`
    and does not write a summary row.
    """
    chat, raw = ensure_transcript(user, conversation_id, agent_id, messages)
    if through_message_id is not None and through_message_id != "":
        span_end = resolve_through_offset(raw, chat, through_message_id)
        if span_start is None:
            span_start = 0
    start = 0 if span_start is None else int(span_start)
    end = len(raw) - 1 if span_end is None else int(span_end)
    start = max(0, start)
    end = min(len(raw) - 1, end)
    if start > end:
        raise CompactError("Invalid span.")

    existing = list(chat.summaries.order_by("id"))
    mix: list[dict[str, Any]] = []
    for item in build_context_items(raw, existing):
        if item.get("kind") == "summary":
            span = normalize_span(item.get("span"))
            if span["end"] < start or span["start"] > end:
                continue
            mix.append(item)
            continue
        if is_ui_only_item(item):
            continue
        offset = item.get("offset")
        if isinstance(offset, int) and start <= offset <= end:
            mix.append(item)
    if not mix:
        raise CompactError("Nothing to compact in that span.")

    summarize = summarizer or llm_summarize_items
    try:
        body = summarize(mix, agent_id=agent_id)
    except CompactError:
        raise
    except TypeError:
        # Test doubles that only accept items.
        try:
            body = summarize(mix)
        except CompactError:
            raise
        except Exception as exc:
            raise CompactError(_public_llm_error(exc), status=502) from exc
    except Exception as exc:
        raise CompactError(_public_llm_error(exc), status=502) from exc
    body = (body or "").strip()
    if not body:
        raise CompactError(
            "Compact summary failed: the model returned an empty summary.",
            status=502,
        )
    parent = choose_parent(existing, start, end)
    row = ConversationSummary.objects.create(
        conversation=chat,
        span={"start": start, "end": end},
        parent_summary=parent,
        body=body,
    )
    return row, raw

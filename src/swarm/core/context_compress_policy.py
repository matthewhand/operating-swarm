"""REQ-87 — shared context-compress policy (SPA / CLI / HTTP API).

One persisted threshold (default 80%, range 1–99) decides when a send
auto-compacts older turns. Manual + / hover-to-here still call the REQ-37
compact operator. Unknown model max → skip auto (do not guess 128k) with
an honest info line. No secrets, no Neon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from swarm.core.chat_compact import (
    CompactError,
    build_model_context,
    compact_backlog,
    list_summaries,
    summarize_items,
)
from swarm.core.transcript_roles import is_ui_only_item, messages_for_model

DEFAULT_AUTO_COMPRESS_PCT = 80
MIN_AUTO_COMPRESS_PCT = 1
MAX_AUTO_COMPRESS_PCT = 99
AUTO_COMPRESS_PCT_KEY = "context_auto_compress_pct"
CONTEXT_COMPRESS_API_ONLY = "context_compress_api_only"

# Leave the latest user draft plus a recent assistant turn uncompressed.
AUTO_COMPRESS_KEEP_RECENT = 2

UNKNOWN_MAX_INFO = "Auto-compress skipped — model context length unknown."

CONTEXT_LENGTH_KEYS = (
    "context_length",
    "context_window",
    "max_context",
    "max_context_tokens",
)


@dataclass
class AutoCompactResult:
    """Outcome of the shared auto-compress helper (CLI/API/SPA send path)."""

    acted: bool
    reason: str
    info: str | None = None
    threshold_pct: int = DEFAULT_AUTO_COMPRESS_PCT
    estimated_tokens: int = 0
    max_context: int | None = None
    context: list[dict[str, Any]] = field(default_factory=list)
    summary: Any = None


def normalize_auto_compress_pct(raw: Any) -> int:
    """Clamp to 1–99. Missing / invalid → default 80."""
    if raw is None or raw == "":
        return DEFAULT_AUTO_COMPRESS_PCT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_AUTO_COMPRESS_PCT
    if value < MIN_AUTO_COMPRESS_PCT:
        return MIN_AUTO_COMPRESS_PCT
    if value > MAX_AUTO_COMPRESS_PCT:
        return MAX_AUTO_COMPRESS_PCT
    return value


def load_auto_compress_threshold(
    user=None,
    *,
    principal: str | None = None,
    values: dict[str, Any] | None = None,
) -> int | None:
    """Read the shared threshold from UserPreference (or an explicit bag).

    Returns None when API-only mode is enabled (compression skipped for CLI agents).
    """
    if values is not None:
        if values.get(CONTEXT_COMPRESS_API_ONLY):
            return None
        return normalize_auto_compress_pct(values.get(AUTO_COMPRESS_PCT_KEY))

    from swarm.models.preferences import UserPreference

    row = None
    if user is not None and getattr(user, "is_authenticated", False):
        row = UserPreference.objects.filter(user=user).first()
        if row is None:
            name = user.get_username() if hasattr(user, "get_username") else ""
            if name:
                row = UserPreference.objects.filter(principal=f"user:{name}").first()
    if row is None and principal:
        row = UserPreference.objects.filter(principal=principal).first()
    bag = row.values if row is not None and isinstance(row.values, dict) else {}
    if bag.get(CONTEXT_COMPRESS_API_ONLY):
        return None
    return normalize_auto_compress_pct(bag.get(AUTO_COMPRESS_PCT_KEY))


def _positive_int(raw: Any) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def context_length_from_mapping(raw: Any) -> int | None:
    """Read a context window from a profile / inference mapping. No 128k guess."""
    if not isinstance(raw, dict):
        return None
    for key in CONTEXT_LENGTH_KEYS:
        found = _positive_int(raw.get(key))
        if found is not None:
            return found
    return None


def resolve_model_context_max(
    *,
    profile: dict[str, Any] | None = None,
    inference_entry: dict[str, Any] | None = None,
    model_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> int | None:
    """Return a known context length, or None. Never invent 128k."""
    found = context_length_from_mapping(inference_entry)
    if found is not None:
        return found
    found = context_length_from_mapping(profile)
    if found is not None:
        return found
    ident = (model_id or "").strip()
    if not ident:
        return None
    try:
        from swarm.core import llm_task_routing as routing

        loaded = routing.get_profile_dict(ident, config)
    except Exception:
        loaded = None
    return context_length_from_mapping(loaded)


def estimate_context_tokens(
    messages: list[dict[str, Any]] | None,
    *,
    model: str = "cl100k_base",
) -> int:
    """Estimate tokens in the served model context (not the raw transcript)."""
    rows = list(messages or [])
    if not rows:
        return 0
    try:
        from swarm.utils.context_utils import get_token_count

        return sum(get_token_count(row, model) for row in rows)
    except Exception:
        chars = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            chars += len(str(row.get("content") or row.get("text") or ""))
        return max(0, round(chars / 4))


def should_auto_compress(
    estimated: int,
    max_ctx: int | None,
    threshold_pct: int,
) -> bool:
    """True when estimated tokens are at or above N% of a *known* max."""
    if max_ctx is None or max_ctx <= 0:
        return False
    pct = normalize_auto_compress_pct(threshold_pct)
    return estimated >= (max_ctx * pct) / 100.0


def choose_auto_compact_span(
    raw_count: int,
    *,
    keep_recent: int = AUTO_COMPRESS_KEEP_RECENT,
) -> tuple[int, int] | None:
    """Inclusive span covering older turns; leave ``keep_recent`` + draft tail."""
    keep = max(1, int(keep_recent))
    if raw_count <= keep:
        return None
    end = raw_count - keep - 1
    if end < 0:
        return None
    return (0, end)


def compact_messages_in_memory(
    messages: list[dict[str, Any]],
    span_start: int,
    span_end: int,
) -> list[dict[str, Any]]:
    """Replace a span with one summary system row (stateless API send)."""
    raw = list(messages or [])
    start = max(0, int(span_start))
    end = min(len(raw) - 1, int(span_end)) if raw else -1
    if start > end or not raw:
        return raw
    mix = []
    for item in raw[start : end + 1]:
        if not isinstance(item, dict) or is_ui_only_item(item):
            continue
        mix.append(item)
    if not mix:
        return raw
    body = summarize_items(mix)
    summary_row = {"role": "system", "content": f"[Conversation summary]\n{body}"}
    return raw[:start] + [summary_row] + raw[end + 1 :]


def _model_ready_messages(
    messages: list[dict[str, Any]],
    summaries: list[Any] | None = None,
) -> list[dict[str, Any]]:
    if summaries:
        return build_model_context(messages, summaries)
    return messages_for_model(messages)


def auto_compact_before_send(
    *,
    user=None,
    conversation_id: str = "",
    agent_id: str = "",
    messages: list[dict[str, Any]] | None = None,
    model_id: str | None = None,
    profile: dict[str, Any] | None = None,
    inference_entry: dict[str, Any] | None = None,
    threshold_pct: int | None = None,
    persist: bool = True,
) -> AutoCompactResult:
    """Shared send-path hook. CLI / ``/v1/`` / websocket all call this.

    When max context is unknown, auto is skipped with ``UNKNOWN_MAX_INFO``.
    Manual compact is unchanged. Raw transcript stays on disk when persisted.
    """
    pct = (
        normalize_auto_compress_pct(threshold_pct)
        if threshold_pct is not None
        else load_auto_compress_threshold(user)
    )
    if pct is None:
        return AutoCompactResult(
            acted=False,
            reason="api_only",
            info="Context compression skipped — API-only mode enabled",
            threshold_pct=DEFAULT_AUTO_COMPRESS_PCT,
            estimated_tokens=0,
            max_context=None,
            context=list(messages or []) if messages else [],
        )
    max_ctx = resolve_model_context_max(
        profile=profile,
        inference_entry=inference_entry,
        model_id=model_id,
    )
    raw = list(messages or [])
    summaries = list_summaries(conversation_id) if conversation_id else []
    served = _model_ready_messages(raw, summaries)
    estimated = estimate_context_tokens(served, model=str(model_id or "cl100k_base"))

    if max_ctx is None:
        span = choose_auto_compact_span(len(raw))
        return AutoCompactResult(
            acted=False,
            reason="unknown_max",
            info=UNKNOWN_MAX_INFO if span is not None else None,
            threshold_pct=pct,
            estimated_tokens=estimated,
            max_context=None,
            context=served,
        )

    if not should_auto_compress(estimated, max_ctx, pct):
        return AutoCompactResult(
            acted=False,
            reason="below_threshold",
            threshold_pct=pct,
            estimated_tokens=estimated,
            max_context=max_ctx,
            context=served,
        )

    span = choose_auto_compact_span(len(raw))
    if span is None:
        return AutoCompactResult(
            acted=False,
            reason="nothing_to_compact",
            threshold_pct=pct,
            estimated_tokens=estimated,
            max_context=max_ctx,
            context=served,
        )

    start, end = span
    can_persist = (
        persist
        and conversation_id
        and user is not None
        and getattr(user, "is_authenticated", False)
    )
    if can_persist:
        try:
            row, persisted_raw = compact_backlog(
                user=user,
                conversation_id=conversation_id,
                agent_id=agent_id,
                messages=raw,
                span_start=start,
                span_end=end,
            )
        except CompactError:
            return AutoCompactResult(
                acted=False,
                reason="nothing_to_compact",
                threshold_pct=pct,
                estimated_tokens=estimated,
                max_context=max_ctx,
                context=served,
            )
        context = build_model_context(persisted_raw, list_summaries(conversation_id))
        return AutoCompactResult(
            acted=True,
            reason="compacted",
            threshold_pct=pct,
            estimated_tokens=estimate_context_tokens(
                context, model=str(model_id or "cl100k_base")
            ),
            max_context=max_ctx,
            context=context,
            summary=row,
        )

    rewritten = compact_messages_in_memory(raw, start, end)
    context = messages_for_model(rewritten)
    return AutoCompactResult(
        acted=True,
        reason="compacted_in_memory",
        threshold_pct=pct,
        estimated_tokens=estimate_context_tokens(
            context, model=str(model_id or "cl100k_base")
        ),
        max_context=max_ctx,
        context=context,
    )

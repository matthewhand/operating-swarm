"""REQ-121 — cache-friendly cull / start-context-from-here (API agents).

Distinct from REQ-87 compress (#444) and the LLM-summariser bug (#672).
Cull drops the oldest slice so the recent suffix stays byte-stable for
input token caching. Manual hover is “start the chat context from here”
(earlier turns excluded from subsequent prompts). CLI is out of v1.

Settings live in ``UserPreference`` (local DB). Per-conversation start
offset lives on ``ChatConversation.context_meta``. No secrets, no Neon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from swarm.core.chat_compact import (
    CompactError,
    ensure_transcript,
    list_summaries,
    resolve_through_offset,
)
from swarm.core.context_compress_policy import (
    AUTO_COMPRESS_PCT_KEY,
    CONTEXT_COMPRESS_API_ONLY,
    DEFAULT_AUTO_COMPRESS_PCT,
    AutoCompactResult,
    auto_compact_before_send,
    estimate_context_tokens,
    load_auto_compress_threshold,
    normalize_auto_compress_pct,
    resolve_model_context_max,
    should_auto_compress,
)
from swarm.core.transcript_roles import messages_for_model

STRATEGY_COMPRESS = "compress"
STRATEGY_CULL = "cull"
DEFAULT_CONTEXT_STRATEGY = STRATEGY_COMPRESS
CONTEXT_STRATEGY_KEY = "context_strategy"

DEFAULT_CULL_TRIGGER_PCT = 90
DEFAULT_CULL_FRACTION_PCT = 50
MIN_PCT = 1
MAX_PCT = 99
CULL_TRIGGER_PCT_KEY = "context_cull_trigger_pct"
CULL_FRACTION_PCT_KEY = "context_cull_fraction_pct"

UNKNOWN_MAX_CULL_INFO = "Auto-cull skipped — model context length unknown."
AUTO_CULL_INFO = (
    "Context culled — oldest {fraction}% dropped; recent turns kept."
)

EVENT_CULL = "cull"
EVENT_START_FROM_HERE = "start_from_here"
EVENT_COMPRESS = "compress"


@dataclass
class ContextPolicy:
    strategy: str = DEFAULT_CONTEXT_STRATEGY
    compress_pct: int = DEFAULT_AUTO_COMPRESS_PCT
    cull_trigger_pct: int = DEFAULT_CULL_TRIGGER_PCT
    cull_fraction_pct: int = DEFAULT_CULL_FRACTION_PCT


@dataclass
class ContextPrepResult:
    """Unified send-path outcome for compress (#444) or cull (#504)."""

    acted: bool
    reason: str
    strategy: str = DEFAULT_CONTEXT_STRATEGY
    info: str | None = None
    threshold_pct: int = DEFAULT_AUTO_COMPRESS_PCT
    estimated_tokens: int = 0
    max_context: int | None = None
    context: list[dict[str, Any]] = field(default_factory=list)
    start_offset: int = 0
    last_event: dict[str, Any] | None = None
    summary: Any = None
    warning: bool = False
    cull_fraction_pct: int = DEFAULT_CULL_FRACTION_PCT
    estimated_pct: float | None = None


def normalize_context_strategy(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if text in (STRATEGY_CULL, "cull-head", "trim", "drop"):
        return STRATEGY_CULL
    return STRATEGY_COMPRESS


def normalize_pct(raw: Any, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value < MIN_PCT:
        return MIN_PCT
    if value > MAX_PCT:
        return MAX_PCT
    return value


def normalize_cull_trigger_pct(raw: Any) -> int:
    return normalize_pct(raw, DEFAULT_CULL_TRIGGER_PCT)


def normalize_cull_fraction_pct(raw: Any) -> int:
    return normalize_pct(raw, DEFAULT_CULL_FRACTION_PCT)


def policy_from_values(values: dict[str, Any] | None) -> ContextPolicy:
    bag = values if isinstance(values, dict) else {}
    return ContextPolicy(
        strategy=normalize_context_strategy(bag.get(CONTEXT_STRATEGY_KEY)),
        compress_pct=normalize_auto_compress_pct(bag.get(AUTO_COMPRESS_PCT_KEY)),
        cull_trigger_pct=normalize_cull_trigger_pct(bag.get(CULL_TRIGGER_PCT_KEY)),
        cull_fraction_pct=normalize_cull_fraction_pct(bag.get(CULL_FRACTION_PCT_KEY)),
    )


def load_context_policy(
    user=None,
    *,
    principal: str | None = None,
    values: dict[str, Any] | None = None,
) -> ContextPolicy:
    """Read compress/cull knobs from UserPreference (or an explicit bag)."""
    if values is not None:
        return policy_from_values(values)

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
    policy = policy_from_values(bag)
    if bag.get(CONTEXT_COMPRESS_API_ONLY):
        policy.strategy = "api_only"
    if AUTO_COMPRESS_PCT_KEY not in bag:
        policy.compress_pct = load_auto_compress_threshold(user, principal=principal)
    return policy


def should_auto_cull(
    estimated: int,
    max_ctx: int | None,
    trigger_pct: int,
) -> bool:
    """True when estimated tokens are at or above cull-trigger % of a known max."""
    return should_auto_compress(estimated, max_ctx, normalize_cull_trigger_pct(trigger_pct))


def usage_pct(estimated: int, max_ctx: int | None) -> float | None:
    if max_ctx is None or max_ctx <= 0:
        return None
    return (max(0, int(estimated)) * 100.0) / float(max_ctx)


def would_warn_after_start(
    estimated: int,
    max_ctx: int | None,
    trigger_pct: int,
) -> bool:
    """Warning when remaining usage is still ≥ cull-trigger % (known max only)."""
    return should_auto_cull(estimated, max_ctx, trigger_pct)


def choose_cull_start(
    raw_count: int,
    *,
    current_start: int = 0,
    fraction_pct: int = DEFAULT_CULL_FRACTION_PCT,
) -> int | None:
    """Advance start so the oldest ``fraction_pct`` of the current window is dropped.

    Recent suffix offsets stay unchanged (cache-friendly). Always keep ≥ 1 turn.
    """
    start = max(0, int(current_start or 0))
    window = int(raw_count) - start
    if window <= 1:
        return None
    fraction = normalize_cull_fraction_pct(fraction_pct)
    drop = max(1, (window * fraction) // 100)
    drop = min(drop, window - 1)
    return start + drop


def apply_context_start(
    messages: list[dict[str, Any]] | None,
    start_offset: int,
) -> list[dict[str, Any]]:
    """Keep this message and later; earlier turns leave the prompt."""
    raw = list(messages or [])
    start = max(0, int(start_offset or 0))
    if start <= 0:
        return raw
    return raw[start:]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_context_event(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "").strip()
    if kind not in (EVENT_CULL, EVENT_START_FROM_HERE, EVENT_COMPRESS):
        return None
    event: dict[str, Any] = {"kind": kind}
    at = raw.get("at")
    if isinstance(at, str) and at.strip():
        event["at"] = at.strip()[:40]
    for key in ("start_offset", "culled_count", "fraction_pct"):
        value = raw.get(key)
        try:
            event[key] = int(value)
        except (TypeError, ValueError):
            continue
    pct = raw.get("estimated_pct")
    try:
        event["estimated_pct"] = round(float(pct), 1)
    except (TypeError, ValueError):
        pass
    return event


def public_context_meta(raw: Any) -> dict[str, Any]:
    bag = raw if isinstance(raw, dict) else {}
    start = 0
    try:
        start = max(0, int(bag.get("start_offset") or 0))
    except (TypeError, ValueError):
        start = 0
    return {
        "start_offset": start,
        "last_event": sanitize_context_event(bag.get("last_event")),
    }


def load_context_meta(conversation_id: str) -> dict[str, Any]:
    if not conversation_id:
        return public_context_meta({})
    try:
        from swarm.models import ChatConversation

        row = ChatConversation.objects.filter(conversation_id=conversation_id).first()
    except Exception:
        return public_context_meta({})
    bag = getattr(row, "context_meta", None) if row is not None else None
    return public_context_meta(bag)


def _ensure_conversation(conversation_id: str, user=None, agent_id: str = ""):
    from swarm.models import ChatConversation

    if not conversation_id:
        return None
    defaults: dict[str, Any] = {"agent_id": agent_id or ""}
    if user is not None and getattr(user, "is_authenticated", False):
        defaults["student"] = user
    row, _created = ChatConversation.objects.get_or_create(
        conversation_id=conversation_id,
        defaults=defaults,
    )
    if user is not None and getattr(user, "pk", None) and row.student_id is None:
        row.student = user
        row.save(update_fields=["student"])
    return row


def record_context_event(
    conversation_id: str,
    kind: str,
    *,
    user=None,
    agent_id: str = "",
    start_offset: int | None = None,
    culled_count: int | None = None,
    fraction_pct: int | None = None,
    estimated_pct: float | None = None,
) -> dict[str, Any]:
    """Persist last cull / start-from-here / compress marker. No prompt text."""
    row = _ensure_conversation(conversation_id, user=user, agent_id=agent_id)
    event: dict[str, Any] = {"kind": kind, "at": _iso_now()}
    if start_offset is not None:
        event["start_offset"] = int(start_offset)
    if culled_count is not None:
        event["culled_count"] = int(culled_count)
    if fraction_pct is not None:
        event["fraction_pct"] = int(fraction_pct)
    if estimated_pct is not None:
        event["estimated_pct"] = round(float(estimated_pct), 1)
    clean = sanitize_context_event(event) or event
    if row is None:
        return public_context_meta({"last_event": clean, "start_offset": start_offset or 0})
    meta = public_context_meta(getattr(row, "context_meta", None) or {})
    if start_offset is not None:
        meta["start_offset"] = max(0, int(start_offset))
    meta["last_event"] = clean
    row.context_meta = meta
    row.save(update_fields=["context_meta", "updated_at"])
    return public_context_meta(row.context_meta)


def set_context_start_offset(
    conversation_id: str,
    start_offset: int,
    *,
    user=None,
    agent_id: str = "",
    kind: str = EVENT_START_FROM_HERE,
    culled_count: int | None = None,
    fraction_pct: int | None = None,
    estimated_pct: float | None = None,
) -> dict[str, Any]:
    return record_context_event(
        conversation_id,
        kind,
        user=user,
        agent_id=agent_id,
        start_offset=start_offset,
        culled_count=culled_count,
        fraction_pct=fraction_pct,
        estimated_pct=estimated_pct,
    )


def _model_suffix(messages: list[dict[str, Any]], start_offset: int) -> list[dict[str, Any]]:
    """Cull-mode prompt: raw suffix only (no summary rewrite — cache-friendly)."""
    return messages_for_model(apply_context_start(messages, start_offset))


def _from_compress(result: AutoCompactResult) -> ContextPrepResult:
    return ContextPrepResult(
        acted=result.acted,
        reason=result.reason,
        strategy=STRATEGY_COMPRESS,
        info=result.info,
        threshold_pct=result.threshold_pct,
        estimated_tokens=result.estimated_tokens,
        max_context=result.max_context,
        context=list(result.context or []),
        summary=result.summary,
    )


def auto_cull_before_send(
    *,
    user=None,
    conversation_id: str = "",
    agent_id: str = "",
    messages: list[dict[str, Any]] | None = None,
    model_id: str | None = None,
    profile: dict[str, Any] | None = None,
    inference_entry: dict[str, Any] | None = None,
    trigger_pct: int | None = None,
    fraction_pct: int | None = None,
    persist: bool = True,
) -> ContextPrepResult:
    """Drop the oldest slice when usage hits the cull trigger. Recent suffix stays."""
    policy = load_context_policy(user)
    if policy.strategy == "api_only":
        return ContextPrepResult(
            acted=False,
            reason="api_only",
            strategy=STRATEGY_CULL,
            info="Context culling skipped — API-only mode enabled",
            threshold_pct=policy.cull_trigger_pct,
            estimated_tokens=0,
            max_context=None,
            context=list(messages) if messages else [],
            start_offset=0,
        )
    trigger = (
        normalize_cull_trigger_pct(trigger_pct)
        if trigger_pct is not None
        else policy.cull_trigger_pct
    )
    fraction = (
        normalize_cull_fraction_pct(fraction_pct)
        if fraction_pct is not None
        else policy.cull_fraction_pct
    )
    max_ctx = resolve_model_context_max(
        profile=profile,
        inference_entry=inference_entry,
        model_id=model_id,
    )
    raw = list(messages or [])
    meta = load_context_meta(conversation_id)
    start = int(meta.get("start_offset") or 0)
    start = min(start, max(0, len(raw) - 1)) if raw else 0
    served = _model_suffix(raw, start)
    estimated = estimate_context_tokens(served, model=str(model_id or "cl100k_base"))
    pct = usage_pct(estimated, max_ctx)

    if max_ctx is None:
        next_start = choose_cull_start(len(raw), current_start=start, fraction_pct=fraction)
        return ContextPrepResult(
            acted=False,
            reason="unknown_max",
            strategy=STRATEGY_CULL,
            info=UNKNOWN_MAX_CULL_INFO if next_start is not None else None,
            threshold_pct=trigger,
            estimated_tokens=estimated,
            max_context=None,
            context=served,
            start_offset=start,
            last_event=meta.get("last_event"),
            cull_fraction_pct=fraction,
            estimated_pct=pct,
        )

    if not should_auto_cull(estimated, max_ctx, trigger):
        return ContextPrepResult(
            acted=False,
            reason="below_threshold",
            strategy=STRATEGY_CULL,
            threshold_pct=trigger,
            estimated_tokens=estimated,
            max_context=max_ctx,
            context=served,
            start_offset=start,
            last_event=meta.get("last_event"),
            cull_fraction_pct=fraction,
            estimated_pct=pct,
        )

    next_start = choose_cull_start(len(raw), current_start=start, fraction_pct=fraction)
    if next_start is None:
        return ContextPrepResult(
            acted=False,
            reason="nothing_to_cull",
            strategy=STRATEGY_CULL,
            threshold_pct=trigger,
            estimated_tokens=estimated,
            max_context=max_ctx,
            context=served,
            start_offset=start,
            last_event=meta.get("last_event"),
            cull_fraction_pct=fraction,
            estimated_pct=pct,
        )

    culled = next_start - start
    context = _model_suffix(raw, next_start)
    after_est = estimate_context_tokens(context, model=str(model_id or "cl100k_base"))
    after_pct = usage_pct(after_est, max_ctx)
    stored = meta
    if persist and conversation_id:
        stored = set_context_start_offset(
            conversation_id,
            next_start,
            user=user,
            agent_id=agent_id,
            kind=EVENT_CULL,
            culled_count=culled,
            fraction_pct=fraction,
            estimated_pct=after_pct,
        )
    return ContextPrepResult(
        acted=True,
        reason="culled",
        strategy=STRATEGY_CULL,
        info=AUTO_CULL_INFO.format(fraction=fraction),
        threshold_pct=trigger,
        estimated_tokens=after_est,
        max_context=max_ctx,
        context=context,
        start_offset=next_start,
        last_event=stored.get("last_event"),
        cull_fraction_pct=fraction,
        estimated_pct=after_pct,
    )


def preview_start_from_here(
    *,
    user=None,
    conversation_id: str = "",
    agent_id: str = "",
    messages: list[dict[str, Any]] | None = None,
    start_offset: int | None = None,
    through_message_id: Any = None,
    model_id: str | None = None,
    profile: dict[str, Any] | None = None,
    inference_entry: dict[str, Any] | None = None,
    confirm: bool = False,
    persist: bool = True,
) -> ContextPrepResult:
    """Set context start at a message. Warn if remaining usage still ≥ cull trigger."""
    policy = load_context_policy(user)
    raw: list[dict[str, Any]] = list(messages or [])
    chat = None
    if conversation_id and user is not None and getattr(user, "is_authenticated", False):
        try:
            chat, persisted = ensure_transcript(user, conversation_id, agent_id, raw or None)
            raw = list(persisted or raw)
        except CompactError:
            chat = None
    if through_message_id is not None and through_message_id != "":
        try:
            start = resolve_through_offset(raw, chat, through_message_id)
        except CompactError as exc:
            return ContextPrepResult(
                acted=False,
                reason="unknown_message",
                strategy=STRATEGY_CULL,
                info=str(exc),
                threshold_pct=policy.cull_trigger_pct,
                context=[],
            )
    elif start_offset is not None:
        start = max(0, int(start_offset))
    else:
        return ContextPrepResult(
            acted=False,
            reason="missing_start",
            strategy=STRATEGY_CULL,
            info="start_offset or through_message_id is required.",
            threshold_pct=policy.cull_trigger_pct,
            context=[],
        )
    if raw:
        start = min(start, len(raw) - 1)
    context = _model_suffix(raw, start)
    max_ctx = resolve_model_context_max(
        profile=profile,
        inference_entry=inference_entry,
        model_id=model_id,
    )
    estimated = estimate_context_tokens(context, model=str(model_id or "cl100k_base"))
    pct = usage_pct(estimated, max_ctx)
    warn = would_warn_after_start(estimated, max_ctx, policy.cull_trigger_pct)
    if warn and not confirm:
        return ContextPrepResult(
            acted=False,
            reason="over_full_warning",
            strategy=STRATEGY_CULL,
            info=(
                "Starting context here still leaves usage at "
                f"{pct:.0f}% (cull trigger {policy.cull_trigger_pct}%). "
                "Confirm to proceed or cancel."
            ),
            threshold_pct=policy.cull_trigger_pct,
            estimated_tokens=estimated,
            max_context=max_ctx,
            context=context,
            start_offset=start,
            warning=True,
            cull_fraction_pct=policy.cull_fraction_pct,
            estimated_pct=pct,
        )

    stored = load_context_meta(conversation_id)
    if persist and conversation_id:
        stored = set_context_start_offset(
            conversation_id,
            start,
            user=user,
            agent_id=agent_id,
            kind=EVENT_START_FROM_HERE,
            estimated_pct=pct,
        )
    return ContextPrepResult(
        acted=True,
        reason="start_from_here",
        strategy=STRATEGY_CULL,
        threshold_pct=policy.cull_trigger_pct,
        estimated_tokens=estimated,
        max_context=max_ctx,
        context=context,
        start_offset=start,
        last_event=stored.get("last_event"),
        warning=False,
        cull_fraction_pct=policy.cull_fraction_pct,
        estimated_pct=pct,
    )


def prepare_context_before_send(
    *,
    user=None,
    conversation_id: str = "",
    agent_id: str = "",
    messages: list[dict[str, Any]] | None = None,
    model_id: str | None = None,
    profile: dict[str, Any] | None = None,
    inference_entry: dict[str, Any] | None = None,
    persist: bool = True,
) -> ContextPrepResult:
    """SPA / websocket / ``/v1/`` hook. Compress vs cull from Settings."""
    policy = load_context_policy(user)
    if policy.strategy == STRATEGY_CULL:
        return auto_cull_before_send(
            user=user,
            conversation_id=conversation_id,
            agent_id=agent_id,
            messages=messages,
            model_id=model_id,
            profile=profile,
            inference_entry=inference_entry,
            trigger_pct=policy.cull_trigger_pct,
            fraction_pct=policy.cull_fraction_pct,
            persist=persist,
        )
    result = auto_compact_before_send(
        user=user,
        conversation_id=conversation_id,
        agent_id=agent_id,
        messages=messages,
        model_id=model_id,
        profile=profile,
        inference_entry=inference_entry,
        threshold_pct=policy.compress_pct,
        persist=persist,
    )
    wrapped = _from_compress(result)
    if result.acted and conversation_id:
        summaries = list_summaries(conversation_id)
        latest = summaries[-1] if summaries else None
        created = ""
        if latest is not None and getattr(latest, "created_at", None):
            created = latest.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        stored = record_context_event(
            conversation_id,
            EVENT_COMPRESS,
            user=user,
            agent_id=agent_id,
            estimated_pct=usage_pct(result.estimated_tokens, result.max_context),
        )
        if created and isinstance(stored.get("last_event"), dict):
            stored["last_event"]["at"] = created
        wrapped.last_event = stored.get("last_event")
    else:
        wrapped.last_event = load_context_meta(conversation_id).get("last_event")
    return wrapped


def last_context_event_for_popup(
    conversation_id: str,
    summaries: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Prefer persisted last event; fall back to latest compact timestamp."""
    meta = load_context_meta(conversation_id)
    event = meta.get("last_event")
    if isinstance(event, dict):
        return event
    rows = list(summaries or [])
    if not rows:
        rows = list_summaries(conversation_id) if conversation_id else []
    if not rows:
        return None
    latest = rows[-1]
    created = getattr(latest, "created_at", None)
    at = created.strftime("%Y-%m-%dT%H:%M:%SZ") if created is not None else ""
    return sanitize_context_event({"kind": EVENT_COMPRESS, "at": at})

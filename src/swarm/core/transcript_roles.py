"""Transcript roles that are UI chrome vs model context (REQ-70 / #789).

Status/info/hop chrome is UI metadata stored outside the model-turn list.
The UI reconstructs those lines; the model sees real turns only.

``messages_for_model`` / ``is_ui_only_role`` remain a safety belt when mixed
rows still exist temporarily. They are not the Success architecture.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

# Bubble-less chrome. ``system`` is kept: compact summaries and real prompts
# use it. Frontend maps leftover ``system`` rows to status *display* only.
# ``prior_history`` is the REQ-104 archive pill — same family as status/info.
UI_ONLY_ROLES = frozenset({"status", "info"})
UI_ONLY_KINDS = frozenset({"prior_history"})
MODEL_ROLES = frozenset({"system", "user", "assistant", "tool", "developer"})


def _role_of(item: dict[str, Any]) -> str:
    return str(item.get("role") or item.get("sender") or "user").strip().lower()


def is_ui_only_role(role: Any) -> bool:
    return str(role or "").strip().lower() in UI_ONLY_ROLES


def is_ui_only_item(item: Any) -> bool:
    """True for status/info rows and the prior-history archive pill."""
    if not isinstance(item, dict):
        return False
    if is_ui_only_role(_role_of(item)):
        return True
    for key in ("kind", "source_kind"):
        val = item.get(key)
        if isinstance(val, str) and val.strip().lower() in UI_ONLY_KINDS:
            return True
    return False


def message_timestamp(item: dict[str, Any] | None) -> str:
    """ISO timestamp already on the row, or empty."""
    if not isinstance(item, dict):
        return ""
    ts = item.get("ts") or item.get("timestamp") or item.get("created_at")
    return ts.strip() if isinstance(ts, str) and ts.strip() else ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp_ui_event(item: dict[str, Any]) -> dict[str, Any]:
    """Ensure a UI-only row has ``ts`` so reload can show when it occurred."""
    row = dict(item)
    if not message_timestamp(row):
        row["ts"] = utc_now_iso()
    return row


def _reaction_only_model_content(raw: dict[str, Any]) -> str:
    """Palette emoji for a reaction-only turn.

    The stored ``content`` stays empty so the bubble does not also render
    text. The model still needs a turn here: dropping it leaves two user
    messages adjacent on the next send.
    """
    from swarm.core.message_reactions import normalize_emoji

    reactions = raw.get("reactions")
    if not isinstance(reactions, list):
        return ""
    for row in reactions:
        if not isinstance(row, dict):
            continue
        emoji = normalize_emoji(row.get("emoji"))
        if emoji:
            return emoji
    return ""


def messages_for_model(messages: Iterable[Any] | None) -> list[dict[str, Any]]:
    """Transcript → LLM payload: drop status/info and prior_history archive.

    Keeps real turns + tool rows. Preserves ``name`` / ``tool_call_id`` /
    ``tool_calls`` so speaker identity and tool pairing survive. Does not
    invent content or wrap speakers. A reaction-only turn contributes its
    palette emoji, which is the reply the operator already saw.
    """
    out: list[dict[str, Any]] = []
    for raw in messages or []:
        if not isinstance(raw, dict):
            continue
        role = _role_of(raw)
        if is_ui_only_item(raw):
            continue
        if raw.get("reaction_only") is True:
            text = raw.get("content")
            if not isinstance(text, str) or not text.strip():
                emoji = _reaction_only_model_content(raw)
                if emoji and role in MODEL_ROLES:
                    out.append({"role": role, "content": emoji})
                continue
        if role not in MODEL_ROLES:
            # Unknown chrome (e.g. leftover ``suggestions``) stays out of context.
            continue
        content = raw.get("content")
        if content is None:
            content = raw.get("text") or ""
        row: dict[str, Any] = {"role": role, "content": content}
        name = raw.get("name") or raw.get("speaker") or raw.get("agent")
        if isinstance(name, str) and name.strip():
            row["name"] = name.strip()
        if raw.get("tool_call_id"):
            row["tool_call_id"] = raw["tool_call_id"]
        if raw.get("tool_calls"):
            row["tool_calls"] = raw["tool_calls"]
        out.append(row)
    return out


def context_blob(messages: Iterable[dict[str, Any]] | None) -> str:
    """Concatenated payload text for leak assertions."""
    parts: list[str] = []
    for item in messages or []:
        parts.append(str(item.get("role") or ""))
        parts.append(str(item.get("content") or ""))
        parts.append(str(item.get("name") or ""))
    return "\n".join(parts)


CHROME_KINDS = frozenset(
    {"status", "info", "hop", "pr_opened", "teammate_task", "prior_history", "rate_limit"}
)

# #1694: the shape of the ``carried_summary`` payload on a ``context_carried``
# event, and the one normalizer both of its whitelists share. A session hop
# records what it carried on the boundary marker so the chat's own history can
# answer "what was my next message built on?" — on the next turn, after a
# handoff, and after a reload. The payload is chrome: it lives on the
# ``ui_events`` side channel and never becomes a model turn, so it is not
# re-sent to the model and is not re-carried by the next hop.
#
# Shared on purpose. ``chat_store._normalize_messages`` (the derived cache)
# and ``thread_load.public_message`` (the HTTP/WS projection) are BOTH
# fixed-key rebuilds, and #1722 was precisely a key missing from one of them:
# the write looked fine and the value was gone by the time anything read it.
# One normalizer, called from both, makes "a key that is not in both" a
# TypeError at the call site rather than a silent drop.
CARRIED_SUMMARY_TEXT_MAX = 200_000
CARRIED_SUMMARY_LABELS = ("from_cli", "to_cli", "mode")
CARRIED_SUMMARY_COUNTS = ("tokens", "turn_count")


def carried_summary_from_row(raw: Any) -> dict[str, Any] | None:
    """Project one carried summary off a stored row, or ``None``.

    Rebuilds the fixed key set, so a stored row cannot smuggle extra fields
    into the chat payload. ``text`` is the redacted injection blob (the caller
    redacts again — see the call sites), and ``None`` for an empty or
    non-dict payload is deliberate: a summary the session was not actually
    seeded with must not be recorded, let alone rendered.
    """
    if not isinstance(raw, dict):
        return None
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    def _label(key: str) -> str:
        value = raw.get(key)
        return value.strip()[:128] if isinstance(value, str) else ""

    def _count(key: str) -> int:
        value = raw.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return max(0, value)

    omitted = raw.get("omitted")
    return {
        "text": text[:CARRIED_SUMMARY_TEXT_MAX],
        **{key: _label(key) for key in CARRIED_SUMMARY_LABELS},
        **{key: _count(key) for key in CARRIED_SUMMARY_COUNTS},
        "omitted": [str(item)[:64] for item in omitted][:8] if isinstance(omitted, list) else [],
    }
HOP_PREFIXES = ("Messaged ", "Message from ")

# Belt alias: same filter, named for the reconstructed (turns-only) path.
turns_for_model = messages_for_model


def _int_seq(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def next_seq(turns: Iterable[Any] | None, events: Iterable[Any] | None) -> int:
    """Next monotonic seq across turns + UI events."""
    vals: list[int] = []
    for item in list(turns or []) + list(events or []):
        if not isinstance(item, dict):
            continue
        seq = _int_seq(item.get("seq"))
        if seq is not None:
            vals.append(seq)
    return (max(vals) + 1) if vals else 0


def event_kind(item: dict[str, Any]) -> str:
    kind = item.get("kind")
    if isinstance(kind, str) and kind.strip():
        return kind.strip()[:64]
    role = _role_of(item)
    content = str(item.get("content") or item.get("text") or "")
    if content.startswith(HOP_PREFIXES):
        return "hop"
    if role in UI_ONLY_ROLES:
        return role
    return "status"


def is_chrome_message(item: Any) -> bool:
    """True when a row is UI chrome, not a model turn."""
    if not isinstance(item, dict):
        return False
    kind = item.get("kind")
    if isinstance(kind, str) and kind.strip().lower() in CHROME_KINDS:
        return True
    if is_ui_only_role(_role_of(item)):
        return True
    content = str(item.get("content") or item.get("text") or "")
    return content.startswith(HOP_PREFIXES)


def _as_turn(item: dict[str, Any]) -> dict[str, Any]:
    row = dict(item)
    row.pop("kind", None)
    return row


def _as_event(item: dict[str, Any]) -> dict[str, Any]:
    row = stamp_ui_event(dict(item))
    kind = event_kind(row)
    row["kind"] = kind
    if kind == "prior_history":
        # Archive pill stays system+kind so the UI reconstructs the REQ-104 card.
        if _role_of(row) != "system":
            row["role"] = "system"
        return row
    role = _role_of(row)
    if role not in UI_ONLY_ROLES:
        row["role"] = "status"
    return row


def split_store(
    messages: Iterable[Any] | None,
    ui_events: Iterable[Any] | None = None,
    *,
    stamp_seq: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split a mixed (or turns-only) list into model turns + UI events.

    Schema-1 threads that still mix ``role=status|info`` into ``messages``
    are migrated here. Existing ``ui_events`` are kept unless ``messages``
    already contains the same chrome (reconstructed payload).
    """
    turns: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    seq = 0
    mixed = list(messages or [])
    has_chrome = any(is_chrome_message(item) for item in mixed)

    def _stamp(row: dict[str, Any]) -> dict[str, Any]:
        nonlocal seq
        out = dict(row)
        existing = _int_seq(out.get("seq"))
        if stamp_seq and existing is None:
            out["seq"] = seq
            seq += 1
        elif existing is not None:
            seq = max(seq, existing + 1)
        return out

    for raw in mixed:
        if not isinstance(raw, dict):
            continue
        row = _stamp(raw)
        if is_chrome_message(row):
            events.append(_as_event(row))
        else:
            turns.append(_as_turn(row))

    if ui_events and not has_chrome:
        for raw in ui_events:
            if not isinstance(raw, dict):
                continue
            events.append(_as_event(_stamp(raw)))
    elif ui_events and not mixed:
        for raw in ui_events:
            if not isinstance(raw, dict):
                continue
            events.append(_as_event(_stamp(raw)))
    return turns, events


def reconstruct_display(
    turns: Iterable[Any] | None,
    events: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    """Interleave model turns and UI events by ``seq`` for chrome display."""
    items: list[tuple[int, int, dict[str, Any]]] = []
    for idx, raw in enumerate(turns or []):
        if not isinstance(raw, dict):
            continue
        seq = _int_seq(raw.get("seq"))
        items.append((seq if seq is not None else idx, 0, dict(raw)))
    for idx, raw in enumerate(events or []):
        if not isinstance(raw, dict):
            continue
        seq = _int_seq(raw.get("seq"))
        row = dict(raw)
        if not row.get("role"):
            row["role"] = "status"
        items.append((seq if seq is not None else idx, 1, row))
    items.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in items]


def append_turn(
    turns: list[dict[str, Any]],
    events: list[dict[str, Any]],
    role: str,
    content: str,
    **extra: Any,
) -> dict[str, Any]:
    """Append a real user/assistant/tool turn with the next ``seq``."""
    row: dict[str, Any] = {"role": role, "content": content, "seq": next_seq(turns, events)}
    for key, value in extra.items():
        if value is not None:
            row[key] = value
    turns.append(row)
    return row


def append_event(
    turns: list[dict[str, Any]],
    events: list[dict[str, Any]],
    role: str,
    content: str,
    **extra: Any,
) -> dict[str, Any]:
    """Append UI chrome to the side channel (never the model-turn list)."""
    kind = extra.get("kind")
    if isinstance(kind, str) and kind.strip().lower() == "prior_history":
        stored_role = "system"
    elif is_ui_only_role(role):
        stored_role = role
    else:
        stored_role = "status"
    row: dict[str, Any] = {
        "role": stored_role,
        "content": content,
        "seq": next_seq(turns, events),
    }
    for key, value in extra.items():
        if value is not None:
            row[key] = value
    stamped = _as_event(row)
    events.append(stamped)
    return stamped


def stamp_event(item: dict[str, Any]) -> dict[str, Any]:
    """Alias for ``stamp_ui_event`` (reconstruction naming)."""
    return stamp_ui_event(item)


def build_model_context_from_store(
    turns: Iterable[Any] | None,
    events: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    """Model payload from the reconstructed store: turns only.

    ``events`` is accepted so callers can pass the split pair; chrome is
    never read. The belt still runs in case a turn list is mixed.
    """
    del events
    return messages_for_model(turns)

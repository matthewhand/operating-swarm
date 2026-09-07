"""REQ-88 / #445 — provider-level rate limits (shared queue, no vendor defaults).

User-defined rules live on the provider row in local ``swarm_config.json``
(not Neon, not per-agent). Empty / omitted = unlimited. Several agents that
send through the same provider share one in-process queue. Different
providers never block each other.

Countdown / delay copy is UI chrome (``role=info``, ``kind=rate_limit``) and
must stay out of the model prompt (REQ-70 / #407).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

logger = logging.getLogger("swarm.provider_rate_limit")

RULE_KEYS: tuple[str, ...] = (
    "messages_per_minute",
    "requests_per_minute",
    "tokens_per_minute",
    "tokens_per_day",
)

RULE_LABELS: dict[str, str] = {
    "messages_per_minute": "messages per minute",
    "requests_per_minute": "requests per minute",
    "tokens_per_minute": "tokens per minute",
    "tokens_per_day": "tokens per day",
}

KIND_SECTION: dict[str, str] = {
    "cli": "cli_agents",
    "llm": "llm",
    "remote": "remotes",
}

KIND_SETTINGS_PANE: dict[str, str] = {
    "cli": "cli-agents",
    "llm": "llm-profiles",
    "remote": "remotes",
}

ENTRY_FIELD = "rate_limits"

WaitCallback = Callable[["WaitDecision"], Awaitable[None] | None]


@dataclass(frozen=True)
class RateLimitRules:
    """User-defined caps. ``None`` on a field means no limit."""

    messages_per_minute: int | None = None
    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None
    tokens_per_day: int | None = None

    def is_unlimited(self) -> bool:
        return all(getattr(self, key) is None for key in RULE_KEYS)

    def public_dict(self) -> dict[str, int | None]:
        return {key: getattr(self, key) for key in RULE_KEYS}

    def stored_dict(self) -> dict[str, int]:
        return {key: value for key in RULE_KEYS if (value := getattr(self, key)) is not None}


@dataclass(frozen=True)
class WaitDecision:
    provider_key: str
    rule: str
    remaining_seconds: float
    limit: int
    wait_until: float

    def remaining_int(self) -> int:
        return max(0, int(math.ceil(self.remaining_seconds)))

    def public_dict(self) -> dict[str, Any]:
        """Serialize wait decision for API and frontend consumers.

        Note: Internal rate limiting math uses time.monotonic() to avoid clock
        jump skew. The frontend expects wait_until_ms in Unix epoch milliseconds
        relative to Date.now(), so we explicitly anchor remaining time to time.time().
        """
        remaining = self.remaining_int()
        return {
            "reason": self.rule,
            "remaining_seconds": remaining,
            "provider": self.provider_key,
            "text": format_wait_text(self),
            "settings": settings_target(self.provider_key),
            "wait_until_ms": int((time.time() + remaining) * 1000),
        }


@dataclass
class _UsageEvent:
    ts: float
    messages: int = 0
    requests: int = 0
    tokens: int = 0


@dataclass
class ProviderRateLimiter:
    """Process-wide shared queue, one ledger per provider key."""

    minute_window: float = 60.0
    day_window: float = 86400.0
    now: Callable[[], float] = field(default=time.monotonic)
    sleep: Callable[[float], Awaitable[None]] = field(default=asyncio.sleep)
    _events: dict[str, list[_UsageEvent]] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _meta: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def _lock_for(self, key: str) -> asyncio.Lock:
        async with self._meta:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    def _prune(self, key: str, now: float) -> list[_UsageEvent]:
        keep_for = max(self.minute_window, self.day_window)
        events = [row for row in self._events.get(key, []) if now - row.ts < keep_for]
        self._events[key] = events
        return events

    def inspect(
        self,
        provider_key: str,
        rules: RateLimitRules | None,
        *,
        messages: int = 1,
        requests: int = 1,
        tokens: int = 0,
    ) -> WaitDecision | None:
        """Return the longest wait required, or ``None`` when the send may go."""
        key = normalize_provider_key(provider_key)
        if not key:
            return None
        parsed = rules if isinstance(rules, RateLimitRules) else parse_rules(rules)
        if parsed.is_unlimited():
            return None
        now = float(self.now())
        events = self._prune(key, now)
        waits: list[WaitDecision] = []

        def _consider(rule: str, incoming: int, limit: int | None, window: float) -> None:
            if limit is None or incoming <= 0:
                return
            wait_s = _window_wait(events, rule_amount_attr(rule), incoming, limit, window, now)
            if wait_s > 0:
                waits.append(
                    WaitDecision(
                        provider_key=key,
                        rule=rule,
                        remaining_seconds=wait_s,
                        limit=limit,
                        wait_until=now + wait_s,
                    )
                )

        _consider("messages_per_minute", messages, parsed.messages_per_minute, self.minute_window)
        _consider("requests_per_minute", requests, parsed.requests_per_minute, self.minute_window)
        _consider("tokens_per_minute", tokens, parsed.tokens_per_minute, self.minute_window)
        _consider("tokens_per_day", tokens, parsed.tokens_per_day, self.day_window)
        if not waits:
            return None
        return max(waits, key=lambda row: row.remaining_seconds)

    def record(
        self,
        provider_key: str,
        *,
        messages: int = 1,
        requests: int = 1,
        tokens: int = 0,
    ) -> None:
        key = normalize_provider_key(provider_key)
        if not key:
            return
        now = float(self.now())
        self._prune(key, now)
        self._events.setdefault(key, []).append(
            _UsageEvent(ts=now, messages=messages, requests=requests, tokens=max(0, tokens))
        )

    async def acquire(
        self,
        provider_key: str,
        rules: RateLimitRules | None,
        *,
        messages: int = 1,
        requests: int = 1,
        tokens: int = 0,
        on_wait: WaitCallback | None = None,
    ) -> WaitDecision | None:
        """Wait until the send is allowed, then record usage. Returns last wait."""
        key = normalize_provider_key(provider_key)
        parsed = rules if isinstance(rules, RateLimitRules) else parse_rules(rules)
        if not key or parsed.is_unlimited():
            return None
        lock = await self._lock_for(key)
        last: WaitDecision | None = None
        async with lock:
            while True:
                decision = self.inspect(
                    key,
                    parsed,
                    messages=messages,
                    requests=requests,
                    tokens=tokens,
                )
                if decision is None:
                    self.record(key, messages=messages, requests=requests, tokens=tokens)
                    return last
                last = decision
                if on_wait is not None:
                    maybe = on_wait(decision)
                    if asyncio.iscoroutine(maybe):
                        await maybe
                await self.sleep(min(1.0, max(0.0, decision.remaining_seconds)))
        return last


_LIMITER: ProviderRateLimiter | None = None


def get_limiter() -> ProviderRateLimiter:
    global _LIMITER
    if _LIMITER is None:
        _LIMITER = ProviderRateLimiter()
    return _LIMITER


def reset_limiter(limiter: ProviderRateLimiter | None = None) -> ProviderRateLimiter:
    """Test hook: replace the process-wide singleton."""
    global _LIMITER
    _LIMITER = limiter if limiter is not None else ProviderRateLimiter()
    return _LIMITER


def rule_amount_attr(rule: str) -> str:
    if rule.startswith("messages_"):
        return "messages"
    if rule.startswith("requests_"):
        return "requests"
    return "tokens"


def _window_wait(
    events: Iterable[_UsageEvent],
    attr: str,
    incoming: int,
    limit: int,
    window: float,
    now: float,
) -> float:
    relevant = [(row.ts, int(getattr(row, attr, 0) or 0)) for row in events if now - row.ts < window]
    total = sum(amount for _, amount in relevant)
    if total + incoming <= limit:
        return 0.0
    need = total + incoming - limit
    dropped = 0
    for ts, amount in relevant:
        dropped += amount
        if dropped >= need:
            return max(0.0, (ts + window) - now)
    return window


def parse_limit_value(raw: Any) -> int | None:
    """Empty / missing / non-positive = no limit. No baked vendor defaults."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            raw = float(text) if "." in text else int(text)
        except ValueError:
            return None
    if isinstance(raw, float):
        if not math.isfinite(raw):
            return None
        raw = int(raw)
    if isinstance(raw, int):
        return raw if raw > 0 else None
    return None


def parse_rules(raw: Any) -> RateLimitRules:
    if isinstance(raw, RateLimitRules):
        return raw
    blob = raw if isinstance(raw, dict) else {}
    return RateLimitRules(
        **{key: parse_limit_value(blob.get(key)) for key in RULE_KEYS}
    )


def normalize_provider_key(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    for kind in ("cli", "llm", "remote"):
        prefix = f"{kind}:"
        if lowered.startswith(prefix):
            ident = text[len(prefix) :].strip()
            return f"{kind}:{ident}" if ident else ""
    return text


def parse_provider_key(raw: Any) -> tuple[str, str]:
    key = normalize_provider_key(raw)
    if ":" not in key:
        return "", key
    kind, ident = key.split(":", 1)
    return kind, ident


def provider_display_name(provider_key: str) -> str:
    _kind, ident = parse_provider_key(provider_key)
    return ident or provider_key or "provider"


def settings_target(provider_key: str) -> dict[str, str]:
    kind, ident = parse_provider_key(provider_key)
    pane = KIND_SETTINGS_PANE.get(kind, "llm-profiles")
    return {
        "section": pane,
        "provider_id": normalize_provider_key(provider_key) or ident,
        "focus": "rate-limits",
        "field_id": fieldset_id(provider_key),
    }


def fieldset_id(provider_key: str) -> str:
    key = normalize_provider_key(provider_key) or str(provider_key or "provider")
    return "rate-limits-" + key.replace(":", "-")


def format_wait_text(decision: WaitDecision, *, remaining: int | None = None) -> str:
    name = provider_display_name(decision.provider_key)
    rule = RULE_LABELS.get(decision.rule, decision.rule.replace("_", " "))
    secs = decision.remaining_int() if remaining is None else max(0, int(remaining))
    return f"Waiting for {name} — {rule} — {secs}s"


def format_cli_wait(decision: WaitDecision) -> str:
    payload = decision.public_dict()
    return (
        f"{payload['text']} remaining "
        f"(reason={payload['reason']}, remaining_seconds={payload['remaining_seconds']})"
    )


def estimate_tokens(messages: Iterable[Any] | None) -> int:
    """Rough prompt-size estimate when a token rule is set. Never invents a quota."""
    total = 0
    for raw in messages or []:
        if isinstance(raw, dict):
            text = raw.get("content")
            if text is None:
                text = raw.get("text") or ""
        else:
            text = raw
        if not isinstance(text, str):
            text = str(text or "")
        total += max(1, len(text) // 4) if text else 0
    return total


def infer_provider_key(
    name: str,
    config: dict[str, Any] | None = None,
) -> str:
    """Map a bare id to ``cli:`` / ``llm:`` / ``remote:`` using local config."""
    text = str(name or "").strip()
    if not text or text == "default":
        return ""
    keyed = normalize_provider_key(text)
    if ":" in keyed and keyed.split(":", 1)[0] in KIND_SECTION:
        return keyed
    cfg = config if isinstance(config, dict) else load_config()
    remotes = cfg.get("remotes") if isinstance(cfg.get("remotes"), dict) else {}
    clis = cfg.get("cli_agents") if isinstance(cfg.get("cli_agents"), dict) else {}
    llms = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    if text in remotes:
        return f"remote:{text}"
    if text in clis:
        return f"cli:{text}"
    if text in llms:
        return f"llm:{text}"
    return f"llm:{text}"


def resolve_provider_key(
    *,
    params: dict[str, Any] | None = None,
    blueprint_id: str = "",
    model: str = "",
    config: dict[str, Any] | None = None,
) -> str:
    """Seat that will actually send — inference list, then CLI / remote / LLM."""
    from swarm.core.inference_list import normalize_inference_list, seat_id, seat_kind

    blob = params if isinstance(params, dict) else {}
    seats = normalize_inference_list(blob.get("inference_list"))
    if seats:
        first = seats[0]
        return f"{seat_kind(first)}:{seat_id(first)}"
    cli = blob.get("cli")
    if isinstance(cli, str) and cli.strip():
        return f"cli:{cli.strip()}"
    remote = blob.get("remote_id") or blob.get("remote")
    if isinstance(remote, str) and remote.strip():
        return f"remote:{remote.strip()}"
    profile = blob.get("llm_profile") or blob.get("model")
    if isinstance(profile, str) and profile.strip() and profile.strip() != "default":
        return infer_provider_key(profile.strip(), config)
    if blueprint_id:
        try:
            from swarm.core.cli_catalog import cli_from_rail_id

            cli_name = cli_from_rail_id(blueprint_id)
        except Exception:
            cli_name = None
        if cli_name:
            return f"cli:{cli_name}"
    if model and model.strip() and model.strip() != "default":
        return infer_provider_key(model.strip(), config)
    return ""


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    from swarm.core.remotes import load_raw_config

    cfg, _path = load_raw_config(config_path)
    return cfg if isinstance(cfg, dict) else {}


def rules_from_entry(entry: Any) -> RateLimitRules:
    if not isinstance(entry, dict):
        return RateLimitRules()
    return parse_rules(entry.get(ENTRY_FIELD))


def load_rules(
    provider_key: str,
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> RateLimitRules:
    key = normalize_provider_key(provider_key)
    kind, ident = parse_provider_key(key)
    if not kind or not ident:
        return RateLimitRules()
    cfg = config if isinstance(config, dict) else load_config(config_path)
    section = KIND_SECTION.get(kind)
    if not section:
        return RateLimitRules()
    bucket = cfg.get(section)
    if not isinstance(bucket, dict):
        return RateLimitRules()
    return rules_from_entry(bucket.get(ident))


def persist_provider_rate_limits(
    provider_key: str,
    rules: RateLimitRules | dict[str, Any] | None,
    *,
    config_path: str | Path | None = None,
) -> tuple[RateLimitRules, Path]:
    """Merge ``rate_limits`` onto the provider entry in local swarm_config.json."""
    from swarm.core import config_ownership as ownership
    from swarm.core.remotes import load_raw_config

    key = normalize_provider_key(provider_key)
    kind, ident = parse_provider_key(key)
    if kind not in KIND_SECTION or not ident:
        raise ownership.ConfigOwnershipError(
            "provider must be cli:<name>, llm:<id>, or remote:<id>.",
            status=400,
            code="bad_provider",
        )
    parsed = parse_rules(rules)
    section = KIND_SECTION[kind]
    ownership.refuse_out_of_partition(section)
    cfg, path = load_raw_config(config_path)
    bucket = cfg.get(section)
    if not isinstance(bucket, dict):
        bucket = {}
    bucket = dict(bucket)
    entry = bucket.get(ident)
    entry = dict(entry) if isinstance(entry, dict) else {}
    stored = parsed.stored_dict()
    if stored:
        entry[ENTRY_FIELD] = stored
    else:
        entry.pop(ENTRY_FIELD, None)
    bucket[ident] = entry
    ownership.refuse_plaintext_secrets(bucket)
    cfg[section] = bucket
    if "llm" not in cfg or not isinstance(cfg.get("llm"), dict):
        cfg.setdefault("llm", {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    ownership.refresh_app_config(cfg)
    logger.info("Persisted %s.%s.rate_limits to %s", section, ident, path)
    return parsed, path


def list_provider_rate_limits(
    config: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Public catalog of provider rows + their user-defined rules. No secrets."""
    cfg = config if isinstance(config, dict) else load_config(config_path)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(kind: str, ident: str, entry: Any) -> None:
        ident = str(ident or "").strip()
        if not ident:
            return
        key = f"{kind}:{ident}"
        if key in seen:
            return
        seen.add(key)
        rules = rules_from_entry(entry)
        rows.append(
            {
                "id": key,
                "kind": kind,
                "name": ident,
                "object": "provider_rate_limits",
                "rules": rules.public_dict(),
                "settings": settings_target(key),
            }
        )

    for kind, section in KIND_SECTION.items():
        bucket = cfg.get(section)
        if not isinstance(bucket, dict):
            continue
        for ident, entry in bucket.items():
            _add(kind, str(ident), entry)
    return rows


def public_rules_for_entry(entry: Any) -> dict[str, int | None]:
    return rules_from_entry(entry).public_dict()


async def gate_provider_send(
    *,
    params: dict[str, Any] | None = None,
    blueprint_id: str = "",
    model: str = "",
    messages: Iterable[Any] | None = None,
    config: dict[str, Any] | None = None,
    on_wait: WaitCallback | None = None,
    limiter: ProviderRateLimiter | None = None,
) -> WaitDecision | None:
    """Shared SPA / CLI / API choke point. No-op when the provider has no rules."""
    cfg = config if isinstance(config, dict) else load_config()
    key = resolve_provider_key(
        params=params,
        blueprint_id=blueprint_id,
        model=model,
        config=cfg,
    )
    if not key:
        return None
    rules = load_rules(key, cfg)
    if rules.is_unlimited():
        return None
    tokens = 0
    if rules.tokens_per_minute or rules.tokens_per_day:
        tokens = estimate_tokens(messages)
    engine = limiter or get_limiter()
    emitted = {"done": False}

    async def _emit(decision: WaitDecision) -> None:
        if not emitted["done"]:
            sys.stderr.write(format_cli_wait(decision) + "\n")
            emitted["done"] = True
        if on_wait is not None:
            maybe = on_wait(decision)
            if asyncio.iscoroutine(maybe):
                await maybe

    return await engine.acquire(
        key,
        rules,
        messages=1,
        requests=1,
        tokens=tokens,
        on_wait=_emit,
    )

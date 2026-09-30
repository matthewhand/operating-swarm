"""#800 — in-process request telemetry for 429 burst forensics.

A per-client sliding-window ring of recent requests (method, path, status,
caller provenance) plus the log lines an operator needs to answer "why do we
keep getting rate limited?" *without* grepping interleaved uvicorn access
lines. Purely observational: it never throttles or blocks — DRF's throttles
keep deciding. The 429 exception handler reads the window back and this module
owns everything that reaches the journal about it:

* ``[REQUEST]`` — one single-line structured record per HTTP request
  (method, normalised path, status, client, user, duration, bytes), emitted
  from :meth:`RequestTelemetry.record`, which the request middleware already
  calls on every request. A request never spans more than one line, so the
  journal stays greppable and per-client volume is countable.
* ``[RATE_LIMIT_WINDOW]`` — one line per (client, endpoint) bucket per window
  when that bucket's window closes, carrying the **rejection count** and the
  **minimum inter-arrival time** between rejections. That number is what tells
  a runaway loop (``min Δ 0.1ms``) apart from organic traffic.
* ``[RATE_LIMIT_SUMMARY]`` — one line per window across buckets: noisiest
  client, hottest endpoint, total rejections, tightest cadence seen.

Before this, the throttle report was emitted on *every* rejected request: a
burst of 300 rejections produced 300 identical multi-line reports, so the
logger, not the client, was the flood. Dedup is enforced in
:mod:`swarm.core.request_logging`, which installs a filter on the throttle
logger and lets exactly one report per bucket through per window.

In-memory by design: telemetry is diagnostic, not audit. Restarting the
process resets it. Every structure is bounded — the per-client ring
(``max_records_per_client``), the client map (``max_clients``, LRU + idle
sweep), the throttle buckets (``max_throttle_buckets``) and the closed-bucket
results the window summary aggregates (``max_window_results``) — so neither a
flood nor a client-IP scan can grow memory without limit.

Nothing secret is logged. Query strings, headers and bodies never reach a log
line; paths are normalised through :func:`normalize_path`, and every free-text
field (client, user, ``X-Swarm-Client-Source``) goes through
:func:`sanitize_field`, which also strips the control characters that would
otherwise let a client inject forged log lines.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Tuple

#: One structured line per request. Not ``swarm.throttle``: the throttle
#: logger carries a filter (see ``request_logging``) and the per-request line
#: must never be caught by it.
request_logger = logging.getLogger("swarm.requests")

#: Sibling of ``swarm.throttle`` (a child of ``swarm``, *not* of
#: ``swarm.throttle``) so the dedup filter cannot swallow the rollups it
#: produces. Journal-side: ``journalctl -t swarm.throttle_summary``.
throttle_window_logger = logging.getLogger("swarm.throttle_summary")

REQUEST_LOG_ENABLED_DEFAULT = True

# ---------------------------------------------------------------------------
# Log-line normalisation. One implementation, used by the request line, the
# throttle report and the throttle log filter, so a path cannot be normalised
# one way in one place and another way somewhere else.
# ---------------------------------------------------------------------------

MAX_PATH_CHARS = 256
MAX_FIELD_CHARS = 64
MAX_PATH_SEGMENT_CHARS = 64
MAX_TOP_ENDPOINTS_IN_LINE = 3
MAX_LOG_LINE_CHARS = 900
#: An endpoint is "METHOD path", and a path is already bounded to
#: MAX_PATH_CHARS — so quoting one gets a little more room than a scalar.
_ENDPOINT_QUOTE = MAX_PATH_CHARS + 16

#: Anything outside this set is dropped from a free-text log field. Newlines
#: and CR are the point: an ``X-Swarm-Client-Source`` carrying "\nWARNING ..."
#: would otherwise forge a log line. Printable non-ASCII (typographic dashes,
#: the ``Δ`` the cadence report uses) is kept — the journal is read by humans,
#: and mangle-everything is not a security control.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")

#: Credential *shapes*, applied to every field that reaches a log. Anchored on
#: both sides on purpose: unanchored ``sk-`` matches the "sk" inside
#: ``ask-user`` and ``task-manager-token-store``, which is how this repo's own
#: repository-wide scanner produced false positives. A real key of these
#: families mixes cases and carries digits; ordinary hyphenated English does
#: not, so the shape requires both.
_SECRET_SHAPES = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:"
    r"sk-[A-Za-z0-9_-]{12,}"
    r"|ghp_[A-Za-z0-9]{16,}"
    r"|github_pat_[A-Za-z0-9_]{16,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}"
    r")"
    r"(?![A-Za-z0-9])"
)

REDACTED = "[redacted]"

_UUID_SEGMENT = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_HEX_SEGMENT = re.compile(r"\A[0-9a-fA-F]+\Z")
_DIGITS_SEGMENT = re.compile(r"\A[0-9]+\Z")


def redact_secrets(text: str) -> str:
    """Replace credential-shaped substrings with ``[redacted]``."""
    if ("-" not in text) and ("_" not in text) and (":" not in text) and ("." not in text):
        # Cheap prefilter: every shape above carries one of these.
        return text
    if not (
        any(ch.isdigit() for ch in text)
        and any(ch.isupper() for ch in text)
        and any(ch.islower() for ch in text)
    ):
        return text
    return _SECRET_SHAPES.sub(REDACTED, text)


def sanitize_field(value: Any, *, limit: int = MAX_FIELD_CHARS, default: str = "") -> str:
    """Reduce an arbitrary value to safe single-line log text.

    Control characters are removed (log-injection defence), credential shapes
    are redacted, and the result is truncated — so a hostile
    ``X-Swarm-Client-Source`` can neither forge a line nor leak a key. Never
    returns a newline. Redaction runs *before* truncation, so a secret at the
    tail of a long value is caught rather than merely shortened.
    """
    if value is None:
        return default
    text = value if isinstance(value, str) else str(value)
    cleaned = redact_secrets(_CONTROL_CHARS.sub("", text))
    if len(cleaned) > limit:
        cleaned = cleaned[:limit]
    return cleaned


def _looks_like_token(segment: str) -> bool:
    """True for a segment that reads as an opaque credential, not a name.

    Long, mixed-case and containing a digit: a reset token, a signed URL
    segment, a base64 blob. A slug (``alpha``), a filename
    (``settings.json``) and an endpoint word (``status``) all fail this, so
    over-normalising cannot collapse two different operations together.
    """
    if len(segment) < 20:
        return False
    return (
        any(ch.isdigit() for ch in segment)
        and any(ch.isupper() for ch in segment)
        and any(ch.islower() for ch in segment)
    )


def _normalize_segment(segment: str) -> str:
    if not segment:
        return segment
    if len(segment) > MAX_PATH_SEGMENT_CHARS:
        # Truncating a credential and logging the prefix still leaks it.
        return "{long}"
    # Shape decisions run on the control-char-stripped segment, before any
    # redaction: a redacted ``[redacted]`` would stop looking like a token and
    # be logged verbatim instead of being collapsed to a placeholder.
    clean = _CONTROL_CHARS.sub("", segment)
    if not clean:
        return "{opaque}"
    if _UUID_SEGMENT.match(clean):
        return "{uuid}"
    if _DIGITS_SEGMENT.match(clean):
        return "{int}"
    if len(clean) >= 8 and _HEX_SEGMENT.match(clean):
        return "{hex}"
    if "@" in clean:
        return "{email}"
    if _looks_like_token(clean):
        return "{token}"
    return sanitize_field(clean, limit=MAX_PATH_SEGMENT_CHARS)


def normalize_path(path: Any) -> str:
    """Collapse identifier segments so like requests aggregate; drop queries.

    ``/chat/<uuid>/messages?token=...`` -> ``/chat/{uuid}/messages``. Identical
    operations from different rows merge (which is the point); genuinely
    different operations never do, because only uuid / hex / int / email /
    token-shaped segments are replaced.
    """
    raw = "" if path is None else str(path)
    for separator in ("?", "#"):
        cut = raw.find(separator)
        if cut != -1:
            raw = raw[:cut]
    if not raw:
        return "-"
    if len(raw) > MAX_PATH_CHARS:
        raw = raw[:MAX_PATH_CHARS]
    normalized = "/".join(_normalize_segment(part) for part in raw.split("/"))
    return normalized or "-"


@dataclass(frozen=True)
class RequestRecord:
    timestamp: float  # monotonic
    method: str
    path: str  # normalised — see normalize_path
    status_code: int | None
    client_ip: str
    user_key: str
    source: str
    duration_ms: float = 0.0
    response_bytes: int | None = None


@dataclass
class _ClientWindow:
    records: Deque[RequestRecord] = field(default_factory=deque)


@dataclass(frozen=True)
class ThrottleEvent:
    """What the dedup filter needs to decide about one rejection."""

    client_ip: str
    endpoint: str  # "GET /v1/preferences/"
    first: bool  # True -> this is the first rejection of this bucket's window
    rejections: int  # rejections so far in this bucket's window
    min_interarrival_ms: float | None
    wait_s: float | None
    window_seconds: float


@dataclass
class _ThrottleBucket:
    """One (client, endpoint) rejection bucket for one window."""

    first_ts: float
    last_ts: float
    rejections: int = 1
    min_interval_ms: float | None = None
    max_interval_ms: float | None = None
    interval_total_ms: float = 0.0
    interval_count: int = 0
    last_wait_s: float | None = None
    user_key: str = ""
    source: str = ""
    client_ip: str = ""
    endpoint: str = ""

    def observe(self, ts: float) -> None:
        delta_ms = (ts - self.last_ts) * 1000.0
        if delta_ms >= 0.0:
            self.interval_total_ms += delta_ms
            self.interval_count += 1
            if self.min_interval_ms is None or delta_ms < self.min_interval_ms:
                self.min_interval_ms = delta_ms
            if self.max_interval_ms is None or delta_ms > self.max_interval_ms:
                self.max_interval_ms = delta_ms
        self.last_ts = ts
        self.rejections += 1

    @property
    def avg_interval_ms(self) -> float | None:
        if not self.interval_count:
            return None
        return self.interval_total_ms / self.interval_count

    def rollup_line(self, window_seconds: float) -> str:
        wait = "none" if self.last_wait_s is None else f"{self.last_wait_s:.0f}s"
        return (
            f"[RATE_LIMIT_WINDOW] window={window_seconds:.0f}s "
            f"rejections={self.rejections} "
            f"client={sanitize_field(self.client_ip, limit=45) or 'unknown'} "
            f'endpoint="{_quote(self.endpoint)}" '
            f"user={_quote(self.user_key) or '-'} "
            f"source={_quote(self.source) or '-'} "
            f"wait={wait} "
            f"min_interarrival_ms={_ms(self.min_interval_ms)} "
            f"avg_interarrival_ms={_ms(self.avg_interval_ms)} "
            f"max_interarrival_ms={_ms(self.max_interval_ms)}"
        )


def _quote(value: Any, *, limit: int = MAX_FIELD_CHARS) -> str:
    """A log-safe, quote-escaped rendering of one value."""
    return sanitize_field(value, limit=limit).replace('"', "'")


def _ms(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}"


class RequestTelemetry:
    """Sliding-window request tracker keyed by client IP."""

    def __init__(
        self,
        *,
        window_seconds: float = 120.0,
        max_records_per_client: int = 500,
        max_clients: int = 512,
        throttle_window_seconds: float = 60.0,
        max_throttle_buckets: int = 512,
        max_window_results: int = 512,
        summary_window_seconds: float | None = None,
        emit_request_log: bool | None = None,
        clock=time.monotonic,
    ) -> None:
        self._window = float(window_seconds)
        self._max_records = int(max_records_per_client)
        self._max_clients = max(1, int(max_clients))
        self._clock = clock
        self._clients: "OrderedDict[str, _ClientWindow]" = OrderedDict()

        self._throttle_window = float(throttle_window_seconds)
        self._max_buckets = max(1, int(max_throttle_buckets))
        self._buckets: "OrderedDict[Tuple[str, str], _ThrottleBucket]" = OrderedDict()
        self._max_window_results = max(1, int(max_window_results))
        self._summary_window = (
            float(summary_window_seconds)
            if summary_window_seconds is not None
            else float(throttle_window_seconds)
        )
        self._window_results: List[_ThrottleBucket] = []
        self._window_opened: float | None = None

        self._emit_request_log = (
            request_log_enabled() if emit_request_log is None else bool(emit_request_log)
        )
        self._lock = threading.Lock()
        self._local = threading.local()
        # Amortised expiry: one float compare on the request path, a scan
        # every ``_sweep_interval``. Keeps memory honest when traffic stops
        # being interesting, without touching the per-request work.
        self._sweep_interval = max(1.0, min(self._window, self._throttle_window) / 4.0)
        self._last_sweep: float | None = None

    # -- per-request path --------------------------------------------------

    def record(
        self,
        *,
        client_ip: str,
        method: str,
        path: str,
        status_code: int | None,
        user_key: str,
        source: str = "",
        duration_ms: float = 0.0,
        response_bytes: int | None = None,
        now: float | None = None,
    ) -> None:
        ts = self._clock() if now is None else float(now)
        rec = RequestRecord(
            timestamp=ts,
            method=sanitize_field(method, limit=16).upper(),
            path=normalize_path(path),
            status_code=status_code,
            client_ip=sanitize_field(client_ip, limit=45),
            user_key=sanitize_field(user_key, limit=32),
            source=sanitize_field(source),
            duration_ms=float(duration_ms or 0.0),
            response_bytes=_coerce_bytes(response_bytes),
        )
        if self._emit_request_log and request_logger.isEnabledFor(logging.INFO):
            request_logger.info("[REQUEST] %s", format_request_line(rec))
        pending: List[str] = []
        with self._lock:
            window = self._clients.get(rec.client_ip)
            if window is None:
                window = _ClientWindow()
                self._clients[rec.client_ip] = window
            else:
                self._clients.move_to_end(rec.client_ip)
            window.records.append(rec)
            while len(window.records) > self._max_records:
                window.records.popleft()
            # A dict keyed by client IP is a dict a client-IP scan can grow
            # forever; evict the least-recently-seen entry instead.
            while len(self._clients) > self._max_clients:
                self._clients.popitem(last=False)
            pending = self._sweep_locked(ts)
        self._emit(pending)

    def client_summary(self, client_ip: str, *, now: float | None = None) -> dict[str, Any]:
        """Frequency breakdown for one client inside the sliding window."""
        ts = self._clock() if now is None else float(now)
        ip = sanitize_field(client_ip, limit=45)
        with self._lock:
            window = self._clients.get(ip)
            if window is None:
                return {
                    "total": 0,
                    "window_seconds": self._window,
                    "top_paths": [],
                    "sources": [],
                }
            self._prune_locked(window, ts)
            records = list(window.records)

        return self._summarize(records)

    def _prune_locked(self, window: _ClientWindow, now: float) -> None:
        cutoff = now - self._window
        while window.records and window.records[0].timestamp < cutoff:
            window.records.popleft()

    def _summarize(self, records: List[RequestRecord]) -> dict[str, Any]:
        per_path: Dict[str, List[RequestRecord]] = defaultdict(list)
        per_source: Dict[str, int] = defaultdict(int)
        for rec in records:
            per_path[rec.path].append(rec)
            per_source[rec.source or "(unknown)"] += 1

        top_paths: List[dict[str, Any]] = []
        for path, rows in per_path.items():
            rows.sort(key=lambda r: r.timestamp)
            intervals = [
                (b.timestamp - a.timestamp) * 1000.0 for a, b in zip(rows, rows[1:])
            ]
            top_paths.append(
                {
                    "path": path,
                    "count": len(rows),
                    "methods": sorted({r.method for r in rows}),
                    "min_interval_ms": round(min(intervals), 1) if intervals else None,
                    "avg_interval_ms": (
                        round(sum(intervals) / len(intervals), 1) if intervals else None
                    ),
                    "sources": sorted({r.source for r in rows if r.source}),
                }
            )
        top_paths.sort(key=lambda row: row["count"], reverse=True)

        sources = [
            {"source": name, "count": count}
            for name, count in sorted(
                per_source.items(), key=lambda kv: kv[1], reverse=True
            )
        ]
        return {
            "total": len(records),
            "window_seconds": self._window,
            "top_paths": top_paths,
            "sources": sources,
        }

    def format_top_endpoints(self, client_ip: str, *, limit: int = 8) -> str:
        suppressed = self._suppressed_note(client_ip)
        if suppressed is not None:
            return suppressed
        summary = self.client_summary(client_ip)
        if not summary["top_paths"]:
            return "    (no recent requests recorded)"
        lines = []
        for row in summary["top_paths"][:limit]:
            interval = row["min_interval_ms"]
            cadence = f" min Δ {interval}ms" if interval is not None else ""
            lines.append(
                f"    {row['count']:>4}× {'/'.join(row['methods'])} {row['path']}{cadence}"
            )
        return "\n".join(lines)

    def format_sources(self, client_ip: str, *, limit: int = 8) -> str:
        suppressed = self._suppressed_note(client_ip)
        if suppressed is not None:
            return suppressed
        summary = self.client_summary(client_ip)
        if not summary["sources"]:
            return "(no provenance headers — client did not send X-Swarm-Client-Source)"
        return ", ".join(
            f"{row['source']}×{row['count']}" for row in summary["sources"][:limit]
        )

    def _suppressed_note(self, client_ip: str) -> str | None:
        """One cheap line to stand in for a report already logged this window.

        The 429 handler builds its report from these two formatters *before*
        the record reaches the dedup filter, so returning a short note here is
        what stops the report being stringified 300 times per window. With the
        filter installed the note is discarded with the record; without it, it
        still caps the damage to one line per rejection.
        """
        event = getattr(self._local, "throttle_event", None)
        if event is None or event.first:
            return None
        if event.client_ip != sanitize_field(client_ip, limit=45):
            return None
        return (
            f"    (report suppressed — rejections={event.rejections} for this "
            "client+endpoint this window; see the [RATE_LIMIT_WINDOW] line)"
        )

    # -- rate-limit path ---------------------------------------------------

    def note_throttle(
        self,
        *,
        client_ip: str,
        method: str,
        path: str,
        wait: float | None = None,
        now: float | None = None,
    ) -> ThrottleEvent:
        """Count one rejection into its (client, endpoint) bucket.

        Cheap by design: a dict lookup, a counter bump and — for the minimum
        inter-arrival time the operator actually reads — one subtraction and
        two comparisons. No string building, no formatting, no I/O unless the
        bucket's window (or the summary window) has closed.
        """
        ts = self._clock() if now is None else float(now)
        ip = sanitize_field(client_ip, limit=45) or "unknown"
        endpoint = f"{sanitize_field(method, limit=16).upper() or '?'} {normalize_path(path)}"
        key = (ip, endpoint)
        pending: List[str] = []
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or (ts - bucket.first_ts) >= self._throttle_window:
                if bucket is not None:
                    pending.append(self._close_bucket_locked(key, bucket))
                user_key, source = self._identity_locked(ip)
                bucket = _ThrottleBucket(
                    first_ts=ts,
                    last_ts=ts,
                    last_wait_s=wait,
                    user_key=user_key,
                    source=source,
                    client_ip=ip,
                    endpoint=endpoint,
                )
                self._buckets[key] = bucket
                self._buckets.move_to_end(key)
                first = True
                while len(self._buckets) > self._max_buckets:
                    stale_key, stale = self._buckets.popitem(last=False)
                    pending.append(self._close_bucket_locked(stale_key, stale))
            else:
                bucket.observe(ts)
                bucket.last_wait_s = wait
                self._buckets.move_to_end(key)
                first = False
            event = ThrottleEvent(
                client_ip=ip,
                endpoint=endpoint,
                first=first,
                rejections=bucket.rejections,
                min_interarrival_ms=bucket.min_interval_ms,
                wait_s=wait,
                window_seconds=self._throttle_window,
            )
            self._local.throttle_event = event
            pending.extend(self._sweep_locked(ts))
        self._emit(pending)
        return event

    def _identity_locked(self, ip: str) -> tuple[str, str]:
        window = self._clients.get(ip)
        if window is None or not window.records:
            return "", ""
        last = window.records[-1]
        return last.user_key, last.source

    def _close_bucket_locked(
        self, key: Tuple[str, str], bucket: _ThrottleBucket
    ) -> str:
        """Fold one bucket into the window's results and return its line."""
        bucket.client_ip = bucket.client_ip or key[0]
        bucket.endpoint = bucket.endpoint or key[1]
        line = bucket.rollup_line(self._throttle_window)
        self._window_results.append(bucket)
        # Keep the summary's working set bounded; the oldest bucket is the
        # least interesting one to an operator reading "noisiest client".
        while len(self._window_results) > self._max_window_results:
            self._window_results.pop(0)
        return line

    def _summary_line_locked(self) -> str | None:
        if not self._window_results:
            return None
        results = sorted(self._window_results, key=lambda b: b.rejections, reverse=True)
        total = sum(b.rejections for b in results)
        noisiest = max(results, key=lambda b: b.rejections)
        by_client: Dict[str, int] = defaultdict(int)
        by_endpoint: Dict[str, int] = defaultdict(int)
        cadences = [b.min_interval_ms for b in results if b.min_interval_ms is not None]
        for bucket in results:
            by_client[bucket.client_ip] += bucket.rejections
            by_endpoint[f"{bucket.endpoint}"] += bucket.rejections
        hottest_endpoint, hottest_count = max(
            by_endpoint.items(), key=lambda kv: kv[1], default=("", 0)
        )
        top = ", ".join(
            f"{bucket.rejections}× {_quote(bucket.endpoint, limit=_ENDPOINT_QUOTE)} "
            f"(min Δ {_ms(bucket.min_interval_ms)}ms)"
            for bucket in results[:MAX_TOP_ENDPOINTS_IN_LINE]
        )
        line = (
            f"[RATE_LIMIT_SUMMARY] window={self._summary_window:.0f}s "
            f"rejections={total} buckets={len(results)} clients={len(by_client)} "
            f"noisiest_client={sanitize_field(noisiest.client_ip, limit=45)}"
            f"({noisiest.rejections}) "
            f'hottest_endpoint="{_quote(hottest_endpoint, limit=_ENDPOINT_QUOTE)}"'
            f"({hottest_count}) "
            f"min_interarrival_ms={_ms(min(cadences) if cadences else None)} "
            f"endpoints=[{top}]"
        )
        if len(line) > MAX_LOG_LINE_CHARS:
            line = line[: MAX_LOG_LINE_CHARS - 3] + "..."
        self._window_results = []
        self._window_opened = None
        return line

    # -- expiry / flush ----------------------------------------------------

    def _sweep_locked(self, now: float) -> List[str]:
        if self._last_sweep is not None and (now - self._last_sweep) < self._sweep_interval:
            return []
        self._last_sweep = now
        lines: List[str] = []
        # Idle clients: dropped wholesale so a client-IP scan cannot pin
        # memory for the life of the process.
        cutoff = now - self._window
        for ip in [ip for ip, win in self._clients.items() if win.records and win.records[-1].timestamp < cutoff]:
            del self._clients[ip]
        for win in self._clients.values():
            self._prune_locked(win, now)
        # Throttle buckets whose window has closed, oldest first.
        expired = [key for key, b in self._buckets.items() if (now - b.first_ts) >= self._throttle_window]
        for key in expired:
            lines.append(self._close_bucket_locked(key, self._buckets.pop(key)))
        if self._window_opened is None:
            if self._window_results:
                self._window_opened = now
        elif (now - self._window_opened) >= self._summary_window:
            summary = self._summary_line_locked()
            if summary:
                lines.append(summary)
            self._window_opened = now
        return lines

    def flush(self, *, now: float | None = None) -> List[str]:
        """Close every open bucket and emit the window summary.

        Returns the lines instead of logging them when ``emit=False`` (tests
        and measurement); otherwise logs them and returns them.
        """
        ts = self._clock() if now is None else float(now)
        with self._lock:
            lines: List[str] = []
            for key in list(self._buckets):
                lines.append(self._close_bucket_locked(key, self._buckets.pop(key)))
            summary = self._summary_line_locked()
            if summary:
                lines.append(summary)
            self._buckets.clear()
            self._window_opened = None
            self._last_sweep = ts
        self._emit(lines)
        return lines

    def _emit(self, lines: List[str]) -> None:
        if not lines:
            return
        for line in lines:
            try:
                throttle_window_logger.warning("%s", line)
            except Exception:  # pragma: no cover - logging must never raise
                pass

    # -- introspection / tests --------------------------------------------

    @property
    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._clients)

    @property
    def tracked_throttle_buckets(self) -> int:
        with self._lock:
            return len(self._buckets)

    def reset(self) -> None:
        with self._lock:
            self._clients.clear()
            self._buckets.clear()
            self._window_results = []
            self._window_opened = None
            self._last_sweep = None
        self._local = threading.local()


def format_request_line(rec: RequestRecord) -> str:
    """One request, one line. Never more."""
    line = (
        f"method={rec.method or '-'} path={rec.path} "
        f"status={rec.status_code if rec.status_code is not None else '-'} "
        f"client={rec.client_ip or 'unknown'} user={rec.user_key or '-'} "
        f"bytes={rec.response_bytes if rec.response_bytes is not None else '-'} "
        f"duration_ms={rec.duration_ms:.1f}"
    )
    if rec.source:
        line += f" source={_quote(rec.source)}"
    return line


def _coerce_bytes(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


def request_log_enabled() -> bool:
    """``SWARM_REQUEST_LOG=off`` silences the per-request line.

    The line is one per request, which is the price of "who hit what, when".
    An operator who would rather not pay it in the journal can turn it off
    without a code change; the throttle rollups are unaffected.
    """
    raw = os.getenv("SWARM_REQUEST_LOG")
    if raw is None:
        return REQUEST_LOG_ENABLED_DEFAULT
    return raw.strip().lower() not in {"0", "off", "false", "no", "none"}


_INSTANCE: RequestTelemetry | None = None
_INSTANCE_LOCK = threading.Lock()


def default_telemetry() -> RequestTelemetry:
    """Process-wide telemetry instance (created lazily, thread-safe)."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            from swarm.throttle_defaults import RATE_WINDOW_SECONDS

            _INSTANCE = RequestTelemetry(
                throttle_window_seconds=float(RATE_WINDOW_SECONDS)
            )
        return _INSTANCE


def get_client_burst_summary(client_ip: str) -> dict[str, Any]:
    """Convenience accessor for the exception handler."""
    return default_telemetry().client_summary(client_ip)
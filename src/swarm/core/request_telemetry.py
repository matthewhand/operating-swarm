"""#800 — in-process request telemetry for 429 burst forensics.

A per-client sliding-window ring of recent requests (method, path, status,
caller provenance). Purely observational: it never throttles or blocks —
DRF's throttles keep deciding. When a 429 fires, the exception handler pulls
the client's window from here and logs the frequency breakdown, so an
operator can see exactly which endpoint and which frontend caller flooded
the budget (the #738 class of loop) without grepping browser consoles.

In-memory by design: telemetry is diagnostic, not audit. Restarting the
process resets it, and the ring is bounded (``max_records_per_client``)
so a flood cannot grow memory.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List


@dataclass(frozen=True)
class RequestRecord:
    timestamp: float  # monotonic
    method: str
    path: str
    status_code: int | None
    client_ip: str
    user_key: str
    source: str
    duration_ms: float = 0.0


@dataclass
class _ClientWindow:
    records: Deque[RequestRecord] = field(default_factory=deque)


class RequestTelemetry:
    """Sliding-window request tracker keyed by client IP."""

    def __init__(
        self,
        *,
        window_seconds: float = 120.0,
        max_records_per_client: int = 500,
        clock=time.monotonic,
    ) -> None:
        self._window = float(window_seconds)
        self._max_records = int(max_records_per_client)
        self._clock = clock
        self._clients: Dict[str, _ClientWindow] = {}
        self._lock = threading.Lock()

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
        now: float | None = None,
    ) -> None:
        ts = self._clock() if now is None else float(now)
        rec = RequestRecord(
            timestamp=ts,
            method=str(method or "").upper(),
            path=str(path or ""),
            status_code=status_code,
            client_ip=str(client_ip or ""),
            user_key=str(user_key or ""),
            source=str(source or ""),
            duration_ms=float(duration_ms or 0.0),
        )
        with self._lock:
            window = self._clients.get(rec.client_ip)
            if window is None:
                window = _ClientWindow()
                self._clients[rec.client_ip] = window
            window.records.append(rec)
            while len(window.records) > self._max_records:
                window.records.popleft()

    def _prune_locked(self, window: _ClientWindow, now: float) -> None:
        cutoff = now - self._window
        while window.records and window.records[0].timestamp < cutoff:
            window.records.popleft()

    def client_summary(self, client_ip: str, *, now: float | None = None) -> dict[str, Any]:
        """Frequency breakdown for one client inside the sliding window."""
        ts = self._clock() if now is None else float(now)
        with self._lock:
            window = self._clients.get(str(client_ip or ""))
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
        summary = self.client_summary(client_ip)
        if not summary["sources"]:
            return "(no provenance headers — client did not send X-Swarm-Client-Source)"
        return ", ".join(
            f"{row['source']}×{row['count']}" for row in summary["sources"][:limit]
        )


_INSTANCE: RequestTelemetry | None = None
_INSTANCE_LOCK = threading.Lock()


def default_telemetry() -> RequestTelemetry:
    """Process-wide telemetry instance (created lazily, thread-safe)."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = RequestTelemetry()
        return _INSTANCE


def get_client_burst_summary(client_ip: str) -> dict[str, Any]:
    """Convenience accessor for the exception handler."""
    return default_telemetry().client_summary(client_ip)

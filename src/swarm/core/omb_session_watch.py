"""Live watch of OpenMousBot follow-up bot texts (issue #125).

After ``_omb_send`` returns the first ``role=bot`` text, keep listening on
``GET /api/events`` (SSE) for later messages on that thread. Each new bot
text is its own Swarm assistant turn (chat_store + WS). Poll
``GET /api/threads/{id}/messages`` only when SSE is down.

Quiet window: drop a track after ``QUIET_IDLE_SECONDS`` with no new bot
text (default 45s). Leaving the seat (WS disconnect / unwatch) stops it
immediately. No WSS. Never render ``OpenMousBot accepted the turn``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

QUIET_IDLE_SECONDS = 45.0
POLL_FALLBACK_SECONDS = 2.0
MAX_WATCH_SECONDS = 10 * 60.0
PENDING_LIMIT = 100
_PENDING_TTL_SECONDS = 10 * 60
_SSE_CONNECT_TIMEOUT_S = 8.0


@dataclass
class OmbWatchTrack:
    user_key: str
    agent_id: str
    conversation_id: str
    bot_id: str
    thread_id: str
    base_url: str
    headers: dict[str, str]
    seen_ids: set[str] = field(default_factory=set)
    last_change: float = field(default_factory=time.monotonic)
    started_at: float = field(default_factory=time.monotonic)
    sse_ok: bool = False


@dataclass
class _Consumer:
    user_key: str
    queue: Any
    loop: Any = None


def parse_sse_block(block: str) -> dict[str, Any] | None:
    """One SSE event (id/data/comment lines) → JSON payload, or None."""
    data_lines: list[str] = []
    for raw in (block or "").splitlines():
        line = raw.rstrip("\r")
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        return None
    blob = "\n".join(data_lines).strip()
    if not blob:
        return None
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def followup_from_sse(
    payload: dict[str, Any] | None,
    *,
    thread_id: str,
    seen_ids: set[str],
) -> dict[str, str] | None:
    """Extract a new bot text from an OMB SSE ``kind=message`` frame."""
    from swarm.core.remotes import _omb_is_bot_text, _omb_message_text

    if not isinstance(payload, dict):
        return None
    kind = str(payload.get("kind") or "")
    if kind not in ("message", "message.patch"):
        return None
    if str(payload.get("threadId") or "").strip() != thread_id:
        return None
    msg = payload.get("message")
    if not _omb_is_bot_text(msg):
        return None
    mid = str((msg or {}).get("id") or "").strip()
    if mid and mid in seen_ids:
        return None
    text = _omb_message_text(msg)
    if not text:
        return None
    if not mid:
        mid = f"text:{hash(text)}"
        if mid in seen_ids:
            return None
    return {"id": mid, "text": text}


class OmbSessionMonitor:
    """Process-global OMB thread watcher (SSE + poll fallback)."""

    def __init__(self) -> None:
        self._tracks: dict[tuple[str, str, str], OmbWatchTrack] = {}
        self._consumers: list[_Consumer] = []
        self._pending: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sse_stops: dict[str, threading.Event] = {}

    def register_consumer(self, user_key: str, queue: Any, loop: Any = None) -> None:
        if not user_key:
            return
        with self._lock:
            if any(c.queue is queue for c in self._consumers):
                return
            self._consumers.append(_Consumer(user_key=user_key, queue=queue, loop=loop))
        self._flush_pending(user_key, queue, loop)
        self._ensure_worker()

    def unregister_consumer(self, queue: Any) -> None:
        with self._lock:
            self._consumers = [c for c in self._consumers if c.queue is not queue]

    def watch_thread(
        self,
        *,
        user_key: str,
        agent_id: str,
        conversation_id: str,
        spec: Any,
        bot_id: str,
        thread_id: str,
        seen_ids: set[str] | None = None,
        start_worker: bool = True,
    ) -> OmbWatchTrack | None:
        user_key = (user_key or "").strip()
        thread_id = (thread_id or "").strip()
        conversation_id = (conversation_id or "").strip()
        if not user_key or not thread_id or not conversation_id:
            return None
        from swarm.core.remotes import _auth_headers

        base_url = str(getattr(spec, "base_url", "") or "").rstrip("/")
        if not base_url:
            return None
        key = (user_key, conversation_id, thread_id)
        with self._lock:
            track = self._tracks.get(key)
            if track is None:
                track = OmbWatchTrack(
                    user_key=user_key,
                    agent_id=(agent_id or "").strip(),
                    conversation_id=conversation_id,
                    bot_id=(bot_id or "").strip(),
                    thread_id=thread_id,
                    base_url=base_url,
                    headers=_auth_headers(spec),
                    seen_ids=set(seen_ids or ()),
                )
                self._tracks[key] = track
            else:
                if agent_id:
                    track.agent_id = agent_id.strip()
                if bot_id:
                    track.bot_id = bot_id.strip()
                if seen_ids:
                    track.seen_ids.update(seen_ids)
                track.last_change = time.monotonic()
        if start_worker:
            self._ensure_worker()
        return track

    def unwatch_conversation(self, user_key: str, conversation_id: str) -> None:
        cid = (conversation_id or "").strip()
        uk = (user_key or "").strip()
        if not cid:
            return
        with self._lock:
            drop = [k for k, t in self._tracks.items() if t.user_key == uk and t.conversation_id == cid]
            for key in drop:
                self._tracks.pop(key, None)
        self._stop_orphan_sse()

    def track_count(self) -> int:
        with self._lock:
            return len(self._tracks)

    def tracks(self) -> list[OmbWatchTrack]:
        with self._lock:
            return list(self._tracks.values())

    def ingest_sse(self, payload: dict[str, Any] | None) -> None:
        """Apply one SSE JSON payload to matching tracks (tests + worker)."""
        if not isinstance(payload, dict):
            return
        thread_id = str(payload.get("threadId") or "").strip()
        with self._lock:
            tracks = (
                [t for t in self._tracks.values() if t.thread_id == thread_id]
                if thread_id
                else list(self._tracks.values())
            )
        for track in tracks:
            row = followup_from_sse(payload, thread_id=track.thread_id, seen_ids=track.seen_ids)
            if row:
                self._emit(track, row["id"], row["text"])

    def ingest_messages(self, track: OmbWatchTrack, messages: list[Any]) -> None:
        from swarm.core.remotes import _omb_is_bot_text, _omb_message_text

        for msg in messages:
            if not _omb_is_bot_text(msg):
                continue
            mid = str((msg or {}).get("id") or "").strip()
            text = _omb_message_text(msg)
            if not text:
                continue
            if not mid:
                mid = f"text:{hash(text)}"
            if mid in track.seen_ids:
                continue
            self._emit(track, mid, text)

    def prune_idle(self) -> None:
        now = time.monotonic()
        with self._lock:
            for key, track in list(self._tracks.items()):
                quiet = now - track.last_change
                aged = now - track.started_at
                if quiet >= QUIET_IDLE_SECONDS or aged >= MAX_WATCH_SECONDS:
                    self._tracks.pop(key, None)
        self._stop_orphan_sse()

    def _stop_orphan_sse(self) -> None:
        with self._lock:
            live = {t.base_url for t in self._tracks.values()}
            stops = list(self._sse_stops.items())
        for base, ev in stops:
            if base not in live:
                ev.set()

    def close(self) -> None:
        self._stop.set()
        for ev in list(self._sse_stops.values()):
            ev.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        with self._lock:
            self._tracks.clear()
        self._thread = None
        self._stop = threading.Event()

    def _ensure_worker(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="omb-session-watch", daemon=True)
        self._thread.start()

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                logger.exception("omb session watch tick failed")
            self.prune_idle()
            with self._lock:
                empty = not self._tracks and not self._consumers and not self._pending
            if empty:
                return
            self._stop.wait(POLL_FALLBACK_SECONDS)

    def _tick(self) -> None:
        with self._lock:
            tracks = list(self._tracks.values())
        by_base: dict[str, list[OmbWatchTrack]] = {}
        for track in tracks:
            by_base.setdefault(track.base_url, []).append(track)
        for base_url, group in by_base.items():
            if any(t.sse_ok for t in group):
                continue
            self._ensure_sse(base_url, group[0].headers)
            for track in group:
                if track.sse_ok:
                    continue
                self._poll_thread(track)

    def _ensure_sse(self, base_url: str, headers: dict[str, str]) -> None:
        stop = self._sse_stops.get(base_url)
        if stop is not None and not stop.is_set():
            return
        ev = threading.Event()
        self._sse_stops[base_url] = ev
        threading.Thread(
            target=self._sse_loop,
            args=(base_url, headers, ev),
            name=f"omb-sse-{base_url}",
            daemon=True,
        ).start()

    def _sse_loop(self, base_url: str, headers: dict[str, str], stop: threading.Event) -> None:
        url = f"{base_url}/api/events"
        req_headers = dict(headers)
        req_headers["Accept"] = "text/event-stream"
        req_headers["Cache-Control"] = "no-cache"
        request = urllib.request.Request(url, headers=req_headers, method="GET")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            resp = opener.open(request, timeout=_SSE_CONNECT_TIMEOUT_S)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            logger.debug("omb SSE subscribe failed: %s", exc)
            stop.set()
            return
        with self._lock:
            for track in self._tracks.values():
                if track.base_url == base_url:
                    track.sse_ok = True
        try:
            resp.fp.raw._sock.settimeout(1.0)  # type: ignore[attr-defined]
        except Exception:
            pass
        buf_lines: list[str] = []
        try:
            while not stop.is_set() and not self._stop.is_set():
                try:
                    raw_line = resp.readline()
                except TimeoutError:
                    continue
                except OSError:
                    break
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace")
                if line in ("\n", "\r\n"):
                    payload = parse_sse_block("".join(buf_lines))
                    buf_lines = []
                    if payload:
                        self.ingest_sse(payload)
                    continue
                buf_lines.append(line)
        finally:
            with contextlib.suppress(Exception):
                resp.close()
            with self._lock:
                for track in self._tracks.values():
                    if track.base_url == base_url:
                        track.sse_ok = False
            stop.set()

    def _poll_thread(self, track: OmbWatchTrack) -> None:
        from swarm.core.remotes import _UP, _omb_messages_from, http_json

        page = http_json(
            "GET",
            f"{track.base_url}/api/threads/{track.thread_id}/messages?limit=40",
            headers=track.headers,
            timeout=min(8.0, POLL_FALLBACK_SECONDS * 4),
        )
        if page.status not in _UP:
            return
        self.ingest_messages(track, _omb_messages_from(page.body))

    def _emit(self, track: OmbWatchTrack, msg_id: str, text: str) -> None:
        track.seen_ids.add(msg_id)
        track.last_change = time.monotonic()
        self._persist(track, text)
        self._publish(track, text)

    def _persist(self, track: OmbWatchTrack, text: str) -> None:
        try:
            from swarm.core import chat_store
            from swarm.core.transcript_roles import append_turn

            record, sid = _load_track_record(track)
            messages = list(record.get("messages") or [])
            events = list(record.get("ui_events") or [])
            for row in messages:
                if (
                    str(row.get("role") or "") == "assistant"
                    and str(row.get("content") or "").strip() == text
                ):
                    return
            append_turn(messages, events, "assistant", text)
            chat_store.save(
                track.user_key,
                track.agent_id,
                messages,
                conversation_id=track.conversation_id,
                session_id=sid,
                ui_events=events,
            )
        except Exception:
            logger.debug("omb follow-up persist failed", exc_info=True)

    def _publish(self, track: OmbWatchTrack, text: str) -> None:
        payload = {
            "type": "omb_followup",
            "source": "omb",
            "user_key": track.user_key,
            "agent_id": track.agent_id,
            "conversation_id": track.conversation_id,
            "session_id": track.thread_id,
            "text": text,
            "events": [{"role": "assistant", "text": text, "ts": _utc_now_iso()}],
            "ts": _utc_now_iso(),
        }
        with self._lock:
            listeners = [c for c in self._consumers if c.user_key == track.user_key]
        if listeners:
            for consumer in listeners:
                _put_nowait(consumer.queue, payload, loop=consumer.loop)
            return
        bucket = self._pending.setdefault(track.user_key, deque(maxlen=PENDING_LIMIT))
        row = dict(payload)
        row["_enqueued_at"] = time.monotonic()
        bucket.append(row)

    def _flush_pending(self, user_key: str, queue: Any, loop: Any = None) -> None:
        bucket = self._pending.get(user_key)
        if not bucket:
            return
        cutoff = time.monotonic() - _PENDING_TTL_SECONDS
        fresh = [row for row in bucket if row.get("_enqueued_at", 0) >= cutoff]
        self._pending[user_key] = deque(fresh, maxlen=PENDING_LIMIT)
        for row in fresh:
            _put_nowait(queue, row, loop=loop)


def _load_track_record(track: OmbWatchTrack) -> tuple[dict[str, Any], str]:
    from swarm.core import chat_store

    record = chat_store.load(
        track.user_key,
        track.agent_id,
        conversation_id=track.conversation_id,
        session_id=track.conversation_id,
    )
    if record is not None:
        return record, track.conversation_id
    record = chat_store.load(
        track.user_key,
        track.agent_id,
        conversation_id=track.conversation_id,
    )
    if record is not None:
        return record, str(record.get("session_id") or "")
    return (
        chat_store.empty_record(
            user_key=track.user_key,
            agent_id=track.agent_id,
            conversation_id=track.conversation_id,
        ),
        track.conversation_id,
    )


def _put_nowait(queue: Any, payload: dict[str, Any], loop: Any = None) -> None:
    with contextlib.suppress(Exception):
        if loop is not None:
            loop.call_soon_threadsafe(queue.put_nowait, payload)
            return
        queue.put_nowait(payload)


_monitor: OmbSessionMonitor | None = None
_monitor_lock = threading.Lock()


def get_monitor() -> OmbSessionMonitor:
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = OmbSessionMonitor()
        return _monitor


def reset_monitor_for_tests() -> None:
    global _monitor
    with _monitor_lock:
        if _monitor is not None:
            _monitor.close()
        _monitor = None


def register_consumer(user_key: str, queue: Any, loop: Any = None) -> None:
    get_monitor().register_consumer(user_key, queue, loop=loop)


def unregister_consumer(queue: Any) -> None:
    get_monitor().unregister_consumer(queue)


def unwatch_conversation(user_key: str, conversation_id: str) -> None:
    with contextlib.suppress(Exception):
        get_monitor().unwatch_conversation(user_key, conversation_id)


def watch_thread(**kwargs: Any) -> OmbWatchTrack | None:
    return get_monitor().watch_thread(**kwargs)


def watch_from_operate(
    result: Any,
    *,
    user_key: str,
    agent_id: str,
    conversation_id: str,
    spec: Any | None = None,
) -> OmbWatchTrack | None:
    """Arm a follow-up watch after the first OMB reply is already persisted."""
    if result is None or not getattr(result, "ok", False):
        return None
    if str(getattr(result, "remote", "") or "") != "omb":
        return None
    data = result.data if isinstance(result.data, dict) else {}
    thread_id = str(data.get("thread_id") or "").strip()
    bot_id = str(data.get("bot_id") or "").strip()
    message_id = str(data.get("message_id") or "").strip()
    if not thread_id:
        return None
    if spec is None:
        try:
            from swarm.core.remotes import load_remote

            spec = load_remote("omb")
        except Exception:
            return None
    seen = {message_id} if message_id else set()
    first_text = str(data.get("text") or "").strip()
    if first_text:
        seen.add(f"text:{hash(first_text)}")
    return get_monitor().watch_thread(
        user_key=user_key,
        agent_id=agent_id,
        conversation_id=conversation_id,
        spec=spec,
        bot_id=bot_id,
        thread_id=thread_id,
        seen_ids=seen,
    )


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

"""Live watch of Herdr panes — external turns + incremental streaming (#794).

When a socket is focused on ``?remote=herdr&session=<target>``, the monitor
polls ``herdr agent get`` for the pane's lifecycle state and
``state_change_seq``. While the pane is ``working``, recent pane output is
read and dispatched as incremental deltas; on ``done``/``idle`` the final
text is sanitized (#790/#850), persisted to chat_store, and closed as an
assistant turn.

Turns initiated directly in Herdr (tmux/CLI) are detected the same way: a
``state_change_seq`` increment with ``working`` while no Swarm prompt is in
flight mirrors the activity — best-effort prompt hint becomes a user turn.

SSH-hop seats just get the poll loop (no socket subscription is available
from here); the poll interval is the same, so no dual code path. Quiet
tracks drop after ``QUIET_IDLE_SECONDS`` (60s) — mirrors omb_session_watch
(#125) semantics.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

QUIET_IDLE_SECONDS = 60.0
POLL_SECONDS = 1.5
MAX_WATCH_SECONDS = 15 * 60.0
PENDING_LIMIT = 100
_PENDING_TTL_SECONDS = 10 * 60
# Pane snapshots can be large; cap what we keep per track for delta math.
MAX_SNAPSHOT_CHARS = 20_000

# How long after a Swarm-initiated send a working transition is attributed to
# that send (not mirrored as external) (#794). Generous: the harness op may
# wait behind a queue before the pane flips to working.
SWARM_SEND_WINDOW = 120.0

WORKING_STATES = frozenset({"working", "running", "busy"})
DONE_STATES = frozenset({"done", "idle", "stopped", "unknown"})


@dataclass
class HerdrWatchTrack:
    user_key: str
    agent_id: str
    conversation_id: str
    target: str
    last_seq: int | None = None
    last_status: str = ""
    last_text: str = ""
    last_change: float = field(default_factory=time.monotonic)
    started_at: float = field(default_factory=time.monotonic)
    streaming: bool = False
    # Set when a seq increment started a turn we did not initiate from Swarm.
    external_turn: bool = False
    prompt_hint: str = ""
    # Monotonic stamp of the last Swarm-initiated send (#794): a working
    # transition within SWARM_SEND_WINDOW of this stamp is ours — no mirror.
    swarm_send_at: float = 0.0


@dataclass
class _Consumer:
    user_key: str
    queue: Any
    loop: Any = None


def pane_delta(previous: str, current: str) -> str:
    """New pane text beyond ``previous`` (#794 streaming delta).

    Terminal output appends, so a prefix match yields the tail. When the
    pane re-rendered (cursor moves redraw lines), the honest fallback is the
    full snapshot — the client replaces rather than duplicates.
    """
    previous = previous or ""
    current = current or ""
    if not previous:
        return current
    if current.startswith(previous):
        return current[len(previous) :]
    return current


def extract_prompt_hint(snapshot: str) -> str:
    """Best-effort user-prompt hint from the last pane snapshot.

    The typed prompt is usually the last clean line before agent output
    begins. TUI chrome is already gone from sanitized snapshots; take the
    last non-empty line, capped, and skip obvious status fragments.
    """
    for line in reversed((snapshot or "").splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) > 500:
            return ""
        return stripped
    return ""


def _clip(text: str) -> str:
    return text[-MAX_SNAPSHOT_CHARS:] if len(text) > MAX_SNAPSHOT_CHARS else text


def note_swarm_send(*, user_key: str, conversation_id: str, target: str) -> None:
    """Record a Swarm-initiated send so its turn is not mirrored (#794).

    Called from the send path right before the harness op is queued. A
    working transition within :data:`SWARM_SEND_WINDOW` of the stamp is
    attributed to Swarm; anything later (or never stamped) is external.
    """
    with contextlib.suppress(Exception):
        get_monitor().note_swarm_send(
            user_key=user_key, conversation_id=conversation_id, target=target
        )


class HerdrSessionMonitor:
    """Process-global Herdr pane watcher (poll-based, per focus).

    ``autostart=False`` (tests) never spawns the background worker — the
    caller drives :meth:`poll_once` manually for deterministic scripts.
    """

    def __init__(self, *, autostart: bool = True) -> None:
        self._autostart = autostart
        self._tracks: dict[tuple[str, str, str], HerdrWatchTrack] = {}
        self._consumers: list[_Consumer] = []
        self._pending: dict[str, list] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- consumer registry -------------------------------------------------

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

    # -- tracks -------------------------------------------------------------

    def watch_session(
        self,
        *,
        user_key: str,
        agent_id: str,
        conversation_id: str,
        target: str,
        last_text: str = "",
    ) -> HerdrWatchTrack | None:
        user_key = (user_key or "").strip()
        conversation_id = (conversation_id or "").strip()
        target = (target or "").strip()
        if not user_key or not conversation_id or not target:
            return None
        key = (user_key, conversation_id, target)
        with self._lock:
            track = self._tracks.get(key)
            if track is None:
                track = HerdrWatchTrack(
                    user_key=user_key,
                    agent_id=(agent_id or "remote_harness").strip(),
                    conversation_id=conversation_id,
                    target=target,
                    last_text=_clip(last_text),
                )
                self._tracks[key] = track
            else:
                track.last_change = time.monotonic()
        self._ensure_worker()
        return track

    def unwatch_conversation(self, user_key: str, conversation_id: str) -> None:
        cid = (conversation_id or "").strip()
        uk = (user_key or "").strip()
        if not cid:
            return
        with self._lock:
            drop = [
                k
                for k, t in self._tracks.items()
                if t.user_key == uk and t.conversation_id == cid
            ]
            for key in drop:
                self._tracks.pop(key, None)

    def note_swarm_send(self, *, user_key: str, conversation_id: str, target: str) -> None:
        """Stamp the track so its next transition is attributed to Swarm."""
        uk = (user_key or "").strip()
        cid = (conversation_id or "").strip()
        tgt = (target or "").strip()
        if not uk or not cid or not tgt:
            return
        with self._lock:
            track = self._tracks.get((uk, cid, tgt))
            if track is None:
                # No live track (seat not focused / watch not armed) — nothing
                # to attribute; the mirror path only exists for live watches.
                return
            track.swarm_send_at = time.monotonic()

    def track_count(self) -> int:
        with self._lock:
            return len(self._tracks)

    def tracks(self) -> list[HerdrWatchTrack]:
        with self._lock:
            return list(self._tracks.values())

    # -- polling ------------------------------------------------------------

    def poll_once(self) -> None:
        """One poll pass over all tracks (also the test seam)."""
        with self._lock:
            tracks = list(self._tracks.values())
        for track in tracks:
            try:
                self._poll_track(track)
            except Exception:
                logger.debug("herdr watch poll failed for %s", track.target, exc_info=True)

    def _poll_track(self, track: HerdrWatchTrack) -> None:
        from swarm.core.remotes import read_herdr_recent_raw
        from swarm.herdr.client import extract_agent_state, extract_state_change_seq

        client = _load_client()
        get_payload = client.agent_get(track.target)
        state = (extract_agent_state(get_payload) or "").strip().lower()
        seq = extract_state_change_seq(get_payload)

        seq_moved = seq is not None and track.last_seq is not None and seq != track.last_seq
        if seq is not None:
            track.last_seq = seq

        if state in WORKING_STATES:
            was_idle = track.last_status in DONE_STATES or not track.last_status
            snapshot = _clip(read_herdr_recent_raw(track.target))
            if was_idle or seq_moved and not track.streaming:
                # A turn began. If we did not start it from Swarm, mirror it.
                if was_idle and not track.streaming:
                    # Attribute the turn: a working transition right after a
                    # Swarm send is ours (#794); anything else is external.
                    ours = (
                        track.swarm_send_at > 0
                        and (time.monotonic() - track.swarm_send_at)
                        <= SWARM_SEND_WINDOW
                    )
                    if not ours:
                        track.external_turn = True
                        track.prompt_hint = extract_prompt_hint(track.last_text)
                        if track.prompt_hint:
                            self._publish(
                                track,
                                {
                                    "type": "herdr_external_turn",
                                    "text": track.prompt_hint,
                                },
                            )
                track.streaming = True
                track.last_text = _clip(track.last_text)
            delta = pane_delta(track.last_text, snapshot)
            if delta:
                track.last_text = snapshot
                self._publish(
                    track,
                    {
                        "type": "herdr_stream",
                        "text": delta,
                        "final": False,
                        "status": state,
                    },
                )
        elif state in DONE_STATES:
            if not track.streaming:
                # Idle snapshot: remember the pane so an externally started
                # turn can mirror the user's typed prompt (#794).
                track.last_text = _clip(read_herdr_recent_raw(track.target))
                if state:
                    track.last_status = state
                track.last_change = time.monotonic()
                return
            from swarm.core.remotes import sanitize_herdr_response

            final_text = sanitize_herdr_response(read_herdr_recent_raw(track.target)).strip()
            track.streaming = False
            track.last_text = _clip(final_text)
            if final_text:
                self._publish(
                    track,
                    {"type": "herdr_stream", "text": final_text, "final": True, "status": state},
                )
            track.external_turn = False
            track.prompt_hint = ""

        if state:
            track.last_status = state
        track.last_change = time.monotonic()

    # -- lifecycle ------------------------------------------------------------

    def prune_idle(self) -> None:
        now = time.monotonic()
        with self._lock:
            for key, track in list(self._tracks.items()):
                quiet = now - track.last_change
                aged = now - track.started_at
                if quiet >= QUIET_IDLE_SECONDS or aged >= MAX_WATCH_SECONDS:
                    self._tracks.pop(key, None)

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        with self._lock:
            self._tracks.clear()
        self._thread = None
        self._stop = threading.Event()

    def _ensure_worker(self) -> None:
        if not self._autostart:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="herdr-session-watch", daemon=True)
        self._thread.start()

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                logger.exception("herdr session watch tick failed")
            self.prune_idle()
            with self._lock:
                empty = not self._tracks and not self._consumers and not self._pending
            if empty:
                return
            self._stop.wait(POLL_SECONDS)

    # -- emission -------------------------------------------------------------

    def _publish(self, track: HerdrWatchTrack, extra: dict[str, Any]) -> None:
        payload = {
            "source": "herdr",
            "user_key": track.user_key,
            "agent_id": track.agent_id,
            "conversation_id": track.conversation_id,
            "session_id": track.target,
            "target": track.target,
            "ts": _utc_now_iso(),
            **extra,
        }
        with self._lock:
            listeners = [c for c in self._consumers if c.user_key == track.user_key]
        if listeners:
            for consumer in listeners:
                _put_nowait(consumer.queue, payload, loop=consumer.loop)
            return
        bucket = self._pending.setdefault(track.user_key, [])
        row = dict(payload)
        row["_enqueued_at"] = time.monotonic()
        bucket.append(row)
        del bucket[:-PENDING_LIMIT]

    def _flush_pending(self, user_key: str, queue: Any, loop: Any = None) -> None:
        bucket = self._pending.get(user_key)
        if not bucket:
            return
        cutoff = time.monotonic() - _PENDING_TTL_SECONDS
        fresh = [row for row in bucket if row.get("_enqueued_at", 0) >= cutoff]
        self._pending[user_key] = fresh
        for row in fresh:
            _put_nowait(queue, row, loop=loop)


def _load_client() -> Any:
    """Herdr CLI client for the local/SSH seat (test seam: monkeypatch this)."""
    from swarm.core.remote_teams import herdr_client_from_settings

    return herdr_client_from_settings()


def _put_nowait(queue: Any, payload: dict[str, Any], loop: Any = None) -> None:
    with contextlib.suppress(Exception):
        if loop is not None:
            loop.call_soon_threadsafe(queue.put_nowait, payload)
            return
        queue.put_nowait(payload)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_monitor: HerdrSessionMonitor | None = None
_monitor_lock = threading.Lock()


def get_monitor() -> HerdrSessionMonitor:
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = HerdrSessionMonitor()
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


def watch_session(**kwargs: Any) -> HerdrWatchTrack | None:
    return get_monitor().watch_session(**kwargs)


def note_swarm_send(**kwargs: Any) -> None:
    get_monitor().note_swarm_send(**kwargs)

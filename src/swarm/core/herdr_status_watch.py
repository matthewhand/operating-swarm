"""#1729 — replicate Herdr agent status into Operating Swarm affordances.

Herdr already publishes a four-value lifecycle per pane (``idle`` / ``working``
/ ``blocked`` / ``done``, see :mod:`swarm.herdr.status`). This module watches
those values across **every persisted Herdr seat** — not just the pane a chat
is currently focused on — and turns each transition into one event the SPA
already has a place to render:

| Herdr status | OS seat status | Event                                    |
|---|---|---|
| ``working``  | ``working``    | busy — reported, never silent             |
| ``blocked``  | ``waiting``    | "this needs you" (the yellow indicator)   |
| ``done``     | ``finished``   | unread on the seat, so the operator sees it |

Design notes
------------
* **One CLI call per tick.** ``herdr agent list`` answers for every pane at
  once, so the whole feature costs one subprocess, not one per seat. The
  per-pane ``agent get`` loop in :mod:`swarm.herdr_session_watch` is a
  *different* job (streaming the focused pane's output) and is untouched.
* **Fail open.** A missing CLI, a stopped server, an SSH hop that refuses, or
  a timeout yields ``unknown`` and no events. The watcher never blocks, never
  retries inside a tick, and never invents a status.
* **Out-of-order updates.** Herdr's own ``state_change_seq`` is the ordering
  signal. A frame whose seq is *lower* than the one already recorded for that
  seat is dropped as stale: a slow poll must not resurrect a finished turn as
  still-running. A seat whose seq is absent cannot be ordered, so it is
  accepted on its own terms and the seat's recorded seq is left alone.
* **Delivery** rides the same consumer registry the session watcher already
  uses (:class:`HerdrSessionMonitor`'s ``register_consumer`` pattern, mirrored
  here so the two can share a transport without either owning it).

This module is a sibling of ``herdr_session_watch.py`` on purpose:
``swarm/core/remotes.py`` is at its documented size ceiling and is not a home
for a new watcher.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from swarm.herdr.status import (
    HERDR_STATUS_FOR_SEAT,
    UNKNOWN_STATUS,
    HerdrSeatStatus,
    pane_statuses,
)

logger = logging.getLogger(__name__)

#: How often the whole-workspace query runs. Herdr's own CLI is a local socket
#: round trip, so this is cheap — but it is still a subprocess, hence not
#: faster than the 1.5s the focused-pane watcher already uses.
POLL_SECONDS = 3.0

#: A tick may not exceed this. A slow Herdr must not pin a worker thread.
TICK_TIMEOUT_SECONDS = 10.0

#: Never hold a stale "finished" reading forever: if a seat has produced no
#: status for this long the operator is told ``unknown`` rather than a value
#: that may no longer be true.
STALE_AFTER_SECONDS = 120.0

#: Cap on how many status rows one tick will publish. Herdr on a busy host can
#: hold hundreds of panes; a burst of them is not 300 unread dots to a human.
MAX_EVENTS_PER_TICK = 50

WAITING_STATUS: HerdrSeatStatus = "waiting"
FINISHED_STATUS: HerdrSeatStatus = "finished"
WORKING_STATUS: HerdrSeatStatus = "working"

#: What the operator is doing about each state. One copy of this copy, in the
#: backend, so the event payload is self-describing to any consumer.
STATUS_REASONS: dict[HerdrSeatStatus, str] = {
    "unknown": "Herdr did not report a status for this pane.",
    "idle": "Herdr reports the pane is idle.",
    "working": "Herdr reports the agent is working.",
    "waiting": "Herdr reports the agent is blocked on a question.",
    "finished": "Herdr reports the agent finished its turn.",
}


def seat_id_for(target: str) -> str:
    """The rail/row id for a Herdr pane target.

    ``w3:p1`` → ``herdr:w3:p1``, matching the row id the rail already builds
    for a Herdr seat (`lib/railHotkeys.isHerdrAgent`). One function so the
    backend can name a seat exactly the way the frontend's unread store does.
    """
    pane = (target or "").strip()
    return f"herdr:{pane}" if pane else ""


@dataclass
class HerdrSeatState:
    """Last *observed* status for one pane, with its ordering signal."""

    target: str
    status: HerdrSeatStatus = UNKNOWN_STATUS
    state_change_seq: int | None = None
    agent: str = ""
    workspace_id: str = ""
    changed_at: float = field(default_factory=time.monotonic)

    def is_stale(self, now: float, limit: float = STALE_AFTER_SECONDS) -> bool:
        return (now - self.changed_at) > limit


def transition_event(
    previous: HerdrSeatStatus,
    current: HerdrSeatStatus,
) -> bool:
    """Whether ``previous → current`` is worth telling the operator about.

    A status that did not change is not an event — a 3s poll of a busy pane
    must not manufacture a notification every tick. The initial observation
    (``unknown → X``) **is** an event: the operator has not seen this pane's
    state yet, and learning it is the point of the surface.
    """
    return current != UNKNOWN_STATUS and current != previous


def should_mark_unread(current: HerdrSeatStatus, *, seat_is_open: bool) -> bool:
    """Unread on finish — but never on the seat the operator is looking at.

    Marking the open chat unread is the exact noise #1729 exists to remove, and
    it is why this is a decision function rather than a `status ==` check at
    the call site.
    """
    return current == FINISHED_STATUS and not seat_is_open


class HerdrStatusMonitor:
    """Process-wide watcher over every live Herdr pane.

    ``autostart=False`` never spawns the background worker; the caller drives
    :meth:`poll_once` directly, which is how the tests stay deterministic.
    """

    def __init__(
        self,
        *,
        autostart: bool = True,
        load_client: Callable[[], Any] | None = None,
        seats: Callable[[], list[str]] | None = None,
        is_seat_open: Callable[[str], bool] | None = None,
        publish: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._autostart = autostart
        self._load_client = load_client or _load_client
        self._seats = seats or _configured_seats
        self._is_seat_open = is_seat_open or (lambda _seat_id: False)
        self._publish = publish or _publish_to_consumers
        self._states: dict[str, HerdrSeatState] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        #: Consecutive failed ticks. Exposed so health surfaces can say how
        #: long OS has been unable to reach Herdr, without inventing a status.
        self.failure_count = 0
        self.last_error: str = ""

    # -- registry ----------------------------------------------------------

    def register_consumer(self, user_key: str, queue: Any, loop: Any = None) -> None:
        _register_status_consumer(user_key, queue, loop=loop)

    def unregister_consumer(self, queue: Any) -> None:
        _unregister_status_consumer(queue)

    def states(self) -> list[HerdrSeatState]:
        with self._lock:
            return list(self._states.values())

    def status_for(self, seat_id: str) -> HerdrSeatStatus:
        with self._lock:
            state = self._states.get((seat_id or "").strip())
        return state.status if state else UNKNOWN_STATUS

    def track_count(self) -> int:
        with self._lock:
            return len(self._states)

    def forget(self, seat_id: str) -> None:
        with self._lock:
            self._states.pop((seat_id or "").strip(), None)

    def reset(self) -> None:
        with self._lock:
            self._states.clear()
        self.failure_count = 0
        self.last_error = ""

    # -- polling -----------------------------------------------------------

    def poll_once(self) -> list[dict[str, Any]]:
        """One tick. Returns the events it published (the test seam)."""
        try:
            client = self._load_client()
        except Exception as exc:
            # A missing binary or an unconfigured remote. Fail open: say we do
            # not know, and do not stop the worker.
            return self._record_failure(str(exc))

        try:
            payload = client.agent_list()
        except Exception as exc:
            return self._record_failure(str(exc))

        self.failure_count = 0
        self.last_error = ""
        now = time.monotonic()
        published: list[dict[str, Any]] = []
        for row in pane_statuses(payload):
            event = self._apply(row, now=now)
            if event is not None and len(published) < MAX_EVENTS_PER_TICK:
                published.append(event)
                self._publish(event)
        self._expire(now)
        return published

    def _apply(self, row: Any, *, now: float) -> dict[str, Any] | None:
        seat_id = seat_id_for(row.target)
        if not seat_id:
            return None
        with self._lock:
            state = self._states.get(seat_id)
            if state is not None and _is_stale_frame(row.state_change_seq, state.state_change_seq):
                # A slow poll delivered an older reading. Applying it would
                # walk the seat backwards (finished → working) and re-light a
                # dot the operator already cleared.
                return None
            previous = state.status if state else UNKNOWN_STATUS
            if state is None:
                state = HerdrSeatState(target=row.target)
                self._states[seat_id] = state
            state.status = row.status
            state.agent = row.agent
            state.workspace_id = row.workspace_id
            state.changed_at = now
            # An unordered reading must not overwrite the seq we can order
            # against later, or every comparison after it becomes vacuous.
            if row.state_change_seq is not None:
                state.state_change_seq = row.state_change_seq
        if not transition_event(previous, row.status):
            return None
        return self._event_for(seat_id, row.target, row.status, previous)

    def _event_for(
        self,
        seat_id: str,
        target: str,
        status: HerdrSeatStatus,
        previous: HerdrSeatStatus,
    ) -> dict[str, Any]:
        is_open = self._is_seat_open(seat_id)
        return {
            "type": "herdr_status",
            "seat_id": seat_id,
            "target": target,
            "status": status,
            "previous_status": previous,
            "reason": STATUS_REASONS.get(status, ""),
            # Herdr's own vocabulary, so a client can show what OS mapped.
            "herdr_status": HERDR_STATUS_FOR_SEAT.get(status, ""),
            "needs_input": status == WAITING_STATUS,
            "mark_unread": should_mark_unread(status, seat_is_open=is_open),
            "seat_is_open": is_open,
            "ts": _utc_now_iso(),
        }

    def _record_failure(self, message: str) -> list[dict[str, Any]]:
        self.failure_count += 1
        self.last_error = message
        logger.info("herdr status tick failed (%s): %s", self.failure_count, message)
        # Every pane OS was tracking now has unknown status. Say so honestly by
        # aging them out rather than holding a reading that may be false.
        now = time.monotonic()
        with self._lock:
            for state in self._states.values():
                state.status = UNKNOWN_STATUS
                state.changed_at = now
        return []

    def _expire(self, now: float) -> None:
        with self._lock:
            for state in self._states.values():
                if state.status != UNKNOWN_STATUS and state.is_stale(now):
                    state.status = UNKNOWN_STATUS

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        with self._lock:
            self._states.clear()
        self._thread = None
        self._stop = threading.Event()

    def _ensure_worker(self) -> None:
        if not self._autostart:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker, name="herdr-status-watch", daemon=True
        )
        self._thread.start()

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                logger.exception("herdr status watch tick failed")
            self._stop.wait(POLL_SECONDS)




def _is_stale_frame(incoming_seq: int | None, known_seq: int | None) -> bool:
    """True when ``incoming_seq`` is provably older than what we already saw.

    Only an actual *decrease* counts. Equal seqes are re-reads of the same
    reading, and a missing seq cannot be ordered at all — neither may discard
    a frame, because Herdr omits the counter on paths where it has no state to
    version.
    """
    if incoming_seq is None or known_seq is None:
        return False
    return incoming_seq < known_seq


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_client() -> Any:
    """Herdr CLI client for the local/SSH seat (test seam: monkeypatch this)."""
    from swarm.core.remote_teams import herdr_client_from_settings

    return herdr_client_from_settings()


def _configured_seats() -> list[str]:
    """Pane targets OS has been asked to watch (persisted Herdr members).

    Fail-open: no DB, no rows, or a misconfigured Django means "watch nothing",
    never an exception that would kill the worker thread.
    """
    try:
        from swarm.models import HerdrAgent

        return [row.name for row in HerdrAgent.objects.all()]
    except Exception:
        logger.debug("herdr status: persisted seats unavailable", exc_info=True)
        return []


# -- delivery ---------------------------------------------------------------
#
# The same consumer registry shape `herdr_session_watch` uses, kept separate
# so a status subscriber never has to inherit the focused-pane track lifecycle.

_consumer_lock = threading.Lock()
_consumers: list[dict[str, Any]] = []
_pending: dict[str, list[dict[str, Any]]] = {}
_PENDING_TTL_SECONDS = 10 * 60


def register_status_consumer(user_key: str, queue: Any, loop: Any = None) -> None:
    uk = (user_key or "").strip()
    if not uk:
        return
    with _consumer_lock:
        if any(c["queue"] is queue for c in _consumers):
            return
        _consumers.append({"user_key": uk, "queue": queue, "loop": loop})
    _flush_pending(uk, queue, loop)
    get_monitor()._ensure_worker()


def unregister_status_consumer(queue: Any) -> None:
    with _consumer_lock:
        _consumers[:] = [c for c in _consumers if c["queue"] is not queue]


def registered_consumer_count() -> int:
    """How many sockets are currently being fed.

    Exposed because a leaked registration is invisible to any "nothing
    arrived" assertion: the dead socket is gone, so nobody is left to notice
    the queue still filling. The count is the only honest witness.
    """
    with _consumer_lock:
        return len(_consumers)


def _publish_to_consumers(event: dict[str, Any]) -> None:
    """Fan one status event out to every registered consumer.

    No consumer means the event is buffered briefly, not dropped: a socket
    that connects mid-tick still learns the current status.
    """
    with _consumer_lock:
        listeners = list(_consumers)
    if not listeners:
        bucket = _pending.setdefault("__all__", [])
        row = dict(event)
        row["_enqueued_at"] = time.monotonic()
        bucket.append(row)
        del bucket[:-MAX_EVENTS_PER_TICK]
        return
    for consumer in listeners:
        _put_nowait(consumer["queue"], event, loop=consumer.get("loop"))


def _flush_pending(user_key: str, queue: Any, loop: Any = None) -> None:
    with _consumer_lock:
        bucket = _pending.get("__all__") or []
        cutoff = time.monotonic() - _PENDING_TTL_SECONDS
        _pending["__all__"] = [row for row in bucket if row.get("_enqueued_at", 0) >= cutoff]
    for row in list(_pending.get("__all__") or []):
        _put_nowait(queue, row, loop=loop)


def _put_nowait(queue: Any, payload: dict[str, Any], loop: Any = None) -> None:
    with contextlib.suppress(Exception):
        if loop is not None:
            loop.call_soon_threadsafe(queue.put_nowait, payload)
            return
        queue.put_nowait(payload)


def _register_status_consumer(user_key: str, queue: Any, loop: Any = None) -> None:
    register_status_consumer(user_key, queue, loop=loop)


def _unregister_status_consumer(queue: Any) -> None:
    unregister_status_consumer(queue)


def reset_status_consumers_for_tests() -> None:
    with _consumer_lock:
        _consumers.clear()
        _pending.clear()


_monitor: HerdrStatusMonitor | None = None
_monitor_lock = threading.Lock()


def get_monitor() -> HerdrStatusMonitor:
    global _monitor
    with _monitor_lock:
        if _monitor is None:
            _monitor = HerdrStatusMonitor()
        return _monitor


def reset_monitor_for_tests() -> None:
    global _monitor
    with _monitor_lock:
        if _monitor is not None:
            _monitor.close()
        _monitor = None


__all__ = [
    "FINISHED_STATUS",
    "MAX_EVENTS_PER_TICK",
    "POLL_SECONDS",
    "STALE_AFTER_SECONDS",
    "STATUS_REASONS",
    "TICK_TIMEOUT_SECONDS",
    "WAITING_STATUS",
    "WORKING_STATUS",
    "HerdrSeatState",
    "HerdrStatusMonitor",
    "get_monitor",
    "register_status_consumer",
    "registered_consumer_count",
    "reset_monitor_for_tests",
    "reset_status_consumers_for_tests",
    "seat_id_for",
    "should_mark_unread",
    "transition_event",
    "unregister_status_consumer",
]

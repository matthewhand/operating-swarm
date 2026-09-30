"""#1729 — Herdr status transitions become OS affordances.

The watcher is the half of the feature that decides *when* something is worth
telling the operator. These tests pin the decisions, not the plumbing: a status
that did not change must not manufacture a notification, a slow poll must not
walk a seat backwards, and a Herdr that is down must produce `unknown` and
silence rather than a fabricated "nothing is happening".

The CLI is always mocked. Naming: NEW file for #1729; it does not edit
`tests/core/test_herdr_session_watch.py`.
"""

from __future__ import annotations

import queue
import time

import pytest

from swarm.core import herdr_status_watch as watch
from swarm.herdr.client import HerdrCLIError
from swarm.herdr.status import UNKNOWN_STATUS


def _agent(pane: str, status: str, seq: int | None = None, **extra) -> dict:
    row = {"pane_id": pane, "agent": "grok", "agent_status": status, **extra}
    if seq is not None:
        row["state_change_seq"] = seq
    return row


def _client(script: list, error: Exception | None = None):
    """A client whose ``agent_list`` walks ``script`` in order, one per tick.

    The cursor lives on the instance, and :func:`_monitor` reuses one instance
    across ticks — a fresh client per tick would silently restart the script
    and make every multi-tick test assert against the wrong reading.
    """
    cursor = {"i": 0}

    class _Client:
        def agent_list(self):
            if error is not None:
                raise error
            i = cursor["i"]
            cursor["i"] += 1
            nxt = script[i] if i < len(script) else []
            return _as_cli_payload(nxt)

    return _Client()


def _as_cli_payload(entry) -> dict:
    """Normalise one script entry into a ``herdr agent list`` payload.

    A script entry is one tick's reading and may be written as a list of agent
    records, a single record, or a full CLI envelope. Only the last is passed
    through; the others are wrapped, so a bare record can never be mistaken
    for an envelope (its keys would be read as a status field).
    """
    if isinstance(entry, dict):
        if any(k in entry for k in ("agents", "items", "result", "snapshot")):
            return entry
        return {"agents": [entry]}
    return {"agents": list(entry or [])}


def _monitor(
    *payloads,
    error: Exception | None = None,
    seats=lambda: [],
    is_open=lambda _s: False,
    use_module_publish: bool = False,
):
    """A monitor with a scripted CLI and a captured event list.

    ``use_module_publish`` leaves the module's own fan-out in place, which is
    what the delivery tests need; the rest capture locally so a test never
    depends on the process-global consumer registry.
    """
    events: list[dict] = []
    client = _client(list(payloads), error=error)
    monitor = watch.HerdrStatusMonitor(
        autostart=False,
        load_client=lambda: client,
        seats=seats,
        is_seat_open=is_open,
        publish=None if use_module_publish else events.append,
    )
    return monitor, events


def _isolate_module_monitor(monkeypatch) -> None:
    """Keep `register_status_consumer` from spawning a live poller.

    Registration arms the process-global watcher, whose client is the *real*
    ``herdr`` binary. A test that registers a consumer must not inherit a
    background thread talking to a live TUI on this host.
    """
    stub = watch.HerdrStatusMonitor(autostart=False)
    monkeypatch.setattr(watch, "get_monitor", lambda: stub)


# --------------------------------------------------------------------------
# Seat identity
# --------------------------------------------------------------------------


def test_seat_id_is_the_rail_row_shape():
    """The backend must name a seat exactly the way the frontend's unread
    store and the rail's `data-agent-id` do, or the dot lights on nothing."""
    assert watch.seat_id_for("w3:p1") == "herdr:w3:p1"
    assert watch.seat_id_for("  w3:p1  ") == "herdr:w3:p1"
    assert watch.seat_id_for("") == ""
    assert watch.seat_id_for("   ") == ""


# --------------------------------------------------------------------------
# Transition rules
# --------------------------------------------------------------------------


def test_blocked_becomes_waiting_and_asks_for_attention():
    monitor, events = _monitor([_agent("w3:p1", "blocked", 1)])
    published = monitor.poll_once()
    assert len(published) == 1
    event = published[0]
    assert event["seat_id"] == "herdr:w3:p1"
    assert event["status"] == "waiting"
    assert event["herdr_status"] == "blocked"
    assert event["needs_input"] is True
    assert event["mark_unread"] is False
    assert "blocked on a question" in event["reason"]
    assert events == published


def test_done_becomes_finished_and_marks_unread_when_the_seat_is_closed():
    monitor, _ = _monitor([_agent("w3:p1", "done", 2)])
    event = monitor.poll_once()[0]
    assert event["status"] == "finished"
    assert event["herdr_status"] == "done"
    assert event["mark_unread"] is True
    assert event["seat_is_open"] is False


def test_done_does_not_mark_unread_on_the_seat_the_operator_is_reading():
    """Marking the open chat unread is the exact noise this issue removes."""
    monitor, _ = _monitor([_agent("w3:p1", "done", 2)], is_open=lambda s: s == "herdr:w3:p1")
    event = monitor.poll_once()[0]
    assert event["status"] == "finished"
    assert event["seat_is_open"] is True
    assert event["mark_unread"] is False


def test_working_is_reported_rather_than_left_silent():
    """#1729 §4: in-progress must map to a busy state, not silence."""
    monitor, _ = _monitor([_agent("w3:p1", "working", 3)])
    event = monitor.poll_once()[0]
    assert event["status"] == "working"
    assert event["needs_input"] is False
    assert event["mark_unread"] is False


def test_an_unchanged_status_is_not_an_event():
    """A 3s poll of a busy pane must not manufacture a notification per tick."""
    monitor, _ = _monitor([_agent("w3:p1", "working", 3), _agent("w3:p1", "working", 4)])
    first = monitor.poll_once()
    second = monitor.poll_once()
    assert len(first) == 1
    assert second == []


def test_the_first_sighting_of_a_pane_is_an_event():
    """The operator has not seen this pane's state yet; learning it is the
    point of the surface."""
    monitor, _ = _monitor([_agent("w3:p9", "idle", 99)])
    published = monitor.poll_once()
    assert len(published) == 1
    assert published[0]["status"] == "idle"
    assert published[0]["mark_unread"] is False


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ("unknown", "working", True),
        ("working", "working", False),
        ("working", "waiting", True),
        ("waiting", "finished", True),
        ("finished", "unknown", False),
        ("unknown", "unknown", False),
    ],
)
def test_transition_event_truth_table(previous, current, expected):
    assert watch.transition_event(previous, current) is expected


@pytest.mark.parametrize(
    ("status", "seat_is_open", "expected"),
    [
        ("finished", False, True),
        ("finished", True, False),
        ("waiting", False, False),
        ("working", False, False),
        ("unknown", False, False),
    ],
)
def test_should_mark_unread_truth_table(status, seat_is_open, expected):
    assert watch.should_mark_unread(status, seat_is_open=seat_is_open) is expected


# --------------------------------------------------------------------------
# Out-of-order updates
# --------------------------------------------------------------------------


def test_a_stale_frame_cannot_walk_a_seat_backwards():
    """seq 9 (finished) then seq 8 (working) is a slow poll, not a new fact.
    Applying it would re-light a dot the operator just cleared."""
    # One row per tick. Two rows in ONE payload would be deduped to the first,
    # so the second tick would never carry the stale reading at all.
    monitor, _ = _monitor([_agent("w3:p1", "done", 9)], [_agent("w3:p1", "working", 8)])
    first = monitor.poll_once()
    second = monitor.poll_once()
    assert first[0]["status"] == "finished"
    assert second == []
    assert monitor.status_for("herdr:w3:p1") == "finished"


def test_a_repeat_of_the_same_seq_is_accepted_but_not_re_announced():
    monitor, _ = _monitor([_agent("w3:p1", "done", 9), _agent("w3:p1", "done", 9)])
    assert len(monitor.poll_once()) == 1
    assert monitor.poll_once() == []
    assert monitor.status_for("herdr:w3:p1") == "finished"


def test_a_frame_with_no_seq_cannot_be_discarded_as_stale():
    """Herdr omits the counter on paths with no state to version. An absent
    ordering signal must not silently throw the reading away."""
    # One row per tick: same pane, so the second reading is the comparison.
    monitor, _ = _monitor([_agent("w3:p1", "done", 9)], [_agent("w3:p1", "working")])
    monitor.poll_once()
    published = monitor.poll_once()
    assert len(published) == 1
    assert published[0]["status"] == "working"
    # The unorderable frame must not erase the seq we can still order against.
    assert monitor.states()[0].state_change_seq == 9


@pytest.mark.parametrize(
    ("incoming", "known", "expected"),
    [
        (8, 9, True),
        (9, 9, False),
        (10, 9, False),
        (None, 9, False),
        (8, None, False),
    ],
)
def test_is_stale_frame_truth_table(incoming, known, expected):
    assert watch._is_stale_frame(incoming, known) is expected


# --------------------------------------------------------------------------
# Fail open
# --------------------------------------------------------------------------


def test_a_missing_cli_yields_no_events_and_says_it_failed():
    monitor, _ = _monitor(error=HerdrCLIError("herdr CLI not found on PATH"))
    assert monitor.poll_once() == []
    assert monitor.failure_count == 1
    assert "not found on PATH" in monitor.last_error


def test_a_down_herdr_fails_every_tracked_seat_to_unknown():
    """A seat OS was tracking must stop claiming to be working when OS can no
    longer ask. Silence would read as "busy" and keep a stale indicator lit."""
    healthy = _client([_agent("w3:p1", "working", 1)])
    down = _client([], error=HerdrCLIError("server is not running"))
    client = {"current": healthy}
    monitor = watch.HerdrStatusMonitor(
        autostart=False,
        load_client=lambda: client["current"],
        seats=lambda: [],
        is_seat_open=lambda _s: False,
        publish=lambda _e: None,
    )
    monitor.poll_once()
    assert monitor.status_for("herdr:w3:p1") == "working"
    client["current"] = down
    assert monitor.poll_once() == []
    assert monitor.status_for("herdr:w3:p1") == UNKNOWN_STATUS
    assert monitor.failure_count == 1


def test_recovery_resets_the_failure_counter():
    down = _client([], error=HerdrCLIError("down"))
    healthy = _client([_agent("w3:p1", "idle", 5)])
    client = {"current": down}
    monitor = watch.HerdrStatusMonitor(
        autostart=False,
        load_client=lambda: client["current"],
        seats=lambda: [],
        is_seat_open=lambda _s: False,
        publish=lambda _e: None,
    )
    assert monitor.poll_once() == []
    assert monitor.failure_count == 1
    # The Herdr comes back on the next tick; the failure state must not stick.
    client["current"] = healthy
    assert monitor.poll_once() != []
    assert monitor.failure_count == 0
    assert monitor.last_error == ""


def test_a_worker_that_cannot_even_build_a_client_does_not_raise():
    monitor = watch.HerdrStatusMonitor(
        autostart=False,
        load_client=lambda: (_ for _ in ()).throw(RuntimeError("herdr is not on PATH")),
    )
    assert monitor.poll_once() == []
    assert "not on PATH" in monitor.last_error


def test_an_unrecognised_status_is_never_published_as_a_positive_state():
    monitor, _ = _monitor([_agent("w3:p1", "quantum-entangled", 1)])
    assert monitor.poll_once() == []
    assert monitor.status_for("herdr:w3:p1") == UNKNOWN_STATUS


def test_a_stale_reading_expires_to_unknown_rather_than_holding_forever():
    """A status OS can no longer vouch for must not keep a dot lit."""
    # "blocked" is the Herdr value; the OS status is "waiting". A test that
    # passed the OS spelling would be asserting on `unknown` the whole way.
    monitor, _ = _monitor([_agent("w3:p1", "blocked", 1)])
    monitor.poll_once()
    assert monitor.status_for("herdr:w3:p1") == "waiting"
    # Age the reading past STALE_AFTER_SECONDS by hand — a real tick would
    # take two minutes, and the point under test is the rule, not the clock.
    for state in monitor.states():
        state.changed_at = time.monotonic() - watch.STALE_AFTER_SECONDS - 1
    monitor._expire(time.monotonic())
    assert monitor.status_for("herdr:w3:p1") == UNKNOWN_STATUS


# --------------------------------------------------------------------------
# Bounded fan-out
# --------------------------------------------------------------------------


def test_a_pane_storm_cannot_unbound_one_tick():
    """Herdr on a busy host can hold hundreds of panes; a burst is not 300
    unread dots at a human."""
    rows = [_agent(f"w3:p{i}", "done", i) for i in range(watch.MAX_EVENTS_PER_TICK + 25)]
    monitor, _ = _monitor(rows)
    assert len(monitor.poll_once()) == watch.MAX_EVENTS_PER_TICK


def test_a_pane_without_an_id_is_skipped_not_invented():
    monitor, _ = _monitor([{"agents": [{"agent_status": "blocked"}]}])
    assert monitor.poll_once() == []
    assert monitor.track_count() == 0


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------


def test_events_reach_every_registered_consumer(monkeypatch):
    watch.reset_status_consumers_for_tests()
    try:
        _isolate_module_monitor(monkeypatch)
        first: queue.Queue = queue.Queue()
        second: queue.Queue = queue.Queue()
        watch.register_status_consumer("alice", first)
        watch.register_status_consumer("bob", second)
        monitor, _ = _monitor([_agent("w3:p1", "blocked", 1)], use_module_publish=True)
        monitor.poll_once()
        for sink in (first, second):
            payload = sink.get_nowait()
            assert payload["type"] == "herdr_status"
            assert payload["seat_id"] == "herdr:w3:p1"
    finally:
        watch.reset_status_consumers_for_tests()
        watch.reset_monitor_for_tests()


def test_an_event_with_no_consumer_is_buffered_not_dropped(monkeypatch):
    """A socket that connects mid-tick must still learn the current status."""
    watch.reset_status_consumers_for_tests()
    try:
        _isolate_module_monitor(monkeypatch)
        monitor, _ = _monitor([_agent("w3:p1", "blocked", 1)], use_module_publish=True)
        monitor.poll_once()
        late: queue.Queue = queue.Queue()
        watch.register_status_consumer("alice", late)
        assert late.get_nowait()["status"] == "waiting"
    finally:
        watch.reset_status_consumers_for_tests()
        watch.reset_monitor_for_tests()


def test_unregistering_stops_delivery(monkeypatch):
    watch.reset_status_consumers_for_tests()
    try:
        _isolate_module_monitor(monkeypatch)
        sink: queue.Queue = queue.Queue()
        watch.register_status_consumer("alice", sink)
        watch.unregister_status_consumer(sink)
        monitor, _ = _monitor([_agent("w3:p1", "blocked", 1)], use_module_publish=True)
        monitor.poll_once()
        assert sink.empty()
    finally:
        watch.reset_status_consumers_for_tests()
        watch.reset_monitor_for_tests()


def test_a_consumer_with_no_key_is_not_registered(monkeypatch):
    watch.reset_status_consumers_for_tests()
    try:
        _isolate_module_monitor(monkeypatch)
        sink: queue.Queue = queue.Queue()
        watch.register_status_consumer("  ", sink)
        monitor, _ = _monitor([_agent("w3:p1", "blocked", 1)], use_module_publish=True)
        monitor.poll_once()
        assert sink.empty()
    finally:
        watch.reset_status_consumers_for_tests()
        watch.reset_monitor_for_tests()


# --------------------------------------------------------------------------
# Non-regression guards — before and after on purpose.
# --------------------------------------------------------------------------


def test_guard_status_reasons_cover_every_os_state():
    """Deliberate non-regression guard: an unmapped state would ship a blank
    reason field. Passes before and after the change."""
    from swarm.herdr.status import SEAT_STATUSES

    assert set(watch.STATUS_REASONS) == set(SEAT_STATUSES)
    assert all(watch.STATUS_REASONS[state] for state in SEAT_STATUSES)


def test_guard_the_focused_pane_watcher_is_untouched():
    """Deliberate non-regression guard: #1729 adds a *whole-workspace*
    watcher; it must not have refactored `herdr_session_watch` into it. The
    focused-pane streaming path keeps its own module and its own states."""
    from swarm.core import herdr_session_watch

    assert herdr_session_watch.WORKING_STATES == frozenset(
        {"working", "running", "busy"}
    )
    assert "done" in herdr_session_watch.DONE_STATES
    assert not hasattr(herdr_session_watch, "HerdrStatusMonitor")


def test_guard_status_mapping_comes_from_the_shared_table():
    """Deliberate non-regression guard: the watcher's payload echo must come
    from `swarm.herdr.status`, not a private re-declaration of the map."""
    from swarm.herdr.status import HERDR_STATUS_FOR_SEAT

    for seat, raw in HERDR_STATUS_FOR_SEAT.items():
        assert watch.STATUS_REASONS[seat]
        assert raw in ("", "idle", "working", "blocked", "done")

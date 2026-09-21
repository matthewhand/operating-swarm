"""#794 — Herdr session watch: lifecycle, delta streaming, teardown."""

from __future__ import annotations

import queue
from typing import Any

import pytest

from swarm.core import herdr_session_watch as watch_mod
from swarm.core.herdr_session_watch import (
    HerdrSessionMonitor,
    extract_prompt_hint,
    pane_delta,
)


@pytest.fixture(autouse=True)
def _fresh_monitor():
    watch_mod.reset_monitor_for_tests()
    yield
    watch_mod.reset_monitor_for_tests()


class _FakeClient:
    """Scripted herdr agent_get/agent_read responses per poll."""

    def __init__(self, script):
        self.script = list(script)  # list of (state, seq, snapshot)
        self.calls = 0

    def agent_get(self, target):
        state, seq, _snap = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return {"state": state, "state_change_seq": seq, "pane": target}

    def read_recent(self, target):
        _state, _seq, snap = self.script[min(self.calls - 1, len(self.script) - 1)]
        return snap


@pytest.fixture
def fake_client(monkeypatch):
    holder = {}

    def _install(script):
        client = _FakeClient(script)
        holder["client"] = client
        monkeypatch.setattr(
            watch_mod, "_load_client", lambda: client, raising=True
        )
        monkeypatch.setattr(
            "swarm.core.remotes.read_herdr_recent_raw",
            lambda target, config=None: client.read_recent(target),
            raising=True,
        )
        return client

    yield _install


def _monitor_with_track(target="w3:p5") -> HerdrSessionMonitor:
    monitor = HerdrSessionMonitor(autostart=False)
    monitor.watch_session(
        user_key="u1",
        agent_id="remote_harness",
        conversation_id="c1",
        target=target,
    )
    return monitor


def test_pane_delta_appends_and_replaces():
    assert pane_delta("", "hello") == "hello"
    assert pane_delta("hel", "hello") == "lo"
    # Pane re-render (not a prefix) → full snapshot, honest replace.
    assert pane_delta("old content", "fresh") == "fresh"


def test_extract_prompt_hint_takes_last_clean_line():
    snapshot = "user note here\nThinking...\n"
    assert extract_prompt_hint(snapshot) == "Thinking..."
    assert extract_prompt_hint("") == ""
    assert extract_prompt_hint("x" * 600) == ""


def test_watch_lifecycle_register_and_unwatch(fake_client):
    fake_client([("idle", 1, "before")])
    monitor = _monitor_with_track()
    assert monitor.track_count() == 1
    monitor.unwatch_conversation("u1", "c1")
    assert monitor.track_count() == 0


def test_working_state_streams_deltas_then_finalizes(fake_client):
    fake_client(
        [
            ("idle", 10, "base"),
            ("working", 11, "base\npartial answer"),
            ("working", 11, "base\npartial answer\nmore"),
            ("done", 12, "base\npartial answer\nmore\nFINAL PROSE"),
        ]
    )
    monitor = _monitor_with_track()
    q: queue.Queue = queue.Queue()
    monitor.register_consumer("u1", q)

    monitor.poll_once()  # idle baseline: no emission
    assert q.empty()

    # Swarm initiates the turn — the send path stamps the track (#794),
    # so the working transition must NOT mirror an external prompt.
    monitor.note_swarm_send(user_key="u1", conversation_id="c1", target="w3:p5")

    monitor.poll_once()  # working: first delta
    first = q.get_nowait()
    assert first["type"] == "herdr_stream"
    assert "partial answer" in first["text"]
    assert first["final"] is False

    monitor.poll_once()  # more output: next delta only
    second = q.get_nowait()
    assert second["text"].strip() == "more"

    monitor.poll_once()  # done: final chunk, sanitized
    final = q.get_nowait()
    assert final["final"] is True
    assert "FINAL PROSE" in final["text"]
    # No further frames after completion.
    assert q.empty()


def test_external_turn_mirrors_user_prompt(fake_client):
    """#794: working with no Swarm prompt → mirrored user turn first."""
    fake_client(
        [
            ("idle", 5, "typed in tmux: run the tests"),
            ("working", 6, "typed in tmux: run the tests\nrunning..."),
        ]
    )
    monitor = _monitor_with_track()
    q: queue.Queue = queue.Queue()
    monitor.register_consumer("u1", q)

    monitor.poll_once()  # baseline
    monitor.poll_once()  # external turn starts

    frames = []
    while not q.empty():
        frames.append(q.get_nowait())
    kinds = [f["type"] for f in frames]
    assert "herdr_external_turn" in kinds
    assert frames[0]["type"] == "herdr_external_turn"
    assert "run the tests" in frames[0]["text"]


def test_swarm_send_suppresses_mirror_within_window(fake_client, monkeypatch):
    """#794: a transition right after note_swarm_send is ours — no mirror."""
    fake_client(
        [
            ("idle", 5, "base"),
            ("working", 6, "base\noutput"),
        ]
    )
    monitor = _monitor_with_track()
    q: queue.Queue = queue.Queue()
    monitor.register_consumer("u1", q)
    monitor.poll_once()
    monitor.note_swarm_send(user_key="u1", conversation_id="c1", target="w3:p5")
    monitor.poll_once()
    kinds = []
    while not q.empty():
        kinds.append(q.get_nowait()["type"])
    assert "herdr_external_turn" not in kinds


def test_swarm_send_window_expiry_mirrors_again(fake_client, monkeypatch):
    """#794: a send older than SWARM_SEND_WINDOW no longer suppresses."""
    import swarm.core.herdr_session_watch as wm

    monkeypatch.setattr(wm, "SWARM_SEND_WINDOW", 0.0, raising=True)
    fake_client(
        [
            ("idle", 5, "typed: hi"),
            ("working", 6, "typed: hi\nreply"),
        ]
    )
    monitor = _monitor_with_track()
    q: queue.Queue = queue.Queue()
    monitor.register_consumer("u1", q)
    monitor.poll_once()
    monitor.note_swarm_send(user_key="u1", conversation_id="c1", target="w3:p5")
    monitor.poll_once()  # window already expired → external
    kinds = []
    while not q.empty():
        kinds.append(q.get_nowait()["type"])
    assert "herdr_external_turn" in kinds


def test_quiet_track_is_pruned(fake_client, monkeypatch):
    fake_client([("idle", 1, "")])
    monitor = _monitor_with_track()
    assert monitor.track_count() == 1
    monkeypatch.setattr(watch_mod, "QUIET_IDLE_SECONDS", 0.0)
    monitor.prune_idle()
    assert monitor.track_count() == 0


def test_pending_frames_flush_to_late_consumer(fake_client):
    fake_client([("idle", 1, "")])
    monitor = _monitor_with_track()  # autostart=False: no worker races the script
    monitor._publish(
        monitor.tracks()[0],
        {"type": "herdr_stream", "text": "late", "final": True, "status": "done"},
    )
    q: queue.Queue = queue.Queue()
    monitor.register_consumer("u1", q)
    assert q.get_nowait()["text"] == "late"


def test_module_level_helpers_delegate_to_singleton(monkeypatch):
    q: queue.Queue = queue.Queue()
    # Keep the singleton offline: no worker, no real CLI invocations.
    monkeypatch.setattr(watch_mod.HerdrSessionMonitor, "_ensure_worker", lambda self: None)
    watch_mod.register_consumer("uX", q)
    try:
        assert watch_mod.get_monitor().track_count() >= 0
        watch_mod.unregister_consumer(q)
    finally:
        watch_mod.reset_monitor_for_tests()


def test_consumer_module_wires_herdr_watch():
    """The consumer module references the watch module (wired surface)."""
    import inspect

    from swarm import consumers

    src = inspect.getsource(consumers)
    assert "_maybe_start_herdr_session_watch" in src
    assert "herdr_session_watch" in src
    assert "_drain_herdr_frames" in src


def test_sanitize_used_for_final_text(fake_client, monkeypatch):
    """Final frames pass through #790/#850 chrome stripping."""
    fake_client(
        [
            ("working", 3, "answer"),
            (
                "done",
                4,
                "answer\n┃ Build GLM ─────── 35.3K (4%) ctrl+p commands\n",
            ),
        ]
    )
    monitor = _monitor_with_track()
    q: queue.Queue = queue.Queue()
    monitor.register_consumer("u1", q)
    monitor.poll_once()
    monitor.poll_once()
    frames = []
    while not q.empty():
        frames.append(q.get_nowait())
    final = [f for f in frames if f.get("final")]
    assert final and "ctrl+p" not in final[-1]["text"]
    assert "┃" not in final[-1]["text"]


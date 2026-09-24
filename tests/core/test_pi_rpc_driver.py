"""#1081 Phase 1 — Pi RPC driver contract tests.

Hermetic: the "Pi subprocess" is a fake Python script that speaks the
documented JSONL protocol (accept → stream text_delta → agent_end →
agent_settled), so the suite runs on hosts without Node/Pi. No test
touches the network or requires the real CLI.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from swarm.core import pi_rpc_driver
from swarm.core.pi_rpc_driver import (
    PiRpcError,
    PiRpcProcessError,
    PiSession,
    chunk_events_from_records,
    default_pi_command,
)

FAKE_PI = """\
import json, sys, time

# The driver appends "--mode rpc --no-session"; a real CLI tolerates flags,
# so this fake never parses argv.

for line in sys.stdin.buffer:
    line = line.strip(b"\\r\\n")
    if not line:
        continue
    cmd = json.loads(line)
    rid = cmd.get("id")
    ctype = cmd.get("type")
    if ctype == "prompt":
        sys.stdout.write(json.dumps({"id": rid, "type": "response", "command": "prompt", "success": True}) + "\\n")
        sys.stdout.flush()
        for delta in ("Hello", " ", "from", " Pi"):
            sys.stdout.write(json.dumps({
                "type": "message_update",
                "assistantMessageEvent": {"type": "text_delta", "delta": delta},
            }) + "\\n")
        sys.stdout.flush()
        sys.stdout.write(json.dumps({"type": "agent_end"}) + "\\n")
        sys.stdout.write(json.dumps({"type": "agent_settled"}) + "\\n")
        sys.stdout.flush()
    elif ctype == "abort":
        sys.stdout.write(json.dumps({"id": rid, "type": "response", "command": "abort", "success": True}) + "\\n")
        sys.stdout.flush()
    elif ctype == "fail":
        sys.stdout.write(json.dumps({"id": rid, "type": "response", "command": "fail", "success": False, "error": "nope"}) + "\\n")
        sys.stdout.flush()
    elif ctype == "slow":
        time.sleep(30)
"""


def write_fake_pi(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "fake_pi.py"
    script.write_text(body)
    return [sys.executable, str(script)]


def records_of_session(events: list[dict]) -> list[dict]:
    return list(events)


class TestDefaultPiCommand:
    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv("SWARM_PI_BIN", "/opt/pi/bin/pi --mode rpc")
        assert default_pi_command() == ["/opt/pi/bin/pi", "--mode", "rpc"]

    def test_unset_and_missing_binary_resolves_empty(self, monkeypatch):
        monkeypatch.delenv("SWARM_PI_BIN", raising=False)
        monkeypatch.setattr(pi_rpc_driver.shutil, "which", lambda _: None)
        assert default_pi_command() == []

    def test_found_on_path(self, monkeypatch):
        monkeypatch.delenv("SWARM_PI_BIN", raising=False)
        monkeypatch.setattr(pi_rpc_driver.shutil, "which", lambda name: f"/usr/bin/{name}")
        assert default_pi_command() == ["/usr/bin/pi"]


class TestPiSession:
    def test_missing_command_raises_friendly_error(self):
        with pytest.raises(PiRpcProcessError, match="Pi CLI not found"):
            PiSession(command=[])

    def test_prompt_streams_text_and_settles(self, tmp_path):
        events: list[dict] = []
        session = PiSession(command=write_fake_pi(tmp_path, FAKE_PI), on_event=events.append)
        try:
            session.prompt("hi")
            # prompt() returns on accept; the fake streams the whole turn
            # immediately. Wait for the settle event so the assertion sees
            # the full record set regardless of reader-thread timing.
            deadline = time.monotonic() + 10
            while not any(e.get("type") == "agent_settled" for e in events):
                assert time.monotonic() < deadline, "fake pi never settled"
                time.sleep(0.05)
            chunks = list(chunk_events_from_records(records_of_session(events)))
            assert [c["type"] for c in chunks] == ["text", "text", "text", "text", "end"]
            text = "".join(c["text"] for c in chunks if c["type"] == "text")
            assert text == "Hello from Pi"
        finally:
            session.close()

    def test_close_is_idempotent_and_reaps_child(self, tmp_path):
        session = PiSession(command=write_fake_pi(tmp_path, FAKE_PI))
        session.close()
        session.close()
        assert session._proc.poll() is not None

    def test_failed_command_raises_with_error_text(self, tmp_path):
        session = PiSession(command=write_fake_pi(tmp_path, FAKE_PI))
        try:
            with pytest.raises(PiRpcError, match="nope"):
                session._call({"type": "fail"}, timeout=10)
        finally:
            session.close()

    def test_command_timeout_raises(self, tmp_path):
        session = PiSession(command=write_fake_pi(tmp_path, FAKE_PI))
        try:
            with pytest.raises(PiRpcError, match="timed out"):
                session._call({"type": "slow"}, timeout=0.2)
        finally:
            session.close()

    def test_command_timeout_raises_and_pending_call_is_dropped(self, tmp_path):
        events: list[dict] = []
        session = PiSession(
            command=write_fake_pi(tmp_path, FAKE_PI + "\n" * 0 or FAKE_PI),
            on_event=events.append,
        )
        try:
            # 'slow' sleeps 30s in the fake; a 0.2s budget must time out.
            with pytest.raises(PiRpcError, match="timed out"):
                session._call({"type": "slow"}, timeout=0.2)
        finally:
            session.close()

    def test_stdin_write_failure_raises_process_error(self, tmp_path):
        session = PiSession(command=write_fake_pi(tmp_path, FAKE_PI))
        session.close()
        with pytest.raises(PiRpcProcessError, match="not running"):
            session._call({"type": "prompt", "message": "x"}, timeout=1)

    def test_correlated_ids_do_not_cross(self, tmp_path):
        # Two sessions; each resolves only its own pending call. The fake
        # echoes the id back, so a cross-wire would fail the settle assert.
        events_a: list[dict] = []
        events_b: list[dict] = []
        cmd = write_fake_pi(tmp_path, FAKE_PI)
        a = PiSession(command=cmd, on_event=events_a.append)
        b = PiSession(command=cmd, on_event=events_b.append)
        try:
            a.prompt("a")
            b.prompt("b")
            assert a._pending == {} and b._pending == {}
        finally:
            a.close()
            b.close()

    def test_malformed_lines_are_ignored(self, tmp_path):
        body = FAKE_PI.replace(
            'cmd = json.loads(line)',
            'sys.stdout.write("NOT JSON\\n"); sys.stdout.flush(); cmd = json.loads(line)',
        )
        events: list[dict] = []
        session = PiSession(command=write_fake_pi(tmp_path, body), on_event=events.append)
        try:
            session.prompt("hi")
            assert events  # the real events still arrived
        finally:
            session.close()


class TestChunkMapping:
    def test_text_deltas_map_to_text_chunks(self):
        records = [
            {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "he"}},
            {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "y"}},
        ]
        assert list(chunk_events_from_records(records)) == [{"type": "text", "text": "he"}, {"type": "text", "text": "y"}]

    def test_agent_end_maps_to_end_chunk(self):
        assert list(chunk_events_from_records([{"type": "agent_end"}])) == [{"type": "end"}]

    def test_empty_deltas_and_unknown_events_are_dropped(self):
        records = [
            {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": ""}},
            {"type": "tool_execution_start", "tool": "bash"},
        ]
        assert list(chunk_events_from_records(records)) == []

    def test_mapping_is_importable_from_the_driver_module(self):
        assert callable(pi_rpc_driver.chunk_events_from_records)

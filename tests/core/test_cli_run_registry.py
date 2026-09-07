"""REQ-114 — registry tracks swarm-spawned CLI groups and terminates only those."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from swarm.core.cli_adapter import CliAdapter
from swarm.core.cli_run_registry import (
    is_cli_run_running,
    list_cli_runs,
    register_cli_run,
    reset_cli_run_registry,
    terminate_cli_runs,
    terminate_process_group,
)

PY = sys.executable


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_cli_run_registry()
    yield
    reset_cli_run_registry()


def _looping_child() -> subprocess.Popen:
    return subprocess.Popen(
        [PY, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait_dead(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def test_idle_is_not_running():
    assert is_cli_run_running("u0", "cli_agent") is False
    assert terminate_cli_runs("u0", "cli_agent") == "not_running"


def test_terminate_looping_fixture_kills_group_only():
    child = _looping_child()
    pgid = os.getpgid(child.pid)
    token = register_cli_run(
        user_key="u0",
        agent_id="cli_agent",
        conversation_id="conv-1",
        pid=child.pid,
        pgid=pgid,
    )
    assert token
    assert is_cli_run_running("u0", "cli_agent") is True
    os.kill(child.pid, 0)

    assert terminate_cli_runs("u0", "cli_agent") == "terminated"
    child.wait(timeout=5)
    assert child.poll() is not None
    assert _wait_dead(child.pid)
    assert is_cli_run_running("u0", "cli_agent") is False
    # Agent identity is untouched — registry is empty, no delete side effect.
    assert list_cli_runs("u0", "cli_agent") == []


def test_terminate_does_not_signal_unrelated_pid(monkeypatch):
    """Refuse to kill a process whose pgid no longer matches the registration."""
    child = _looping_child()
    try:
        register_cli_run(
            user_key="u0",
            agent_id="cli_agent",
            pid=child.pid,
            pgid=child.pid,
        )
        sent = []

        def _fake_killpg(pgid, sig):
            sent.append((pgid, sig))

        monkeypatch.setattr(os, "getpgid", lambda pid: -1 if pid == child.pid else os.getpgid(pid))
        # getpgid mismatch → terminate_process_group returns False; no killpg.
        assert terminate_process_group(child.pid, child.pid) is False
        assert sent == []
        os.kill(child.pid, 0)  # still ours to reap
    finally:
        child.terminate()
        child.wait(timeout=5)


@pytest.mark.asyncio
async def test_stream_run_registers_and_user_terminate_sets_flag(tmp_path):

    pidfile = tmp_path / "child.pid"
    code = (
        "import os, sys, time\n"
        f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "sys.stdout.write('ping\\n'); sys.stdout.flush()\n"
        "time.sleep(60)\n"
    )
    adapter = CliAdapter.from_config(
        "loop",
        {"cmd": [PY, "-c", code, "{prompt}"], "timeout": 30.0},
    )
    owner = {"user_key": "u0", "agent_id": "cli_agent", "conversation_id": "c1"}
    gen = adapter.stream_run("hi", run_owner=owner)
    first = await gen.__anext__()
    assert first.delta and "ping" in first.delta
    assert is_cli_run_running("u0", "cli_agent")
    pid = list_cli_runs("u0", "cli_agent")[0].pid
    os.kill(pid, 0)

    assert terminate_cli_runs("u0", "cli_agent") == "terminated"
    chunks = [first]
    async for chunk in gen:
        chunks.append(chunk)
    assert _wait_dead(pid)
    finals = [c for c in chunks if c.final]
    assert finals and finals[-1].result is not None and finals[-1].result.terminated

def test_terminate_already_dead_process_returns_not_running():
    child = _looping_child()
    pgid = os.getpgid(child.pid)
    token = register_cli_run(
        user_key="u0",
        agent_id="cli_agent",
        conversation_id="conv-1",
        pid=child.pid,
        pgid=pgid,
    )
    assert token
    child.terminate()
    child.wait(timeout=5)
    assert terminate_cli_runs("u0", "cli_agent") == "not_running"


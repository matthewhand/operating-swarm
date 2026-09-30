"""#1374 — live team send on shipped N≥3 rosters hits the concurrent executor.

Hermetic overlap of mocked blueprint legs is not enough: ``target=all`` on
the shipped showoff rosters used to collapse through
``blueprint_id_for_team_target`` into one ``respond_with_blueprint``. These
tests drive that consumer path, prove ``cancel_turn`` + ``leg_id`` stops one
leg while siblings finish, and prove remote and CLI cancel stop the worker.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from swarm.core import team_roster_executor as ex
from swarm.core.team_roster_executor import team_send_fans_out


def test_shipped_rosters_of_three_or_more_fan_out():
    """Operator "all" on every shipped N≥3 roster is a concurrent send."""
    assert team_send_fans_out("demo-sdlc-pipeline", "all") is True
    assert team_send_fans_out("demo-sdlc-skeptic-loop", "all") is True
    assert team_send_fans_out("demo-harness-kinds", "all") is True
    assert team_send_fans_out("demo-bridge", "all") is True
    # A named blueprint member stays on the single-blueprint path (#113).
    assert team_send_fans_out("demo-sdlc-pipeline", "ba") is False
    # One CLI member is not a multi-leg fan-out.
    assert team_send_fans_out("demo-harness-kinds", "grok-cli") is False
    # demo-team's unsourced API members receive a default blueprint source,
    # so "all" is two runnable legs and uses the same concurrent executor.
    assert team_send_fans_out("demo-team", "all") is True


def _consumer():
    from swarm.consumers import DjangoChatConsumer

    user = MagicMock()
    user.is_authenticated = True
    user.pk = 1
    consumer = DjangoChatConsumer()
    consumer.scope = {
        "user": user,
        "url_route": {"kwargs": {"conversation_id": "fanout-1374"}},
    }
    consumer.user = user
    consumer.messages = []
    consumer.ui_events = []
    consumer.send = AsyncMock()
    return consumer


def _frames(send: AsyncMock) -> list[dict]:
    out = []
    for call in send.await_args_list:
        raw = call.kwargs.get("text_data") or (call.args[0] if call.args else "")
        if not isinstance(raw, str) or not raw.startswith("{"):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _has_frame(send: AsyncMock, frame_type: str) -> bool:
    return any(frame.get("type") == frame_type for frame in _frames(send))


async def test_shipped_pipeline_send_runs_legs_and_ws_cancel(monkeypatch):
    """demo-sdlc-pipeline / all overlaps N≥3 and cancel_turn stops one leg.

    The send stays inside ``receive`` until the legs finish. The SPA mux
    dispatches ``cancel_turn`` on a second task while that receive is
    awaiting the roster, which is what this test does. Returning from
    receive early would emit ``turn_finished`` and drop composer Stop
    before the legs were done.
    """
    in_flight = 0
    max_in_flight = 0
    entered = asyncio.Event()

    async def slow(blueprint_id, prompt, *, brief=None, **_kwargs):
        nonlocal in_flight, max_in_flight
        del blueprint_id, prompt, brief
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        if max_in_flight >= 3:
            entered.set()
        try:
            await asyncio.sleep(0.45)
            return "ok"
        finally:
            in_flight -= 1

    monkeypatch.setattr(ex, "_run_blueprint_member", slow)
    monkeypatch.setattr("swarm.demo.is_demo_mode", lambda: False)

    consumer = _consumer()
    with patch("swarm.consumers.render_to_string", return_value="<div></div>"):
        with patch.object(consumer, "respond_with_blueprint", new_callable=AsyncMock) as blueprint:
            with patch.object(consumer, "respond_with_roster_run", new_callable=AsyncMock) as roster_reply:
                started = time.monotonic()
                send_task = asyncio.create_task(
                    consumer.receive(
                        json.dumps(
                            {
                                "message": "fan out the pipeline",
                                "params": {"team": "demo-sdlc-pipeline", "target": "all"},
                            }
                        )
                    )
                )
                await asyncio.wait_for(entered.wait(), timeout=2)
                assert max_in_flight >= 3
                assert not send_task.done()
                assert consumer.active_turns
                assert consumer._fan_out_handles()
                assert not _has_frame(consumer.send, "turn_finished")
                blueprint.assert_not_awaited()

                await consumer.receive(
                    json.dumps({"type": "cancel_turn", "leg_id": "engineer"})
                )
                await asyncio.wait_for(send_task, timeout=3)
                elapsed = time.monotonic() - started

    blueprint.assert_not_awaited()
    roster_reply.assert_awaited()
    assert elapsed < 1.5, f"legs look serial ({elapsed:.2f}s)"
    assert not consumer.active_turns
    assert _has_frame(consumer.send, "turn_finished")
    run = roster_reply.await_args.args[3]
    by_id = {row.member_id: row.status for row in run.results}
    assert set(by_id) == {"cos", "ba", "engineer", "tester"}
    assert by_id["engineer"] == "cancelled"
    assert by_id["cos"] == "done"
    assert by_id["ba"] == "done"
    assert by_id["tester"] == "done"
    running_ids = {
        frame["leg_id"]
        for frame in _frames(consumer.send)
        if frame.get("type") == "fan_out_leg" and frame.get("status") == "running"
    }
    assert running_ids >= {"cos", "ba", "engineer", "tester"}


async def test_remote_cancel_stops_the_worker(monkeypatch):
    """Cancel sets the remote thread's event and the worker exits."""
    from swarm.core import remotes

    started = threading.Event()
    exited = threading.Event()

    def operate(remote_id, op, **kwargs):
        del remote_id, op, kwargs
        started.set()
        try:
            while True:
                remotes.interruptible_sleep(0.05)
        except remotes.RemoteCallCancelled:
            exited.set()
            raise

    monkeypatch.setattr(remotes, "operate", operate)
    roster = {
        "id": "t-remote",
        "name": "Remote",
        "members": [
            {
                "id": "hermes",
                "name": "Hermes",
                "kind": "remote",
                "role": "default",
                "source": "remote:hermes",
            }
        ],
    }
    monkeypatch.setattr(ex, "resolve_roster", lambda rid: roster if rid == "t-remote" else None)
    cancel = ex.FanOutCancel()

    async def stop_once_started():
        while not started.is_set():
            await asyncio.sleep(0.01)
        assert cancel.cancel("hermes") is True

    stopper = asyncio.create_task(stop_once_started())
    run = await ex.execute_roster("t-remote", "all", "ping", config={}, cancel=cancel)
    await stopper
    assert exited.is_set()
    assert run.results[0].status == "cancelled"
    assert run.results[0].member_id == "hermes"


def test_get_observes_remote_cancel_without_waiting_out_the_timeout():
    """An in-flight GET poll stops when the leg's cancel event is set."""
    import socket

    from swarm.core import remotes

    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(2)
    port = server.getsockname()[1]
    stop = threading.Event()

    def _accept():
        try:
            conn, _addr = server.accept()
            # Hold the accepted socket open so the client blocks in read.
            time.sleep(3)
            conn.close()
        except OSError:
            return

    acceptor = threading.Thread(target=_accept, daemon=True)
    acceptor.start()

    def _cancel():
        time.sleep(0.15)
        stop.set()

    threading.Thread(target=_cancel, daemon=True).start()
    started = time.monotonic()
    try:
        with remotes.remote_cancel_scope(stop):
            with pytest.raises(remotes.RemoteCallCancelled):
                remotes.http_json(
                    "GET",
                    f"http://127.0.0.1:{port}/hang",
                    timeout=30,
                )
        elapsed = time.monotonic() - started
    finally:
        server.close()
    assert elapsed < 2.0, f"GET kept running after cancel ({elapsed:.2f}s)"


async def test_cli_cancel_kills_the_subprocess(monkeypatch):
    """Stopping a CLI leg kills its process group, not just the asyncio task."""
    from swarm.blueprints.common import cli_fusion_support
    from swarm.core.cli_adapter import CliAdapter, CliAgentConfig

    adapter = CliAdapter(
        CliAgentConfig(
            name="sleeper",
            cmd=["sleep", "30"],
            prompt_mode="none",
            parse="text",
            timeout=60,
        )
    )

    class _Reg:
        def get(self, name):
            assert name == "sleeper"
            return adapter

    monkeypatch.setattr(cli_fusion_support, "build_registry", lambda config=None: _Reg())

    import swarm.core.cli_adapter as cli_adapter_mod

    pids: list[int] = []
    real_spawn = cli_adapter_mod.asyncio.create_subprocess_exec

    async def _spy(*args, **kwargs):
        proc = await real_spawn(*args, **kwargs)
        if proc.pid:
            pids.append(proc.pid)
        return proc

    monkeypatch.setattr(cli_adapter_mod.asyncio, "create_subprocess_exec", _spy)
    roster = {
        "id": "t-cli",
        "name": "CLI",
        "members": [
            {
                "id": "grok-cli",
                "name": "Grok CLI",
                "kind": "cli",
                "role": "default",
                "source": "cli:sleeper",
            }
        ],
    }
    monkeypatch.setattr(ex, "resolve_roster", lambda rid: roster if rid == "t-cli" else None)
    cancel = ex.FanOutCancel()

    async def stop_once_started():
        while not pids:
            await asyncio.sleep(0.01)
        assert cancel.cancel("grok-cli") is True

    stopper = asyncio.create_task(stop_once_started())
    try:
        run = await ex.execute_roster("t-cli", "all", "ping", config={}, cancel=cancel)
        await stopper
        assert run.results[0].status == "cancelled"
        pid = pids[0]
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"CLI process {pid} still alive after cancel")
    finally:
        for pid in pids:
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass

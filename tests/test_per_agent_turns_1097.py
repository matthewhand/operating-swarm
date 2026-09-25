"""ADR-017 PR-1 — per-turn identity, per-agent locks and scoped cancels.

Implements the minimal concurrency slice from
``docs/adr/017-concurrent-per-agent-turns.md``:

1. Every chat turn gets a ``turn_id`` (uuid) and an ``agent_id`` (resolved
   blueprint/remote); outbound frames for that turn carry both, and the wire
   gains ``turn_started`` / ``turn_finished`` bookends.
2. Cancels are per-turn: ``cancel_turn`` with an ``agent`` (or ``turn_id``)
   sets only that turn's event. A bare ``cancel_turn`` keeps the #198 legacy
   behaviour (cancel everything running on the socket).
3. Serialisation is per agent: two sends for the SAME agent still queue on
   one lock (REQ-171A-3/#603 semantics preserved); different agents run
   concurrently.

No mixin changes — every ``self._cancel_event()`` call site resolves via
task-local turn identity.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from swarm.consumers import DjangoChatConsumer, _TURN_STATE_CTX

# The consumer fixtures (mock_scope/mock_user/consumer) live in
# tests/test_consumers.py — import them so this file shares one definition.
from tests.test_consumers import consumer, mock_scope, mock_user  # noqa: F401

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# 1. Turn identity on the wire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turn_frames_carry_turn_id_and_agent_id(consumer, monkeypatch):
    """The bookend frames name the turn and the agent that owns it."""
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    consumer.messages = []
    consumer.conversation_id = "test-conv-123"
    consumer.default_blueprint = "jeeves"

    instance = MagicMock()

    async def fake_run(messages, **kwargs):
        yield {"messages": [{"role": "assistant", "content": "done"}], "delta": "done"}

    instance.run = fake_run
    instance._params = {}

    sent = []

    async def capture_send(*, text_data=None, **_kwargs):
        sent.append(text_data or "")

    def fake_render(template, context):
        name = str(template)
        cid = context.get("contents_div_id", "")
        if "final_system" in name:
            return f'<div id="{cid}" class="assistant-final"></div>'
        return f'<div id="{cid}" class="assistant-start"></div>'

    with patch("swarm.consumers.render_to_string", side_effect=fake_render):
        with patch.object(consumer, "send", new_callable=AsyncMock, side_effect=capture_send):
            with patch(
                "swarm.views.utils.get_blueprint_instance",
                new_callable=AsyncMock,
                return_value=instance,
            ):
                await consumer.receive(
                    json.dumps({"message": "hello", "blueprint": "jeeves"})
                )

    joined = "\n".join(sent)
    assert "turn_started" in joined
    assert "turn_finished" in joined
    started = json.loads(
        next(line for line in joined.split("\n") if '"turn_started"' in line)
    )
    finished = json.loads(
        next(line for line in joined.split("\n") if '"turn_finished"' in line)
    )
    assert started["agent_id"] == "jeeves"
    assert started["turn_id"]
    assert finished["turn_id"] == started["turn_id"]


@pytest.mark.asyncio
async def test_cancel_event_resolves_per_turn_not_globally(consumer):
    """Two concurrent turns: cancelling agent A must NOT set B's event."""
    consumer.messages = []

    async def run_agent_a():
        turn = await consumer._begin_turn(agent_id="agent-a")
        try:
            await asyncio.sleep(0.05)
            # The cancel for agent-a lands while we run; ours resolves.
            assert consumer._cancel_event().is_set()
        finally:
            await consumer._end_turn(turn)

    async def run_agent_b():
        await asyncio.sleep(0.01)
        turn = await consumer._begin_turn(agent_id="agent-b")
        try:
            await asyncio.sleep(0.08)
            # B's event is untouched by the cancel aimed at A.
            assert not consumer._cancel_event().is_set()
        finally:
            await consumer._end_turn(turn)

    await asyncio.gather(
        run_agent_a(),
        run_agent_b(),
        consumer._cancel_current_turn(agent_id="agent-a"),
    )


@pytest.mark.asyncio
async def test_bare_cancel_turn_cancels_all_running_turns(consumer):
    """Legacy #198 frame with no identity: cancel every running turn."""
    consumer.messages = []
    turn_a = await consumer._begin_turn(agent_id="agent-a")
    turn_b = await consumer._begin_turn(agent_id="agent-b")
    with patch.object(consumer, "send", new_callable=AsyncMock):
        await consumer.receive(json.dumps({"type": "cancel_turn"}))
    assert consumer._cancel_event().is_set()  # resolves to "current task" turn
    assert turn_a.cancel_event.is_set()
    assert turn_b.cancel_event.is_set()


@pytest.mark.asyncio
async def test_cancel_turn_with_agent_only_sets_that_agent(consumer):
    consumer.messages = []
    turn_a = await consumer._begin_turn(agent_id="agent-a")
    turn_b = await consumer._begin_turn(agent_id="agent-b")
    with patch.object(consumer, "send", new_callable=AsyncMock):
        await consumer.receive(
            json.dumps({"type": "cancel_turn", "agent": "agent-a"})
        )
    assert turn_a.cancel_event.is_set()
    assert not turn_b.cancel_event.is_set()


@pytest.mark.asyncio
async def test_same_agent_sends_serialise_different_agents_run_concurrently(consumer):
    """REQ-171A-3 preserved per agent; parallelism across agents (ADR-017 §3.3)."""
    consumer.messages = []
    order: list[str] = []
    inside = asyncio.Event()
    first_done = asyncio.Event()

    async def body(name, release):
        lock = consumer._agent_lock(name)
        async with lock:
            order.append(f"{name}:start")
            if name == "agent-a":
                inside.set()
                await asyncio.wait_for(release.wait(), timeout=2)
            order.append(f"{name}:end")
            if name == "agent-a":
                first_done.set()

    release_a = asyncio.Event()
    task_a = asyncio.create_task(body("agent-a", release_a))
    await inside.wait()

    # agent-b starts while agent-a still holds its own lock.
    task_b = asyncio.create_task(body("agent-b", release_a))
    await asyncio.sleep(0.02)
    order.append("probe:b-started-while-a-running")
    assert "agent-b:start" in order

    release_a.set()
    await asyncio.gather(task_a, task_b)
    # Same agent still serialises: b ran fully while a was mid-turn, and a's
    # own end came after its start.
    assert order.index("agent-a:start") < order.index("agent-a:end")
    assert order.index("agent-b:start") < order.index("agent-b:end")


@pytest.mark.asyncio
async def test_turn_registry_bookends(consumer):
    """_begin_turn registers; _end_turn unregisters and closes the event."""
    consumer.messages = []
    assert consumer.active_turns == {}
    turn = await consumer._begin_turn(agent_id="agent-a")
    assert turn.turn_id in consumer.active_turns
    assert consumer.active_turns[turn.turn_id].agent_id == "agent-a"
    await consumer._end_turn(turn)
    assert turn.turn_id not in consumer.active_turns
    assert turn.finished_at is not None


# ---------------------------------------------------------------------------
# ADR-017 PR-5 — team member-granular concurrency — team member-granular concurrency
# ---------------------------------------------------------------------------


def _team_frame(target: str) -> dict:
    return {
        "message": "hi",
        "blueprint": "demo-team",
        "params": {"team": "demo-team", "target": target, "enabled_tools": []},
    }


@pytest.mark.asyncio
async def test_member_targeted_sends_use_member_lock_key(consumer, monkeypatch):
    """PR-5: params {team, target:member} locks on team#member, not the team."""
    seen: list[str] = []

    async def fake_body(text_data_json, message_text, blueprint_id, params):
        seen.append(_TURN_STATE_CTX.get().agent_id)

    monkeypatch.setattr(consumer, "_run_chat_turn_body", fake_body)
    monkeypatch.setattr(consumer, "send", AsyncMock())
    await consumer._run_serialised_chat_turn(_team_frame("codey"), "hi")
    assert seen == ["demo-team#codey"]


@pytest.mark.asyncio
async def test_all_compose_keeps_team_wide_lock(consumer, monkeypatch):
    """PR-5: target=all (the whole-team compose) keeps the team lock key."""
    seen: list[str] = []

    async def fake_body(text_data_json, message_text, blueprint_id, params):
        seen.append(_TURN_STATE_CTX.get().agent_id)

    monkeypatch.setattr(consumer, "_run_chat_turn_body", fake_body)
    monkeypatch.setattr(consumer, "send", AsyncMock())
    await consumer._run_serialised_chat_turn(_team_frame("all"), "hi")
    assert seen == ["demo-team"]


@pytest.mark.asyncio
async def test_different_members_run_concurrently_same_member_serialises(consumer):
    """Two members interleave; the same member queues exactly as before."""
    order: list[str] = []
    inside = asyncio.Event()

    async def member_turn(target: str, release: asyncio.Event | None):
        lock = consumer._agent_lock(f"demo-team#{target}")
        async with lock:
            order.append(f"{target}:start")
            if target == "codey" and release is not None:
                inside.set()
                await asyncio.wait_for(release.wait(), timeout=2)
            order.append(f"{target}:end")

    release = asyncio.Event()
    task_a = asyncio.create_task(member_turn("codey", release))
    await inside.wait()
    task_b = asyncio.create_task(member_turn("poet", None))
    await asyncio.sleep(0.05)
    assert "poet:start" in order, f"member poet must not queue behind codey: {order}"

    task_c = asyncio.create_task(member_turn("codey", None))
    await asyncio.sleep(0.05)
    release.set()
    await asyncio.gather(task_a, task_b, task_c)
    starts = [i for i, o in enumerate(order) if o == "codey:start"]
    ends = [i for i, o in enumerate(order) if o == "codey:end"]
    assert len(starts) == 2 and len(ends) == 2
    assert ends[0] < starts[1], f"same member must serialise: {order}"


@pytest.mark.asyncio
async def test_cancel_by_member_only_stops_that_member(consumer, monkeypatch):
    """PR-5: cancel(agent='demo-team#poet') leaves codey's turn running."""
    monkeypatch.setattr(consumer, "send", AsyncMock())
    codey_turn = await consumer._begin_turn(agent_id="demo-team#codey")
    poet_turn = await consumer._begin_turn(agent_id="demo-team#poet")

    await consumer._cancel_current_turn(agent_id="demo-team#poet")
    assert poet_turn.cancel_event.is_set()
    assert not codey_turn.cancel_event.is_set()

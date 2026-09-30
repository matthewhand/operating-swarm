"""#1684 — the turn-phase ``tool_status`` producer.

The client-side parser contract is a *cross-language* contract, so
:data:`CLIENT_TOOL_STATUSES` below is the literal status set from
``webui/frontend/src/lib/chatWs.ts:43`` / ``TOOL_STATUSES`` at ``:254``,
reproduced rather than imported. If the SPA's set ever changes, this file must
change with it — that is the point of pinning it here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from agents import Agent
from agents.items import ModelResponse
from agents.lifecycle import AgentHooksBase
from agents.models.interface import Model
from agents.run_context import RunContextWrapper
from agents.tool import FunctionTool, function_tool
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
)
from openai.types.responses.response_output_text import ResponseOutputText

from swarm.core.kind_bases import ApiKindBase
from swarm.core.safety import (
    CHANNEL_API,
    CHANNEL_CLI,
    CHANNEL_REMOTE,
    SafetySession,
    install_safety_session,
    reset_safety_session,
)
from swarm.core.turn_phase import (
    ToolPhaseHooks,
    attach_turn_phase_hooks,
    terminal_status_for,
)
from swarm.tool_executor import (
    COMMAND_DENIED_RESULT_PREFIX,
    DENIED_RESULT_PREFIX,
    emit_tool_status,
)

#: The exact literal set `parseToolJsonFrame` will accept. Anything outside it
#: is downgraded to `{kind: 'unknown'}` and the tool row is never created.
CLIENT_TOOL_STATUSES = frozenset({"running", "allowed", "done", "denied", "error"})


def read_file(path: str) -> str:
    return f"contents of {path}"


READ_FILE_TOOL = function_tool(read_file, name_override="read_file")


class Recorder:
    """Collects the frames the hooks put on ``SafetySession.emit_fn``."""

    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []

    def __call__(self, payload: dict[str, Any]) -> None:
        self.frames.append(payload)

    def statuses(self) -> list[str]:
        return [str(f.get("status")) for f in self.frames]

    def by_status(self, status: str) -> list[dict[str, Any]]:
        return [f for f in self.frames if f.get("status") == status]


def make_session(
    *, agent_id: str = "codey", channel: str = CHANNEL_API, emit: Any = None
) -> SafetySession:
    return SafetySession(agent_id=agent_id, channel=channel, emit_fn=emit)


def make_context(call_id: str = "call_abc") -> RunContextWrapper[Any]:
    """A ``ToolContext``-shaped context, as the SDK builds for function tools.

    ``agents/_run_impl.py:748-752`` constructs a real ``ToolContext`` via
    ``ToolContext.from_agent_context`` and passes that same object to both
    ``on_tool_start`` and ``on_tool_end``. ``tool_call_id`` is a
    ``RunContextWrapper`` *field-less* attribute, so it is attached here the
    same way the dataclass would — no need to import the SDK's ToolContext and
    drag its openai Responses types in.
    """
    ctx = RunContextWrapper(context=None)
    ctx.tool_call_id = call_id
    return ctx


def bare_context() -> RunContextWrapper[Any]:
    """A plain RunContextWrapper — the hosted computer/local-shell shape, which
    carries no ``tool_call_id`` (``agents/_run_impl.py:1285``, ``:1388``)."""
    return RunContextWrapper(context=None)


# =============================================================================
# on_tool_start
# =============================================================================


class TestOnToolStart:
    async def test_emits_running_with_name_and_agent_id(self):
        rec = Recorder()
        session = make_session(agent_id="codey", emit=rec)
        token = install_safety_session(session)
        try:
            await ToolPhaseHooks().on_tool_start(
                make_context(), Agent(name="codey"), READ_FILE_TOOL
            )
        finally:
            reset_safety_session(token)

        assert len(rec.frames) == 1
        frame = rec.frames[0]
        assert frame["type"] == "tool_status"
        assert frame["name"] == "read_file"
        assert frame["status"] == "running"
        assert frame["agent_id"] == "codey"

    @pytest.mark.parametrize(
        "channel", [CHANNEL_API, CHANNEL_CLI, CHANNEL_REMOTE], ids=str
    )
    async def test_emits_for_every_channel(self, channel):
        """#1684: the old gate was ``uses_swarm_approval()`` — API-only — so CLI
        and remote seats could never report a tool in flight. Status reporting
        is not an approval question, so all three channels emit."""
        rec = Recorder()
        session = make_session(channel=channel, emit=rec)
        token = install_safety_session(session)
        try:
            await ToolPhaseHooks().on_tool_start(
                make_context(), Agent(name="codey"), READ_FILE_TOOL
            )
        finally:
            reset_safety_session(token)

        assert rec.statuses() == ["running"]


# =============================================================================
# on_tool_end
# =============================================================================


class TestOnToolEnd:
    async def _run(self, result: Any, *, agent_id: str = "codey") -> list[dict[str, Any]]:
        rec = Recorder()
        token = install_safety_session(make_session(agent_id=agent_id, emit=rec))
        hooks = ToolPhaseHooks()
        context = make_context()
        agent = Agent(name="codey")
        try:
            await hooks.on_tool_start(context, agent, READ_FILE_TOOL)
            await hooks.on_tool_end(context, agent, READ_FILE_TOOL, result)
        finally:
            reset_safety_session(token)
        return rec.frames

    async def test_emits_done_for_a_plain_result(self):
        frames = await self._run("contents of /tmp/x")
        assert frames[-1]["status"] == "done"
        assert frames[-1]["name"] == "read_file"

    async def test_end_reuses_the_id_minted_at_start(self):
        """The client's `upsertToolCall` keys on `id`. If `on_tool_end` minted a
        fresh key it would append a *second* row instead of closing the first,
        leaving a tool row stuck on 'running' forever."""
        frames = await self._run("ok")
        assert len(frames) == 2
        assert frames[0]["id"] == frames[1]["id"]

    @pytest.mark.parametrize(
        ("result", "why"),
        [
            pytest.param(
                f"{DENIED_RESULT_PREFIX}tool call 'wipe' was not approved",
                "swarm-approval denial (tool_executor._maybe_deny_tool / "
                "core.safety._wrap_callable / core.tool_gate.gate_wrap_callable)",
                id="swarm-denied",
            ),
            pytest.param(
                f"{COMMAND_DENIED_RESULT_PREFIX}rm is not allowlisted",
                "#1312 command-allowlist denial",
                id="command-denied",
            ),
            pytest.param(
                json.dumps({"error": "Tool 'nope' is not available."}),
                "missing-tool failure, as JSON text",
                id="error-json-text",
            ),
            pytest.param(
                {"error": "Execution failed: boom"},
                "tool exception, as the raw dict the SDK hands to on_tool_end",
                id="error-dict",
            ),
        ],
    )
    async def test_emits_error_for_terminal_sentinels(self, result, why):
        frames = await self._run(result)
        assert frames[-1]["status"] == "error", why

    @pytest.mark.parametrize(
        "result",
        [
            "done reading 2 files",
            json.dumps({"rows": 12}),
            {"rows": 12},
            "",
            "A file that mentions DENIED: in its body is still a success",
        ],
    )
    async def test_non_sentinel_results_are_done(self, result):
        assert terminal_status_for(result) == "done"


# =============================================================================
# The key-collision trap (#1684 regression)
# =============================================================================


class TestConcurrentSameNamedTools:
    async def test_two_concurrent_same_named_tools_get_different_ids(self):
        """Two `read_file` calls in one turn overlap: the SDK fans a batch of
        parallel tool calls out through `asyncio.gather`
        (`agents/_run_impl.py:717-726`). A name-derived key would make the
        second overwrite the first in the client's `upsertToolCall` reducer and
        the first would never reach a terminal status. Remove `next(self._seq)`
        from the id and this fails.
        """
        rec = Recorder()
        token = install_safety_session(make_session(agent_id="codey", emit=rec))
        hooks = ToolPhaseHooks()
        agent = Agent(name="codey")
        first, second = make_context("call_1"), make_context("call_2")
        try:
            await hooks.on_tool_start(first, agent, READ_FILE_TOOL)
            await hooks.on_tool_start(second, agent, READ_FILE_TOOL)
        finally:
            reset_safety_session(token)

        starts = rec.by_status("running")
        assert len(starts) == 2
        assert starts[0]["id"] != starts[1]["id"]
        assert {starts[0]["name"], starts[1]["name"]} == {"read_file"}

    async def test_interleaved_concurrent_tools_each_close_their_own_row(self):
        """Starts 1,2,1 again — same-name overlap, ends out of start order. Each
        terminal frame must reuse the id its own start minted, so the client
        closes the right row."""
        rec = Recorder()
        token = install_safety_session(make_session(agent_id="codey", emit=rec))
        hooks = ToolPhaseHooks()
        agent = Agent(name="codey")
        a1, b, a2 = make_context("a1"), make_context("b"), make_context("a2")
        try:
            await hooks.on_tool_start(a1, agent, READ_FILE_TOOL)
            await hooks.on_tool_start(b, agent, READ_FILE_TOOL)
            await hooks.on_tool_start(a2, agent, READ_FILE_TOOL)
            await hooks.on_tool_end(a2, agent, READ_FILE_TOOL, "second done")
            await hooks.on_tool_end(a1, agent, READ_FILE_TOOL, "first done")
            await hooks.on_tool_end(b, agent, READ_FILE_TOOL, "b done")
        finally:
            reset_safety_session(token)

        started = {f["id"] for f in rec.by_status("running")}
        done = {f["id"] for f in rec.by_status("done")}
        assert len(started) == 3
        assert len(done) == 3
        assert done == started

    async def test_id_counter_is_monotonic_across_agents_and_names(self):
        rec = Recorder()
        token = install_safety_session(make_session(agent_id="codey", emit=rec))
        hooks = ToolPhaseHooks()
        agent = Agent(name="codey")
        try:
            for call_id in ("c1", "c2", "c3"):
                await hooks.on_tool_start(
                    make_context(call_id), agent, READ_FILE_TOOL
                )
        finally:
            reset_safety_session(token)
        suffixes = [f["id"].rsplit(":", 1)[-1] for f in rec.frames]
        assert suffixes == ["0", "1", "2"]


# =============================================================================
# No-op contracts
# =============================================================================


class TestNoOpPaths:
    async def test_no_session_installed_emits_nothing_and_does_not_raise(self):
        from swarm.core.safety import current_safety_session

        assert current_safety_session() is None
        hooks = ToolPhaseHooks()
        context = make_context()
        agent = Agent(name="codey")
        await hooks.on_tool_start(context, agent, READ_FILE_TOOL)
        await hooks.on_tool_end(context, agent, READ_FILE_TOOL, "ok")
        # Nothing to assert on emission — the contract is "did not raise", and
        # the assertion above is what proves no session leaked in.
        assert hooks._inflight == {}

    async def test_emit_fn_none_emits_nothing_and_does_not_raise(self):
        token = install_safety_session(make_session(emit=None))
        hooks = ToolPhaseHooks()
        context = make_context()
        agent = Agent(name="codey")
        try:
            await hooks.on_tool_start(context, agent, READ_FILE_TOOL)
            await hooks.on_tool_end(context, agent, READ_FILE_TOOL, "ok")
        finally:
            reset_safety_session(token)
        assert hooks._inflight == {}

    async def test_a_raising_emit_fn_never_breaks_the_turn(self):
        def boom(_payload: dict[str, Any]) -> None:
            raise RuntimeError("socket is gone")

        token = install_safety_session(make_session(emit=boom))
        hooks = ToolPhaseHooks()
        context = make_context()
        agent = Agent(name="codey")
        try:
            await hooks.on_tool_start(context, agent, READ_FILE_TOOL)
            await hooks.on_tool_end(context, agent, READ_FILE_TOOL, "ok")
        finally:
            reset_safety_session(token)
        # The in-flight entry is still released even though emit blew up.
        assert hooks._inflight == {}

    async def test_tool_without_a_name_attribute_still_emits(self):
        rec = Recorder()
        token = install_safety_session(make_session(emit=rec))
        try:
            await ToolPhaseHooks().on_tool_start(
                make_context(), Agent(name="codey"), object()
            )
        finally:
            reset_safety_session(token)
        assert rec.frames[0]["name"] == "tool"
        assert rec.frames[0]["id"]


# =============================================================================
# attach_turn_phase_hooks
# =============================================================================


class TestAttach:
    def test_sets_hooks_on_a_real_agent(self):
        agent = Agent(name="codey")
        assert agent.hooks is None
        attach_turn_phase_hooks(agent)
        assert isinstance(agent.hooks, ToolPhaseHooks)
        assert agent.hooks.previous is None

    def test_is_idempotent(self):
        agent = Agent(name="codey")
        attach_turn_phase_hooks(agent)
        first = agent.hooks
        attach_turn_phase_hooks(agent)
        assert agent.hooks is first

    def test_chains_rather_than_clobbers_an_existing_hook(self):
        class Existing(AgentHooksBase):
            def __init__(self) -> None:
                self.seen: list[str] = []

            async def on_tool_start(self, context, agent, tool) -> None:  # noqa: ARG002
                self.seen.append(f"start:{tool.name}")

            async def on_tool_end(self, context, agent, tool, result) -> None:  # noqa: ARG002
                self.seen.append(f"end:{tool.name}")

        # The SDK validates `hooks` in `Agent.__post_init__`
        # (`agents/agent.py:339-346`), so pass ours through the constructor
        # exactly the way a pre-existing decorator would have.
        existing = Existing()
        agent = Agent(name="codey", hooks=existing)
        attach_turn_phase_hooks(agent)
        assert isinstance(agent.hooks, ToolPhaseHooks)
        assert agent.hooks.previous is existing

    async def test_chained_hook_still_receives_tool_events(self):
        class Existing(AgentHooksBase):
            def __init__(self) -> None:
                self.seen: list[str] = []

            async def on_tool_start(self, context, agent, tool) -> None:  # noqa: ARG002
                self.seen.append("start")

            async def on_tool_end(self, context, agent, tool, result) -> None:  # noqa: ARG002
                self.seen.append("end")

        rec = Recorder()
        existing = Existing()
        agent = Agent(name="codey", hooks=existing)
        attach_turn_phase_hooks(agent)
        context = make_context()
        token = install_safety_session(make_session(emit=rec))
        try:
            await agent.hooks.on_tool_start(context, agent, READ_FILE_TOOL)
            await agent.hooks.on_tool_end(context, agent, READ_FILE_TOOL, "ok")
        finally:
            reset_safety_session(token)
        assert existing.seen == ["start", "end"]
        assert rec.statuses() == ["running", "done"]

    async def test_a_raising_chained_hook_does_not_block_our_frame(self):
        class Hostile(AgentHooksBase):
            async def on_tool_start(self, context, agent, tool) -> None:  # noqa: ARG002
                raise RuntimeError("third-party hook is broken")

        rec = Recorder()
        agent = Agent(name="codey", hooks=Hostile())
        attach_turn_phase_hooks(agent)
        token = install_safety_session(make_session(emit=rec))
        try:
            await agent.hooks.on_tool_start(make_context(), agent, READ_FILE_TOOL)
        finally:
            reset_safety_session(token)
        assert rec.statuses() == ["running"]

    def test_none_agent_is_a_no_op(self):
        assert attach_turn_phase_hooks(None) is None

    def test_non_agent_object_does_not_raise(self):
        sentinel = object()
        assert attach_turn_phase_hooks(sentinel) is sentinel


# =============================================================================
# The emit gate (#1684 step 3) and the client parser contract
# =============================================================================


class TestEmitGate:
    @pytest.mark.parametrize(
        "channel", [CHANNEL_API, CHANNEL_CLI, CHANNEL_REMOTE], ids=str
    )
    async def test_emit_is_not_gated_on_swarm_approval(self, channel):
        rec = Recorder()
        session = make_session(channel=channel, emit=rec)
        assert session.uses_swarm_approval() is (channel == CHANNEL_API)
        token = install_safety_session(session)
        try:
            await emit_tool_status("id-1", "read_file", "done")
        finally:
            reset_safety_session(token)
        assert rec.frames == [
            {
                "type": "tool_status",
                "id": "id-1",
                "name": "read_file",
                "status": "done",
                "agent_id": "codey",
            }
        ]

    async def test_no_session_is_a_no_op(self):
        await emit_tool_status("id-1", "read_file", "done")

    async def test_no_emit_fn_is_a_no_op(self):
        token = install_safety_session(make_session(emit=None))
        try:
            await emit_tool_status("id-1", "read_file", "done")
        finally:
            reset_safety_session(token)


class TestClientParserContract:
    """The frame must survive `parseToolJsonFrame` (chatWs.ts:256-277), which
    drops it — as `{kind: 'unknown'}` — unless every one of these holds."""

    @staticmethod
    def _parse(raw: str) -> dict[str, Any] | None:
        """A faithful re-implementation of the two guards the SPA applies."""
        payload = json.loads(raw)
        type_ = str(payload.get("type") or "")
        id_ = str(payload.get("id") or "")
        name = str(payload.get("name") or "")
        if type_ != "tool_status" or not id_ or not name:
            return None
        status = str(payload.get("status") or "")
        if status not in CLIENT_TOOL_STATUSES:
            return None
        return {
            "kind": "tool_status",
            "id": id_,
            "name": name,
            "status": status,
            "agentId": str(payload["agent_id"]) if payload.get("agent_id") else None,
        }

    @pytest.mark.parametrize(
        "agent_id", ["codey", "cli_agent", "hermes", "sdlc_handoff"], ids=str
    )
    @pytest.mark.parametrize("result", ["ok", "DENIED: nope", {"error": "boom"}])
    async def test_every_emitted_frame_is_parseable_by_the_client(
        self, agent_id, result
    ):
        rec = Recorder()
        token = install_safety_session(
            make_session(agent_id=agent_id, channel=CHANNEL_CLI, emit=rec)
        )
        hooks = ToolPhaseHooks()
        agent = Agent(name=agent_id or "anon")
        context = make_context()
        try:
            await hooks.on_tool_start(context, agent, READ_FILE_TOOL)
            await hooks.on_tool_end(context, agent, READ_FILE_TOOL, result)
        finally:
            reset_safety_session(token)

        assert len(rec.frames) == 2
        for frame in rec.frames:
            assert set(frame) >= {"type", "id", "name", "status"}
            assert frame["status"] in CLIENT_TOOL_STATUSES
            assert frame["id"], "chatWs.ts:267 drops a frame with an empty id"
            assert frame["name"], "chatWs.ts:267 drops a frame with an empty name"
            assert self._parse(json.dumps(frame)) is not None

    async def test_statuses_emitted_across_a_turn_stay_inside_the_client_set(self):
        rec = Recorder()
        token = install_safety_session(make_session(emit=rec))
        hooks = ToolPhaseHooks()
        agent = Agent(name="codey")
        try:
            for call_id, result in (
                ("c1", "ok"),
                ("c2", f"{DENIED_RESULT_PREFIX}tool call 'x' was not approved"),
                ("c3", json.dumps({"error": "Execution failed: boom"})),
            ):
                context = make_context(call_id)
                await hooks.on_tool_start(context, agent, READ_FILE_TOOL)
                await hooks.on_tool_end(context, agent, READ_FILE_TOOL, result)
        finally:
            reset_safety_session(token)

        assert rec.statuses() == [
            "running",
            "done",
            "running",
            "error",
            "running",
            "error",
        ]
        assert set(rec.statuses()) <= CLIENT_TOOL_STATUSES

    def test_client_status_set_matches_the_spa_literal(self):
        """Trip-wire for the cross-language contract: the SPA's union is
        `ToolStatus = 'running' | 'allowed' | 'denied' | 'error'` plus 'done'."""
        assert {
            "running",
            "allowed",
            "done",
            "denied",
            "error",
        } == CLIENT_TOOL_STATUSES

    def test_the_sdk_actually_fires_agent_hooks_on_tool_start_and_end(self):
        """Guards the wiring assumption itself: `Agent.hooks` exists, is
        type-checked in `__post_init__`, and carries the two callbacks we
        override. If the SDK ever renames or re-poses them, this fails here
        rather than silently in production."""
        agent = Agent(name="codey", hooks=ToolPhaseHooks())
        assert isinstance(agent.hooks, AgentHooksBase)
        assert callable(agent.hooks.on_tool_start)
        assert callable(agent.hooks.on_tool_end)
        # The SDK dispatches `agent.hooks.on_tool_start(tool_context, agent,
        # func_tool)` / `.on_tool_end(..., final_result)`
        # (agents/_run_impl.py:717-726, 787-796) — positionally, not by kwarg.
        assert READ_FILE_TOOL.name == "read_file"
        assert isinstance(READ_FILE_TOOL, FunctionTool)

    def test_send_fn_returns_a_readable_tool_name_for_any_tool_shape(self):
        from swarm.core.turn_phase import _tool_name

        assert _tool_name(READ_FILE_TOOL) == "read_file"
        assert _tool_name(read_file) == "read_file"
        assert _tool_name(object()) == "tool"


# =============================================================================
# End-to-end: a real SDK Runner really does drive the hooks
# =============================================================================


class _OneShotToolCallModel(Model):
    """A stub ``Model`` that asks for two *same-named* parallel tool calls on its
    first turn, then returns a plain assistant message.

    This is the collision case, driven by the real SDK rather than by calling
    the hooks by hand: the SDK fans the two calls out through
    ``asyncio.gather`` (``agents/_run_impl.py:717-726`` and the
    ``execute_function_tool_calls`` gather), so if the minted keys ever
    regressed to something name-derived this is the test that would notice.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def get_response(
        self,
        system_instructions,  # noqa: ARG002
        input,  # noqa: ARG002
        model_settings,  # noqa: ARG002
        tools,  # noqa: ARG002
        output_schema,  # noqa: ARG002
        handoffs,  # noqa: ARG002
        tracing,  # noqa: ARG002
        *,
        previous_response_id,  # noqa: ARG002
        conversation_id,  # noqa: ARG002
        prompt,  # noqa: ARG002
    ):
        self.calls += 1
        usage = Usage(requests=1, input_tokens=1, output_tokens=1, total_tokens=2)
        if self.calls == 1:
            return ModelResponse(
                output=[
                    ResponseFunctionToolCall(
                        call_id="call_A",
                        name="read_file",
                        arguments='{"path": "a.txt"}',
                        type="function_call",
                    ),
                    ResponseFunctionToolCall(
                        call_id="call_B",
                        name="read_file",
                        arguments='{"path": "b.txt"}',
                        type="function_call",
                    ),
                ],
                usage=usage,
                response_id="resp_1",
            )
        return ModelResponse(
            output=[
                ResponseOutputMessage(
                    id="msg_1",
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[
                        ResponseOutputText(annotations=[], text="done", type="output_text")
                    ],
                )
            ],
            usage=usage,
            response_id="resp_2",
        )

    async def stream_response(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError


class _ProbeBlueprint(ApiKindBase):
    """A minimal blueprint that takes the ``ApiKindBase.run`` chokepoint."""

    def __init__(self) -> None:
        super().__init__(blueprint_id="probe")

    def create_starting_agent(self, mcp_servers=None):  # noqa: ARG002
        return Agent(
            name="probe",
            instructions="probe",
            model=_OneShotToolCallModel(),
            tools=[function_tool(read_file, name_override="read_file")],
        )


class TestRunnerIntegration:
    """The wiring test. Everything above exercises ``ToolPhaseHooks`` directly;
    this proves the SDK actually calls it once the chokepoint installs it."""

    @pytest.mark.parametrize(
        "channel", [CHANNEL_API, CHANNEL_CLI, CHANNEL_REMOTE], ids=str
    )
    async def test_a_real_run_emits_running_then_done_per_parallel_call(self, channel):
        rec = Recorder()
        token = install_safety_session(
            make_session(agent_id="probe", channel=channel, emit=rec)
        )
        try:
            chunks = [
                chunk
                async for chunk in _ProbeBlueprint().run(
                    [{"role": "user", "content": "go"}]
                )
            ]
        finally:
            reset_safety_session(token)

        assert chunks[-1]["messages"][0]["content"] == "done"
        assert rec.statuses() == ["running", "running", "done", "done"]
        # Two same-named calls, two distinct rows — the whole point.
        assert len({f["id"] for f in rec.frames}) == 2
        assert {f["name"] for f in rec.frames} == {"read_file"}
        assert {f["agent_id"] for f in rec.frames} == {"probe"}
        assert set(rec.statuses()) <= CLIENT_TOOL_STATUSES

    async def test_hooks_do_not_stack_across_repeated_runs(self):
        """The chokepoint runs on every turn. A second turn must not leave two
        ``ToolPhaseHooks`` on one agent (which would double every frame)."""
        rec = Recorder()
        token = install_safety_session(make_session(agent_id="probe", emit=rec))
        try:
            for _ in range(2):
                async for _ in _ProbeBlueprint().run(
                    [{"role": "user", "content": "go"}]
                ):
                    pass
        finally:
            reset_safety_session(token)
        # 4 frames per turn, not 8 — a stacked hook would emit 8 per turn.
        assert len(rec.frames) == 8
        assert rec.statuses() == ["running", "running", "done", "done"] * 2

    async def test_ids_are_scoped_to_one_turn_not_the_process(self):
        """Deliberate scope decision, pinned so nobody "fixes" it by accident:
        the counter is per-``ToolPhaseHooks``-instance, and ``run()`` builds a
        fresh Agent (hence a fresh hooks instance) each turn, so turn 2 reuses
        ``...:0`` / ``...:1``. That is correct: ``upsertToolCall`` is scoped to
        one assistant row, and every turn gets a fresh row, so reuse across
        turns cannot merge two turns' tools. Making the counter process-global
        would instead leak state across every seat in the process.
        """
        rec = Recorder()
        token = install_safety_session(make_session(agent_id="probe", emit=rec))
        try:
            for _ in range(2):
                async for _ in _ProbeBlueprint().run(
                    [{"role": "user", "content": "go"}]
                ):
                    pass
        finally:
            reset_safety_session(token)
        assert [f["id"] for f in rec.frames] == [
            "probe:read_file:0",
            "probe:read_file:1",
            "probe:read_file:0",
            "probe:read_file:1",
        ] * 2

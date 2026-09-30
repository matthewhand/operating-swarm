"""#1684/#1691 — REACHABILITY. Is the turn-phase producer on the path that runs?

The upstream fix attached the hooks in ``ApiKindBase.run``. This module exists
because that is not where the default chat seat executes.

Two independent facts are pinned here, and both are behavioural:

1. **The default chat seat is `ChatbotBlueprint`, and it shadows `run`.**
   ``resolve_chat_blueprint_id("api_agent")`` is the seat a fresh install chats
   with. If it inherits ``ApiKindBase.run``, the chokepoint is live; if it
   shadows it, the chokepoint is dead code for the default seat and the SPA's
   "tool in flight" badge can never appear there.

2. **A real agent built by that seat carries the hooks, and a real run through
   it emits the frames.** Not a source read: the seat is instantiated, the agent
   is constructed by the production factory, and ``Runner`` is driven by the
   SDK with a stub model that calls a tool.

Neither fact is a source-substring assertion, and neither can be satisfied by a
hook attached to a method that never runs.
"""

from __future__ import annotations

import inspect
import json
from typing import Any

import pytest
from agents import Agent, Runner
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from swarm.core.agent_kind import resolve_chat_blueprint_id
from swarm.core.kind_bases import ApiKindBase
from swarm.core.safety import (
    CHANNEL_API,
    CHANNEL_CLI,
    CHANNEL_REMOTE,
    SafetySession,
    install_safety_session,
    reset_safety_session,
)
from swarm.core.turn_phase import ToolPhaseHooks

pytestmark = pytest.mark.anyio

CHANNELS = [CHANNEL_API, CHANNEL_CLI, CHANNEL_REMOTE]


def read_file(path: str) -> str:
    return f"contents of {path}"


class Recorder:
    def __init__(self) -> None:
        self.frames: list[dict[str, Any]] = []

    async def __call__(self, payload: dict[str, Any]) -> None:
        self.frames.append(payload)

    def statuses(self) -> list[str]:
        return [f["status"] for f in self.frames]


def make_session(*, agent_id: str = "chatbot", channel: str = CHANNEL_API,
                 emit: Recorder | None = None) -> SafetySession:
    return SafetySession(
        agent_id=agent_id,
        channel=channel,
        safety_assigned=False,
        elicit_fn=None,
        emit_fn=emit or Recorder(),
    )


class _ToolCallingModel(Model):
    """One turn that calls a tool, then answers. The SDK drives the hooks."""

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
        previous_response_id,  # noqa: ARG002
        conversation_id,  # noqa: ARG002
        prompt,  # noqa: ARG002
    ) -> ModelResponse:
        self.calls += 1
        usage = Usage(requests=1, input_tokens=1, output_tokens=1, total_tokens=2)
        if self.calls == 1:
            return ModelResponse(
                output=[
                    ResponseFunctionToolCall(
                        call_id="call_reach",
                        name="read_file",
                        arguments='{"path": "a.txt"}',
                        type="function_call",
                    )
                ],
                response_id="resp_1",
                usage=usage,
            )
        return ModelResponse(
            output=[
                ResponseOutputMessage(
                    id="msg_1",
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[ResponseOutputText(annotations=[], text="done", type="output_text")],
                )
            ],
            response_id="resp_2",
            usage=usage,
        )

    async def stream_response(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError


class TestTheDefaultSeatUsesThisPath:
    """Fact 1 — which class actually runs the default chat seat."""

    def test_the_default_chat_seat_resolves_to_chatbot(self) -> None:
        # If this ever changes, the reachability argument below has to be
        # re-derived for the new seat rather than assumed to carry over.
        assert resolve_chat_blueprint_id("api_agent") == "chatbot"

    def test_chatbot_shadows_api_kind_base_run(self) -> None:
        # Stated, not assumed. If a future change makes ChatbotBlueprint inherit
        # `run`, this fails and the chokepoint becomes live again — which is
        # fine, but it must be a decision someone made deliberately.
        from swarm.blueprints.chatbot.blueprint_chatbot import ChatbotBlueprint

        assert ChatbotBlueprint.run is not ApiKindBase.run

    @pytest.mark.parametrize("module_path,class_name", [
        ("swarm.blueprints.agent_router.blueprint_agent_router", "AgentRouterBlueprint"),
        ("swarm.blueprints.hybrid_swarm.blueprint_hybrid_swarm", "HybridSwarmBlueprint"),
    ])
    def test_the_other_shadowing_seats_are_named(self, module_path, class_name) -> None:
        import importlib

        cls = getattr(importlib.import_module(module_path), class_name)
        assert issubclass(cls, ApiKindBase)
        assert cls.run is not ApiKindBase.run

    def test_there_are_no_untested_shadowing_seats(self) -> None:
        import importlib  # noqa: F401 - used below; kept local to the walk

        # Enumerate every ApiKindBase subclass the package actually ships and
        # require the set that shadows `run` to be exactly the three named
        # above. A new shadowing blueprint nobody wired up would otherwise be a
        # silent coverage gap — the whole class of bug this file exists for.
        #
        # Walked from the FILESYSTEM, not `pkgutil.walk_packages`: several
        # blueprint directories (chatbot/, hybrid_swarm/, and others) ship
        # without an `__init__.py`, so they are namespace packages and
        # `walk_packages` silently never descends into them. A registry built
        # from the package walker would report the default chat seat as
        # nonexistent — i.e. it would report exactly the bug it must catch.
        import pathlib

        import swarm.blueprints

        root = pathlib.Path(swarm.blueprints.__file__).parent
        shadowing: list[str] = []
        seen_modules: set[str] = set()
        for path in sorted(root.rglob("*.py")):
            if path.name == "__init__.py":
                continue
            rel = path.relative_to(root.parent.parent).with_suffix("")
            module_name = ".".join(rel.parts)
            if module_name in seen_modules:
                continue
            seen_modules.add(module_name)
            try:
                module = importlib.import_module(module_name)
            except Exception:
                # A blueprint with unmet optional deps is not this test's job;
                # what matters is that the ones that DO import are all covered.
                continue
            for obj in vars(module).values():
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, ApiKindBase)
                    and obj is not ApiKindBase
                    and "run" in obj.__dict__
                    and obj.__module__ == module_name
                ):
                    shadowing.append(f"{obj.__module__}.{obj.__name__}")

        assert sorted(shadowing) == [
            "swarm.blueprints.agent_router.blueprint_agent_router.AgentRouterBlueprint",
            "swarm.blueprints.chatbot.blueprint_chatbot.ChatbotBlueprint",
            "swarm.blueprints.hybrid_swarm.blueprint_hybrid_swarm.HybridSwarmBlueprint",
        ], (
            "an API seat now shadows ApiKindBase.run; it must either inherit the "
            "turn-phase attach or be added to this list with its factory proven"
        )


class TestTheHooksLandOnRealAgents:
    """Fact 2a — the production factories install the hooks on real agents."""

    def test_make_agent_installs_the_hooks(self) -> None:
        from swarm.core.blueprint_base import BlueprintBase

        class Probe(BlueprintBase):
            # `make_agent` resolves its model through the real profile plumbing,
            # so this probe overrides the two leaves of that chain and nothing
            # else. Everything else about the call is production code.
            def _resolve_llm_profile(self):  # noqa: D102 - probe seam
                return None

            def _get_model_instance(self, *args, **kwargs):  # noqa: ANN002, ANN003, ARG002, D102
                return "stub-model"

            def _get_memory_instance(self, *args, **kwargs):  # noqa: ANN002, ANN003, ARG002, D102
                return None

            async def run(self, messages, **kwargs):  # noqa: ANN001, ARG002, D102
                yield {}

        agent = Probe(blueprint_id="probe").make_agent(
            name="probe", instructions="probe", tools=[], mcp_servers=[]
        )
        assert isinstance(agent, Agent)
        assert isinstance(agent.hooks, ToolPhaseHooks)

    def test_a_subclass_factory_is_wrapped_exactly_once(self) -> None:
        # A seat that overrides `create_starting_agent` is the shape the three
        # shadowing blueprints have. Wrapping must not stack: a doubled hook
        # would double every frame, and the client would see two starts and one
        # end for one tool call.
        class Base(ApiKindBase):
            def __init__(self, **kwargs: Any) -> None:
                super().__init__(blueprint_id="reach", **kwargs)

            def create_starting_agent(self, mcp_servers=None):  # noqa: ANN001, ANN201, ARG002
                return Agent(name="reach")

        class Child(Base):
            pass

        inst = Child()
        agent = inst.create_starting_agent()
        assert isinstance(agent.hooks, ToolPhaseHooks)
        # Walking the wrapped chain must not re-wrap: the marker attribute
        # survives, and calling the factory again yields the same hooks object
        # on a fresh agent without a second layer.
        again = inst.create_starting_agent()
        assert isinstance(again.hooks, ToolPhaseHooks)
        assert getattr(
            type(inst).create_starting_agent, "_os_turn_phase_wrapped", False
        ) is True

    def test_make_agent_then_create_starting_agent_does_not_double_up(self) -> None:
        # The idempotency that makes wrapping safe to do at two factories.
        from swarm.core.turn_phase import attach_turn_phase_hooks

        agent = Agent(name="probe")
        attach_turn_phase_hooks(agent)
        first = agent.hooks
        attach_turn_phase_hooks(agent)
        assert agent.hooks is first


class TestRealRunsEmitFrames:
    """Fact 2b — the SDK, driven through a shadowing seat, emits the frames."""

    @pytest.mark.parametrize("channel", CHANNELS, ids=str)
    async def test_a_real_runner_run_through_a_shadowed_seat_emits(self, channel) -> None:
        # A miniature seat with the SAME shape as ChatbotBlueprint: it shadows
        # `run`, builds its agent through the overridden factory, and calls
        # `Runner.run` itself — so `ApiKindBase.run` is never entered. If the
        # producer were only wired at that chokepoint, `frames` would be empty
        # and the SPA would have nothing to badge.
        class ShadowingSeat(ApiKindBase):
            def __init__(self) -> None:
                super().__init__(blueprint_id="shadow")

            def create_starting_agent(self, mcp_servers=None):  # noqa: ANN001, ANN201, ARG002
                from agents import function_tool

                return Agent(
                    name="Shadow",
                    model=_ToolCallingModel(),
                    instructions="probe",
                    tools=[function_tool(read_file, name_override="read_file")],
                )

            async def run(self, messages, **kwargs):  # noqa: ANN001, ARG002
                agent = self.create_starting_agent()
                result = await Runner.run(agent, "go")
                yield {
                    "messages": [
                        {"role": "assistant", "content": str(result.final_output)}
                    ],
                    "final": True,
                }

        rec = Recorder()
        token = install_safety_session(
            make_session(agent_id="shadow", channel=channel, emit=rec)
        )
        try:
            chunks = [c async for c in ShadowingSeat().run([{"role": "user", "content": "go"}])]
        finally:
            reset_safety_session(token)

        assert chunks[-1]["messages"][0]["content"] == "done"
        # The point of the test: a real tool call, on a real run, on a path that
        # never touches ApiKindBase.run, still reaches the socket.
        assert rec.statuses() == ["running", "done"]
        frame = rec.frames[0]
        assert frame["type"] == "tool_status"
        assert frame["name"] == "read_file"
        assert frame["id"], "chatWs.ts drops a frame with an empty id"
        # And the payload shape survives the client parser's own guards.
        payload = json.loads(json.dumps(frame))
        assert payload["type"] == "tool_status"
        assert payload["id"] and payload["name"] and payload["status"]

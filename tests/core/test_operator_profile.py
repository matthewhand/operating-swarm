"""#1323 — operator About me profile normalize + chat injection."""

from __future__ import annotations

import sys

import pytest

from swarm.core.operator_profile import (
    OPERATOR_PROFILE_PREFIX,
    format_operator_profile,
    load_operator_profile,
    messages_with_operator_profile,
    messages_with_operator_profile_for_user,
)
from swarm.core.user_preferences import (
    OPERATOR_PROFILE_ABOUT_MAX,
    OPERATOR_PROFILE_KEY,
    coerce_values,
    merge_values,
    normalize_operator_profile,
    operator_profile_has_content,
    public_payload,
)


def test_normalize_drops_unknown_and_secret_keys():
    card = normalize_operator_profile(
        {
            "name": "  Matthew\n",
            "timezone": "Australia/Sydney",
            "about": "Prefer terse answers.",
            "api_key": "sk-nope",
            "extra": "drop me",
        }
    )
    assert card == {
        "name": "Matthew",
        "timezone": "Australia/Sydney",
        "about": "Prefer terse answers.",
    }
    assert "api_key" not in card
    assert "extra" not in card


def test_normalize_caps_and_strips_controls():
    card = normalize_operator_profile(
        {
            "name": "A" * 200,
            "timezone": "America/New_York\t",
            "about": "x" * (OPERATOR_PROFILE_ABOUT_MAX + 50),
        }
    )
    assert len(card["name"]) == 120
    assert card["timezone"] == "America/New_York"
    assert len(card["about"]) == OPERATOR_PROFILE_ABOUT_MAX


def test_empty_profile_formats_to_blank():
    assert format_operator_profile({}) == ""
    assert format_operator_profile(None) == ""
    assert operator_profile_has_content(normalize_operator_profile(None)) is False


def test_format_omits_empty_fields():
    body = format_operator_profile({"name": "Ada", "timezone": "", "about": "Be brief."})
    assert body.startswith(OPERATOR_PROFILE_PREFIX)
    assert "- Name: Ada" in body
    assert "Timezone" not in body
    assert "- Notes: Be brief." in body


def test_apply_operator_profile_to_agent_copies_card_onto_instructions():
    """Runner.run only receives the user turn, so the card must move onto instructions."""
    from swarm.core.operator_profile import apply_operator_profile_to_agent

    class _Agent:
        instructions = "You are a helpful chatbot."

    agent = _Agent()
    messages = messages_with_operator_profile(
        [{"role": "user", "content": "hello"}],
        {"name": "Ada", "about": "Be brief."},
    )
    apply_operator_profile_to_agent(agent, messages)
    assert agent.instructions.startswith(OPERATOR_PROFILE_PREFIX)
    assert "Ada" in agent.instructions
    assert "Be brief." in agent.instructions
    assert agent.instructions.endswith("You are a helpful chatbot.")
    apply_operator_profile_to_agent(agent, messages)
    assert agent.instructions.count(OPERATOR_PROFILE_PREFIX) == 1


def test_apply_operator_profile_skips_empty_and_callable_instructions():
    from swarm.core.operator_profile import apply_operator_profile_to_agent

    class _Agent:
        instructions = "stay"

    agent = _Agent()
    apply_operator_profile_to_agent(agent, [{"role": "user", "content": "hi"}])
    assert agent.instructions == "stay"

    class _Callable:
        def instructions(self):
            return "dynamic"

    callable_agent = _Callable()
    apply_operator_profile_to_agent(
        callable_agent,
        messages_with_operator_profile([{"role": "user", "content": "hi"}], {"name": "Ada"}),
    )
    assert callable(callable_agent.instructions)

    class _Unset:
        instructions = None

    unset = _Unset()
    apply_operator_profile_to_agent(
        unset,
        messages_with_operator_profile([{"role": "user", "content": "hi"}], {"name": "Ada"}),
    )
    assert isinstance(unset.instructions, str)
    assert unset.instructions.startswith(OPERATOR_PROFILE_PREFIX)
    assert "Ada" in unset.instructions


def test_inject_prepends_once_and_skips_empty():
    messages = [{"role": "user", "content": "hello"}]
    assert messages_with_operator_profile(messages, {}) == messages
    once = messages_with_operator_profile(messages, {"name": "Ada"})
    assert once[0]["role"] == "system"
    assert once[0]["content"].startswith(OPERATOR_PROFILE_PREFIX)
    assert once[1] == messages[0]
    twice = messages_with_operator_profile(once, {"name": "Ada"})
    assert sum(1 for m in twice if isinstance(m, dict) and str(m.get("content", "")).startswith(OPERATOR_PROFILE_PREFIX)) == 1


def test_coerce_and_public_payload_surface_operator_profile():
    bag = coerce_values({OPERATOR_PROFILE_KEY: {"name": "Ada", "api_key": "sk-nope"}})
    assert bag[OPERATOR_PROFILE_KEY]["name"] == "Ada"
    assert "api_key" not in bag[OPERATOR_PROFILE_KEY]
    payload = public_payload(principal="user:ada", guest=False, empty=False, values=bag)
    assert payload[OPERATOR_PROFILE_KEY]["name"] == "Ada"
    assert "sk-nope" not in str(payload)


def test_merge_replaces_operator_profile_object():
    current = {OPERATOR_PROFILE_KEY: {"name": "Old", "timezone": "UTC", "about": "x"}}
    merged = merge_values(current, {OPERATOR_PROFILE_KEY: {"name": "New"}})
    assert merged[OPERATOR_PROFILE_KEY] == {"name": "New", "timezone": "", "about": ""}


@pytest.mark.django_db
def test_load_and_inject_from_preference_row():
    from swarm.models import UserPreference

    UserPreference.objects.create(
        principal="user:ada",
        values={OPERATOR_PROFILE_KEY: {"name": "Ada", "timezone": "UTC", "about": "Be brief."}},
    )

    class _User:
        is_authenticated = True

        def get_username(self):
            return "ada"

    profile = load_operator_profile(user=_User())
    assert profile["name"] == "Ada"
    injected = messages_with_operator_profile_for_user(_User(), [{"role": "user", "content": "hi"}])
    assert injected[0]["content"].startswith(OPERATOR_PROFILE_PREFIX)
    assert "Ada" in injected[0]["content"]
    assert injected[1]["content"] == "hi"


@pytest.mark.django_db
def test_request_identity_loads_the_operator_card():
    from django.test import RequestFactory

    from swarm.core.operator_profile import messages_with_operator_profile_for_request
    from swarm.models import UserPreference

    UserPreference.objects.create(
        principal="user:admin",
        values={OPERATOR_PROFILE_KEY: {"name": "Ops", "timezone": "UTC"}},
    )
    request = RequestFactory().post("/v1/chat/completions")
    out = messages_with_operator_profile_for_request(
        request, [{"role": "user", "content": "hi"}]
    )
    assert out[0]["content"].startswith(OPERATOR_PROFILE_PREFIX)
    assert "Ops" in out[0]["content"]
    assert "- Timezone: UTC" in out[0]["content"]


class _ProfileAgent:
    def __init__(self, instructions: str) -> None:
        self.instructions = instructions


class _ProfileResult:
    final_output = "ok"


async def _capture_runner(agent=None, instruction=None, **kwargs):
    target = agent if agent is not None else kwargs.get("starting_agent")
    _capture_runner.seen = {
        "instructions": getattr(target, "instructions", None),
        "instruction": instruction if instruction is not None else kwargs.get("input"),
    }

    return _ProfileResult()


ROUTER_MODULE = "swarm.blueprints.agent_router.blueprint_agent_router"


def _engine_reads_router_module():
    """The one module object ``_run_swarm_agent`` reads its globals from.

    ``swarm.blueprints.agent_router.engines._RouterRef`` late-binds the
    blueprint module with ``importlib.import_module(...)`` on **every**
    attribute access, i.e. a ``sys.modules`` lookup — not a package-attribute
    lookup.

    That matters because ``swarm.core.blueprint_discovery.discover_blueprints``
    re-executes ``blueprint_agent_router.py`` from its file path and rebinds
    ``sys.modules[...]`` to a *second* module object for the same dotted name
    without touching the parent package attribute. After any test that runs
    discovery, ``from swarm.blueprints.agent_router import blueprint_agent_router``
    — and ``monkeypatch.setattr("swarm.blueprints.agent_router.blueprint_agent_router.X", ...)``,
    which pytest resolves the same way — hand back the stale pre-fork object
    while the engine reads the forked one. The patch then lands nowhere, the
    real ``agents.Agent`` gets built, and the About me card silently vanishes:
    a failure that only shows up once another test file has run discovery.

    Always patch what the engine reads. (The double import itself is a
    ``blueprint_discovery`` defect; this keeps the engine's documented
    monkeypatch seam honest in the meantime.)
    """
    import importlib

    return importlib.import_module(ROUTER_MODULE)


@pytest.mark.asyncio
async def test_api_kind_run_keeps_operator_card_on_instructions(monkeypatch):
    """#1323: ApiKindBase.run used to drop the prepended system card."""
    import agents

    from swarm.core.kind_bases import ApiKindBase

    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    monkeypatch.setattr(agents.Runner, "run", staticmethod(_capture_runner))

    class StubApi(ApiKindBase):
        metadata = {"name": "stub", "version": "1.0.0"}

        def create_starting_agent(self, _mcp_servers=None):
            return _ProfileAgent("Base instructions.")

    bp = StubApi("stub", config={})
    messages = messages_with_operator_profile(
        [{"role": "user", "content": "hello"}],
        {"name": "Ada", "timezone": "UTC"},
    )
    chunks = [c async for c in bp.run(messages)]
    assert chunks[-1]["final"] is True
    seen = _capture_runner.seen
    assert seen["instructions"].startswith(OPERATOR_PROFILE_PREFIX)
    assert "Ada" in seen["instructions"]
    assert "Base instructions." in seen["instructions"]
    assert seen["instruction"] == "hello"


@pytest.mark.asyncio
async def test_chatbot_run_keeps_operator_card_on_instructions(monkeypatch):
    """#1323: ChatbotBlueprint.run only forwarded messages[-1] and dropped the card."""
    import agents

    from swarm.blueprints.chatbot.blueprint_chatbot import ChatbotBlueprint

    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    monkeypatch.setattr(agents.Runner, "run", staticmethod(_capture_runner))

    bp = ChatbotBlueprint("chatbot", config={})
    bp.create_starting_agent = lambda *_a, **_k: _ProfileAgent("You are a helpful chatbot.")
    messages = messages_with_operator_profile(
        [{"role": "user", "content": "hello"}],
        {"name": "Ada", "about": "Be brief."},
    )
    chunks = [c async for c in bp.run(messages)]
    assert chunks[-1]["final"] is True
    seen = _capture_runner.seen
    assert seen["instructions"].startswith(OPERATOR_PROFILE_PREFIX)
    assert "Ada" in seen["instructions"]
    assert "Be brief." in seen["instructions"]
    assert "helpful chatbot" in seen["instructions"]
    assert seen["instruction"] == "hello"


@pytest.mark.asyncio
async def test_swarm_runner_keeps_operator_card_on_coordinator_and_persona(monkeypatch):
    """#1323: swarms compose about_me at build time and still drop the Settings card."""
    import agents

    from swarm.blueprints.agent_router import engines as engines_mod
    from swarm.blueprints.agent_router.engines import RouterEnginesMixin

    monkeypatch.setattr(agents.Runner, "run", staticmethod(_capture_runner))
    monkeypatch.setattr(
        engines_mod,
        "instructions_with_about_me",
        lambda text, *_a, **_k: text or "",
    )

    created: list = []

    class _FakeAgent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            created.append(self)

    router_mod = _engine_reads_router_module()
    monkeypatch.setattr(router_mod, "HAS_AGENTS", True)
    monkeypatch.setattr(router_mod, "Agent", _FakeAgent)
    monkeypatch.setattr(router_mod, "function_tool", lambda fn: fn)

    class _Host(RouterEnginesMixin):
        _config: dict = {}

        def _resolve_llm_profile(self):
            return "default"

        def _get_model_instance(self, _name):
            return object()

    seat = type("Seat", (), {})()
    seat.name = "Squad"
    seat.instructions = "Coordinate the team."
    seat.personas = [{"name": "Researcher", "instructions": "Find sources."}]
    messages = messages_with_operator_profile(
        [{"role": "user", "content": "hello"}],
        {"name": "Grace"},
    )
    chunks = [c async for c in _Host()._run_swarm_agent(seat, "hello", messages)]
    assert chunks[-1]["content"] == "ok"
    seen = _capture_runner.seen
    assert seen["instructions"].startswith(OPERATOR_PROFILE_PREFIX)
    assert "Grace" in seen["instructions"]
    assert "Coordinate the team." in seen["instructions"]
    assert seen["instruction"] == "hello"
    assert seat.instructions == "Coordinate the team."
    personas = [agent for agent in created if getattr(agent, "name", "") == "Researcher"]
    assert personas and personas[0].instructions.startswith(OPERATOR_PROFILE_PREFIX)
    assert "Find sources." in personas[0].instructions


@pytest.mark.asyncio
async def test_swarm_card_survives_a_relabelled_router_module(monkeypatch):
    """Order independence: the swarm engine must not be patch-order dependent.

    Regression for cross-test pollution. ``blueprint_discovery`` re-executes
    ``blueprint_agent_router.py`` under a fresh module object bound to the
    same dotted name, so ``sys.modules[ROUTER_MODULE]`` and the parent package
    attribute can be two different modules (see
    ``_engine_reads_router_module``). The engine reads the former.

    This test installs exactly that split — a relabelled ``sys.modules``
    entry with the *real* ``agents.Agent`` behind it, leaving the
    package-attribute module untouched — then asserts the same coordinator and
    persona behaviour the suite asserts in the unforked case. With a seam that
    patches the package attribute instead of the module the engine reads, the
    real ``agents.Agent`` is constructed here, blows up on the stub model, and
    the run silently degrades to the canned text block: the exact failure that
    only reproduced when ``tests/test_agent_router.py`` ran first.
    """
    import agents
    import types

    from swarm.blueprints.agent_router import engines as engines_mod
    from swarm.blueprints.agent_router.engines import RouterEnginesMixin

    monkeypatch.setattr(agents.Runner, "run", staticmethod(_capture_runner))
    monkeypatch.setattr(
        engines_mod,
        "instructions_with_about_me",
        lambda text, *_a, **_k: text or "",
    )

    created: list = []

    class _FakeAgent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            created.append(self)

    # The polluted shape: a second module object under the same dotted name,
    # carrying the globals the engine actually reads — unpatched.
    relabelled = types.ModuleType(ROUTER_MODULE)
    relabelled.__dict__.update(
        {
            "HAS_AGENTS": True,
            "Agent": agents.Agent,
            "function_tool": agents.function_tool,
            "logger": _engine_reads_router_module().logger,
        }
    )
    monkeypatch.setitem(sys.modules, ROUTER_MODULE, relabelled)
    assert _engine_reads_router_module() is relabelled

    router_mod = _engine_reads_router_module()
    monkeypatch.setattr(router_mod, "HAS_AGENTS", True)
    monkeypatch.setattr(router_mod, "Agent", _FakeAgent)
    monkeypatch.setattr(router_mod, "function_tool", lambda fn: fn)

    class _Host(RouterEnginesMixin):
        _config: dict = {}

        def _resolve_llm_profile(self):
            return "default"

        def _get_model_instance(self, _name):
            return object()

    seat = type("Seat", (), {})()
    seat.name = "Squad"
    seat.instructions = "Coordinate the team."
    seat.personas = [{"name": "Researcher", "instructions": "Find sources."}]
    messages = messages_with_operator_profile(
        [{"role": "user", "content": "hello"}],
        {"name": "Grace"},
    )
    chunks = [c async for c in _Host()._run_swarm_agent(seat, "hello", messages)]
    assert chunks[-1]["content"] == "ok", (
        "the engine read a module object the seam did not patch — the About me "
        "card and the fake Agent were lost to cross-test pollution"
    )
    seen = _capture_runner.seen
    assert seen["instructions"].startswith(OPERATOR_PROFILE_PREFIX)
    assert "Grace" in seen["instructions"]
    assert "Coordinate the team." in seen["instructions"]
    personas = [agent for agent in created if getattr(agent, "name", "") == "Researcher"]
    assert personas and personas[0].instructions.startswith(OPERATOR_PROFILE_PREFIX)
    assert "Find sources." in personas[0].instructions

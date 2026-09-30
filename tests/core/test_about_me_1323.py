"""#1323 — about_me preference and [Operator profile] instruction injection."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from swarm.core.operator_profile import (
    OPERATOR_PROFILE_FOOTER,
    OPERATOR_PROFILE_HEADER,
    format_about_me_block,
    instructions_with_about_me,
    load_about_me,
)
from swarm.core.user_preferences import (
    ABOUT_ME_KEY,
    ABOUT_ME_MAX,
    coerce_values,
    merge_values,
    normalize_about_me,
    normalize_operator_profile,
    public_payload,
    secret_looking_content,
)


def test_normalize_about_me_bounds_length_and_rejects_secret_content():
    assert normalize_about_me(None) == ""
    assert normalize_about_me("  \n") == ""
    assert normalize_about_me("Works nights.") == "Works nights."
    assert len(normalize_about_me("x" * (ABOUT_ME_MAX + 40))) == ABOUT_ME_MAX
    assert normalize_about_me("password=hunter2") == ""
    assert normalize_about_me("api_key=sk-abcdefghijklmnop") == ""
    assert secret_looking_content("I like short answers.") is False
    assert normalize_about_me("note\x00 with null") == "note with null"


def test_operator_profile_field_values_reject_secret_content():
    card = normalize_operator_profile(
        {
            "name": "Ada",
            "timezone": "UTC",
            "about": "password=hunter2",
        }
    )
    assert card == {"name": "Ada", "timezone": "UTC", "about": ""}


def test_coerce_merge_and_public_payload_surface_about_me():
    """``about_me`` is a registered, surfaced first-class preference.

    Intent (#1323): the key must be *advertised* in the published registry —
    that is what makes the field first-class rather than an extras-bag row —
    and its value must ride the payload next to it.

    Position is deliberately not asserted. ``PREF_REGISTRY`` order is an
    append-only published contract (documented on ``PREF_REGISTRY`` and pinned
    key-for-key by ``tests/core/test_user_preferences.py`` and
    ``tests/views/test_preferences_api.py``), and a later preference —
    ``activity_log_visibility`` — legitimately landed after ``about_me``. A
    "I am the last key" claim encodes no requirement of #1323 and rots on the
    next append, so it is registration, not slot, that is pinned here.
    """
    bag = coerce_values({ABOUT_ME_KEY: "  Works nights.  ", "api_key": "sk-nope"})
    assert bag[ABOUT_ME_KEY] == "Works nights."
    assert "api_key" not in bag
    merged = merge_values(bag, {ABOUT_ME_KEY: ""})
    assert merged[ABOUT_ME_KEY] == ""
    payload = public_payload(
        principal="user:ada",
        guest=False,
        empty=False,
        values={ABOUT_ME_KEY: "Be brief."},
    )
    assert payload[ABOUT_ME_KEY] == "Be brief."
    entry = next(
        (item for item in payload["registry"] if item["key"] == ABOUT_ME_KEY),
        None,
    )
    assert entry is not None, "about_me must be advertised in the preferences registry"
    assert entry["type"] == "about_me_string"


def test_empty_about_me_adds_no_instruction_block():
    assert format_about_me_block("") == ""
    assert format_about_me_block(None) == ""
    assert instructions_with_about_me("Be helpful.", "") == "Be helpful."
    assert instructions_with_about_me("Be helpful.", "   ") == "Be helpful."


def test_instructions_append_delimited_block_once():
    composed = instructions_with_about_me("Be helpful.", "Works nights.")
    assert composed.startswith("Be helpful.")
    assert OPERATOR_PROFILE_HEADER in composed
    assert "Works nights." in composed
    assert composed.strip().endswith(OPERATOR_PROFILE_FOOTER)
    again = instructions_with_about_me(composed, "Works nights.")
    assert again.count(OPERATOR_PROFILE_HEADER) == 1


def test_non_string_instructions_pass_through():
    def dynamic(_ctx):
        return "later"

    assert instructions_with_about_me(dynamic, "Works nights.") is dynamic


@pytest.mark.django_db
def test_load_about_me_is_per_principal():
    from swarm.models import UserPreference

    UserPreference.objects.create(
        principal="user:ada",
        values={ABOUT_ME_KEY: "Ada's note"},
    )
    UserPreference.objects.create(
        principal="user:admin",
        values={ABOUT_ME_KEY: "Admin note"},
    )

    class _User:
        is_authenticated = True

        def get_username(self):
            return "ada"

    assert load_about_me(user=_User()) == "Ada's note"
    assert load_about_me(principal="user:admin") == "Admin note"


@pytest.mark.django_db
def test_make_agent_appends_block_to_composed_instructions():
    from swarm.core.blueprint_base import BlueprintBase
    from swarm.core.user_preferences import primary_operator_principal
    from swarm.models import UserPreference

    principal = primary_operator_principal()
    UserPreference.objects.create(
        principal=principal,
        values={ABOUT_ME_KEY: "Works nights."},
    )

    class _Bp(BlueprintBase):
        async def run(self, messages, **kwargs):
            if False:
                yield {}

        @property
        def metadata(self):
            return {}

    bp = _Bp("about_me_test", config={"llm": {}, "settings": {}})
    captured: dict = {}

    class _Agent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    with (
        patch.object(bp, "_get_model_instance", return_value=object()),
        patch.object(bp, "_get_memory_instance", return_value=None),
        patch("agents.Agent", _Agent),
    ):
        bp.make_agent("Tester", "Be helpful.", [])

    text = captured["instructions"]
    assert text.startswith("Be helpful.")
    assert OPERATOR_PROFILE_HEADER in text
    assert "Works nights." in text
    assert text.strip().endswith(OPERATOR_PROFILE_FOOTER)


@pytest.mark.django_db
def test_make_agent_skips_block_when_about_me_empty():
    from swarm.core.blueprint_base import BlueprintBase

    class _Bp(BlueprintBase):
        async def run(self, messages, **kwargs):
            if False:
                yield {}

        @property
        def metadata(self):
            return {}

    bp = _Bp("about_me_empty", config={"llm": {}, "settings": {}})
    captured: dict = {}

    class _Agent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    with (
        patch.object(bp, "_get_model_instance", return_value=object()),
        patch.object(bp, "_get_memory_instance", return_value=None),
        patch("agents.Agent", _Agent),
    ):
        bp.make_agent("Tester", "Be helpful.", [])

    assert captured["instructions"] == "Be helpful."


@pytest.mark.django_db
def test_chatbot_and_agent_router_compose_the_block():
    from swarm.blueprints.agent_router.blueprint_agent_router import AgentRouterBlueprint
    from swarm.blueprints.chatbot.blueprint_chatbot import ChatbotBlueprint
    from swarm.core.user_preferences import primary_operator_principal
    from swarm.models import UserPreference

    UserPreference.objects.create(
        principal=primary_operator_principal(),
        values={ABOUT_ME_KEY: "Works nights."},
    )

    class _Agent:
        def __init__(self, **kwargs):
            tools = kwargs.pop("tools", None)
            self.tools = list(tools or [])
            self.__dict__.update(kwargs)

    with (
        patch.object(ChatbotBlueprint, "_get_model_instance", return_value=object()),
        patch("swarm.blueprints.chatbot.blueprint_chatbot.Agent", _Agent),
    ):
        bot = ChatbotBlueprint("chatbot", config={"llm": {}, "settings": {}})
        agent = bot.create_starting_agent([])
    assert OPERATOR_PROFILE_HEADER in agent.instructions
    assert "Works nights." in agent.instructions

    with (
        patch.object(AgentRouterBlueprint, "load_designed_agents", lambda self: None),
        patch.object(AgentRouterBlueprint, "_get_model_instance", lambda self, _name: object()),
        patch("swarm.blueprints.agent_router.blueprint_agent_router.Agent", _Agent),
    ):
        router = AgentRouterBlueprint("agent_router", config={"llm": {}, "settings": {}})
    researcher = router._agents["researcher"]
    lead = router._agents["router"]
    assert OPERATOR_PROFILE_HEADER in researcher.instructions
    assert "Works nights." in researcher.instructions
    assert OPERATOR_PROFILE_HEADER in lead.instructions
    assert "Works nights." in lead.instructions

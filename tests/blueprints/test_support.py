"""Support blueprint — role marker, as_tool wiring, deterministic chips."""

from __future__ import annotations

import pytest

from swarm.blueprints.common import cli_fusion_support as fusion
from swarm.blueprints.common.support_blueprint import (
    CLICK_BUBBLE_TO_EDIT,
    SUPPORT_SKILL_FIXTURE,
    SUPPORT_SKILL_NAME,
    support_turn_context,
    support_turn_reply,
)
from swarm.blueprints.support.blueprint_support import (
    SUPPORT_INSTRUCTIONS,
    SupportBlueprint,
)
from swarm.core import skills
from swarm.core.blueprint_base import BlueprintBase


async def _collect(gen):
    return [c async for c in gen]


def _final_content(chunks):
    text = None
    for chunk in chunks:
        msgs = chunk.get("messages") if isinstance(chunk, dict) else None
        if msgs and msgs[0].get("content") is not None:
            text = msgs[0]["content"]
    return text


@pytest.fixture(autouse=True)
def _test_mode(monkeypatch):
    monkeypatch.setenv("SWARM_TEST_MODE", "1")


def test_metadata_role_is_support():
    assert SupportBlueprint.metadata["role"] == "support"
    assert SupportBlueprint.metadata["name"] == "support"
    assert SupportBlueprint.metadata["rail"] is True
    assert issubclass(SupportBlueprint, BlueprintBase)


def test_starting_agent_uses_as_tool_not_cli_seats():
    bp = SupportBlueprint(blueprint_id="support")
    agent = bp.create_starting_agent([])
    names = [getattr(t, "name", None) or getattr(t, "__name__", "") for t in (agent.tools or [])]
    joined = " ".join(str(n) for n in names)
    assert "create_blueprint_from_nl" in joined or any("create_blueprint" in str(n).lower() for n in names)
    assert "consult_product_guide" in joined or any("product" in str(n).lower() for n in names)
    assert "consult_blueprint_coder" in joined or any("blueprint" in str(n).lower() for n in names)
    assert "grok" not in joined.lower()
    assert "omb" not in joined.lower()
    assert "rakazo" not in joined.lower()


async def test_empty_run_is_action_chips_not_config_dump():
    bp = SupportBlueprint(blueprint_id="support")
    chunks = await _collect(bp.run([]))
    text = _final_content(chunks)
    assert "[New team](/teams/launch/)" in text
    assert "[Set inference](/settings/)" in text
    assert "[Write blueprint](/agent-creator/)" in text
    assert "**Support**" not in text
    assert "**Agents**" not in text
    assert "**Gate** —" not in text
    assert "Welcome —" not in text


def test_support_instructions_cover_the_journey():
    text = SUPPORT_INSTRUCTIONS
    lowered = text.lower()
    assert "ONBOARD_JOURNEY_CLI_API_REMOTE" in text
    assert "create a team" in lowered
    assert "engineer" in lowered and "tester" in lowered
    assert "add a remote" in lowered
    assert "wire a cli" in lowered
    assert "SUPPORT_NL_BLUEPRINT_NO_USER_PYTHON" in text
    assert "create_blueprint_from_nl" in text
    assert "socratic" in lowered or "```question" in lowered
    assert "add as agent" in lowered
    assert "save as blueprint" in lowered
    assert "chief of staff" in lowered
    assert "hermes" in lowered
    assert "openmousbot" in lowered
    assert "herdr" in lowered
    assert "one-pane" in lowered or "one pane" in lowered
    assert ":8001" not in text


async def test_journey_prompts_include_honest_hints():
    bp = SupportBlueprint(blueprint_id="support")
    team = await _collect(bp.run([{"role": "user", "content": "Create a team"}]))
    team_text = _final_content(team)
    assert "```question" in team_text
    assert "team-purpose" in team_text
    assert "```swarm-nl-blueprint" not in team_text
    assert "```python" not in team_text
    assert "Chief of Staff" in SUPPORT_INSTRUCTIONS or "Chief of Staff" in team_text
    remote = await _collect(bp.run([{"role": "user", "content": "Add a remote"}]))
    remote_text = _final_content(remote)
    assert "Hermes" in remote_text
    assert "OpenMousBot" in remote_text
    assert "Herdr" in remote_text
    cli = await _collect(bp.run([{"role": "user", "content": "Wire a CLI"}]))
    cli_text = _final_content(cli)
    assert "list models" in cli_text.lower()
    assert "click-to-edit" in cli_text.lower() or "click the bubble" not in cli_text.lower()


async def test_ba_eng_tester_nl_create_hides_python():
    bp = SupportBlueprint(blueprint_id="support")
    chunks = await _collect(
        bp.run(
            [
                {
                    "role": "user",
                    "content": "Create a BA → Engineer → Tester workflow",
                }
            ]
        )
    )
    text = _final_content(chunks)
    assert "BA → Engineer → Tester" in text
    assert "```swarm-nl-blueprint" in text
    assert "```python" not in text
    assert '"userWrotePython": false' in text
    assert '"persisted": false' in text
    assert "Add as agent" in text
    assert "Save as blueprint" in text
    assert "Open in chat" not in text
    assert "ba" in text and "engineer" in text and "tester" in text


async def test_blueprint_ask_includes_python_fence():
    bp = SupportBlueprint(blueprint_id="support")
    chunks = await _collect(bp.run([{"role": "user", "content": "write a blueprint"}]))
    text = _final_content(chunks)
    assert "```python" in text
    assert "class FirstTeamBlueprint" in text
    assert "ApiKindBase" in text
    assert "from swarm.core.kind_bases import ApiKindBase" in text


def test_skill_is_discoverable_and_carries_fixture():
    found = skills.discover_skills()
    assert SUPPORT_SKILL_NAME in found
    skill = found[SUPPORT_SKILL_NAME]
    assert SUPPORT_SKILL_FIXTURE in skill.instructions
    assert "ONBOARD_JOURNEY_CLI_API_REMOTE" in skill.instructions
    assert "create a team" in skill.instructions.lower()
    assert "engineer" in skill.instructions.lower()
    assert "view / edit code" in skill.instructions.lower()
    assert "add a remote" in skill.instructions.lower()
    assert "wire a cli" in skill.instructions.lower()
    assert "SUPPORT_NL_BLUEPRINT_NO_USER_PYTHON" in skill.instructions
    assert "hermes" in skill.instructions.lower()
    assert "openmousbot" in skill.instructions.lower()
    assert "herdr" in skill.instructions.lower()
    assert "chief of staff" in skill.instructions.lower()
    assert ":8001" not in skill.instructions
    assert "use when" in skill.description.lower()


def test_apply_skill_to_prompt_attaches_support_skill():
    prompt, name = fusion.apply_skill_to_prompt("hello", {"skill": SUPPORT_SKILL_NAME})
    assert name == SUPPORT_SKILL_NAME
    assert SUPPORT_SKILL_FIXTURE in prompt


def test_support_context_includes_skill_fixture():
    ctx = support_turn_context("api", "how do I edit?")
    assert SUPPORT_SKILL_FIXTURE in ctx
    assert SUPPORT_SKILL_NAME in ctx


def test_support_blueprint_system_prompt_includes_fixture():
    bp = SupportBlueprint(blueprint_id="support")
    prompt = bp.system_prompt([{"role": "user", "content": "hi"}])
    assert SUPPORT_SKILL_FIXTURE in prompt
    assert "SKILL INSTRUCTIONS" in prompt


async def test_cli_mode_support_turn_does_not_claim_click_edit():
    bp = SupportBlueprint(blueprint_id="support")
    bp.set_params({"session_kind": "cli", "skill": SUPPORT_SKILL_NAME})
    chunks = await _collect(
        bp.run([{"role": "user", "content": "how do I edit that last bubble?"}])
    )
    text = _final_content(chunks)
    assert text
    assert CLICK_BUBBLE_TO_EDIT not in text.lower()
    assert "outside" in text.lower()


async def test_remote_mode_support_turn_does_not_claim_click_edit():
    bp = SupportBlueprint(blueprint_id="support")
    bp.set_params({"session_kind": "remote"})
    chunks = await _collect(bp.run([{"role": "user", "content": "can I edit this?"}]))
    assert CLICK_BUBBLE_TO_EDIT not in _final_content(chunks).lower()


def test_cli_reply_helper_never_says_click_edit():
    reply = support_turn_reply([{"role": "user", "content": "edit?"}], "cli")
    assert CLICK_BUBBLE_TO_EDIT not in reply.lower()

"""REQ-212: attach SKILL.md skills to API / Blueprint message lists."""

from swarm.core.skill_attach import (
    apply_skills_to_messages,
    blueprint_applies_own_skills,
)


def test_blueprint_applies_own_skills_for_cli_and_support():
    assert blueprint_applies_own_skills("cli_agent")
    assert blueprint_applies_own_skills("support")
    assert not blueprint_applies_own_skills("chatbot")
    assert not blueprint_applies_own_skills("api_agent")


def test_apply_skills_to_messages_prepends_bundled_skill():
    messages = [
        {"role": "system", "content": "hi"},
        {"role": "user", "content": "write the commit"},
    ]
    out, applied, missing = apply_skills_to_messages(
        messages, {"skills": ["conventional-commit"]}
    )
    assert applied == ["conventional-commit"]
    assert missing == []
    assert out[0]["content"] == "hi"
    assert "Conventional Commit" in out[1]["content"]
    assert out[1]["content"].rstrip().endswith("write the commit")


def test_apply_skills_to_messages_missing_is_honest():
    messages = [{"role": "user", "content": "go"}]
    out, applied, missing = apply_skills_to_messages(
        messages, {"skill": "nope-not-real"}
    )
    assert applied == []
    assert missing == ["nope-not-real"]
    assert out[0]["content"] == "go"


def test_resolve_skills_matches_name_case_insensitively():
    from swarm.core.skills import resolve_skills

    found, missing = resolve_skills({"skill": "Conventional-Commit"})
    assert missing == []
    assert [row.name for row in found] == ["conventional-commit"]


def test_self_applying_recipe_still_consumes_getting_started(tmp_path, monkeypatch):
    """CLI and Support apply requested skills themselves, but first-run still lands."""
    from swarm.core import agent_skills as store
    from swarm.core.skill_attach import attach_params_for_recipe

    monkeypatch.setenv("SWARM_AGENT_SKILLS_PATH", str(tmp_path / "agent_skills.json"))
    store.reset_agent_skills_cache()
    store.create_skill(
        "support",
        {"name": "welcome-tour", "instructions": "Greet the operator on first run."},
    )
    store.set_getting_started("support", {"skill": "welcome-tour"}, first_run=True)
    forwarded = attach_params_for_recipe(
        {"skills": ["reviewing-code"]},
        recipe_applies_own=True,
    )
    assert forwarded == {}
    out, applied, missing = apply_skills_to_messages(
        [{"role": "user", "content": "hello"}],
        forwarded,
        agent_id="support",
    )
    assert applied == ["welcome-tour"]
    assert missing == []
    assert "Greet the operator on first run." in out[0]["content"]
    assert "reviewing-code" not in out[0]["content"]
    assert store.peek_first_run_skill("support") is None
    store.reset_agent_skills_cache()


def test_apply_skills_to_messages_consumes_first_run_getting_started(tmp_path, monkeypatch):
    from swarm.core import agent_skills as store

    monkeypatch.setenv("SWARM_AGENT_SKILLS_PATH", str(tmp_path / "agent_skills.json"))
    store.reset_agent_skills_cache()
    store.create_skill(
        "codey",
        {"name": "welcome-tour", "instructions": "Greet the operator on first run."},
    )
    store.set_getting_started("codey", {"skill": "welcome-tour"}, first_run=True)
    messages = [{"role": "user", "content": "hello"}]
    out, applied, missing = apply_skills_to_messages(messages, {}, agent_id="codey")
    assert applied == ["welcome-tour"]
    assert missing == []
    assert "Greet the operator on first run." in out[0]["content"]
    assert store.peek_first_run_skill("codey") is None
    store.reset_agent_skills_cache()


def test_apply_skills_to_messages_applies_one_or_more():
    messages = [{"role": "user", "content": "task"}]
    out, applied, missing = apply_skills_to_messages(
        messages,
        {"skills": ["conventional-commit", "writing-changelog", "missing-skill"]},
    )
    assert applied == ["conventional-commit", "writing-changelog"]
    assert missing == ["missing-skill"]
    assert "Conventional Commit" in out[0]["content"]
    assert "changelog" in out[0]["content"].lower()

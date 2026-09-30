"""Per-agent skills store (#1392): CRUD, library attach, first-run mark."""

import pytest

from swarm.core import agent_skills as store
from swarm.core.skills import resolve_skills


@pytest.fixture(autouse=True)
def _isolate_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SKILLS_PATH", str(tmp_path / "agent_skills.json"))
    store.reset_agent_skills_cache()
    yield
    store.reset_agent_skills_cache()


def test_create_list_get_update_delete():
    created = store.create_skill(
        "codey",
        {
            "name": "welcome-tour",
            "description": "Walk the first conversation.",
            "instructions": "Greet the operator and list three first steps.",
        },
    )
    assert created["name"] == "welcome-tour"
    assert created["source"] == store.SOURCE_AUTHORED
    assert created["first_run"] is False
    assert "sk-" not in created["instructions"]

    listed = store.list_skills("codey")
    assert [row["name"] for row in listed] == ["welcome-tour"]
    assert store.get_skill("codey", "welcome-tour")["description"].startswith("Walk")

    patched = store.update_skill(
        "codey",
        "welcome-tour",
        {"instructions": "Keep the welcome shorter."},
    )
    assert patched["instructions"] == "Keep the welcome shorter."

    assert store.delete_skill("codey", "welcome-tour") is True
    assert store.list_skills("codey") == []
    assert store.get_skill("codey", "welcome-tour") is None


def test_duplicate_name_is_rejected():
    store.create_skill(
        "codey",
        {"name": "welcome-tour", "instructions": "Say hello."},
    )
    with pytest.raises(ValueError, match="already exists"):
        store.create_skill(
            "codey",
            {"name": "welcome-tour", "instructions": "Say hello again."},
        )


def test_secret_in_instructions_is_rejected():
    with pytest.raises(ValueError, match="secrets"):
        store.create_skill(
            "codey",
            {"name": "leaky", "instructions": "Call with Bearer sk-abcdefghijklmnopqrst"},
        )


def test_attach_library_skill_copies_prose_only():
    row = store.create_skill("codey", {"name": "conventional-commit"})
    assert row["name"] == "conventional-commit"
    assert row["source"] == store.SOURCE_LIBRARY
    assert "assets" not in row
    assert "Conventional" in row["instructions"] or "commit" in row["instructions"].lower()
    catalog = store.agent_skill_catalog("codey")
    assert "conventional-commit" in catalog
    assert catalog["conventional-commit"].assets == []


def test_attach_missing_library_skill_raises():
    with pytest.raises(KeyError, match="not found"):
        store.attach_library_skill("codey", "nope-not-real")


def test_getting_started_must_name_an_attached_skill():
    store.create_skill("codey", {"name": "welcome-tour", "instructions": "Say hi."})
    with pytest.raises(ValueError, match="gettingStarted.skill"):
        store.set_getting_started("codey", {"skill": "missing-skill"})
    payload = store.set_getting_started("codey", {"skill": "welcome-tour"}, first_run=True)
    assert payload["gettingStarted"] == {"skill": "welcome-tour"}
    assert payload["first_run_pending"] is True
    assert store.peek_first_run_skill("codey") == "welcome-tour"


def test_create_with_getting_started_flag():
    store.create_skill(
        "codey",
        {"name": "welcome-tour", "instructions": "Say hi.", "gettingStarted": True},
    )
    assert store.getting_started("codey") == {"skill": "welcome-tour"}


def test_delete_getting_started_skill_clears_mark():
    store.create_skill("codey", {"name": "welcome-tour", "instructions": "Say hi."})
    store.set_getting_started("codey", {"skill": "welcome-tour"}, first_run=True)
    store.delete_skill("codey", "welcome-tour")
    assert store.getting_started("codey") is None
    assert store.first_run_pending("codey") is False
    assert store.peek_first_run_skill("codey") is None


def test_skill_seat_prefers_agent_then_falls_back():
    assert store.skill_seat_from_params(
        {"agent": "starter-cli", "agent_id": "other"},
        "cli_agent",
    ) == "starter-cli"
    assert store.skill_seat_from_params({}, "api_agent") == "api_agent"
    assert store.skill_seat_from_params(None, "", None) is None


def test_first_run_requires_a_named_skill():
    with pytest.raises(ValueError, match="gettingStarted.skill"):
        store.set_getting_started("codey", None, first_run=True)
    assert store.first_run_pending("codey") is False


def test_unrelated_apply_does_not_consume_first_run():
    store.create_skill("codey", {"name": "welcome-tour", "instructions": "Say hi."})
    store.set_getting_started("codey", {"skill": "welcome-tour"}, first_run=True)
    store.consume_applied_first_run("codey", ["reviewing-code"])
    assert store.peek_first_run_skill("codey") == "welcome-tour"
    store.consume_applied_first_run("codey", ["welcome-tour"])
    assert store.peek_first_run_skill("codey") is None


def test_merge_and_clear_first_run():
    store.create_skill("codey", {"name": "welcome-tour", "instructions": "Say hi."})
    store.set_getting_started("codey", {"skill": "welcome-tour"})
    store.mark_getting_started_first_run("codey")
    merged = store.merge_pending_first_run("codey", {"skill": "reviewing-code"})
    assert merged["skills"][0] == "welcome-tour"
    store.clear_first_run("codey")
    assert store.peek_first_run_skill("codey") is None
    assert store.merge_pending_first_run("codey", {}) == {}


def test_resolve_skills_overlays_agent_prose():
    store.create_skill(
        "codey",
        {"name": "seat-only", "instructions": "Use this seat-only skill."},
    )
    found, missing = resolve_skills({"skill": "seat-only"}, agent_id="codey")
    assert missing == []
    assert [row.name for row in found] == ["seat-only"]
    assert "seat-only" in found[0].instructions or found[0].instructions == "Use this seat-only skill."
    found_lib, missing_lib = resolve_skills({"skill": "seat-only"})
    assert found_lib == []
    assert missing_lib == ["seat-only"]

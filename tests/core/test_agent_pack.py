"""Agent pack validation (#1392): selected skills as prose + gettingStarted."""

import pytest

from swarm.core import agent_skills as skills_store
from swarm.core.agent_pack import (
    PackValidationError,
    build_pack,
    import_pack,
    validate_pack,
)


@pytest.fixture(autouse=True)
def _isolate_skills(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SKILLS_PATH", str(tmp_path / "agent_skills.json"))
    skills_store.reset_agent_skills_cache()
    yield
    skills_store.reset_agent_skills_cache()


def _prose_skill(name: str = "welcome-tour", instructions: str = "Greet the operator.") -> dict:
    return {
        "name": name,
        "description": "First conversation.",
        "instructions": instructions,
    }


def test_validate_pack_accepts_prose_and_getting_started():
    pack = validate_pack(
        {
            "skills": [_prose_skill(), _prose_skill("review-notes", "Review the diff.")],
            "gettingStarted": {"skill": "welcome-tour"},
        }
    )
    assert pack["object"] == "agent_pack"
    assert pack["kind"] == "swarm-agent-pack"
    assert [row["name"] for row in pack["skills"]] == ["welcome-tour", "review-notes"]
    assert pack["gettingStarted"] == {"skill": "welcome-tour"}
    assert "assets" not in pack["skills"][0]
    assert "path" not in pack["skills"][0]


def test_missing_getting_started_skill_fails():
    with pytest.raises(PackValidationError, match="gettingStarted.skill") as exc:
        validate_pack({"skills": [_prose_skill()]})
    assert exc.value.code == "pack_getting_started_missing"


def test_getting_started_must_name_a_packed_skill():
    with pytest.raises(PackValidationError, match="must name a packed skill") as exc:
        validate_pack(
            {
                "skills": [_prose_skill()],
                "gettingStarted": {"skill": "not-packed"},
            }
        )
    assert exc.value.code == "pack_getting_started_missing"


def test_empty_skills_fails():
    with pytest.raises(PackValidationError, match="skills") as exc:
        validate_pack({"skills": [], "gettingStarted": {"skill": "welcome-tour"}})
    assert exc.value.code == "pack_skills_missing"


def test_binary_fields_are_refused():
    with pytest.raises(PackValidationError, match="prose only") as exc:
        validate_pack(
            {
                "skills": [{**_prose_skill(), "assets": ["helper.py"]}],
                "gettingStarted": {"skill": "welcome-tour"},
            }
        )
    assert exc.value.code == "pack_binaries"


def test_secret_in_packed_skill_fails():
    with pytest.raises(PackValidationError, match="secrets"):
        validate_pack(
            {
                "skills": [_prose_skill(instructions="Use Bearer sk-abcdefghijklmnopqrst")],
                "gettingStarted": {"skill": "welcome-tour"},
            }
        )


def test_build_pack_matches_library_skill_case_insensitively():
    pack = build_pack(
        "codey",
        skill_names=["Conventional-Commit"],
        getting_started="conventional-commit",
    )
    assert [row["name"] for row in pack["skills"]] == ["conventional-commit"]
    assert pack["gettingStarted"]["skill"] == "conventional-commit"
    assert pack["skills"][0]["instructions"]


def test_build_pack_uses_selected_attached_skills():
    skills_store.create_skill("codey", _prose_skill())
    skills_store.create_skill(
        "codey",
        {"name": "review-notes", "instructions": "Review the diff."},
    )
    skills_store.set_getting_started("codey", {"skill": "welcome-tour"})
    pack = build_pack("codey", skill_names=["welcome-tour"])
    assert [row["name"] for row in pack["skills"]] == ["welcome-tour"]
    assert pack["gettingStarted"]["skill"] == "welcome-tour"


def test_build_pack_fails_when_getting_started_not_selected():
    skills_store.create_skill("codey", _prose_skill())
    skills_store.create_skill(
        "codey",
        {"name": "review-notes", "instructions": "Review the diff."},
    )
    with pytest.raises(PackValidationError, match="must name a packed skill"):
        build_pack(
            "codey",
            skill_names=["review-notes"],
            getting_started={"skill": "welcome-tour"},
        )


def test_import_recreates_skills_and_marks_first_run():
    pack = validate_pack(
        {
            "skills": [_prose_skill(), _prose_skill("review-notes", "Review the diff.")],
            "gettingStarted": {"skill": "welcome-tour"},
        }
    )
    imported = import_pack("writer", pack)
    names = {row["name"] for row in imported["skills"]}
    assert names == {"welcome-tour", "review-notes"}
    assert imported["gettingStarted"] == {"skill": "welcome-tour"}
    assert imported["first_run_pending"] is True
    assert skills_store.peek_first_run_skill("writer") == "welcome-tour"
    welcome = skills_store.get_skill("writer", "welcome-tour")
    assert welcome["source"] == skills_store.SOURCE_PACK
    assert welcome["first_run"] is True
    assert welcome["instructions"] == "Greet the operator."

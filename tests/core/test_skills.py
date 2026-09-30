"""Tests for the skills core (discovery, parsing, prompt composition)."""
from pathlib import Path

import pytest

from swarm.core import skills

SKILL_MD = """---
name: haiku
description: Reply with a 5-7-5 haiku.
---
Respond with exactly three lines forming a 5-7-5 haiku. No other text.
"""


def test_parse_skill_md_reads_frontmatter_and_body():
    s = skills.parse_skill_md(SKILL_MD)
    assert s.name == "haiku"
    assert s.description == "Reply with a 5-7-5 haiku."
    assert s.instructions.startswith("Respond with exactly three lines")
    assert "---" not in s.instructions


def test_parse_skill_md_name_falls_back_to_hint():
    s = skills.parse_skill_md("just a body, no frontmatter", name_hint="my-skill")
    assert s.name == "my-skill"
    assert s.instructions == "just a body, no frontmatter"


def test_parse_skill_md_without_name_raises():
    with pytest.raises(ValueError):
        skills.parse_skill_md("body only, no frontmatter, no hint")


@pytest.mark.parametrize("bad_name", ["Bad_Name", "UPPER", "has space", "x" * 65])
def test_parse_skill_md_rejects_invalid_name(bad_name):
    # Aligns with the Agent Skills standard: lowercase/digits/hyphens, <= 64.
    with pytest.raises(ValueError):
        skills.parse_skill_md("some body", name_hint=bad_name)


@pytest.mark.parametrize("reserved", ["claude-helper", "my-anthropic-skill"])
def test_parse_skill_md_rejects_reserved_words(reserved):
    with pytest.raises(ValueError):
        skills.parse_skill_md("some body", name_hint=reserved)


def test_parse_skill_md_rejects_overlong_description():
    md = f"---\nname: x\ndescription: {'d' * (skills.MAX_DESCRIPTION + 1)}\n---\nbody"
    with pytest.raises(ValueError):
        skills.parse_skill_md(md)


def test_discover_skills_finds_skill_dirs(tmp_path: Path):
    d = tmp_path / "haiku"
    d.mkdir()
    (d / "SKILL.md").write_text(SKILL_MD)
    (d / "helper.py").write_text("print('hi')\n")

    found = skills.discover_skills(tmp_path)
    assert set(found) == {"haiku"}
    assert found["haiku"].assets == ["helper.py"]
    assert found["haiku"].path == d


def test_discover_skills_skips_malformed(tmp_path: Path):
    # A SKILL.md with no body (no instructions) is malformed → skipped.
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "SKILL.md").write_text("---\nname: empty\ndescription: x\n---\n")
    good = tmp_path / "ok"
    good.mkdir()
    (good / "SKILL.md").write_text(SKILL_MD)

    found = skills.discover_skills(tmp_path)
    assert "haiku" in found
    assert "empty" not in found


def test_discover_skills_missing_root_is_empty(tmp_path: Path):
    assert skills.discover_skills(tmp_path / "nope") == {}


def test_apply_skill_injects_instructions_and_task():
    s = skills.parse_skill_md(SKILL_MD)
    prompt = skills.apply_skill(s, "Write about autumn.")
    assert "haiku" in prompt
    assert "SKILL INSTRUCTIONS" in prompt
    assert "5-7-5 haiku" in prompt
    assert prompt.rstrip().endswith("Write about autumn.")


def test_apply_skill_mentions_assets_when_present():
    s = skills.Skill(name="x", description="", instructions="do x", assets=["run.py"])
    prompt = skills.apply_skill(s, "go")
    assert "run.py" in prompt


def test_stage_assets_copies_bundled_files(tmp_path: Path):
    src = tmp_path / "skill"
    src.mkdir()
    (src / "SKILL.md").write_text(SKILL_MD)
    (src / "run.py").write_text("print('hi')\n")
    skill = skills.load_skill(src)

    workdir = tmp_path / "wd"
    staged = skills.stage_assets(skill, workdir)
    assert staged == ["run.py"]
    assert (workdir / "run.py").read_text() == "print('hi')\n"


def test_stage_assets_noop_without_assets(tmp_path: Path):
    s = skills.Skill(name="x", description="", instructions="do x")  # no path/assets
    assert skills.stage_assets(s, tmp_path) == []


def test_bundled_counting_lines_skill_ships_count_script():
    skill = skills.discover_skills()["counting-lines"]
    assert "count.py" in skill.assets


def test_requested_skill_names_merges_skill_and_skills():
    assert skills.requested_skill_names({}) == []
    assert skills.requested_skill_names({"skill": "a"}) == ["a"]
    assert skills.requested_skill_names({"skills": ["b", "a"], "skill": "a"}) == ["b", "a"]


def test_resolve_skills_reports_missing(tmp_path: Path):
    d = tmp_path / "haiku"
    d.mkdir()
    (d / "SKILL.md").write_text(SKILL_MD)
    found, missing = skills.resolve_skills({"skills": ["haiku", "nope"]}, tmp_path)
    assert [s.name for s in found] == ["haiku"]
    assert missing == ["nope"]


def test_apply_skills_composes_multiple():
    first = skills.parse_skill_md(SKILL_MD)
    second = skills.Skill(name="review", description="Review it.", instructions="Be brief.")
    prompt = skills.apply_skills([first, second], "do the work")
    assert '## "haiku"' in prompt
    assert '## "review"' in prompt
    assert prompt.rstrip().endswith("do the work")


def test_skill_relpath_and_payload_use_skill_md():
    skill = skills.discover_skills()["conventional-commit"]
    assert skill_relpath_is_md(skill)
    row = skills.skill_payload(skill)
    assert row["id"] == "conventional-commit"
    assert row["path"].endswith("skills/conventional-commit/SKILL.md")
    assert "instructions" in row


def skill_relpath_is_md(skill: skills.Skill) -> bool:
    return skills.skill_relpath(skill).endswith("/SKILL.md")


def test_bundled_skills_are_discoverable_and_standard_compliant():
    # The repo ships these skills under <root>/skills; each must satisfy the
    # Agent Skills standard (valid name + a what+when description).
    found = skills.discover_skills()
    for name in (
        "conventional-commit",
        "reviewing-code",
        "writing-changelog",
        "support-session-ownership",
        "self-update-pr",
        "orca-cli",
    ):
        assert name in found, f"missing bundled skill: {name}"
        skill = found[name]
        assert skills._NAME_RE.match(skill.name)
        assert skill.description and len(skill.description) <= skills.MAX_DESCRIPTION
        assert "use when" in skill.description.lower()  # description states *when*

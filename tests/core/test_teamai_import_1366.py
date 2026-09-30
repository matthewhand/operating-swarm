"""TeamAI layout → OS skills, baseline, and reviewer blueprints (#1366)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from swarm.blueprints.code_reviewer.blueprint_code_reviewer import CodeReviewerBlueprint
from swarm.blueprints.database_reviewer.blueprint_database_reviewer import (
    DatabaseReviewerBlueprint,
)
from swarm.blueprints.security_reviewer.blueprint_security_reviewer import (
    SecurityReviewerBlueprint,
)
from swarm.core.blueprint_discovery import discover_blueprints
from swarm.core.marketplace_catalog import parse_team_pack
from swarm.core.skills import discover_skills, skills_root
from swarm.core.swarm_cli import app
from swarm.core.team_rosters import normalize_roster
from swarm.core.teamai_import import (
    BASELINE_SKILL_NAME,
    TeamAiImportError,
    apply_teamai_plan,
    bundled_pack_root,
    reviewer_instructions,
    reviewer_model_profile,
    translate_teamai_repo,
)

runner = CliRunner()

GOOD_SKILL = """---
name: demo-skill
description: A tiny portable skill. Use when demonstrating an import.
---
Do the small thing described by the user. Do not run extra tools.
"""

SECRET = "super-secret-token-value"


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "teamai"
    skill = root / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(GOOD_SKILL, encoding="utf-8")
    (skill / "notes.md").write_text("helper note\n", encoding="utf-8")
    rules = root / "rules" / "common"
    rules.mkdir(parents=True)
    (rules / "coding-style.md").write_text(
        "# Coding Style\n\nPrefer small functions.\n", encoding="utf-8"
    )
    agent = root / "agents"
    agent.mkdir()
    (agent / "code-reviewer.md").write_text(
        "---\nname: code-reviewer\ndescription: Reviews diffs.\nmodel: sonnet\n---\n"
        "Review the diff for regressions.\n",
        encoding="utf-8",
    )
    return root


def test_bundled_pack_maps_reviewers_and_drops_sonnet():
    plan = translate_teamai_repo(bundled_pack_root())
    by_name = {row.name: row for row in plan.reviewers}
    assert set(by_name) == {"code-reviewer", "security-reviewer", "database-reviewer"}
    assert by_name["code-reviewer"].role == "skeptic"
    assert by_name["security-reviewer"].role == "gate"
    assert by_name["database-reviewer"].role == "engineer"
    assert by_name["code-reviewer"].source == "blueprint:code_reviewer"
    assert by_name["code-reviewer"].dropped_model == "sonnet"
    assert "sonnet" in plan.dropped_model_pins
    assert "sonnet" not in plan.kept_model_pins
    assert plan.baseline_markdown.startswith("---\nname: teamai-baseline\n")
    normalize_roster(plan.team_pack)
    parsed = parse_team_pack(
        plan.team_pack, fallback_id="teamai", fallback_name="TeamAI"
    )
    assert parsed[0]["id"] == "teamai-reviewers"
    on_disk = json.loads(
        (bundled_pack_root() / "team-pack.json").read_text(encoding="utf-8")
    )
    assert on_disk == plan.team_pack
    baseline = (skills_root() / BASELINE_SKILL_NAME / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert baseline == plan.baseline_markdown


def test_vendored_skills_are_in_the_catalog():
    found = discover_skills(skills_root())
    for name in (
        "api-design",
        "backend-patterns",
        "tdd-workflow",
        "security-review",
        "tdd",
        "research",
        "domain-modeling",
        "grill-me",
        "grilling",
        BASELINE_SKILL_NAME,
    ):
        assert name in found, name
    assert (
        "Copyright (c) 2026 Affaan Mustafa." in found[BASELINE_SKILL_NAME].instructions
    )
    assert (skills_root() / "mattpocock" / "LICENSE").is_file()
    assert (bundled_pack_root() / "LICENSE").is_file()


def test_reviewer_blueprints_use_roles_and_drop_cli_model_pin():
    assert CodeReviewerBlueprint.metadata["role"] == "skeptic"
    assert SecurityReviewerBlueprint.metadata["role"] == "gate"
    assert DatabaseReviewerBlueprint.metadata["role"] == "engineer"
    text = reviewer_instructions("code-reviewer")
    assert "skeptic" in text
    assert "sonnet" in text
    assert "not applied" in text
    assert "does not attach the upstream" in text
    assert text.rstrip().endswith("material in this conversation.")
    assert reviewer_model_profile("code-reviewer") is None
    found = discover_blueprints(str(Path("src/swarm/blueprints").resolve()))
    assert found["code_reviewer"]["metadata"]["role"] == "skeptic"
    assert found["security_reviewer"]["metadata"]["role"] == "gate"
    assert found["database_reviewer"]["metadata"]["role"] == "engineer"


def test_translate_synthetic_repo_keeps_api_pin_and_strips_mcp_secrets(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "agents" / "extra-reviewer.md").write_text(
        "---\nname: extra-reviewer\ndescription: Extra.\nmodel: default\n---\n"
        "Look at the schema.\n",
        encoding="utf-8",
    )
    mcp = root / "mcp"
    mcp.mkdir()
    (mcp / "mcp.yaml").write_text(
        "servers:\n"
        "  - name: demo\n"
        "    transport: http\n"
        "    url: https://example.test/${DEMO_URL}\n"
        "    env:\n"
        f"      TOKEN: {SECRET}\n"
        "    headers:\n"
        "      Authorization: Bearer ${GITHUB_TOKEN}\n",
        encoding="utf-8",
    )
    (root / "mcp.json").write_text(f'{{"token": "{SECRET}"}}\n', encoding="utf-8")
    models = root / "models"
    models.mkdir()
    (models / "models.yaml").write_text(
        "profiles:\n"
        "  - id: hub\n"
        "    api_key: ${API_KEY}\n"
        "    model_groups:\n"
        "      - models: [sonnet, default]\n",
        encoding="utf-8",
    )
    (root / ".env").write_text(f"LEAKED={SECRET}\n", encoding="utf-8")
    (root / ".env.example").write_text("EXAMPLE_TOKEN=replace-me\n", encoding="utf-8")
    hook = root / "hooks"
    hook.mkdir()
    (hook / "pre.sh").write_text("#!/bin/sh\necho run\n", encoding="utf-8")

    plan = translate_teamai_repo(root)
    blob = json.dumps(plan.as_dict())
    assert SECRET not in blob
    assert "replace-me" not in blob
    names = {row.name for row in plan.skills}
    assert names == {"demo-skill"}
    assert plan.baseline_markdown
    extra = next(row for row in plan.reviewers if row.name == "extra-reviewer")
    assert extra.kept_model == "default"
    assert extra.dropped_model == ""
    assert extra.source.startswith("personality:")
    code = next(row for row in plan.reviewers if row.name == "code-reviewer")
    assert code.dropped_model == "sonnet"
    assert code.source.startswith("personality:")
    assert plan.mcp_servers == [
        {
            "name": "demo",
            "transport": "http",
            "required_env": ["TOKEN", "GITHUB_TOKEN", "DEMO_URL"],
            "installed": False,
        }
    ]
    assert "API_KEY" in plan.required_env
    assert "EXAMPLE_TOKEN" in plan.required_env
    assert "default" in plan.kept_model_pins
    assert any("mcp.json" in note for note in plan.warnings)
    assert any(".env" in note for note in plan.warnings)
    assert any(item.endswith("pre.sh") for item in plan.skipped)
    normalize_roster(plan.team_pack)


def test_malformed_skill_is_skipped_and_empty_layout_fails(tmp_path: Path):
    root = tmp_path / "mixed"
    bad = root / "skills" / "bad"
    good = root / "skills" / "good"
    bad.mkdir(parents=True)
    good.mkdir()
    (bad / "SKILL.md").write_text(
        "---\nname: bad\ndescription: x\n---\n", encoding="utf-8"
    )
    (good / "SKILL.md").write_text(GOOD_SKILL, encoding="utf-8")
    plan = translate_teamai_repo(root)
    assert [row.name for row in plan.skills] == ["demo-skill"]
    assert any("bad" in item for item in plan.skipped)

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(TeamAiImportError):
        translate_teamai_repo(empty)
    only_bad = tmp_path / "only-bad"
    (only_bad / "skills" / "bad").mkdir(parents=True)
    (only_bad / "skills" / "bad" / "SKILL.md").write_text(
        "---\nname: bad\ndescription: x\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(TeamAiImportError):
        translate_teamai_repo(only_bad)
    not_dir = tmp_path / "file.txt"
    not_dir.write_text("nope", encoding="utf-8")
    with pytest.raises(TeamAiImportError):
        translate_teamai_repo(not_dir)


def test_apply_copies_skills_without_executing_or_following_symlinks(tmp_path: Path):
    root = _repo(tmp_path)
    skill = root / "skills" / "demo"
    marker = tmp_path / "MARKER"
    script = skill / "explode.py"
    script.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    outside = tmp_path / "outside-secret.txt"
    outside.write_text(SECRET, encoding="utf-8")
    (skill / "linked.txt").symlink_to(outside)
    (root / "LICENSE").write_text(
        "MIT\nCopyright (c) 2026 Affaan Mustafa\n", encoding="utf-8"
    )

    plan = translate_teamai_repo(root)
    dest = tmp_path / "installed"
    result = apply_teamai_plan(plan, source=root, skills_dest=dest)
    assert "demo-skill" in result["installed_skills"]
    assert BASELINE_SKILL_NAME in result["installed_skills"]
    assert result["mcp_installed"] is False
    assert result["personalities"] == []
    copied = dest / "demo-skill" / "explode.py"
    assert copied.is_file()
    assert copied.stat().st_mode & 0o111 == 0
    assert not marker.exists()
    assert SECRET not in "\n".join(
        p.read_text(encoding="utf-8") for p in dest.rglob("*") if p.is_file()
    )
    assert not (dest / "demo-skill" / "linked.txt").exists()
    assert "Affaan Mustafa" in (dest / "LICENSE").read_text(encoding="utf-8")
    assert not (dest / "hooks").exists()
    assert result["warnings"] == []


def test_seed_personalities_skips_bundled_blueprint_seats(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(tmp_path / "designs.json"))
    plan = translate_teamai_repo(bundled_pack_root())
    dest = tmp_path / "skills"
    result = apply_teamai_plan(
        plan,
        source=bundled_pack_root(),
        skills_dest=dest,
        seed_personalities=True,
    )
    assert result["personalities"] == []
    assert not (tmp_path / "designs.json").exists()

    root = _repo(tmp_path)
    body = "Look carefully.\n" + ("word " * 3000)
    (root / "agents" / "code-reviewer.md").write_text(
        "---\nname: code-reviewer\ndescription: Reviews diffs.\nmodel: sonnet\n---\n"
        + body,
        encoding="utf-8",
    )
    foreign = translate_teamai_repo(root)
    seeded = apply_teamai_plan(
        foreign,
        source=root,
        skills_dest=tmp_path / "more-skills",
        seed_personalities=True,
    )
    assert seeded["personalities"] == ["code-reviewer"]
    stored = json.loads((tmp_path / "designs.json").read_text(encoding="utf-8"))
    instructions = stored["agents"][0]["instructions"]
    assert len(instructions) <= 8000
    assert "truncated" in instructions
    assert "does not attach the upstream" in instructions
    assert SECRET not in instructions


def test_cli_dry_run_and_write(tmp_path: Path):
    root = _repo(tmp_path)
    dry = runner.invoke(app, ["teamai-import", str(root)])
    assert dry.exit_code == 0, dry.stdout
    payload = json.loads(dry.stdout)
    assert payload["skills"][0]["name"] == "demo-skill"
    assert payload["mcp_servers"] == []
    blob = dry.stdout
    assert SECRET not in blob

    dest = tmp_path / "out"
    wrote = runner.invoke(
        app,
        ["teamai-import", str(root), "--write", "--skills-dir", str(dest)],
    )
    assert wrote.exit_code == 0, wrote.stdout
    assert (dest / "demo-skill" / "SKILL.md").is_file()
    assert (dest / BASELINE_SKILL_NAME / "SKILL.md").is_file()

    missing = runner.invoke(app, ["teamai-import", str(tmp_path / "missing")])
    assert missing.exit_code == 1


def test_apply_keeps_skill_md_and_mattpocock_license(tmp_path: Path):
    root = _repo(tmp_path)
    skill = root / "skills" / "demo"
    # These names sort before SKILL.md. A pure sorted walk fills the 32-file
    # cap with them and drops the skill body. `a00.md` does not: uppercase
    # SKILL.md sorts first, so that fixture passes without the priority copy.
    for index in range(40):
        (skill / f"0-extra-{index:02d}.md").write_text("note\n", encoding="utf-8")
    (root / "LICENSE").write_text(
        "MIT\nCopyright (c) 2026 Affaan Mustafa\n", encoding="utf-8"
    )
    matt = root / "skills" / "mattpocock"
    matt.mkdir()
    (matt / "LICENSE").write_text(
        "MIT\nCopyright (c) 2026 Matt Pocock\n", encoding="utf-8"
    )

    plan = translate_teamai_repo(root)
    dest = tmp_path / "installed"
    result = apply_teamai_plan(plan, source=root, skills_dest=dest)
    copied = dest / "demo-skill"
    files = [path for path in copied.rglob("*") if path.is_file()]
    assert (copied / "SKILL.md").is_file()
    assert (copied / "0-extra-00.md").is_file()
    assert (copied / "0-extra-30.md").is_file()
    # Old sorted walk kept this file and dropped SKILL.md.
    assert not (copied / "0-extra-31.md").exists()
    assert not (copied / "notes.md").exists()
    assert "demo-skill" in result["installed_skills"]
    assert len(files) == 32
    assert any(
        "Copied 32 files for skill 'demo-skill' and left 10 behind" in note
        for note in result["warnings"]
    )
    assert "Matt Pocock" in (dest / "LICENSE-mattpocock").read_text(encoding="utf-8")
    assert "Affaan Mustafa" in (dest / "LICENSE").read_text(encoding="utf-8")

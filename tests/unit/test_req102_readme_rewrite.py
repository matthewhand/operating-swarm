"""#791: README is the user front door; internals live in docs/DEVELOPER.md.

Parent #466 closed by #785. This file locks the remaining shape bump:
WebUI-first + kinds lock stay (landed #785); mermaid / layout / CI live
on DEVELOPER.md; README must not become a developer novel again.
"""

from swarm.core.handoff_graph import repo_root
from helpers.private_net import assert_no_private_ip


def _readme() -> str:
    return (repo_root() / "README.md").read_text(encoding="utf-8")


def _developer() -> str:
    return (repo_root() / "docs" / "DEVELOPER.md").read_text(encoding="utf-8")


def test_readme_is_webui_first_and_names_four_kinds():
    text = _readme()
    assert "## WebUI (start here)" in text
    assert "## Kinds (locked)" in text
    assert "**CLI**" in text
    assert "**API**" in text
    assert "**Blueprint**" in text
    assert "**Remote**" in text
    assert "Team" in text
    assert "subtype" in text.lower()
    assert "not a fifth kind" in text.lower()
    assert "Hermes" in text
    assert "OpenMousBot" in text
    assert "Rakazo" in text
    assert "Herdr" in text
    assert "docs/DEVELOPER.md" in text
    assert "docs/VISION.md" in text
    assert "first-class" in text.lower()


def test_readme_version_honesty_names_published_cut():
    text = _readme()
    assert "0.5.4" in text
    assert "main" in text
    assert "Orchestrating AI Agent Swarms with Django" in text
    assert "Alpha" in text
    assert "pip install open-swarm" in text
    assert "## Short history" in text


def test_readme_is_not_a_developer_novel():
    text = _readme()
    lowered = text.lower()
    assert "landing.png" not in text
    assert "```mermaid" not in text
    assert "ApiKindBase" not in text
    assert "blueprint-builder" not in lowered and "blueprint builder" not in lowered
    assert "## Architecture" not in text
    assert "## Bundled Blueprints" not in text
    assert "## Environment Variables" not in text
    assert "1100+" not in text
    assert "Status: beta" not in text
    # Historical GitHub Release title may mention django_chat; nothing else.
    if "django_chat" in text:
        assert "django_chat resolves its LLM profile" in text


def test_developer_doc_holds_moved_internals():
    text = _developer()
    assert "## Why openai-agents" in text
    assert "```mermaid" in text
    assert "BA" in text and "Engineer" in text and "Tester" in text
    assert "Skeptic" in text
    assert "ApiKindBase" in text
    assert "## Package layout" in text
    assert "## Dev setup, tests, CI" in text
    assert "## Gateway vs workers" in text
    assert "CONTRIBUTING.md" in text
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_"):
        assert needle not in lowered
    assert_no_private_ip(text)


def test_vision_points_at_current_readme_not_stale_466():
    """#782 skeptic nit: What remains points at #791, not unfinished README #466."""
    text = (repo_root() / "docs" / "VISION.md").read_text(encoding="utf-8")
    remains = text.split("## What remains", 1)[-1].split("## How the pieces fit", 1)[0]
    assert "#791" in remains
    assert "DEVELOPER.md" in remains
    assert "sibling rewrite" not in remains.lower()
    assert "unfinished" not in remains.lower()
    if "#466" in remains:
        assert "#785" in remains
        assert "not the old" in remains.lower() or "already landed" in remains.lower()
    assert "[README](../README.md)" in text or "[README.md](../README.md)" in text
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_"):
        assert needle not in lowered

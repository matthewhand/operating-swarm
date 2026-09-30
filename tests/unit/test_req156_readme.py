"""REQ-156: openai-agents graphs live on DEVELOPER.md; README sells the kinds.

#791 parks mermaid off the README. README still names the differentiator
and links the developer doc + the examples pack.
"""

from swarm.core.handoff_graph import repo_root
from helpers.private_net import assert_no_private_ip


def test_developer_doc_has_forced_circular_and_harness_diagrams():
    text = (repo_root() / "docs" / "DEVELOPER.md").read_text(encoding="utf-8")
    assert "## Why openai-agents" in text
    assert "```mermaid" in text
    assert "BA" in text and "Engineer" in text and "Tester" in text
    assert "Skeptic" in text
    assert "API" in text and "CLI" in text and "Remote" in text
    assert "cannot inject" in text.lower() or "stay native" in text.lower()
    assert "openai-agents-handoff-graphs" in text
    assert "#564" in text or "REQ-156" in text
    assert "005-kind-bases.md" in text


def test_readme_sells_openai_agents_and_points_at_developer_doc():
    text = (repo_root() / "README.md").read_text(encoding="utf-8")
    assert "## Why openai-agents" in text
    assert "```mermaid" not in text
    assert "BA" in text and "Engineer" in text and "Tester" in text
    assert "Skeptic" in text
    assert "API" in text and "CLI" in text and "Remote" in text
    assert "cannot inject" in text.lower() or "stay native" in text.lower()
    assert "docs/DEVELOPER.md" in text
    assert "docs/examples/openai-agents-handoff-graphs" in text
    assert "#564" in text or "REQ-156" in text
    assert "docs/adr/005-kind-bases.md" in text


def test_readme_kinds_lock_is_visible():
    """Matthew lock: CLI | API | Blueprint | Remote; Team is a Blueprint subtype."""
    text = (repo_root() / "README.md").read_text(encoding="utf-8")
    assert "## Kinds (locked)" in text
    assert "**CLI**" in text
    assert "true inference" in text.lower() or "True inference" in text
    assert "**Blueprint**" in text
    assert "openai-agents" in text
    assert "Hermes" in text and "OpenMousBot" in text and "Rakazo" in text and "Herdr" in text
    assert "subtype" in text.lower()
    assert "not a fifth kind" in text.lower()
    assert "docs/adr/006-api-vs-blueprint-kinds.md" in text
    assert "## WebUI (start here)" in text
    assert "first-class" in text.lower()
    assert "Blueprint-Builder" not in text
    assert "## Bundled Blueprints" not in text
    if "django_chat" in text:
        assert "django_chat resolves its LLM profile" in text


def test_readme_version_honesty_and_history():
    text = (repo_root() / "README.md").read_text(encoding="utf-8")
    assert "## Short history" in text
    assert "0.5.4" in text
    assert "Orchestrating AI Agent Swarms with Django" in text
    assert "pip install open-swarm" in text
    assert "main" in text
    assert "docs/DEVELOPER.md" in text


def test_example_readme_documents_8001_seed_without_secrets():
    pack = repo_root() / "docs" / "examples" / "openai-agents-handoff-graphs" / "README.md"
    text = pack.read_text(encoding="utf-8")
    assert ":8001" in text
    assert "seed_req156_demo.py" in text
    assert "Intent:" in text and "Success:" in text and "Constraints:" in text
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_"):
        assert needle not in lowered
    assert_no_private_ip(text)

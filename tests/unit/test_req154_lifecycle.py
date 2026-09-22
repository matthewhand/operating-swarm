"""REQ-154 / #562 — docs + wiring locks. No live demo port, no secrets, no Wave labels."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "src" / "swarm" / "core" / "agent_lifecycle.py"
ROLES = REPO / "src" / "swarm" / "core" / "agent_roles.py"
CONSUMER = REPO / "src" / "swarm" / "consumers.py"
CHAT = REPO / "src" / "swarm" / "views" / "chat_views.py"
BASE = REPO / "src" / "swarm" / "core" / "blueprint_base.py"
CMD = REPO / "src" / "swarm" / "management" / "commands" / "purge_archived_agents.py"
DOCS = REPO / "docs" / "AGENT_LIFECYCLE.md"
POINTER = REPO / "docs" / "requirements" / "REQ-154.md"
ADR = REPO / "docs" / "adr" / "009-peer-mailbox.md"
CI = REPO / ".github" / "workflows" / "req154-lifecycle.yml"
CHANGELOG = REPO / "CHANGELOG.md"
SKILL = REPO / "skills" / "support-session-ownership" / "SKILL.md"
SUPPORT_BP = REPO / "src" / "swarm" / "blueprints" / "support" / "blueprint_support.py"


def _no_secrets(text: str) -> None:
    lowered = text.lower()
    for needle in ("github_pat_", "ghp_", "10.0.0."):
        assert needle not in lowered


def _no_demo_port(text: str) -> None:
    assert ":8001" not in text
    assert "WAVE" not in text


def test_pointer_is_github_issue_only():
    text = POINTER.read_text(encoding="utf-8")
    assert "github.com/matthewhand/open-swarm/issues/562" in text
    _no_demo_port(text)
    _no_secrets(text)


def test_lifecycle_doc_covers_success_and_matrix():
    text = DOCS.read_text(encoding="utf-8")
    assert "create_agent" in text
    assert "archive_agent" in text
    assert "30" in text
    assert "purge_archived_agents" in text
    assert "Support" in text
    assert "CoS" in text or "chief_of_staff" in text
    assert "SWARM_CHAT_MAX_AGE_DAYS" in text
    assert "#530" in text or "REQ-137" in text
    assert "role=default" in text
    _no_demo_port(text)
    _no_secrets(text)


def test_core_exposes_tools_and_role_gate():
    core = CORE.read_text(encoding="utf-8")
    roles = ROLES.read_text(encoding="utf-8")
    assert "create_agent" in core
    assert "archive_agent" in core
    assert "can_manage_agent_lifecycle" in core
    assert "can_manage_agent_lifecycle" in roles
    assert "ROLE_SUPPORT" in roles
    assert "ROLE_CHIEF_OF_STAFF" in roles
    _no_demo_port(core)
    _no_secrets(core)


def test_wired_on_chat_ws_and_completions():
    # #855 slice 2: the WS install site moved with respond_with_blueprint
    # into the stubs mixin; the doctrine spans both homes.
    assert "install_lifecycle_for_runtime" in (
        CONSUMER.read_text(encoding="utf-8")
        + (REPO / "src" / "swarm" / "chat" / "stubs_mixin.py").read_text(encoding="utf-8")
    )
    assert "install_lifecycle_for_runtime" in CHAT.read_text(encoding="utf-8")
    assert "_lifecycle_context" in BASE.read_text(encoding="utf-8")
    assert "purge_archived_agents" in CMD.read_text(encoding="utf-8")


def test_support_copy_names_the_tools():
    skill = SKILL.read_text(encoding="utf-8")
    blueprint = SUPPORT_BP.read_text(encoding="utf-8")
    assert "create_agent" in skill
    assert "archive_agent" in skill
    assert "REQ-154" in skill
    assert "create_agent" in blueprint
    assert "archive_agent" in blueprint
    _no_demo_port(skill)
    _no_demo_port(blueprint)
    _no_secrets(skill)


def test_adr009_points_at_req154():
    text = ADR.read_text(encoding="utf-8")
    assert "REQ-154" in text
    assert "562" in text
    assert "AGENT_LIFECYCLE" in text or "archive_agent" in text


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "req154" in text.lower() or "REQ-154" in text
    assert "own-diff" in text
    assert "pytest" in text
    assert "test_agent_lifecycle.py" in text
    _no_demo_port(text)


def test_changelog_fixes_562():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "Fixes #562" in text
    chunk = text.split("Fixes #562")[0][-500:]
    assert "WAVE" not in chunk
    assert "create" in chunk.lower()
    assert "archive" in chunk.lower()

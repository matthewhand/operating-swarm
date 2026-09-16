"""Issue #219 — docs + wiring locks. No :8001, no secrets, no Wave labels."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TOPOLOGY = REPO / "src" / "swarm" / "core" / "cos_topology.py"
SECTIONS = REPO / "src" / "swarm" / "core" / "agent_sections.py"
ROLES = REPO / "src" / "swarm" / "core" / "agent_roles.py"
ADAPTERS = REPO / "src" / "swarm" / "core" / "roles" / "adapters.py"
MAILBOX = REPO / "src" / "swarm" / "core" / "agent_mailbox.py"
ACL = REPO / "src" / "swarm" / "core" / "agent_mailbox_acl.py"
CONSUMER = REPO / "src" / "swarm" / "consumers.py"
CHAT = REPO / "src" / "swarm" / "views" / "chat_views.py"
BASE = REPO / "src" / "swarm" / "core" / "blueprint_base.py"
DOCS = REPO / "docs" / "COS_TOPOLOGY.md"
POINTER = REPO / "docs" / "requirements" / "ISSUE-219.md"
CI = REPO / ".github" / "workflows" / "issue219-cos-topology.yml"
CHANGELOG = REPO / "CHANGELOG.md"
PEER = REPO / "docs" / "PEER_MAILBOX.md"


def _no_secrets(text: str) -> None:
    lowered = text.lower()
    for needle in ("github_pat_", "ghp_", "10.0.0.", "sk-"):
        assert needle not in lowered


def _no_demo_port(text: str) -> None:
    assert ":8001" not in text
    assert "WAVE" not in text


def test_pointer_is_github_issue_only():
    text = POINTER.read_text(encoding="utf-8")
    assert "github.com/matthewhand/open-swarm-private/issues/219" in text
    _no_demo_port(text)
    _no_secrets(text)


def test_docs_cover_persistent_create_and_tools():
    text = DOCS.read_text(encoding="utf-8")
    assert "create_agent" in text
    assert "create_section" in text
    assert "rename_section" in text
    assert "archive_section" in text
    assert "move_agent_to_section" in text
    assert "set_talk_acl" in text
    assert "TrueForge" in text
    assert "chief_of_staff" in text or "CoS" in text
    assert "Support" in text
    _no_demo_port(text)
    _no_secrets(text)


def test_core_exposes_tools_and_cos_only_gate():
    topology = TOPOLOGY.read_text(encoding="utf-8")
    roles = ROLES.read_text(encoding="utf-8")
    adapters = ADAPTERS.read_text(encoding="utf-8")
    mailbox = MAILBOX.read_text(encoding="utf-8")
    acl = ACL.read_text(encoding="utf-8")
    assert "create_section" in topology
    assert "set_talk_acl" in topology
    assert "can_manage_topology" in topology
    assert "can_manage_topology" in roles
    assert "attach_as_tool" in adapters
    assert "ChiefOfStaffRole" in adapters
    assert '"section"' in mailbox
    assert "section" in acl
    assert "agent_sections.json" in SECTIONS.read_text(encoding="utf-8")
    _no_demo_port(topology)
    _no_secrets(topology)


def test_wired_on_chat_ws_and_completions_via_role():
    consumer = CONSUMER.read_text(encoding="utf-8")
    chat = CHAT.read_text(encoding="utf-8")
    adapters = ADAPTERS.read_text(encoding="utf-8")
    assert "install_topology_for_runtime" in consumer
    assert "install_topology_for_runtime" in chat
    assert "_topology_context" in BASE.read_text(encoding="utf-8")
    assert "install_topology_on_blueprint" in adapters


def test_peer_mailbox_docs_name_section_kind():
    text = PEER.read_text(encoding="utf-8")
    assert "section" in text.lower()
    _no_demo_port(text)
    _no_secrets(text)


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "issue219" in text.lower() or "219" in text
    assert "own-diff" in text
    assert "pytest" in text
    assert "test_cos_topology.py" in text
    _no_demo_port(text)


def test_changelog_fixes_219():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "Fixes #219" in text
    chunk = text.split("Fixes #219")[0][-600:]
    assert "WAVE" not in chunk
    assert "create_section" in chunk or "section" in chunk.lower()
    assert "TrueForge" not in chunk or "persistent" in chunk.lower()

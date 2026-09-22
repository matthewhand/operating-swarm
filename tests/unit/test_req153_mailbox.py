"""REQ-153 / #561 — docs + wiring locks. No :8001, no secrets, no Wave labels."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAILBOX = REPO / "src" / "swarm" / "core" / "agent_mailbox.py"
REL = REPO / "src" / "swarm" / "core" / "agent_relationships.py"
ADR = REPO / "docs" / "adr" / "009-peer-mailbox.md"
PEER = REPO / "docs" / "PEER_MAILBOX.md"
CI = REPO / ".github" / "workflows" / "req153-mailbox.yml"
CONSUMER = REPO / "src" / "swarm" / "consumers.py"
CHAT = REPO / "src" / "swarm" / "views" / "chat_views.py"
BASE = REPO / "src" / "swarm" / "core" / "blueprint_base.py"
CHANGELOG = REPO / "CHANGELOG.md"
POINTER = REPO / "docs" / "requirements" / "REQ-153.md"


def _no_secrets(text: str) -> None:
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_", "10.0.0."):
        assert needle not in lowered


def test_pointer_is_github_issue_only():
    text = POINTER.read_text(encoding="utf-8")
    assert "github.com/matthewhand/open-swarm/issues/561" in text
    assert ":8001" not in text
    _no_secrets(text)


def test_adr_documents_graph_and_eligibility():
    text = ADR.read_text(encoding="utf-8")
    assert "list_agents" in text
    assert "send_message" in text
    assert "same-kind" in text or "API↔API" in text
    assert "team" in text.lower()
    assert "relationship" in text.lower()
    assert "Support" in text
    assert "#561" in text or "REQ-153" in text
    assert ":8001" not in text
    assert "WAVE" not in text
    _no_secrets(text)


def test_core_is_api_first_no_8001():
    mailbox = MAILBOX.read_text(encoding="utf-8")
    rel = REL.read_text(encoding="utf-8")
    peer = PEER.read_text(encoding="utf-8")
    for text in (mailbox, rel, peer):
        assert ":8001" not in text
        assert "WAVE" not in text
        _no_secrets(text)
    assert "list_agents" in mailbox
    assert "send_message" in mailbox
    assert "user_key" in mailbox


def test_wired_on_chat_ws_and_completions():
    # #855 slice 2: the WS install site moved with respond_with_blueprint
    # into the stubs mixin; the doctrine spans both homes.
    assert "install_mailbox_for_runtime" in (
        CONSUMER.read_text(encoding="utf-8")
        + (REPO / "src" / "swarm" / "chat" / "stubs_mixin.py").read_text(encoding="utf-8")
    )
    assert "install_mailbox_for_runtime" in CHAT.read_text(encoding="utf-8")
    assert "_mailbox_context" in BASE.read_text(encoding="utf-8")


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "req153" in text.lower() or "REQ-153" in text
    assert "own-diff" in text
    assert "pytest" in text
    assert "test_agent_mailbox.py" in text
    assert ":8001" not in text


def test_changelog_fixes_561():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "Fixes #561" in text
    assert "WAVE" not in text.split("Fixes #561")[0][-400:]

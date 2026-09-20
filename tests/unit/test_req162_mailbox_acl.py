"""REQ-162 / #573 — docs + wiring locks. No :8001, no secrets, no Wave labels."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAILBOX = REPO / "src" / "swarm" / "core" / "agent_mailbox.py"
ACL = REPO / "src" / "swarm" / "core" / "agent_mailbox_acl.py"
API = REPO / "src" / "swarm" / "views" / "mailbox_acl_api.py"
URLS = REPO / "src" / "swarm" / "urls.py"
EDITOR = REPO / "webui" / "frontend" / "src" / "components" / "MailboxAclEditor.tsx"
AGENT_EDITOR = REPO / "webui" / "frontend" / "src" / "components" / "AgentEditor.tsx"
ADR = REPO / "docs" / "adr" / "009-peer-mailbox.md"
PEER = REPO / "docs" / "PEER_MAILBOX.md"
POINTER = REPO / "docs" / "requirements" / "REQ-162.md"
CI = REPO / ".github" / "workflows" / "req162-mailbox-acl.yml"
CHANGELOG = REPO / "CHANGELOG.md"


def _no_secrets(text: str) -> None:
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_", "10.0.0."):
        assert needle not in lowered


def test_pointer_is_github_issue_only():
    text = POINTER.read_text(encoding="utf-8")
    assert "github.com/matthewhand/open-swarm/issues/573" in text
    assert ":8001" not in text
    _no_secrets(text)


def test_docs_name_entry_kinds_and_support_allow_all():
    for path in (ADR, PEER):
        text = path.read_text(encoding="utf-8")
        assert "whitelist" in text.lower()
        assert "blacklist" in text.lower()
        assert "agent" in text.lower()
        assert "team" in text.lower()
        assert "role" in text.lower()
        assert "Support" in text
        assert ":8001" not in text
        assert "WAVE" not in text
        _no_secrets(text)


def test_store_and_api_exist():
    acl = ACL.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")
    urls = URLS.read_text(encoding="utf-8")
    mailbox = MAILBOX.read_text(encoding="utf-8")
    for text in (acl, api, mailbox):
        assert ":8001" not in text
        assert "WAVE" not in text
        _no_secrets(text)
    assert "agent_mailbox_acl.json" in acl
    assert "whitelist" in acl
    assert "blacklist" in acl
    assert "v1/mailbox-acl" in urls
    assert "apply_acl" in mailbox
    assert "resolve_acl_policy" in mailbox


def test_ui_toggle_without_config_files():
    editor = EDITOR.read_text(encoding="utf-8")
    agent = AGENT_EDITOR.read_text(encoding="utf-8")
    assert "MailboxAclEditor" in agent
    # #545 de-jargonized the control: the stored modes stay whitelist/blacklist
    # (wire + persisted contract), the UI says "Permitted or denied".
    assert "Permitted" in editor
    assert "Denied" in editor
    assert "modeToggleId" in editor
    assert "mailbox-acl-editor" in editor
    assert 'data-testid="mailbox-acl-editor"' in editor
    assert "toggle" in editor.lower()
    assert "whitelist" in editor.lower()
    assert "blacklist" in editor.lower()
    assert ":8001" not in editor


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "req162" in text.lower() or "REQ-162" in text
    assert "own-diff" in text
    assert "pytest" in text
    assert "test_agent_mailbox_acl.py" in text
    assert ":8001" not in text


def test_changelog_fixes_573():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "Fixes #573" in text
    assert "WAVE" not in text.split("Fixes #573")[0][-400:]

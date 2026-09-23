"""REQ-171A-4 / #604 — hydrate chat threads honestly.

Source-lock: fetchAgentThread surfaces failure; ChatPage toasts and keeps a
non-empty in-memory bucket; remotes use GET /chat/thread/; remotes stay
non-editable (existing 403 PATCH). Own-diff CI. No Neon, no :8001, no secrets.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AGENT_CHAT = REPO / "webui" / "frontend" / "src" / "lib" / "agentChat.ts"
AGENT_CHAT_TEST = REPO / "webui" / "frontend" / "src" / "lib" / "__tests__" / "agentChat.test.ts"
CHAT_PAGE = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
MSG_LIST = REPO / "webui" / "frontend" / "src" / "features" / "chat" / "ChatMessageList.tsx"
HYDRATE_TEST = (
    REPO / "webui" / "frontend" / "src" / "pages" / "__tests__" / "ChatPage.hydrate.test.tsx"
)
RETENTION = REPO / "tests" / "views" / "test_chat_retention.py"
CI = REPO / ".github" / "workflows" / "req171a4-hydrate-honest.yml"
CHANGELOG = REPO / "CHANGELOG.md"


def _no_secrets(text: str) -> None:
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_", "10.0.0."):
        assert needle not in lowered


def test_fetch_agent_thread_surfaces_failure():
    src = AGENT_CHAT.read_text(encoding="utf-8")
    assert "export async function fetchAgentThread" in src
    assert "REQ-171A-4" in src
    assert "#604" in src
    assert "empty on auth/network failure" not in src
    fn = src.split("export async function fetchAgentThread", 1)[1].split(
        "export interface PatchAgentMessageRequest", 1
    )[0]
    assert "apiGet<AgentThread>" in fn
    assert "messages: []" not in fn
    assert "catch {" not in fn
    _no_secrets(src)
    assert ":8001" not in src
    assert "neon" not in src.lower()


def test_contract_test_no_longer_locks_empty_on_failure():
    src = AGENT_CHAT_TEST.read_text(encoding="utf-8")
    assert "returns an empty thread when fetch fails" not in src
    assert "surfaces failure when fetch is offline" in src
    assert "surfaces failure when the thread endpoint returns 500" in src
    assert "calls the thread endpoint for a remote agent id" in src
    _no_secrets(src)


def test_chat_page_toasts_keeps_bucket_and_hydrates_remotes():
    src = CHAT_PAGE.read_text(encoding="utf-8") + MSG_LIST.read_text(encoding="utf-8")
    assert "noteHydrateFailure" in src
    assert "Could not load chat" in src
    assert "Existing messages were kept" in src
    assert "chat-hydrate-error" in src
    assert "Could not load this chat" in src
    assert "fetchAgentThread(`remote:${remoteFromUrl}`" in src
    assert "Same GET /chat/thread/ path as API/team" in src
    hydrate = src.split("const noteHydrateFailure", 1)[1]
    assert "hadMessages" in hydrate
    assert "setHydrateError" in hydrate
    assert "setThreads((prev) => ({ ...prev, [key]: [] }))" not in src.split(
        "userKeyCounterRef.current = 0", 1
    )[1].split("let cancelled = false", 1)[0]
    hydrate_block = src.split("const noteHydrateFailure", 1)[1].split(
        "const attachToolToThread", 1
    )[0]
    _no_secrets(hydrate_block)
    assert ":8001" not in hydrate_block
    assert "WAVE" not in hydrate_block
    assert "github_pat_" not in src
    assert "sk-ant" not in src
    assert "sk-proj" not in src


def test_hydrate_vitest_covers_switch_500_and_remote_refresh():
    src = HYDRATE_TEST.read_text(encoding="utf-8")
    assert "REQ-171A-4" in src
    assert "#604" in src
    assert "keeps in-memory bubbles and toasts when REST 500 follows an agent switch" in src
    assert "shows an explicit error state on first load when GET fails" in src
    assert "hydrates ?remote= from the thread endpoint and restores a seeded thread on refresh" in src
    assert "calls the thread endpoint for a remote session instead of returning early" in src
    assert "data-messages-editable" in src
    assert "sk-" not in src
    assert "neon" not in src.lower()
    assert ":8001" not in src
    _no_secrets(src)


def test_remote_patch_stays_forbidden():
    src = RETENTION.read_text(encoding="utf-8")
    assert "def test_patch_cli_and_remote_threads_are_forbidden" in src
    block = src.split("def test_patch_cli_and_remote_threads_are_forbidden", 1)[1].split(
        "def test_patch_rejects_bad_index_and_unauthenticated", 1
    )[0]
    assert "/chat/thread/?agent=remote:acp" in block
    assert "status_code == 403" in block
    assert '["editable"] is False' in block


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "REQ-171A-4" in text or "req171a4" in text.lower()
    assert "own-diff" in text
    assert "ChatPage.hydrate.test.tsx" in text
    assert "agentChat.test.ts" in text
    assert "test_req171a4_hydrate_honest.py" in text
    assert "patch_cli_and_remote_threads_are_forbidden" in text
    assert ":8001" not in text
    assert "WAVE" not in text
    _no_secrets(text)


def test_changelog_fixes_604_without_wave():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "Fixes #604" in text
    prefix = text.split("Fixes #604")[0][-400:]
    assert "WAVE" not in prefix
    assert "neon" not in prefix.lower()

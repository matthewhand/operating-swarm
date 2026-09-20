"""REQ-171A-3 / #603 — serialise overlapping websocket chat turns.

Source-lock: own-diff CI, no Neon, no :8001, no secrets, no Wave labels.
Full #447 queue pane is out of scope (link only).
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONSUMER = REPO / "src" / "swarm" / "consumers.py"
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CI = REPO / ".github" / "workflows" / "req171a3-serialise-turns.yml"
CHANGELOG = REPO / "CHANGELOG.md"


def _no_secrets(text: str) -> None:
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_", "10.0.0."):
        assert needle not in lowered


def test_consumer_serialises_chat_turns_not_tool_decisions():
    text = CONSUMER.read_text(encoding="utf-8")
    assert "_ensure_chat_turn_lock" in text
    assert "_run_serialised_chat_turn" in text
    assert "REQ-171A-3" in text
    assert "#603" in text
    assert "#447" in text or "447" in text
    assert "tool_decision" in text
    assert ":8001" not in text
    assert "neon" not in text.lower()
    assert "WAVE" not in text
    _no_secrets(text)


def test_spa_queues_second_send_via_generation_in_flight():
    text = CHAT.read_text(encoding="utf-8")
    start = text.index("const submitUserText")
    block = text[start : start + 2500]
    assert "generationIsInFlight(messages, awaitingAssistant)" in block
    assert "REQ-171A-3" in block
    assert "#603" in block
    assert "#447" in block
    assert ":8001" not in block
    _no_secrets(block)


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "REQ-171A-3" in text or "req171a3" in text.lower()
    assert "own-diff" in text
    assert "overlapping_receives" in text
    assert "ChatPage.queued.test.tsx" in text
    assert "ChatPage.test.tsx" in text
    assert "team member dropdown" in text
    assert "REQ-171A-3" in text
    assert ":8001" not in text
    assert "WAVE" not in text
    _no_secrets(text)


def test_changelog_fixes_603_without_wave():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "Fixes #603" in text
    prefix = text.split("Fixes #603")[0][-400:]
    assert "WAVE" not in prefix

"""REQ-171C-5 / #614 — one Herdr client for list + send (C-H4).

Source-lock: own-diff CI, no Neon, no :8001, no secrets, no Wave labels.
SSH shape (#463) stays; this Issue is the configured stub actually sends.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REMOTES = REPO / "src" / "swarm" / "core" / "remotes.py"
TEAMS = REPO / "src" / "swarm" / "core" / "remote_teams.py"
CI = REPO / ".github" / "workflows" / "req171c5-one-herdr-client.yml"
CHANGELOG = REPO / "CHANGELOG.md"


def _no_secrets(text: str) -> None:
    lowered = text.lower()
    for needle in ("sk-", "github_pat_", "ghp_"):
        assert needle not in lowered


def test_operate_send_calls_from_remote_config():
    text = REMOTES.read_text(encoding="utf-8")
    send_start = text.index("def _herdr_send")
    send = text[send_start : send_start + 1800]
    assert "HerdrClient.from_remote_config" in send
    assert "herdr_send_via_cli" not in text
    assert ":8001" not in send
    assert "WAVE" not in send
    _no_secrets(send)


def test_chat_herdr_delegates_to_client_stopped_until():
    """#470 reversed the earlier single ``--until idle`` pin.

    Herdr accepts repeated ``--until`` (``herdr agent wait --help``: "State to
    match; repeat for more than one state"), and a turn that finishes settles in
    ``done`` — proven live: ``--until idle`` returned
    ``{"error":{"code":"timeout"}}`` on a pane whose status was ``done``, while
    ``--until idle --until done --until blocked`` matched it immediately.
    """
    text = TEAMS.read_text(encoding="utf-8")
    start = text.index("def chat_herdr")
    block = text[start : start + 1600]
    assert "from_remote_config" in block
    assert "check_blocked=True" in block
    assert "until=WAIT_UNTIL_STOPPED" in block
    assert 'until="idle"' not in block
    assert ":8001" not in block
    _no_secrets(block)


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "REQ-171C-5" in text or "req171c5" in text.lower()
    assert "own-diff" in text
    assert "test_herdr_remote.py" in text
    assert "test_remote_teams.py" in text
    assert ":8001" not in text
    assert "WAVE" not in text
    assert "neon" not in text.lower()
    _no_secrets(text)


def test_changelog_fixes_614_without_wave():
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "Fixes #614" in text
    prefix = text.split("Fixes #614")[0][-400:]
    assert "WAVE" not in prefix
    assert ":8001" not in prefix

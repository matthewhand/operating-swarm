"""REQ-80 / #432 — computer-icon pane is thumbnail + Routines, chat stays mounted.

Source-lock so the pane is not folded into #361 (driver), #416 (PR-opened card),
or a :8001 webhook. No secrets. GitHub PR-merged trigger only.
"""

from pathlib import Path

from helpers.source_surface import chat_surface

REPO = Path(__file__).resolve().parents[2]
STUB = REPO / "webui" / "frontend" / "src" / "components" / "ComputerControlStub.tsx"
PANE = REPO / "webui" / "frontend" / "src" / "components" / "ComputerRoutinesPane.tsx"
ROUTINES = REPO / "src" / "swarm" / "core" / "routines.py"
API = REPO / "src" / "swarm" / "views" / "routines_api.py"
URLS = REPO / "src" / "swarm" / "urls.py"
APP = REPO / "webui" / "frontend" / "src" / "App.tsx"
CI = REPO / ".github" / "workflows" / "req80-routines.yml"


def test_computer_icon_opens_right_pane_not_wip_modal():
    stub = STUB.read_text(encoding="utf-8")
    assert "ComputerRoutinesPane" in stub
    assert "placement=\"end\"" in stub or "placement='end'" in stub
    assert "WIP" not in stub
    assert "COMPUTER_CONTROL_WIP_COPY" not in stub
    # #1055: shared chat surface — the stub mounts from ChatHeader now.
    chat = chat_surface()
    assert "ChatPage" in chat
    assert "<ComputerControlStub" in chat
    assert 'path="/chat"' in APP.read_text(encoding="utf-8")


def test_pane_thumbnail_sits_above_routines_plus():
    pane = PANE.read_text(encoding="utf-8")
    thumb = pane.index("agent-screen-thumbnail")
    heading = pane.index(">Routines<")
    add = pane.index("Add routine")
    assert thumb < heading < add
    assert "No screen session" in pane
    assert "fake desktop" not in pane.lower()
    assert "<img" not in pane


def test_editor_has_active_delete_test_run_and_pr_merge():
    pane = PANE.read_text(encoding="utf-8")
    for needle in (
        "Active",
        "Delete",
        "Test run",
        "Run now",
        "Name",
        "Instruction",
        "When to run",
        "When a PR merges",
        "Mailbox message",
        "Interval",
        "Cron",
    ):
        assert needle in pane
    core = ROUTINES.read_text(encoding="utf-8")
    assert "github_pr_merged" in core
    assert "mailbox_message" in core
    assert "test_run" in core
    assert "run_now" in core
    assert ":8001" not in core
    assert "ghp_" in core  # rejected as a secret-looking actor
    assert "WAVE" not in core


def test_api_is_agent_scoped_and_merge_delivery_is_github_only():
    urls = URLS.read_text(encoding="utf-8")
    assert "v1/agents/<str:agent_id>/routines/" in urls
    assert "v1/routines/github-merge/" in urls
    assert "v1/routines/mailbox-message/" in urls
    assert "v1/test-schedules/" in urls
    api = API.read_text(encoding="utf-8")
    assert "test-run" in api
    assert "run-now" in api
    assert ":8001" not in api
    assert "localhost" not in api


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "req80" in text.lower() or "REQ-80" in text
    assert "vitest" in text
    assert "pytest" in text

"""REQ-171B / #607 — Add-agent CLI/API seats stay on the rail filter.

Source-lock: create stamps rail + command, list merge lives in the backend,
ChatPage is not the integration point, and own-diff CI does not hit :8001.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAIL = REPO / "src" / "swarm" / "core" / "rail_seats.py"
API = REPO / "src" / "swarm" / "views" / "api_views.py"
WIZARD = REPO / "webui" / "frontend" / "src" / "components" / "AddAgentWizard.tsx"
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CI = REPO / ".github" / "workflows" / "req171b-add-agent-rail.yml"


def test_backend_stamps_rail_and_requires_cli_command():
    text = RAIL.read_text(encoding="utf-8")
    helpers = text.split("ADD_AGENT_SEAT_KINDS", 1)[-1]
    assert "CLI_COMMAND_REQUIRED_ERROR" in text
    assert "UNSUPPORTED_ADD_AGENT_KIND_ERROR" in text
    assert "build_custom_rail_item" in text
    assert "custom_library_to_blueprint_rows" in text
    assert ":8001" not in helpers
    assert "WAVE" not in text
    assert "ghp_" not in text


def test_blueprints_list_merges_custom_rail_seats():
    text = API.read_text(encoding="utf-8")
    assert "custom_library_to_blueprint_rows" in text
    assert "build_custom_rail_item" in text
    assert "CustomSeatError" in text


def test_wizard_sends_kind_command_rail_and_chatpage_untouched_for_this_req():
    wizard = WIZARD.read_text(encoding="utf-8")
    assert "kind: 'cli'" in wizard
    assert "command," in wizard
    assert "rail: true" in wizard
    # API vs custom blueprint kind is decided by the isBp branch.
    assert "kind: isBp ? 'blueprint' : 'api'" in wizard
    chat = CHAT.read_text(encoding="utf-8")
    assert "createCustomBlueprint" not in chat


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "own-diff" in text
    assert "test_req171b_add_agent_rail.py" in text
    assert "test_req171b_add_agent_rail_lock.py" in text
    assert ":8001" not in text

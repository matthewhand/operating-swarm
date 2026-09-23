"""REQ-49: API vs CLI vs remote classification."""

from swarm.core.agent_kind import (
    API_AGENT_BLUEPRINT_ID,
    API_AGENT_RAIL_ID,
    can_edit_agent_messages,
    classify_agent_kind,
    resolve_chat_blueprint_id,
)


def test_api_blueprints_are_editable():
    assert classify_agent_kind("jeeves") == "api"
    assert classify_agent_kind("support") == "api"
    assert can_edit_agent_messages("codey") is True


def test_recipe_blueprints_classify_as_payload_kind_issue_534():
    """#534: ``remote_harness`` / ``cli_agent`` are recipes that *run* a turn
    for their payload kind — the SPA sends ``blueprint: remote_harness`` when a
    remote seat chats, so the recipe id (not the roster id) is what the
    send-path gates see. Classifying it ``api`` made the REQ-87 compression
    gate pass on remote seats and emit 'Auto-compress skipped' notices."""
    assert classify_agent_kind("remote_harness") == "remote"
    assert classify_agent_kind("REMOTE_HARNESS") == "remote"
    assert classify_agent_kind("cli_agent") == "cli"
    # Plain API seats keep their classification:
    assert classify_agent_kind("api_agent") == "api"
    assert classify_agent_kind("chatbot") == "api"
    assert classify_agent_kind("jeeves") == "api"


def test_cli_threads_are_editable_with_session_restart_remote_is_not():
    # CLI edits restart the provider session (caller clears cli_sessions);
    # remote threads stay read-only.
    assert classify_agent_kind("cli:grok") == "cli"
    assert classify_agent_kind("remote:acp") == "remote"
    assert classify_agent_kind("placeholder:remote:acp") == "remote"
    assert can_edit_agent_messages("cli:grok") is True
    assert can_edit_agent_messages("remote:acp") is False


def test_explicit_kind_wins():
    assert classify_agent_kind("jeeves", explicit="cli") == "cli"
    assert classify_agent_kind("cli:grok", explicit="api") == "api"
    assert can_edit_agent_messages("jeeves", explicit="remote") is False


def test_herdr_and_remote_impls_classify_as_remote():
    assert classify_agent_kind("herdr") == "remote"
    assert classify_agent_kind("herdr:w3:p1") == "remote"
    assert classify_agent_kind("pane", explicit="herdr") == "remote"
    assert classify_agent_kind("hermes") == "remote"
    assert classify_agent_kind("omb") == "remote"
    assert can_edit_agent_messages("herdr") is False
    assert classify_agent_kind("swarm") == "api"


def test_blueprint_is_a_first_class_editable_kind():
    assert classify_agent_kind("jeeves", explicit="blueprint") == "blueprint"
    assert classify_agent_kind("blueprint:planner") == "blueprint"
    assert can_edit_agent_messages("blueprint:planner") is True
    assert can_edit_agent_messages("jeeves", explicit="blueprint") is True


def test_recipe_payloads_stay_editable_and_api_seats_unchanged_issue_534():
    """#534 follow-through: recipe ids inherit their payload's edit rights
    (remote stays read-only, CLI restarts the provider session) and explicit
    kinds still win."""
    assert can_edit_agent_messages("remote_harness") is False
    assert can_edit_agent_messages("cli_agent") is True
    assert classify_agent_kind("remote_harness", explicit="api") == "api"


def test_api_agent_rail_id_resolves_to_chatbot_recipe():
    assert resolve_chat_blueprint_id(API_AGENT_RAIL_ID) == API_AGENT_BLUEPRINT_ID
    assert resolve_chat_blueprint_id("API_AGENT") == API_AGENT_BLUEPRINT_ID
    assert resolve_chat_blueprint_id("cli_agent") == "cli_agent"
    assert resolve_chat_blueprint_id("support") == "support"
    assert resolve_chat_blueprint_id("software_dev") == "software_dev"
    assert resolve_chat_blueprint_id(None) == ""

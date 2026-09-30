"""#1441: kind-adjacent error previews are classified, not shown as replies."""

from swarm.core import chat_store
from swarm.core.cli_session_error import classify_output_preview, fatal_config_error_extra
from swarm.core.cli_sessions import is_resume_failure_text


def test_failed_status_and_api_error_text_are_error_previews():
    assert classify_output_preview("execution timed out", status="failed") == "error"
    assert classify_output_preview("[API Error: 429 rate limit]", status="completed") == "error"
    assert classify_output_preview("No CLI agents are configured.") == "error"
    assert classify_output_preview("Refactored the loader", status="completed") == "reply"
    assert classify_output_preview("", status="completed") == ""
    assert classify_output_preview(
        "anything",
        meta={"fatal_config_error": True},
    ) == "error"
    # Ordinary "conversation found" prose must not be stamped fatal. Claude's
    # "No conversation found …" still matches "no conversation". A user quoting
    # config copy is not an error; a stored fatal flag still is.
    prose = "The conversation found the regression"
    assert fatal_config_error_extra(prose) == {}
    assert classify_output_preview(prose, meta={"role": "assistant"}) == "reply"
    assert is_resume_failure_text("No conversation found with session ID") is True
    assert classify_output_preview(
        "No CLI agents are configured.",
        meta={"role": "user"},
    ) == "reply"
    assert classify_output_preview(
        "session not found",
        meta={"role": "assistant", "fatal_config_error": True},
    ) == "error"


def test_rail_summary_classifies_the_snippet_turn(tmp_path):
    path = chat_store._active_path("u0", "remote-trueforge", chat_store.store_dir(base_dir=tmp_path))
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    record = chat_store.empty_record(user_key="u0", agent_id="remote-trueforge")
    record["updated_at"] = "2026-09-18T10:00:00+00:00"
    record["messages"] = [
        {"role": "user", "content": "ping"},
        {"role": "assistant", "content": "[API Error: upstream reset]"},
        {"role": "status", "content": "running tools…"},
    ]
    chat_store._atomic_write(path, record)
    row = chat_store.rail_activity_summaries(base_dir=tmp_path, user_key="u0")["remote-trueforge"]
    assert row["preview_class"] == "error"
    assert row["text"].startswith("[API Error:")
    assert "running tools" not in row["text"]


def test_user_prompt_is_not_stamped_as_an_error_preview(tmp_path):
    path = chat_store._active_path("u0", "remote-trueforge", chat_store.store_dir(base_dir=tmp_path))
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    record = chat_store.empty_record(user_key="u0", agent_id="remote-trueforge")
    record["updated_at"] = "2026-09-18T10:00:00+00:00"
    record["messages"] = [
        {"role": "user", "content": "No CLI agents are configured. Can you fix that?"},
    ]
    chat_store._atomic_write(path, record)
    row = chat_store.rail_activity_summaries(base_dir=tmp_path, user_key="u0")["remote-trueforge"]
    assert row["preview_class"] == "reply"
    assert "No CLI agents" in row["text"]


def test_session_preview_class_uses_the_full_output(tmp_path, monkeypatch):
    """A fatal phrase past the 160-character preview still classifies as error."""
    monkeypatch.setenv("SWARM_RESPONSES_DIR", str(tmp_path))
    from swarm.core import responses_store

    text = ("status nominal. " * 20) + "endpoint not configured for this harness"
    assert len(text) > 160
    responses_store.save({
        "id": "resp_long",
        "object": "response",
        "response": {
            "id": "resp_long",
            "model": "hybrid_team",
            "status": "completed",
            "created_at": 1,
            "output_text": text,
        },
        "messages": [],
        "owner": "user:explorer",
    })
    row = responses_store.list_summaries()[0]
    assert row["output_preview"].endswith("…")
    assert "endpoint not configured" not in row["output_preview"]
    assert row["preview_class"] == "error"


def test_stamp_rail_activity_sets_error_class_only_for_failures():
    payload: dict = {}
    chat_store.stamp_rail_activity(
        payload,
        {"at": "2026-09-18T10:00:00+00:00", "text": "[API Error: down]", "preview_class": "error"},
    )
    assert payload["last_message_class"] == "error"
    assert payload["last_message"] == "[API Error: down]"

    ordinary: dict = {}
    chat_store.stamp_rail_activity(
        ordinary,
        {"at": "2026-09-18T10:00:00+00:00", "text": "shipped", "preview_class": "reply"},
    )
    assert "last_message_class" not in ordinary
    assert ordinary["last_message"] == "shipped"

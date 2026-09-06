"""Tests for REQ-191b: Role agents Mode B wiring (ADR-010)."""

import pytest

from swarm.core.agent_roles import (
    ROLE_GATE,
    ROLE_SKEPTIC,
    ROLE_SUPPORT,
    WORKFLOW_AS_TOOL,
    WORKFLOW_HANDOFF,
    ModeBPayload,
    is_mode_b_payload,
    parse_mode_b_payload,
)


def test_mode_b_payload_valid_as_tool():
    payload = ModeBPayload(
        invocation=WORKFLOW_AS_TOOL,
        caller_id="chief_of_staff",
        role=ROLE_GATE,
        latest_message="classify tool: bash(rm -rf /)",
        caller_context="User asked to clear disk cache",
        callee_thread_id="thread_private_gate_configure_123",
    )
    assert payload.invocation == "as_tool"
    assert payload.role == "gate"

    messages = payload.build_model_messages(system_prompt="You are a safety gate.")
    assert len(messages) == 3
    assert messages[0] == {"role": "system", "content": "You are a safety gate."}
    assert "[Caller Context from chief_of_staff]:\nUser asked to clear disk cache" in messages[1]["content"]
    assert messages[2] == {"role": "user", "content": "classify tool: bash(rm -rf /)"}

    # Verify callee_thread_id is NOT in model context
    for msg in messages:
        assert "thread_private_gate_configure_123" not in msg["content"]


def test_mode_b_payload_valid_handoff():
    caller_history = [
        {"role": "user", "content": "Write a python script"},
        {"role": "assistant", "content": "Here is the code draft..."},
    ]
    payload = ModeBPayload(
        invocation=WORKFLOW_HANDOFF,
        caller_id="engineer",
        role=ROLE_SKEPTIC,
        latest_message="Please review the draft for edge cases",
        caller_context=caller_history,
        callee_thread_id="thread_private_skeptic_mode_a",
    )
    assert payload.invocation == "handoff"
    assert payload.role == "skeptic"

    messages = payload.build_model_messages(system_prompt="Reviewer instructions")
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "Write a python script"
    assert messages[2]["content"] == "Here is the code draft..."
    assert messages[3]["content"] == "Please review the draft for edge cases"

    # Context isolation check
    for msg in messages:
        assert "thread_private_skeptic_mode_a" not in msg["content"]


def test_mode_b_validation_failures():
    with pytest.raises(ValueError, match="Invalid invocation"):
        ModeBPayload(
            invocation="invalid_mode",
            caller_id="agent1",
            role=ROLE_SUPPORT,
            latest_message="help",
            caller_context="ctx",
        )

    with pytest.raises(ValueError, match="caller_id is required"):
        ModeBPayload(
            invocation=WORKFLOW_AS_TOOL,
            caller_id="",
            role=ROLE_SUPPORT,
            latest_message="help",
            caller_context="ctx",
        )

    with pytest.raises(ValueError, match="latest_message is required"):
        ModeBPayload(
            invocation=WORKFLOW_AS_TOOL,
            caller_id="agent1",
            role=ROLE_SUPPORT,
            latest_message="",
            caller_context="ctx",
        )


def test_is_and_parse_mode_b_payload():
    raw = {
        "invocation": "as-tool",
        "caller_id": "coordinator",
        "role": "cos",
        "latest_message": "delegate task",
        "caller_context": "task summary",
    }
    assert is_mode_b_payload(raw)
    parsed = parse_mode_b_payload(raw)
    assert isinstance(parsed, ModeBPayload)
    assert parsed.invocation == "as_tool"
    assert parsed.role == "chief_of_staff"

    invalid_raw = {"role": "gate"}
    assert not is_mode_b_payload(invalid_raw)

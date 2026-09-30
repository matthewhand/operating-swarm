from pathlib import Path


def test_req179_no_visible_names_in_agent_message_bubble():
    repo_root = Path(__file__).resolve().parents[2]
    bubble_tsx = (
        repo_root
        / "webui"
        / "frontend"
        / "src"
        / "components"
        / "AgentChat"
        / "AgentMessageBubble.tsx"
    )
    assert bubble_tsx.exists()
    content = bubble_tsx.read_text(encoding="utf-8")

    # Verifies no visible message.agent rendered above chat bubbles
    assert "{!isUser && message.agent && (" not in content
    # Verifies no visible message.agent appended to review bubble header
    assert "{message.agent ? ` · ${message.agent}` : ''}" not in content
    # Verifies accessible aria-label is present
    assert "aria-label=" in content
    assert "speaker" in content


# `test_req179_chat_message_bubble_preserves_no_names_and_edited` used to live
# here with a body byte-identical to `tests/unit/test_req122_no_bubble_names.py`
# (whole file deleted). Both collected, so the same ChatMessageBubble.tsx grep
# ran twice under two names.
#
# That property -- no visible "You"/agentName above a bubble, an accessible
# label on the container, and a preserved edited hint -- is now asserted by
# RENDERING, in
# `webui/frontend/src/components/__tests__/ChatMessageBubble.test.tsx`
# (describe "REQ-122: No You / agent name labels above chat bubbles"), which is
# strictly stronger: it queries the DOM (`queryByText('You')`,
# `getByLabelText('Stewie message')`, `getByTestId('edited-hint')`) instead of
# grepping a JSX literal. A substring pin could be satisfied by a commented-out
# branch and could not detect the label reappearing in any other form.

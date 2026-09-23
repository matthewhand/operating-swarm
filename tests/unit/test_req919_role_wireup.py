"""
REQ-919 / #532 — role assignment UX + suggestions role end-to-end contracts.

Pin the acceptance points that are otherwise easy to regress:

A. Edit Agent's role picker presents the default as ``Worker (default)``
   (not ``none``) and non-worker roles reveal a consumer wire-up.
B. The wire-up shows the verb diagram (consumers -> provider) and the
   unused-role hint.
C. The suggestions role presents **exactly 3** suggestions: the specialist
   instructions and every mode prompt demand a fixed trio, and
   ``SUGGESTIONS_COUNT`` is the single knob.
D. A provider's chat shows consumer pills (``ConsumerPills``) wired into
   ChatPage that expand the suggestions exchanged with that consumer.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

CHATPAGE = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
EDITOR = REPO / "webui" / "frontend" / "src" / "components" / "AgentEditor.tsx"
PILLS = REPO / "webui" / "frontend" / "src" / "components" / "ConsumerPills.tsx"
ROLE_LIB = REPO / "webui" / "frontend" / "src" / "lib" / "roleConsumers.ts"
SUGGESTIONS = REPO / "src" / "swarm" / "core" / "suggestions.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_worker_is_the_default_role_label():
    editor = _read(EDITOR)
    assert "'Worker (default)'" in editor, "role picker must present Worker as the default"
    assert "{ value: 'default', label: 'none' }" not in editor


def test_role_wireup_ui_exists_in_editor():
    editor = _read(EDITOR)
    assert 'data-testid="role-consumer-wireup"' in editor
    assert 'data-testid="role-unused-hint"' in editor, "the unused-role hint is required"
    assert 'data-testid="role-verb-diagram"' in editor, "verb diagram is required"
    assert "saveRoleConsumers" in editor, "wire-up must persist"


def test_role_consumer_store_contract():
    lib = _read(ROLE_LIB)
    for fn in (
        "loadRoleConsumers",
        "saveRoleConsumers",
        "toggleRoleConsumer",
        "loadProviderEdges",
        "loadConsumerEdges",
    ):
        assert re.search(rf"export function {fn}\b", lib), f"{fn} missing from roleConsumers"


def test_suggestions_demand_exactly_three():
    src = _read(SUGGESTIONS)
    assert "SUGGESTIONS_COUNT = 3" in src, "#532: the role presents exactly 3 suggestions"
    # The canned specialist instructions and both mode prompts all name the count.
    assert src.count("exactly") >= 3
    assert "2-5" not in src, "old 2-5 range must not survive in prompts"


def test_consumer_pills_wired_into_chat():
    chat = _read(CHATPAGE)
    pills = _read(PILLS)
    assert "ConsumerPills" in chat and "providerId={activeChatAgentId}" in chat
    assert 'data-testid="consumer-pills"' in pills
    assert "fetchAgentSuggestions" in pills, "pill expansion shows the live suggestions"

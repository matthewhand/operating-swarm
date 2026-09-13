"""REQ-844 / #166 — speech-bubble tails stay visible and symmetrically spaced.

The default chat transcript keeps the DaisyUI speech-bubble tail on both sides
(assistant bottom-left, user bottom-right) with equal inline room so neither
tail is clipped. Behaviour spec of record (vitest):
webui/frontend/src/lib/__tests__/speechBubbleTails.test.ts
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CSS = REPO / "webui" / "frontend" / "src" / "index.css"
BUBBLE_THEME = REPO / "webui" / "frontend" / "src" / "lib" / "bubbleTheme.ts"
BEHAVIOUR_TEST = (
    REPO / "webui" / "frontend" / "src" / "lib" / "__tests__" / "speechBubbleTails.test.ts"
)


def test_req844_speech_is_the_default_bubble_theme():
    text = BUBBLE_THEME.read_text(encoding="utf-8")
    assert "DEFAULT_BUBBLE_THEME: BubbleTheme = 'speech'" in text
    assert "'speech'" in text


def test_req844_tails_are_shared_and_mirrored():
    css = CSS.read_text(encoding="utf-8")
    assert ".os-chat-transcript .chat-start .chat-bubble::before," in css
    assert ".os-chat-transcript .chat-end .chat-bubble::before" in css


def test_req844_equal_room_on_both_sides_of_transcript():
    css = CSS.read_text(encoding="utf-8")
    blocks = re.findall(r"\.os-chat-transcript\s*\{([^}]*)\}", css)
    base = next((b for b in blocks if "scroll-padding-bottom" in b), None)
    assert base, "missing base .os-chat-transcript rule"
    left = re.search(r"padding-left:\s*([^;]+);", base)
    right = re.search(r"padding-right:\s*([^;]+);", base)
    assert left and right, "transcript needs explicit padding-left and padding-right"
    left_v, right_v = left.group(1).strip(), right.group(1).strip()
    assert left_v == right_v, f"asymmetric gutters: {left_v} vs {right_v}"
    numeric = float(re.sub(r"[^0-9.]", "", left_v))
    assert numeric >= 0.75, "gutter smaller than one tail width"


def test_req844_behaviour_spec_of_record_exists():
    assert BEHAVIOUR_TEST.exists(), "speechBubbleTails.test.ts must exist"
    text = BEHAVIOUR_TEST.read_text(encoding="utf-8")
    assert "#166" in text
    assert "paddingPair" in text
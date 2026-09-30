"""REQ-176: Blob eyes must wander while the agent is working/streaming.

The Python half now reads the stylesheet as parsed rules; the JSX-substring
pins are gone, because the user-visible half of REQ-176 is asserted by a render
test that already exists.

What rotted
-----------
``assert "active={isWorking}" in content`` matched a JSX prop written literally
on an element. The refactor that introduced the local
``headerActive = isWorking || headerWorking || isAgentTurnActive(...)`` is a
strict *widening* of the working signal — #1360 keeps the header animated while
aux/agent turns run and honours the per-thread streaming flag — and the pin
went red for a behaviour improvement. A substring cannot tell a widening from
a regression: it fails both.

What the replacement asserts instead
------------------------------------
The stylesheet, read as parsed rules, with the two properties a string pin
genuinely could not check:

* the ``animation`` shorthand on the active pose names a ``@keyframes`` block
  that actually exists *and* actually transforms the eyes. The old test
  asserted ``"animation: os-blob-wander"`` and ``"@keyframes os-blob-wander"``
  as two independent strings, so a rule pointing at a keyframe nobody defined —
  or a keyframe with no transform, which renders a frozen pose — passed.
* the idle pose is animated too, and slower than the working pose, so a resting
  agent does not read as busy. The active rule alone cannot see the idle branch
  go dead.

The user-visible half — a connected-but-idle header blob reporting
``data-eye-state="idle"``, and the composer working indicator being absent —
is asserted in ``webui/frontend/src/pages/__tests__/BlobEyesActive.test.tsx``,
which mounts ``ChatPage`` with a mocked WebSocket. Pinning *that* file from
here would be the same defect one layer down.
"""

import re
from pathlib import Path

from helpers.css_rules import declaration_in, declarations, read_css, rule

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui/frontend/src/index.css"

ACTIVE = '.os-blob-avatar[data-eye-state="active"] .os-blob-eyes'
IDLE = '.os-blob-avatar[data-eye-state="idle"] .os-blob-eyes'

_TRANSFORM_CALL = re.compile(r"\b(translate|rotate|scale|matrix)\s*\(")


def _animation_of(css: str, selector: str) -> str:
    return declarations(rule(css, selector)).get("animation", "")


def _keyframe_name(animation: str) -> str:
    """The leading identifier of a CSS ``animation`` shorthand."""
    return animation.split()[0] if animation.strip() else ""


def _duration_ms(animation: str) -> int | None:
    """Milliseconds from an ``animation`` shorthand.

    Handles the two shapes the sheet uses: a bare duration, and a
    ``var(--ed, 9s)`` that may be wrapped in ``calc(... * 1.6)`` to slow a
    pose down relative to the working one. Both are matched by regex rather
    than by splitting on whitespace, because ``var(--ed, 9s)`` contains a space
    and the ``calc`` argument list contains parentheses.
    """
    calc = re.search(r"calc\((?:[^()]|\([^()]*\))*\s*\*\s*([0-9.]+)\s*\)", animation)
    base = None
    for pattern, scale in ((r"([\d.]+)ms", 1.0), (r"([\d.]+)s\b", 1000.0)):
        match = re.search(pattern, animation)
        if match:
            base = float(match.group(1)) * scale
            break
    if base is None:
        return None
    if calc:
        base *= float(calc.group(1))
    return int(base)


def test_active_blob_eyes_name_a_keyframe_that_exists_and_actually_moves():
    """The working pose is a real animation, not a dangling name.

    What the old assertion could not catch: ``animation: <name>`` present while
    ``@keyframes <name>`` had been renamed or deleted, or defined with no
    transform at all — both leave the eyes frozen and both passed the two
    independent string checks.
    """
    css = read_css(INDEX_CSS)
    animation = _animation_of(css, ACTIVE)
    assert animation, f"{ACTIVE} sets no animation — the working pose is frozen"

    name = _keyframe_name(animation)
    frames = rule(css, f"@keyframes {name}")
    assert frames, f"the active pose names @keyframes {name}, which is never defined"
    assert _TRANSFORM_CALL.search(frames), (
        f"@keyframes {name} declares no transform, so the eyes never move"
    )
    assert len(re.findall(r"\d+%", frames)) >= 2, (
        f"@keyframes {name} has fewer than two stops — nothing interpolates"
    )


def test_idle_pose_is_animated_and_slower_than_the_working_pose():
    """#110: an idle blob is a drifting rest pose, not a frozen one.

    The active-pose rule cannot see the idle branch disappear, so this is its
    own check. Idle must also be *slower*: at the working pose's cadence a
    resting agent reads as busy, which is the defect #110 was filed for.
    """
    css = read_css(INDEX_CSS)
    idle = _animation_of(css, IDLE)
    assert idle, f"{IDLE} sets no animation — a resting blob is frozen"
    idle_frames = rule(css, f"@keyframes {_keyframe_name(idle)}")
    assert idle_frames, "the idle pose names a @keyframes block that is never defined"
    assert _TRANSFORM_CALL.search(idle_frames)

    working_ms = _duration_ms(_animation_of(css, ACTIVE))
    idle_ms = _duration_ms(idle)
    assert working_ms and idle_ms, "a pose has no readable duration"
    assert idle_ms > working_ms, (
        f"idle ({idle_ms}ms) is not slower than the working pose ({working_ms}ms) — "
        "a resting agent would read as busy"
    )


def test_both_blob_poses_stop_under_prefers_reduced_motion():
    """Reduced motion disables the wandering, but keeps the per-agent offset.

    The old file asserted nothing here at all; only the frontend test covered
    the idle branch. This checks the sheet directly so a dropped
    ``prefers-reduced-motion`` block is caught without a browser.
    """
    css = read_css(INDEX_CSS)
    covered = {
        state
        for state in ("idle", "active")
        if declaration_in(
            css,
            f'.os-blob-avatar[data-eye-state="{state}"] .os-blob-eyes',
            "animation",
            within="@media (prefers-reduced-motion: reduce)",
        )
        == "none"
    }
    missing = {"idle", "active"} - covered
    assert not missing, f"prefers-reduced-motion does not stop the {sorted(missing)} pose(s)"


def test_blob_avatar_exposes_a_data_eye_state_attribute_for_css_to_key_off():
    """The pose is data-driven, so the stylesheet can select it.

    ``BlobAvatar.tsx`` writes ``data-eye-state={eyeState}``; the stylesheet keys
    both poses off that attribute. If the attribute is renamed, every rule above
    silently stops matching and the blob freezes while the rest of this file
    stays green — so the emitter and the consumer are pinned together.
    """
    source = (REPO_ROOT / "webui/frontend/src/components/BlobAvatar.tsx").read_text(
        encoding="utf-8"
    )
    assert "data-eye-state" in source, "BlobAvatar no longer emits data-eye-state"
    css = read_css(INDEX_CSS)
    for state, selector in (("active", ACTIVE), ("idle", IDLE)):
        assert f"'{state}'" in source, f"BlobAvatar no longer produces the {state!r} pose"
        assert rule(css, selector), (
            f"the {state} eye-state is emitted but no stylesheet rule consumes it"
        )

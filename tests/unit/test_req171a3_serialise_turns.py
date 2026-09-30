"""REQ-171A-3 / #603 — serialise overlapping websocket chat turns.

Rewritten off substring pins. Two of the old pins were outright wrong:

``_no_secrets(text)`` rejected the bare string ``"sk-"`` anywhere in
``consumers.py``. That matches ordinary English — the file contains
``ask-user`` twice — so the check was failing for a reason that had nothing to
do with secrets, while a real OpenAI key would have sailed through the same
naive pattern. It is now a set of *shaped* patterns, which is strictly
stronger: a comment full of ``sk-`` prose passes, and ``sk-proj-`` followed by
40 base62 characters fails.

``assert "REQ-171A-3" in text`` / ``"#603" in text`` / ``"#447" in text``
pinned ticket numbers in prose. A comment can be added by someone who has not
read the rule and the test passes; it can be reworded by someone who has and
the test fails. None of them is behaviour. The structural property they stood
in for — *one* ``respond_with_*`` at a time per connection, with tool-approval
frames kept off that lock — is now read from the AST of ``receive()``.

What moved out of this file
---------------------------
``test_spa_queues_second_send_via_generation_in_flight`` sliced 2,500
characters out of ``ChatPage.tsx`` starting at ``const submitUserText`` and
asserted three tokens and three ticket numbers were inside that window. A
window is the worst possible container: it slides as the function grows, and a
refactor that moved one line out of it failed the suite with no behaviour
change. The property it claimed is asserted properly, by rendering, in
``webui/frontend/src/pages/__tests__/ChatPage.queued.test.tsx`` — "queues a
second send before assistant_start so only one WS frame is in flight", plus
fifteen more cases covering queue draining, FIFO with no bypass, and
interrupt promotion.

The overlapping-receive and tool-decision behaviour is asserted by
``tests/test_consumers.py`` (``-k "overlapping_receives or
tool_decision_is_not_blocked"``), which drives real frames through a real
consumer rather than grepping its source.
"""

import ast
import re
from pathlib import Path

import yaml

from helpers.py_ast import (
    awaited_call_count,
    calls_within,
    calls_within_body,
    find_function,
    parse_module,
    string_constants,
)

REPO = Path(__file__).resolve().parents[2]
CONSUMER = REPO / "src/swarm/consumers.py"
CI = REPO / ".github/workflows/req171a3-serialise-turns.yml"
CHANGELOG = REPO / "CHANGELOG.md"

# Shaped credential patterns, not bare prefixes. Each is a real credential
# shape; none of them matches a word in an English sentence, which is exactly
# what the old bare ``sk-`` prefix did.
SECRET_PATTERNS = (
    (r"sk-(?:proj-|ant-|live-)?[A-Za-z0-9_-]{32,}", "an OpenAI-shaped API key"),
    (r"github_pat_[A-Za-z0-9_]{40,}", "a GitHub fine-grained PAT"),
    (r"gh[pousr]_[A-Za-z0-9]{30,}", "a GitHub classic token"),
    (
        r"\b(?:10\.\d{1,3}|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}\.\d{1,3}\b",
        "a private LAN address",
    ),
    (r"\bubuntu-(?:gtx|max)\b", "a private hostname"),
)


def _assert_no_secrets(text: str, where: str) -> None:
    for pattern, label in SECRET_PATTERNS:
        match = re.search(pattern, text)
        assert match is None, f"{where} contains {label}: {match.group(0)[:12]}…"


def test_consumer_serialises_chat_turns_not_tool_decisions():
    """One ``respond_with_*`` at a time per agent; tool approvals stay off it.

    Read from the AST of the consumer rather than from its text. What the old
    substring pins could not distinguish: a *comment* naming the lock from an
    actual lock acquisition, and a per-agent serialiser from a per-socket one.

    Note the mechanism changed under this ticket and the test follows the code,
    not the prose: #603 originally used one whole-socket lock
    (``_ensure_chat_turn_lock``), and ADR-017 PR-1 (#1097) replaced it with a
    per-agent lock so two *different* agents' turns may interleave while two
    sends to the same agent still queue. Both shapes satisfy "not two at once
    for one agent"; only the current one lets unrelated seats run in parallel,
    and a substring pin could not tell them apart.
    """
    module = parse_module(CONSUMER)

    # receive() routes chat frames through the serialised runner…
    assert awaited_call_count(module, "receive", "self._run_serialised_chat_turn") >= 1, (
        "receive() no longer routes chat frames through the serialised runner"
    )
    # …and the runner actually takes a lock. `async with self._agent_lock(...)`
    # is the current form; the legacy whole-socket lock is kept as a fallback
    # for callers that do not run under a turn identity.
    runner = find_function(module, "_run_serialised_chat_turn")
    locks = calls_within_body(module, "_run_serialised_chat_turn")
    assert any(
        name.endswith("_lock") or name.endswith("_lock(") for name in locks
    ) or any(
        isinstance(node, ast.AsyncWith) for node in ast.walk(runner)
    ), (
        "_run_serialised_chat_turn no longer takes a lock, so two sends for one "
        "agent can run a respond_with_* concurrently"
    )
    # The lock is a real asyncio.Lock, built by code and not by a comment.
    assert "asyncio.Lock" in calls_within_body(module, "_agent_lock"), (
        "_agent_lock no longer builds an asyncio.Lock"
    )
    assert "asyncio.Lock" in calls_within(module, "_ensure_chat_turn_lock"), (
        "the legacy fallback lock no longer builds an asyncio.Lock"
    )

    # Tool-approval frames bypass the lock: the frame type is a real literal,
    # and the branch returns before the runner is reached.
    assert "tool_decision" in string_constants(module), (
        "the tool_decision frame type is no longer a literal in consumers.py"
    )
    receive_calls = calls_within_body(module, "receive")
    assert "self._run_serialised_chat_turn" in receive_calls
    assert "self.resolve_tool_decision" in receive_calls, (
        "receive() no longer routes tool approvals to their own resolver"
    )

    source = CONSUMER.read_text(encoding="utf-8")
    _assert_no_secrets(source, "consumers.py")
    assert ":8001" not in source
    assert "neon" not in source.lower()
    assert "WAVE" not in source


def test_own_diff_ci_exists():
    """The own-diff gate is manual and actually runs the overlapping-turn suites.

    Parsed as YAML rather than grepped. The old check asserted six strings
    appeared somewhere in the file, so a workflow whose steps were emptied
    still passed, and editing a comment in it failed the suite.
    """
    raw = CI.read_text(encoding="utf-8")
    workflow = yaml.safe_load(raw)
    triggers = workflow.get("on", workflow.get(True, {}))
    assert set(triggers) == {"workflow_dispatch"}, (
        f"the own-diff gate must be manual, got {sorted(triggers)}"
    )

    steps = workflow["jobs"]["own-diff"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "tests/unit/test_req171a3_serialise_turns.py" in commands
    # The overlapping-receive and tool-decision behaviour lives in the shared
    # consumer suite; a gate that skips it gates nothing.
    assert "tests/test_consumers.py" in commands
    assert "overlapping_receives" in commands
    assert "tool_decision" in commands
    assert "vitest run" in commands
    assert "ChatPage.queued.test.tsx" in commands

    _assert_no_secrets(raw, "req171a3-serialise-turns.yml")
    assert ":8001" not in raw
    assert "WAVE" not in raw


def test_changelog_fixes_603_without_wave():
    """The changelog records the fix, and the retired label vocabulary is gone.

    The old version asserted ``"WAVE" not in text`` over a 400-character window
    ending at the fix entry. The window slides as entries are prepended above
    it, so an unrelated WAVE 500 characters earlier passed while a reworded
    neighbouring entry failed. Whole-file is both stronger and stable.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "Fixes #603" in text
    assert "WAVE" not in text
    _assert_no_secrets(text, "CHANGELOG.md")

"""REQ-893 / #475 — `remotes.py` defined its OpenMousBot helpers twice.

`db385e8d` (#125) *inserted* a rewritten copy of the OMB helper block after
`_omb_mint_dedicated_bot` instead of replacing the originals. Python binds the
**last** definition, so copy B won: the earlier copy — the one that matched a
bot by **name** as well as id — was dead code, while the live call site still
documented the behaviour:

    # Target already names a bot (id or name). Never mint a second one.
    #                       src/swarm/core/remotes.py, _omb_send

Two halves are pinned here:

1. a module-wide guard against duplicate module-level definitions (so a future
   botched insert fails loudly instead of silently shadowing);
2. the id-or-name contract itself, asserted against the *bound* function.

Source of record for the defect: issue #475 / REQ-893.
"""

import ast
from collections import Counter
from pathlib import Path

from swarm.core import remotes

REPO = Path(__file__).resolve().parents[2]
REMOTES = REPO / "src" / "swarm" / "core" / "remotes.py"

# The helper block that was duplicated (both copies lived in this one file).
OMB_HELPERS = (
    "_omb_bot_target",
    "_omb_message_text",
    "_omb_is_bot_text",
    "_omb_messages_from",
    "_omb_bots_from",
    "_omb_find_bot",
    "_omb_receipt_ids",
    "_omb_assistant_after",
    "_omb_poll_assistant",
)

BOTS = {
    "bots": [
        {"id": "scout-id", "name": "Scout"},
        {"id": "Scribe", "name": "Other"},  # a name that collides with another row's id
        {"id": "b3", "name": "Scribe"},
    ]
}


def _module_definitions() -> Counter:
    """Names defined directly in the module body (functions and classes)."""
    tree = ast.parse(REMOTES.read_text(encoding="utf-8"))
    return Counter(
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )


def test_req893_no_duplicate_module_level_definitions():
    """A name defined twice means the earlier definition is unreachable."""
    duplicates = {name: count for name, count in _module_definitions().items() if count > 1}
    assert duplicates == {}, f"shadowed module-level definitions in remotes.py: {duplicates}"


def test_req893_omb_helpers_are_defined_exactly_once():
    """The specific block that was duplicated (copy A 2082-2248 vs copy B 2298-2455)."""
    counts = _module_definitions()
    for name in OMB_HELPERS:
        assert counts[name] == 1, f"{name} is defined {counts[name]}x — one copy is dead code"
    text = REMOTES.read_text(encoding="utf-8")
    assert text.count("def _omb_find_bot(") == 1
    assert text.count("def _omb_poll_assistant(") == 1


def test_req893_find_bot_resolves_by_id():
    assert remotes._omb_find_bot(BOTS, "scout-id") == {"id": "scout-id", "name": "Scout"}


def test_req893_find_bot_resolves_by_name():
    """The behaviour the shadowed copy implemented and the live copy lost."""
    assert remotes._omb_find_bot(BOTS, "Scout") == {"id": "scout-id", "name": "Scout"}


def test_req893_find_bot_prefers_an_exact_id_over_a_name_match():
    """`Scribe` is both row 2's id and row 3's name — the id must win."""
    assert remotes._omb_find_bot(BOTS, "Scribe") == {"id": "Scribe", "name": "Other"}


def test_req893_find_bot_returns_none_for_unknown_or_empty():
    assert remotes._omb_find_bot(BOTS, "nope") is None
    assert remotes._omb_find_bot(BOTS, "") is None
    assert remotes._omb_find_bot(BOTS, None) is None


def test_req893_bots_from_accepts_the_payload_shapes_omb_sends():
    """Dict payloads (bots / agents / data), a bare list, and junk."""
    assert remotes._omb_bots_from(BOTS) == BOTS["bots"]
    assert remotes._omb_bots_from({"agents": [1]}) == [1]
    assert remotes._omb_bots_from({"data": [2]}) == [2]
    assert remotes._omb_bots_from([3]) == [3]
    assert remotes._omb_bots_from({"bots": "nope"}) == []
    assert remotes._omb_bots_from(None) == []

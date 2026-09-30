"""#1411 — the Django ``extra`` projection must not desync from the store.

``chat_store._normalize_messages`` defines which turn keys the transcript
store keeps. ``chat_db.extra_from_turn`` / ``turn_from_row`` project those
keys into and back out of the canonical ``ChatMessage.extra`` JSON blob.
A key that survives the store but is dropped by either projection is
silently lost user data on reload, so the three must agree exactly.

The other half of the contract: ``reaction_only`` is only meaningful with a
palette emoji behind it. Persisting the flag without the reaction writes an
empty assistant bubble that can never render a pill.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swarm.core.chat_db import _TURN_EXTRA_KEYS, extra_from_turn, turn_from_row
from swarm.core.chat_store import _normalize_messages
from swarm.core.message_reactions import REACTION_EMOJIS, reaction_only_record
from swarm.core.thread_load import public_message

PALETTE = REACTION_EMOJIS[0]
OFF_PALETTE = "🔥"


def _row(turn: dict) -> SimpleNamespace:
    return SimpleNamespace(
        sender=turn.get("role", "user"),
        content=turn.get("content", ""),
        extra=extra_from_turn(turn),
        timestamp=None,
    )


def test_every_store_turn_key_survives_the_extra_round_trip():
    """The store allowlist and the Django ``extra`` allowlist must be the same set."""
    turn = {
        "role": "assistant",
        "content": "landed",
        "ts": "2026-09-27T12:00:00+00:00",
        "name": "jeeves",
        "edited": True,
        "kind": "status",
        "from_conversation_id": "c0-abc",
        "seq": 7,
        "fatal_config_error": True,
        "config_target": {"section": "provider"},
        "reactions": [{"emoji": PALETTE, "actors": ["user", "agent:jeeves"]}],
        "reaction_only": True,
    }
    [stored] = _normalize_messages([turn])
    extra = extra_from_turn(stored)
    assert set(extra) == set(_TURN_EXTRA_KEYS) & set(stored)
    restored = turn_from_row(_row(stored))
    assert set(restored) == set(stored)
    assert restored == stored
    assert public_message(restored) == public_message(stored)


def test_turn_extra_keys_have_no_duplicates():
    assert len(_TURN_EXTRA_KEYS) == len(set(_TURN_EXTRA_KEYS))


@pytest.mark.parametrize(
    "turn",
    [
        pytest.param(
            reaction_only_record(emoji=OFF_PALETTE, actor="agent:jeeves"),
            id="off-palette-emoji",
        ),
        pytest.param(
            {
                "role": "assistant",
                "content": "",
                "reaction_only": True,
                "reactions": [{"emoji": PALETTE, "actors": ["nobody"]}],
            },
            id="no-valid-actor",
        ),
        pytest.param(
            {
                "role": "assistant",
                "content": "",
                "reaction_only": True,
                "reactions": "not-a-list",
            },
            id="reactions-not-a-list",
        ),
        pytest.param(
            {
                "role": "assistant",
                "content": "",
                "reaction_only": True,
                "reactions": [{"emoji": PALETTE, "actors": []}],
            },
            id="emoji-without-actors",
        ),
    ],
)
def test_extra_never_persists_a_reaction_only_shell(turn):
    """``reaction_only`` without a surviving pill is an empty bubble: not stored."""
    extra = extra_from_turn(turn)
    assert "reaction_only" not in extra
    assert "reactions" not in extra
    restored = turn_from_row(_row(turn))
    assert "reaction_only" not in restored
    assert "reactions" not in restored
    # A flag with no pill must also not reach the client projection.
    assert "reaction_only" not in public_message(restored)
    assert "reactions" not in public_message(restored)


def test_valid_reaction_only_turn_round_trips_both_ways():
    turn = reaction_only_record(emoji=PALETTE, actor="agent:jeeves")
    extra = extra_from_turn(turn)
    assert extra == {
        "reaction_only": True,
        "reactions": [{"emoji": PALETTE, "actors": ["agent:jeeves"]}],
    }
    restored = turn_from_row(_row(turn))
    assert restored == turn
    public = public_message(restored)
    assert public["reaction_only"] is True
    assert public["content"] == ""
    assert public["reactions"][0]["emoji"] == PALETTE
    assert public["reactions"][0]["agentReacted"] is True
    assert public["reactions"][0]["count"] == 1


def test_reactions_alone_persist_without_the_reaction_only_flag():
    """A plain reacted turn keeps its pill and must not gain the flag."""
    turn = {
        "role": "user",
        "content": "ship it",
        "reactions": [{"emoji": PALETTE, "actors": ["user"]}],
    }
    extra = extra_from_turn(turn)
    assert extra == {"reactions": [{"emoji": PALETTE, "actors": ["user"]}]}
    assert "reaction_only" not in turn_from_row(_row(turn))

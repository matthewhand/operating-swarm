"""#1319 — newest-first transcript paging in the shared loader.

``paginate_thread`` slices one contiguous seq-window of turns + UI events so
that:

- the newest page is bounded by ``limit`` with ``has_more`` + ``next_cursor``;
- ``?before=<cursor>`` walks older pages with no duplicates or gaps;
- UI chrome in the window travels with its turns (spans stay contiguous);
- no ``limit`` / ``before`` keeps the legacy full-transcript load.
"""

from __future__ import annotations

from swarm.core.thread_load import paginate_thread


def _turns(n: int) -> list[dict]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}", "seq": i}
        for i in range(n)
    ]


def test_no_paging_returns_full_transcript():
    turns = _turns(4)
    events = [{"role": "status", "content": "note", "seq": 4}]
    page_turns, page_events, has_more, cursor = paginate_thread(turns, events)
    assert page_turns == turns
    assert page_events == events
    assert has_more is False
    assert cursor == ""


def test_newest_page_is_bounded_with_cursor():
    page, events, has_more, cursor = paginate_thread(_turns(6), [], limit=2)
    assert [row["content"] for row in page] == ["m4", "m5"]
    assert events == []
    assert has_more is True
    assert cursor == "4"


def test_walk_older_pages_without_duplicates_or_gaps():
    turns = _turns(7)
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        page, _, has_more, next_cursor = paginate_thread(
            turns, [], limit=3, before=cursor
        )
        seen = [row["content"] for row in page] + seen
        if not has_more:
            assert next_cursor == ""
            break
        cursor = next_cursor
    else:  # pragma: no cover - safety net
        raise AssertionError("pagination did not terminate")
    assert seen == [f"m{i}" for i in range(7)]
    assert len(seen) == len(set(seen))


def test_before_without_limit_returns_everything_older():
    page, _, has_more, cursor = paginate_thread(_turns(5), [], before=3)
    assert [row["content"] for row in page] == ["m0", "m1", "m2"]
    assert has_more is False
    assert cursor == ""


def test_events_are_windowed_with_their_turns():
    # Interleave a UI event after every turn (shared seq space).
    turns = _turns(6)
    events = [
        {"role": "status", "content": f"e{i}", "seq": i + 100} for i in range(6)
    ]
    # Rebuild a realistic interleaving: event seq sits between turns.
    for i, event in enumerate(events):
        event["seq"] = i * 2 + 1
    for i, turn in enumerate(turns):
        turn["seq"] = i * 2

    newest_turns, newest_events, has_more, cursor = paginate_thread(
        turns, events, limit=2
    )
    assert [row["content"] for row in newest_turns] == ["m4", "m5"]
    # Events at/after the page's oldest turn (seq 8) belong to this page.
    assert [row["content"] for row in newest_events] == ["e4", "e5"]
    assert has_more is True
    assert cursor == "8"

    older_turns, older_events, has_more, _ = paginate_thread(
        turns, events, limit=2, before=cursor
    )
    assert [row["content"] for row in older_turns] == ["m2", "m3"]
    assert [row["content"] for row in older_events] == ["e2", "e3"]
    assert has_more is True

    # The oldest page keeps events that precede the first turn (no loss).
    oldest_turns, oldest_events, has_more, _ = paginate_thread(
        turns, events, limit=2, before="4"
    )
    assert [row["content"] for row in oldest_turns] == ["m0", "m1"]
    assert [row["content"] for row in oldest_events] == ["e0", "e1"]
    assert has_more is False


def test_invalid_cursor_and_limit_fall_back_to_full_load():
    turns = _turns(3)
    page, _, has_more, cursor = paginate_thread(turns, [], limit="nope", before="nope")
    assert page == turns
    assert has_more is False
    assert cursor == ""
    page, _, _, _ = paginate_thread(turns, [], limit=-5)
    assert page == turns


def test_empty_thread_is_safe():
    page, events, has_more, cursor = paginate_thread([], [], limit=10)
    assert page == []
    assert events == []
    assert has_more is False
    assert cursor == ""

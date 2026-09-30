"""#1712: the default-model seat is a real seat and must be exported.

`agent_id=""` is not "no agent". The default-model seat has no blueprint, and
`chat_store.normalize_agent_id("")` maps it to `_default` -- a real, addressable
seat with its own transcript.

Four guard sites in `chat_repository` tested the empty string for emptiness
(`if not agent_id: return`) and therefore skipped the default-model seat
entirely: the JSON export was never written, and clearing a default thread left
the previous export on disk for a later `load` to return as live.

The consequence was a split brain. The Django rows were correct throughout, so
`load_or_django` -- which falls back to the DB -- looked healthy, and the bug
only surfaced on the file-only paths: the archive, retention/prune, the export
endpoint and the one-way import all reported an empty thread for a seat that
had a full conversation in it.

The `user is None` early return is the one that is genuine: `user_key_for(None)`
raises and there is no owner to file an export under. These tests pin both
halves -- an empty `agent_id` still exports, and a `None` user still does not.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from swarm.core import chat_repository, chat_store


def _user(db, name="default-seat"):
    return get_user_model().objects.create_user(username=name, password="pw")


def test_an_empty_agent_id_is_the_default_seat_not_a_skip(db, tmp_path):
    """The property the old guard destroyed: "" exports, and it exports as
    `_default`. A test that only asserted "a file appeared" would pass against
    a fix that picked some other stem, so the stem is pinned too."""
    user = _user(db)
    key = chat_store.user_key_for(user)

    # The premise: "" normalises to a real, addressable seat.
    assert chat_store.normalize_agent_id("") == "_default"

    chat_repository.refresh_cache(
        user,
        "",
        "conv-default-1",
        [{"role": "user", "content": "hello from the default seat"}],
        [],
        base_dir=tmp_path,
    )

    export = tmp_path / "active" / key / "_default.json"
    assert export.is_file(), f"default-model seat was not exported to {export}"
    record = chat_store.load(key, "", base_dir=tmp_path)
    assert record is not None, "the export exists but load() cannot read it back"
    assert [t.get("content") for t in record.get("messages", [])] == [
        "hello from the default seat"
    ]


def test_a_named_seat_and_the_default_seat_are_separate_exports(db, tmp_path):
    """Writing the default seat must not land in, or clobber, a named seat's
    file -- the two are distinct seats and `load` must not cross them."""
    user = _user(db)
    key = chat_store.user_key_for(user)

    chat_repository.refresh_cache(
        user, "jeeves", "conv-j", [{"role": "user", "content": "jeeves line"}], [], base_dir=tmp_path
    )
    chat_repository.refresh_cache(
        user, "", "conv-d", [{"role": "user", "content": "default line"}], [], base_dir=tmp_path
    )

    named = chat_store.load(key, "jeeves", conversation_id="conv-j", base_dir=tmp_path)
    default = chat_store.load(key, "", conversation_id="conv-d", base_dir=tmp_path)
    assert named is not None and default is not None
    assert [t.get("content") for t in named["messages"]] == ["jeeves line"]
    assert [t.get("content") for t in default["messages"]] == ["default line"]


def test_clearing_the_default_thread_overwrites_its_stale_export(db, tmp_path):
    """The stale-export half. `clear_thread` used to return before writing when
    `agent_id` was empty, so the previous `_default.json` survived and a later
    `load` handed back a thread the user had already cleared."""
    user = _user(db)
    key = chat_store.user_key_for(user)
    cid = chat_store.conversation_id_for(user, "")

    chat_repository.refresh_cache(
        user, "", cid, [{"role": "user", "content": "before clear"}], [], base_dir=tmp_path
    )
    assert (tmp_path / "active" / key / "_default.json").is_file()

    chat_repository.clear_thread(user, cid, agent_id="", base_dir=tmp_path)

    record = chat_store.load(key, "", base_dir=tmp_path)
    assert record is None or record.get("messages") == [], (
        "clear_thread left a stale default-model export behind: "
        f"{(tmp_path / 'active' / key / '_default.json').read_text(encoding='utf-8')[:400]}"
    )


def test_a_none_user_is_still_a_genuine_skip(db, tmp_path):
    """The half of the guard that was correct and must stay correct: there is
    no owner to file an export under, and `user_key_for(None)` raises. If this
    ever stops being a skip, the default seat stops being the reason."""
    chat_repository.refresh_cache(
        None, "", "conv-x", [{"role": "user", "content": "no owner"}], [], base_dir=tmp_path
    )
    assert list(tmp_path.rglob("_default.json")) == []

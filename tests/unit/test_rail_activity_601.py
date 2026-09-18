"""#601 — rail activity instants.

The rail's right slot (unread dot > time > badge, #501) defaulted to a
timestamp no row could supply for remotes and teams: the server never sent
one. ``chat_store.rail_activity_index`` is the source that actually knows —
the newest ``updated_at`` across every persisted thread for the requesting
user, keyed by store stem. Team threads persist under ``team-<id>`` (the
SPA's ``teamThreadId``); remote seats under ``remote-<id>`` (the ``:``
slugs to ``-`` in ``normalize_agent_id``).
"""

from swarm.core import chat_store


def _seed(tmp_path, agent_id: str, updated_at: str):
    """Persist a thread record carrying a known updated_at.

    save() stamps updated_at itself and has no backdate knob, so the test
    writes the record JSON through save()'s own helpers.
    """
    path = chat_store._active_path("u0", agent_id, chat_store.store_dir(base_dir=tmp_path))
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    record = chat_store.empty_record(user_key="u0", agent_id=agent_id)
    record["updated_at"] = updated_at
    record["messages"] = [
        {"role": "user", "content": f"hello {agent_id}"},
        {"role": "assistant", "content": f"hi {agent_id}"},
    ]
    chat_store._atomic_write(path, record)


def test_activity_index_reads_iso_updated_at(tmp_path):
    _seed(tmp_path, "remote-trueforge", "2026-09-18T10:00:00+00:00")
    index = chat_store.rail_activity_index(base_dir=tmp_path, user_key="u0")
    assert index["remote-trueforge"] == "2026-09-18T10:00:00+00:00"


def test_activity_index_takes_newest_across_sessions(tmp_path):
    _seed(tmp_path, "team-demo", "2026-09-18T09:00:00+00:00")
    _seed(tmp_path, "team-demo__s2", "2026-09-18T11:30:00+00:00")
    index = chat_store.rail_activity_index(base_dir=tmp_path, user_key="u0")
    assert index["team-demo"] == "2026-09-18T11:30:00+00:00"


def test_activity_index_user_key_scopes_results(tmp_path):
    _seed(tmp_path, "remote-omb", "2026-09-18T08:00:00+00:00")
    assert "remote-omb" in chat_store.rail_activity_index(base_dir=tmp_path, user_key="u0")
    assert chat_store.rail_activity_index(base_dir=tmp_path, user_key="u7") == {}


def test_activity_index_no_store_returns_empty(tmp_path):
    assert chat_store.rail_activity_index(base_dir=tmp_path, user_key="u0") == {}

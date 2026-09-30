"""Swarm's migration graph has one leaf.

Three empty 0021 merges (#1448, #1492, #1518) all join the same 0020
Company and chat-extra parents. ``0022_chatmessage_timestamp_explicit``
depends on every one of them. The activity row, chat trash, and the two
empty 0022 merges join at ``0024_merge_activity_and_chat_leaves``.

``0021_merge_0020_chatmessage_and_0020_company`` (#1600) repeats that
0020 pair and has no child of its own. ``0023_sharedlibraryitem``
(#1570) branches off the timestamp node. ``0025_merge_0020_join_with_activity_leaf``
joins those leaves. A new migration has to depend on 0025, or
``migrate`` refuses to run.

``0026_chatconversation_purged_at`` (#1721) is that new migration: the
hard-delete tombstone that stops the one-way JSON import from resurrecting a
permanently deleted conversation. It depends on 0025, so the graph still has
exactly one leaf and an install that already applied 0025 migrates forward
without a merge node.
"""

from django.db.migrations.loader import MigrationLoader

_COMPANY = "0020_company"
_CHAT_EXTRA = "0020_chatmessage_extra_chatconversation_ui_events"
_MERGES = (
    "0021_merge_company_and_chat_extra",
    "0021_merge_company_and_chat_restore",
    "0021_merge_company_ui_events",
)
_ORPHAN_0021 = "0021_merge_0020_chatmessage_and_0020_company"
_TIMESTAMP = "0022_chatmessage_timestamp_explicit"
_DUPLICATE_THREE = "0022_merge_duplicate_company_chat_leaves"
_DUPLICATE_TWO = "0022_merge_duplicate_company_leaves"
_ACTIVITY = "0023_activityeventrow"
_TRASH = "0023_chatconversation_trashed_at"
_LIBRARY = "0023_sharedlibraryitem"
_ACTIVITY_LEAF = "0024_merge_activity_and_chat_leaves"
_HEADS = (_DUPLICATE_THREE, _DUPLICATE_TWO, _ACTIVITY, _TRASH)
_JOIN_LEAF = "0025_merge_0020_join_with_activity_leaf"
# #1721: the hard-delete tombstone. Depends on the 0025 join, so the graph keeps
# exactly one leaf and an install that already applied 0025 migrates forward.
_PURGED = "0026_chatconversation_purged_at"
_LEAF = _PURGED


def test_swarm_migration_graph_has_one_leaf():
    loader = MigrationLoader(None, ignore_no_migrations=True)
    assert loader.detect_conflicts() == {}
    leaves = sorted(name for app, name in loader.graph.leaf_nodes() if app == "swarm")
    assert leaves == [_LEAF]

    names = {
        node[1]
        for node in loader.graph.forwards_plan(("swarm", _LEAF))
        if node[0] == "swarm"
    }
    assert {
        _COMPANY,
        _CHAT_EXTRA,
        _TIMESTAMP,
        _ORPHAN_0021,
        _LIBRARY,
        _ACTIVITY_LEAF,
        _JOIN_LEAF,
        _PURGED,
        *_MERGES,
        *_HEADS,
    } <= names
    assert "0024_merge_swarm_heads" not in names

    def parents_of(name):
        return {parent.key[1] for parent in loader.graph.node_map[("swarm", name)].parents}

    assert parents_of(_TIMESTAMP) == set(_MERGES)
    assert parents_of(_ORPHAN_0021) == {_COMPANY, _CHAT_EXTRA}
    assert parents_of(_ACTIVITY_LEAF) == set(_HEADS)
    assert parents_of(_JOIN_LEAF) == {_ORPHAN_0021, _LIBRARY, _ACTIVITY_LEAF}
    # A new migration has to hang off the previous leaf, or ``migrate`` refuses.
    assert parents_of(_PURGED) == {_JOIN_LEAF}

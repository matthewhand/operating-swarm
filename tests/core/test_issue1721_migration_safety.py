"""Migration safety for ``0026_chatconversation_purged_at`` (#1721).

An existing install must not lose data on upgrade. The migration is a bare
``AddField`` of a nullable column with no default, no data migration and no
``RunPython``, so the property to prove is the one that is not obvious from
reading it: the upgrade path really does run against a database that predates
the field, keeps every row, and leaves the new column ``NULL`` everywhere —
which is exactly "never purged", i.e. the pre-migration behaviour.

This uses ``MigrationExecutor`` against the test database, so the sequence is
the real one: forward to 0026, back to 0025, forward to 0026 again, with rows
written in between at the *pre*-field schema.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

APP = "swarm"
BEFORE = "0025_merge_0020_join_with_activity_leaf"
AFTER = "0026_chatconversation_purged_at"
TABLE = "swarm_chatconversation"
MESSAGES = "swarm_chatmessage"


def _columns(table: str) -> set[str]:
    with connection.cursor() as cur:
        return {c.name for c in connection.introspection.get_table_description(cur, table)}


def _migrate(target: str) -> None:
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate([(APP, target)])
    executor.loader.build_graph()


@pytest.mark.django_db(transaction=True)
def test_upgrade_adds_the_column_without_touching_existing_rows():
    _migrate(BEFORE)
    assert "purged_at" not in _columns(TABLE), "the fixture is not at the pre-field schema"

    # Write content at the pre-field schema, the way an install that has not
    # upgraded yet holds it.
    from django.utils import timezone

    now = timezone.now()
    with connection.cursor() as cur:
        cur.execute(
            f"INSERT INTO {TABLE}"
            " (conversation_id, created_at, updated_at, student_id, agent_id,"
            "  title, snippet, labels, cli_session_id, context_meta, ui_events, trashed_at)"
            " VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                "conv-mig-1", now, now, "codey", "Before upgrade",
                "a snippet", "[]", "", "{}", "[]", None,
            ],
        )
        cur.execute(
            f"SELECT conversation_id FROM {TABLE} WHERE conversation_id = %s", ["conv-mig-1"]
        )
        cid = cur.fetchone()[0]
        for sender, content in [("user", "question"), ("assistant", "answer")]:
            cur.execute(
                f"INSERT INTO {MESSAGES}"
                " (conversation_id, sender, content, timestamp, tool_call_id, extra)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                [cid, sender, content, now, None, "{}"],
            )

    # The upgrade.
    _migrate(AFTER)
    assert "purged_at" in _columns(TABLE)

    from swarm.models import ChatConversation

    row = ChatConversation.objects.get(conversation_id="conv-mig-1")
    assert [m.content for m in row.chat_messages.order_by("timestamp", "id")] == [
        "question",
        "answer",
    ], "the upgrade lost a message"
    assert row.title == "Before upgrade"
    assert row.snippet == "a snippet"
    assert row.agent_id == "codey"
    # NULL means "never purged", i.e. exactly the pre-migration behaviour.
    assert row.purged_at is None
    assert ChatConversation.objects.filter(purged_at__isnull=False).count() == 0

    # The new column is writable, which is the only thing empty_trash needs.
    row.purged_at = now
    row.save(update_fields=["purged_at"])
    row.refresh_from_db()
    assert row.purged_at is not None


@pytest.mark.django_db(transaction=True)
def test_the_upgrade_is_reversible_without_data_loss():
    """An operator who rolls the code back gets the old schema and its rows."""
    _migrate(AFTER)
    from django.utils import timezone

    from swarm.models import ChatConversation

    ChatConversation.objects.create(
        conversation_id="conv-mig-2", agent_id="codey", title="At 0026"
    )
    _migrate(BEFORE)
    assert "purged_at" not in _columns(TABLE)
    with connection.cursor() as cur:
        cur.execute(f"SELECT title FROM {TABLE} WHERE conversation_id = %s", ["conv-mig-2"])
        assert cur.fetchone()[0] == "At 0026"
    # Leave the test database at the leaf for whatever runs next.
    _migrate(AFTER)
    assert ChatConversation.objects.filter(conversation_id="conv-mig-2").exists()

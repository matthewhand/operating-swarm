"""ChatConversation.purged_at — hard-delete tombstone (#1721).

``empty_trash`` used to ``DELETE`` the ``ChatConversation`` row. That made a
permanently deleted thread indistinguishable from one that never existed, so
the one-way ``chat_store`` JSON import (which only fires when the DB thread is
empty) found the orphan ``active/<agent>__<cid>.json`` cache file and re-created
the conversation — and its ``ChatMessage`` rows — out of it.

This adds a nullable stamp. It is **additive and null for every existing row**,
so no existing install loses data on upgrade: nothing is back-filled, no column
is rewritten, and the default (``NULL``) means "never purged" — the exact
pre-migration behaviour. The tombstone only starts being written by the
``empty_trash`` code that ships alongside it.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("swarm", "0025_merge_0020_join_with_activity_leaf"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="purged_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

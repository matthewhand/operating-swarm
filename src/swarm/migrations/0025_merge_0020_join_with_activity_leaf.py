"""Join the swarm leaves left on main.

``0024_merge_activity_and_chat_leaves`` (#1597) already joins the activity
row, chat trash, and both duplicate Company merges.

``0021_merge_0020_chatmessage_and_0020_company`` (#1600) depends on the
same two 0020 parents as the three earlier 0021 merges, and nothing
depends on it, so it is a second leaf.

``0023_sharedlibraryitem`` (#1570 / #1311) depends on
``0022_chatmessage_timestamp_explicit`` and is a third leaf.

This node is empty. It does not rewrite either parent, so a database
that already applied one of them can migrate forward.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("swarm", "0021_merge_0020_chatmessage_and_0020_company"),
        ("swarm", "0023_sharedlibraryitem"),
        ("swarm", "0024_merge_activity_and_chat_leaves"),
    ]

    operations = []

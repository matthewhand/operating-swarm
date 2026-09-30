"""Merge the two 0020 leaves that landed from separate branches.

`0020_company` (#1315) and `0020_chatmessage_extra_chatconversation_ui_events`
(#1440) were both created against `0019_alter_chatattachment_id_alter_herdragent_remote`,
so neither depends on the other and Django sees two leaf nodes in the `swarm`
graph. `manage.py migrate` refuses to run at all in that state:

    CommandError: Conflicting migrations detected; multiple leaf nodes in the
    migration graph: (0020_chatmessage_extra_chatconversation_ui_events,
    0020_company) in swarm.

The two are schema-disjoint -- one adds a JSONField to ChatConversation, the
other creates the Company model -- so this merge has no operations and applies
both in dependency order. It exists only to give the graph a single leaf.

This went unnoticed because the `postgres-migrate` job is the only CI check
that runs `migrate`, and the Actions budget has been exhausted (#1346) so no
job can start. It reached 845 test errors and would have crash-looped the next
deploy of `main`.

Going forward, a branch that adds a migration should depend on the current leaf
(`manage.py makemigrations` does this automatically once there is only one)
rather than reusing an existing number.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("swarm", "0020_chatmessage_extra_chatconversation_ui_events"),
        ("swarm", "0020_company"),
    ]

    operations = []

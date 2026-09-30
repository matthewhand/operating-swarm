"""#1440: trash lives on the canonical ChatConversation row.

Depends on ``0022_chatmessage_timestamp_explicit``, which already joins
the three 0021 leaves. A second 0022 would fork the graph again.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0022_chatmessage_timestamp_explicit"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="trashed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

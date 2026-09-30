"""#1440: persist restore metadata on Django chat rows."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0019_alter_chatattachment_id_alter_herdragent_remote"),
    ]

    operations = [
        migrations.AddField(
            model_name="chatconversation",
            name="ui_events",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="chatmessage",
            name="extra",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

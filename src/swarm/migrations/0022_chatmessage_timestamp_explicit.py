# #1440: keep a caller-supplied timestamp. auto_now_add overwrote it on insert.

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0021_merge_company_and_chat_extra"),
        ("swarm", "0021_merge_company_and_chat_restore"),
        ("swarm", "0021_merge_company_ui_events"),
    ]

    operations = [
        migrations.AlterField(
            model_name="chatmessage",
            name="timestamp",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterModelOptions(
            name="chatmessage",
            options={
                "ordering": ["timestamp", "id"],
                "verbose_name": "Chat Message",
                "verbose_name_plural": "Chat Messages",
            },
        ),
    ]

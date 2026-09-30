# Merge #1315 Company (0020_company) with #1440 chat extra (0020_chatmessage_extra).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0020_company"),
        ("swarm", "0020_chatmessage_extra_chatconversation_ui_events"),
    ]

    operations = []

# Merge parallel 0020 leaves: Company (#1315) and chat restore fields (#1440).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0020_company"),
        ("swarm", "0020_chatmessage_extra_chatconversation_ui_events"),
    ]

    operations = []

"""Merge parallel 0020 leaves (Company and chat restore metadata)."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0020_company"),
        ("swarm", "0020_chatmessage_extra_chatconversation_ui_events"),
    ]

    operations = []

# Merge the two 0021 leaves that both join Company (#1315) with chat extra (#1440).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0021_merge_company_and_chat_extra"),
        ("swarm", "0021_merge_company_ui_events"),
    ]

    operations = []

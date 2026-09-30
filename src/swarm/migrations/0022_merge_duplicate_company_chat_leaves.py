"""Join three identical empty merges of the Company and chat-restore leaves.

0021_merge_company_and_chat_extra, 0021_merge_company_and_chat_restore, and
0021_merge_company_ui_events all depend on the same 0020 pair and add no
operations. Migrate refuses to run while all three are heads.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("swarm", "0021_merge_company_and_chat_extra"),
        ("swarm", "0021_merge_company_and_chat_restore"),
        ("swarm", "0021_merge_company_ui_events"),
    ]

    operations = []

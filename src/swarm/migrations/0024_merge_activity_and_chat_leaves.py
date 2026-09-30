# One head: activity rows (#1314) and chat trash (#1440) both follow the
# timestamp migration, and two empty 0022 merges were left as extra leaves.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0022_merge_duplicate_company_chat_leaves"),
        ("swarm", "0022_merge_duplicate_company_leaves"),
        ("swarm", "0023_activityeventrow"),
        ("swarm", "0023_chatconversation_trashed_at"),
    ]

    operations = []

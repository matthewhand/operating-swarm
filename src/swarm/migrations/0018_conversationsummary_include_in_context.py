"""#214: per-summary include_in_context toggle (default True)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("swarm", "0017_chatconversation_context_meta"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationsummary",
            name="include_in_context",
            field=models.BooleanField(default=True),
        ),
    ]

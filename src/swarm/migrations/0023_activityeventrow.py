from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0022_chatmessage_timestamp_explicit"),
    ]

    operations = [
        migrations.CreateModel(
            name="ActivityEventRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.CharField(db_index=True, max_length=64, unique=True)),
                ("actor_type", models.CharField(max_length=16)),
                ("actor_id", models.CharField(db_index=True, max_length=256)),
                ("action", models.CharField(db_index=True, max_length=128)),
                ("entity_type", models.CharField(db_index=True, max_length=64)),
                ("entity_id", models.CharField(db_index=True, max_length=256)),
                ("agent_id", models.CharField(blank=True, default="", max_length=256)),
                ("run_id", models.CharField(blank=True, default="", max_length=256)),
                ("responsible_user_id", models.CharField(blank=True, default="", max_length=256)),
                ("detail", models.JSONField(blank=True, null=True)),
                ("created_at", models.CharField(max_length=64)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Activity event",
                "verbose_name_plural": "Activity events",
                "ordering": ["-recorded_at"],
            },
        ),
    ]

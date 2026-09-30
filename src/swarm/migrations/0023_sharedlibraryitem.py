# Generated manually for #1311 scoped workspace library.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0022_chatmessage_timestamp_explicit"),
    ]

    operations = [
        migrations.CreateModel(
            name="SharedLibraryItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "scope",
                    models.CharField(
                        choices=[("personal", "personal"), ("team", "team"), ("org", "org")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[("blueprint", "blueprint"), ("plugin", "plugin"), ("team", "team")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("item_key", models.CharField(db_index=True, max_length=128)),
                ("owner_principal", models.CharField(db_index=True, max_length=128)),
                ("owner_team", models.CharField(blank=True, db_index=True, default="", max_length=128)),
                ("title", models.CharField(blank=True, default="", max_length=200)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("published", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Shared library item",
                "verbose_name_plural": "Shared library items",
            },
        ),
        migrations.AddConstraint(
            model_name="sharedlibraryitem",
            constraint=models.UniqueConstraint(
                fields=("scope", "kind", "item_key", "owner_principal", "owner_team"),
                name="swarm_sharedlib_uniq",
            ),
        ),
    ]

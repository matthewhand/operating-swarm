# REQ-21: persist Herdr agent rows (name + optional remote). SQLite default.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("swarm", "0011_blueprint_marketplaceindex_mcpconfig"),
    ]

    operations = [
        migrations.CreateModel(
            name="HerdrAgent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=200, unique=True)),
                (
                    "remote",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text=(
                            "Empty = localhost (no --remote). Examples: "
                            "matthewh@198.51.100.36, workbox, ssh://you@server:2222."
                        ),
                        max_length=255,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Herdr agent",
                "verbose_name_plural": "Herdr agents",
                "db_table": "herdr_agent",
                "ordering": ["name"],
            },
        ),
    ]

"""Persisted Herdr agent rows (REQ-21).

Each row is an operator-facing member (kind=herdr): a display ``name`` plus an
optional ``remote`` target. Empty ``remote`` means localhost — the Herdr already
on this host (unix sockets under ``~/.config/herdr/``). Non-empty values are
passed through as ``herdr --remote <value>`` (see https://herdr.dev/docs/how-to-work/).

This is **not** Hermes, OMB, or Rakazo. SQLite is the default Django DB; do not
point these rows at Neon / DATABASE_URL.
"""

from django.db import models


class HerdrAgent(models.Model):
    """A named Herdr connection Open Swarm can drive via the ``herdr`` CLI."""

    name = models.CharField(max_length=200, unique=True)
    remote = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "Empty = localhost (no --remote). Examples: you@198.51.100.36, "
            "workbox, ssh://you@server:2222."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "herdr_agent"
        ordering = ["name"]
        verbose_name = "Herdr agent"
        verbose_name_plural = "Herdr agents"

    def __str__(self) -> str:
        target = self.remote or "localhost"
        return f"{self.name} ({target})"

    @property
    def is_localhost(self) -> bool:
        return not (self.remote or "").strip()

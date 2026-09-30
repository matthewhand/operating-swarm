"""Shared recipes visible by personal, team, or organisation scope (#1311)."""

from __future__ import annotations

from django.db import models


class SharedLibraryItem(models.Model):
    """A blueprint, plugin, or team pack shared on this server.

    Personal rows are readable only by ``owner_principal``. Team rows are
    visible for ``owner_team``. Org rows are visible to every principal
    on the same install.
    """

    SCOPE_PERSONAL = "personal"
    SCOPE_TEAM = "team"
    SCOPE_ORG = "org"
    SCOPE_CHOICES = (
        (SCOPE_PERSONAL, SCOPE_PERSONAL),
        (SCOPE_TEAM, SCOPE_TEAM),
        (SCOPE_ORG, SCOPE_ORG),
    )
    KIND_CHOICES = (
        ("blueprint", "blueprint"),
        ("plugin", "plugin"),
        ("team", "team"),
    )

    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, db_index=True)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES, db_index=True)
    item_key = models.CharField(max_length=128, db_index=True)
    owner_principal = models.CharField(max_length=128, db_index=True)
    owner_team = models.CharField(max_length=128, blank=True, default="", db_index=True)
    title = models.CharField(max_length=200, blank=True, default="")
    payload = models.JSONField(blank=True, default=dict)
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "swarm"
        verbose_name = "Shared library item"
        verbose_name_plural = "Shared library items"
        constraints = [
            models.UniqueConstraint(
                fields=("scope", "kind", "item_key", "owner_principal", "owner_team"),
                name="swarm_sharedlib_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.kind}:{self.item_key}"

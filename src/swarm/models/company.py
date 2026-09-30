"""First-class Company row with a model policy (#1315).

A Company is the org-level owner of a model policy. New-bot attachment
(#1317) stores ``company_id`` on the created agent seat, not on this row.

SQLite/Postgres only. No Neon. Policy JSON never holds secrets.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from swarm.core.company_model_policy import (
    evaluate_model_policy,
    normalize_model_policy,
    resolve_default_model,
)


def default_company_model_policy() -> dict:
    from swarm.core.company_model_policy import empty_model_policy

    return empty_model_policy()


class Company(models.Model):
    """Named org that owns a model policy for future bot assignment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    model_policy = models.JSONField(blank=True, default=default_company_model_policy)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="companies",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "swarm"
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"Company({self.slug})"

    def clean_model_policy(self) -> dict:
        """Normalize and persist-safe the stored policy bag."""
        self.model_policy = normalize_model_policy(self.model_policy)
        return self.model_policy

    def save(self, *args, **kwargs):
        self.clean_model_policy()
        super().save(*args, **kwargs)

    def evaluate_model(self, model: str):
        """Whether ``model`` is allowed under this Company's policy."""
        return evaluate_model_policy(self.model_policy, model)

    def default_model(self) -> str:
        """Policy default when it is itself allowed, else empty."""
        return resolve_default_model(self.model_policy)

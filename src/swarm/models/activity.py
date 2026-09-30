"""#1314 — Django ActivityEvent row (admin + durable copy of the JSONL spine)."""

from __future__ import annotations

from django.db import models


class ActivityEventRow(models.Model):
    """Append-only operator activity event. ``detail`` is stored already redacted."""

    event_id = models.CharField(max_length=64, unique=True, db_index=True)
    actor_type = models.CharField(max_length=16)
    actor_id = models.CharField(max_length=256, db_index=True)
    action = models.CharField(max_length=128, db_index=True)
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.CharField(max_length=256, db_index=True)
    agent_id = models.CharField(max_length=256, blank=True, default="")
    run_id = models.CharField(max_length=256, blank=True, default="")
    responsible_user_id = models.CharField(max_length=256, blank=True, default="")
    detail = models.JSONField(blank=True, null=True)
    created_at = models.CharField(max_length=64)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "swarm"
        verbose_name = "Activity event"
        verbose_name_plural = "Activity events"
        ordering = ["-recorded_at"]

    def __str__(self) -> str:
        return f"ActivityEvent({self.action} {self.entity_type}:{self.entity_id})"

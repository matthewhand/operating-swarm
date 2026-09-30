"""Django admin registrations.

Herdr agent rows (REQ-21) are also editable on /settings/ and via
``/v1/herdr-agents/``. Admin is a staff fallback — the DaisyUI SPA settings
sheet is not in this tree (ADR-001).
"""

from django.contrib import admin

from swarm.models import ActivityEventRow, Company, HerdrAgent, UserPreference


@admin.register(HerdrAgent)
class HerdrAgentAdmin(admin.ModelAdmin):
    list_display = ("name", "remote_display", "created_at", "updated_at")
    search_fields = ("name", "remote")
    list_filter = ("created_at",)
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Remote", ordering="remote")
    def remote_display(self, obj: HerdrAgent) -> str:
        return obj.remote or "localhost (no --remote)"


@admin.register(ActivityEventRow)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ("action", "entity_type", "entity_id", "actor_id", "created_at")
    search_fields = ("action", "entity_id", "actor_id", "event_id")
    list_filter = ("actor_type", "entity_type", "action")
    readonly_fields = (
        "event_id",
        "actor_type",
        "actor_id",
        "action",
        "entity_type",
        "entity_id",
        "agent_id",
        "run_id",
        "responsible_user_id",
        "detail",
        "created_at",
        "recorded_at",
    )


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("principal", "user", "updated_at")
    search_fields = ("principal", "user__username")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "updated_at")
    search_fields = ("name", "slug")
    readonly_fields = ("id", "created_at", "updated_at")

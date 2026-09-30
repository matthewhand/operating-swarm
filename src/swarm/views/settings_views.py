"""
Settings Views for Operating Swarm
Web views for displaying and managing configuration settings
"""
import logging
import os
import sys

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .settings_manager import settings_manager

logger = logging.getLogger(__name__)

# Ensure module aliasing so tests patching either path work consistently
# Some tests reference this module as 'src.swarm.views.settings_views' while
# Django imports it as 'swarm.views.settings_views'. Create a sys.modules alias
# so both names resolve to the same module object, allowing patches to apply.
_this_mod = sys.modules.get(__name__)
if _this_mod is not None:
    if __name__.startswith("swarm."):
        sys.modules.setdefault(f"src.{__name__}", _this_mod)
    elif __name__.startswith("src."):
        sys.modules.setdefault(__name__[4:], _this_mod)


@login_required
def settings_dashboard(request):
    """Render the comprehensive settings dashboard (authenticated).

    ``settings_groups`` is redacted before template/json_script so viewObject
    never surfaces raw api_key values.
    """
    try:
        all_settings = settings_manager.collect_all_settings()
        # Stats from raw collection (configured counts), display uses redacted copy.
        total_settings = sum(len(group['settings']) for group in all_settings.values())
        configured_settings = sum(
            1 for group in all_settings.values()
            for setting in group['settings'].values()
            if setting['value'] not in ['Not Set', None, '']
        )
        sensitive_settings = sum(
            1 for group in all_settings.values()
            for setting in group['settings'].values()
            if setting.get('sensitive', False)
        )
        safe_groups = redact_settings_groups(all_settings)

        chat_stats = {}
        try:
            from swarm.core import chat_repository

            chat_repository.prune_expired(request.user)
            chat_stats = chat_repository.stats_for(request.user)
        except Exception:
            logger.exception("Failed to collect chat persistence stats")
            chat_stats = {
                "store_dir": "",
                "format": "db",
                "active_count": 0,
                "trash_count": 0,
                "bytes_used": 0,
                "bytes_label": "0 B",
                "max_age_days": 90,
                "auto_archive_enabled": True,
                "chats": [],
                "trash": [],
                "env_dir": "SWARM_CHAT_DIR",
                "env_max_age": "SWARM_CHAT_MAX_AGE_DAYS",
            }

        herdr_agents = []
        try:
            from swarm.models import HerdrAgent

            herdr_agents = list(HerdrAgent.objects.all().order_by("name"))
        except Exception:
            logger.exception("Error loading Herdr agent rows")

        context = {
            'page_title': 'Settings Dashboard',
            'settings_groups': safe_groups,
            'chat_stats': chat_stats,
            'herdr_agents': herdr_agents,
            'stats': {
                'total': total_settings,
                'configured': configured_settings,
                'sensitive': sensitive_settings,
                'completion_rate': round((configured_settings / total_settings) * 100) if total_settings > 0 else 0
            }
        }

        return render(request, 'settings_dashboard.html', context)

    except Exception:
        logger.exception("Error loading settings")
        return HttpResponse("Error loading settings. See server logs for details.", status=500)


def _redact_setting_value(value, *, sensitive: bool):
    """Redact sensitive setting values for API/export using the real redactor."""
    from swarm.utils.redact import redact_sensitive_data

    if sensitive:
        # Never emit raw secrets/objects marked sensitive.
        if isinstance(value, dict | list):
            return redact_sensitive_data(value, mask="***HIDDEN***")
        if value in (None, "", "Not Set"):
            return value
        return "***HIDDEN***"
    # Even non-sensitive dicts may embed api_key-like keys — run recursive redaction.
    if isinstance(value, dict | list):
        return redact_sensitive_data(value, mask="***HIDDEN***")
    return value


def redact_settings_groups(all_settings: dict) -> dict:
    """Deep-copy settings groups with secrets redacted (dashboard + API + json_script)."""
    safe_settings: dict = {}
    for group_name, group_data in all_settings.items():
        safe_settings[group_name] = {
            "title": group_data["title"],
            "description": group_data["description"],
            "icon": group_data["icon"],
            "settings": {},
        }
        for setting_name, setting_data in group_data["settings"].items():
            safe_setting = setting_data.copy()
            safe_setting["value"] = _redact_setting_value(
                setting_data.get("value"),
                sensitive=bool(setting_data.get("sensitive", False)),
            )
            safe_settings[group_name]["settings"][setting_name] = safe_setting
    return safe_settings


@login_required
@require_http_methods(["GET"])
def settings_api(_request):
    """API endpoint to get all settings as JSON (authenticated)."""
    try:
        all_settings = settings_manager.collect_all_settings()
        safe_settings = redact_settings_groups(all_settings)

        return JsonResponse({
            'success': True,
            'settings': safe_settings
        })

    except Exception:
        logger.exception("Settings API request failed")
        return JsonResponse({
            'success': False,
            'error': "Internal error. See server logs for details."
        }, status=500)


@login_required
@require_http_methods(["GET"])
def environment_variables(_request):
    """Get all environment variables related to Operating Swarm (authenticated)."""
    from swarm.utils.redact import is_sensitive_key

    try:
        # Collect all environment variables that might be relevant
        relevant_prefixes = [
            'DJANGO_', 'SWARM_', 'API_', 'ENABLE_', 'OPENAI_',
            'ANTHROPIC_', 'OLLAMA_', 'REDIS_', 'LOG', 'DATABASE_',
            'AWS_', 'MONGODB_', 'MONGO_',
            'HERMES_', 'OMB_', 'RAKAZO_',
        ]

        env_vars = {}
        for key, value in os.environ.items():
            if any(key.startswith(prefix) for prefix in relevant_prefixes):
                # Use shared redaction heuristics (access_key, database_url, …)
                if is_sensitive_key(key):
                    env_vars[key] = '***SET***' if value else 'Not Set'
                else:
                    env_vars[key] = value

        return JsonResponse({
            'success': True,
            'environment_variables': env_vars,
            'count': len(env_vars)
        })

    except Exception:
        logger.exception("Settings API request failed")
        return JsonResponse({
            'success': False,
            'error': "Internal error. See server logs for details."
        }, status=500)

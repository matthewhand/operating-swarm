#!/usr/bin/env python
"""Django's command-line utility for administrative tasks.

Stays at the repository root: Django's project convention is ``python manage.py``
from the checkout (``DJANGO_SETTINGS_MODULE=swarm.settings``). Docker, README,
and ``make``/docs call this path. Do not move it into ``src/`` or ``scripts/``.
"""
import os
import sys
from pathlib import Path


def main():
    # Define the base directory
    BASE_DIR = Path(__file__).resolve().parent

    # Migrate outside the dotenv fallback. Swallowing a conflict or a copy
    # error would load the checkout .env, which can set SWARM_CONFIG_DIR or
    # SWARM_SKIP_CONFIG_MIGRATE so the later startup hooks skip the refusal.
    from swarm.core.paths import (
        migrate_legacy_config_root,
        startup_should_migrate_config,
    )

    if startup_should_migrate_config():
        migrate_legacy_config_root()

    # XDG ~/.config/swarm/.env (primary) + checkout .env (fallback)
    try:
        from swarm.utils.dotenv_load import load_swarm_dotenv
        load_swarm_dotenv(project_root=BASE_DIR)
    except Exception:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=BASE_DIR / '.env')

    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'swarm.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()

#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path


def main():
    # Define the base directory
    base_dir = Path(__file__).resolve().parent

    # Migrate outside the dotenv fallback. Swallowing a conflict or a copy
    # error would load the checkout .env, which can set SWARM_CONFIG_DIR or
    # SWARM_SKIP_CONFIG_MIGRATE so the later startup hooks skip the refusal.
    # src/manage.py → project root is parent of src/
    from swarm.core.paths import (
        migrate_legacy_config_root,
        startup_should_migrate_config,
    )

    if startup_should_migrate_config():
        migrate_legacy_config_root()

    # User-config .env (primary) + checkout .env (fallback)
    try:
        from swarm.utils.dotenv_load import load_swarm_dotenv
        load_swarm_dotenv(project_root=base_dir.parent)
    except Exception:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=base_dir.parent / '.env')

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

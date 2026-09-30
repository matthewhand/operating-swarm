# src/swarm/wsgi.py

import os
from pathlib import Path

from django.core.wsgi import get_wsgi_application

# Define the base directory (src/)
BASE_DIR = Path(__file__).resolve().parent.parent

# User-config .env (primary) + project .env (fallback)
from swarm.utils.dotenv_load import load_swarm_dotenv

load_swarm_dotenv(project_root=BASE_DIR.parent)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'swarm.settings')

application = get_wsgi_application()

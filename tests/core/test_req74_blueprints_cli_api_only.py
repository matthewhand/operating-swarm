"""REQ-74 / #419: blueprints are CLI/API only — no webui / django-chat recipe.

Locks the retirement of `django_chat` as a discoverable webpage/app.
Product Chat stays `/` + `/chat`. No `kind=webui`. GitHub-only; no live host.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

from swarm.core.blueprint_discovery import discover_blueprints
from swarm.settings import BLUEPRINT_DIRECTORY
from swarm.views.agent_creator_views import _render_swarm_blueprint_code

REPO = Path(__file__).resolve().parents[2]
BLUEPRINTS_ROOT = REPO / "src" / "swarm" / "blueprints"
RETIRED_IDS = ("django_chat", "django-chat")
WEBUI_KINDS = ("webui", "django-chat", "django_chat")


def _discover_ids() -> set[str]:
    before = set(sys.modules)
    try:
        found = discover_blueprints(str(BLUEPRINT_DIRECTORY))
    except TypeError:
        found = discover_blueprints(directories=[BLUEPRINT_DIRECTORY])
    for name in set(sys.modules) - before:
        if name.startswith("swarm.blueprints"):
            del sys.modules[name]
    return set(found)


def test_django_chat_package_is_gone():
    assert not (BLUEPRINTS_ROOT / "django_chat").exists()
    leftover = list(BLUEPRINTS_ROOT.rglob("*django_chat*"))
    assert leftover == []


def test_no_blueprint_ships_a_webpage():
    templates = list(BLUEPRINTS_ROOT.rglob("templates"))
    urls = list(BLUEPRINTS_ROOT.rglob("urls.py"))
    views = list(BLUEPRINTS_ROOT.rglob("views.py"))
    apps = list(BLUEPRINTS_ROOT.rglob("apps.py"))
    assert templates == []
    assert urls == []
    assert views == []
    assert apps == []


def test_discover_blueprints_has_no_webui_or_django_chat_id():
    ids = _discover_ids()
    assert ids, "expected bundled CLI/API recipes to remain discoverable"
    for retired in RETIRED_IDS:
        assert retired not in ids
    assert "chatbot" in ids
    assert "dynamic_team" in ids


@pytest.mark.django_db
def test_models_and_blueprints_catalog_omit_webui_kind(api_client, settings):
    settings.ENABLE_API_AUTH = False
    models = api_client.get("/v1/models/")
    assert models.status_code == 200
    model_ids = [row.get("id") for row in models.json().get("data", [])]
    for retired in RETIRED_IDS:
        assert retired not in model_ids
    assert "webui" not in model_ids

    blueprints = api_client.get("/v1/blueprints/")
    assert blueprints.status_code == 200
    rows = blueprints.json().get("data", [])
    assert rows, "expected CLI/API blueprint rows"
    for row in rows:
        row_id = str(row.get("id") or "")
        kind = str(row.get("kind") or "").lower()
        tags = [str(t).lower() for t in (row.get("tags") or [])]
        assert row_id not in RETIRED_IDS
        assert kind not in WEBUI_KINDS
        assert "webui" not in tags
        assert "django_chat" not in tags


@pytest.mark.django_db
@pytest.mark.parametrize("path", ("/django_chat/", "/django_chat", "/django_chat/foo/new/"))
def test_leftover_django_chat_url_is_404_not_a_chat_shell(path):
    client = Client()
    response = client.get(path, follow=True)
    assert response.status_code == 404
    body = response.content.decode("utf-8", errors="replace")
    assert "django_chat_webpage" not in body
    assert "Django Chat Interface" not in body
    assert "spa-chat-composer" not in body


def test_installed_apps_has_no_blueprint_django_app():
    installed = [str(app).lower() for app in settings.INSTALLED_APPS]
    assert all("django_chat" not in app for app in installed)
    assert "blueprints.django_chat" not in settings.INSTALLED_APPS
    assert "swarm.blueprints.django_chat" not in settings.INSTALLED_APPS
    assert "blueprint_django_chat" not in settings.LOGGING.get("loggers", {})


def test_creator_does_not_stamp_webui_kind():
    src = (REPO / "src" / "swarm" / "views" / "agent_creator_views.py").read_text(
        encoding="utf-8"
    )
    assert '"tags": ["swarm", "webui"]' not in src
    assert "kind=webui" not in src
    assert '"kind": "webui"' not in src

    code = _render_swarm_blueprint_code(
        {
            "name": "Req74 Team",
            "description": "CLI/API recipe",
            "coordinator_name": "Lead",
            "agents": [{"name": "Lead", "system_prompt": "Lead.", "role": "default"}],
        }
    )
    assert '"tags": ["swarm"]' in code
    assert "webui" not in code.lower()
    assert "kind=webui" not in code


def test_docs_say_blueprints_are_cli_api_only():
    files = {
        "README.md": REPO / "README.md",
        "USERGUIDE.md": REPO / "USERGUIDE.md",
        "docs/BLUEPRINT_LIBRARY.md": REPO / "docs" / "BLUEPRINT_LIBRARY.md",
        "docs/BLUEPRINT_SPLASH.md": REPO / "docs" / "BLUEPRINT_SPLASH.md",
        "docs/GLOSSARY.md": REPO / "docs" / "GLOSSARY.md",
        "src/swarm/blueprints/README.md": BLUEPRINTS_ROOT / "README.md",
    }
    root_readme = files["README.md"]
    for label, path in files.items():
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        assert "cli/api" in lowered or "cli and api" in lowered, label
        assert "web chat with conversation-history" not in lowered
        if path.resolve() == root_readme.resolve():
            assert "django_chat resolves its LLM profile" in text
            assert text.count("django_chat") == 1
        else:
            assert "django_chat" not in text

    library = files["docs/BLUEPRINT_LIBRARY.md"].read_text(encoding="utf-8")
    assert "| `django_chat`" not in library
    assert "do not ship a webpage" in library.lower() or "cli/api only" in library.lower()

    panels = (REPO / "docs" / "examples" / "webui-config-panels.md").read_text(
        encoding="utf-8"
    )
    assert "CLI/API only" in panels
    assert "Redirect (REQ-74" in panels

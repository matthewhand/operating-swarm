import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

# The Django defaults are secure-by-default (DJANGO_DEBUG defaults to False,
# which makes DJANGO_SECRET_KEY/DJANGO_ALLOWED_HOSTS mandatory). The test
# suite runs in development mode, so enable debug here (before
# swarm.settings is imported by pytest-django) unless the caller has
# explicitly set DJANGO_DEBUG.
os.environ.setdefault("DJANGO_DEBUG", "true")

@pytest.fixture(autouse=True)
def isolate_swarm_chat_dir(tmp_path, monkeypatch):
    """Keep per-agent chat JSON off the real XDG/home tree during tests."""
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))


@pytest.fixture(autouse=True)
def isolate_xdg_config(tmp_path, monkeypatch):
    """Keep the host's real swarm_config.json out of the test suite.

    The config resolver (and blueprint_base's global-config fallback) reads
    cwd/swarm_config.json then the XDG path (~/.config/swarm). A developer's
    real config (settings.default_llm_profile=orchestration, LAN remote URLs)
    leaked into profile-resolution and remote-spec tests, making them
    host-dependent. Tests that need a config write their own into the
    isolated XDG location (or pass config= directly).
    """
    xdg = tmp_path / "xdg-config-home"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("HOME", str(xdg))


@pytest.fixture(autouse=True)
def isolate_custom_blueprint_registry():
    """Keep leftover custom-blueprint POSTs from poisoning empty-list / matrix tests.

    CustomBlueprintsView writes a process-global `_custom_blueprints_registry`
    fallback. A prior create (e.g. REQ-81 fixture) must not fill GET
    `/v1/blueprints/custom/` when the library is empty.
    """
    from swarm.views import api_views

    api_views._custom_blueprints_registry.clear()
    yield
    api_views._custom_blueprints_registry.clear()


@pytest.fixture(autouse=True)
def isolate_app_config():
    """Snapshot/restore the Django AppConfig ``config`` around every test.

    ``config_ownership.refresh_app_config`` mirrors every persist call into the
    process-global ``AppConfig.config`` (ADR-002 §3.1) — correct for the live
    server, but a test persisting a tmp_path swarm_config.json would otherwise
    poison every later blueprint's config discovery in the same process
    (order-dependent failures like the sandbox/AsyncOpenAI api_key crash).
    """
    try:
        from django.apps import apps

        app = apps.get_app_config("swarm") if apps.ready else None
    except Exception:
        app = None
    saved = getattr(app, "config", None)
    yield
    if app is not None:
        app.config = saved


# --- Fixtures ---

def pytest_collection_modifyitems(config, items):
    """Optionally skip asyncio-marked tests in restricted environments.

    Set DISABLE_ASYNC_TESTS=1 to skip tests marked with @pytest.mark.asyncio.
    This is useful in sandboxes that prohibit socketpair(), which
    pytest-asyncio needs to create an event loop.
    """
    if os.getenv("DISABLE_ASYNC_TESTS", "").lower() in ("1", "true", "yes", "y"):
        skip_async = pytest.mark.skip(reason="Async tests disabled in restricted env (socketpair not permitted)")
        for item in items:
            if "asyncio" in item.keywords:
                item.add_marker(skip_async)

# Note: Avoid overriding pytest-django's internal django_db_setup fixture.
# Doing so can lead to subtle ordering/teardown issues in large test runs.
# If you need to perform session-wide DB tweaks, introduce a differently-named
# fixture and depend on pytest-django's built-in setup implicitly.


# Avoid forcing DB access on every single test by default — this can interfere
# with Django TestCase transaction management and increase flakiness. Tests
# that need the DB should request the `db` fixture or subclass Django's
# TestCase/TransactionTestCase explicitly.

@pytest.fixture
def stub_compact_llm(monkeypatch):
    """#672 — compact uses an LLM; tests stub it so no network / secrets."""
    calls: list[dict] = []

    def _fake(items, *, agent_id=""):
        calls.append({"items": items, "agent_id": agent_id})
        return "LLM digest of the compacted range."

    monkeypatch.setattr("swarm.core.chat_compact.llm_summarize_items", _fake)
    return calls


@pytest.fixture
def mock_openai_client():
    from openai import AsyncOpenAI
    client = MagicMock(spec=AsyncOpenAI)
    client.chat.completions.create = AsyncMock()
    return client

@pytest.fixture
def mock_model_instance(mock_openai_client):
    try:
        from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
        with patch('agents.models.openai_chatcompletions.AsyncOpenAI', return_value=mock_openai_client):
             model_mock = MagicMock(spec=OpenAIChatCompletionsModel)
             model_mock.call_model = AsyncMock(return_value=("Mock response", None, None))
             model_mock.get_token_count = MagicMock(return_value=10)
             yield model_mock
    except ImportError:
         pytest.skip("Skipping mock_model_instance fixture: openai-agents not fully available.")

# Removed @pytest.mark.django_db from fixture - keep it on the test classes/functions instead
@pytest.fixture
def test_user(db): # db fixture ensures DB is available *within* this fixture's scope
    """Creates a standard test user."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    # Use update_or_create for robustness
    user, created = User.objects.update_or_create(
        username='testuser',
        defaults={'is_staff': False, 'is_superuser': False}
    )
    if created:
        user.set_password('password')
        user.save()
    return user

@pytest.fixture
def api_client(db): # Request db fixture here too
     from rest_framework.test import APIClient
     return APIClient()

@pytest.fixture
def authenticated_client(api_client, test_user): # Relies on test_user, which relies on db
    api_client.force_authenticate(user=test_user)
    return api_client


@pytest.fixture
async def authenticated_async_client(async_client, test_user):
    await sync_to_async(async_client.force_login)(test_user)
    return async_client

@pytest.fixture
def mock_load_config():
    with patch('swarm.views.settings_manager.load_config') as mock:
        yield mock

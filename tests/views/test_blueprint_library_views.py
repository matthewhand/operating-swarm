"""
Unit tests for src/swarm/views/blueprint_library_views.py
===========================================================

Tests for blueprint library views covering:
- blueprint_library: main library page with browsing
- blueprint_requirements_status: MCP requirements status
- add_blueprint_to_library: add blueprint to user's library
- remove_blueprint_from_library: remove blueprint from library
- blueprint_creator: LLM-powered blueprint creation form
- generate_avatar: avatar generation for blueprints
- check_comfyui_status: ComfyUI availability check
- my_blueprints: user's installed and custom blueprints

Uses mocks for blueprint discovery, DB interactions, and external services; no network.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def request_factory():
    """Return a Django request factory."""
    return RequestFactory()


def _as_user(request, user):
    """Attach an authenticated user for @login_required views under RequestFactory."""
    request.user = user
    if not hasattr(request, "session"):
        request.session = {}
    return request


def _as_anonymous(request):
    """Attach AnonymousUser for login-redirect assertions."""
    request.user = AnonymousUser()
    if not hasattr(request, "session"):
        request.session = {}
    return request


@pytest.fixture
def mock_blueprints_discovered():
    """Sample discovered blueprints metadata."""
    return {
        "codey": {
            "metadata": {
                "name": "Codey",
                "description": "AI coding assistant",
                "required_mcp_servers": ["filesystem"],
                "env_vars": ["OPENAI_API_KEY"]
            }
        },
        "gawd": {
            "metadata": {
                "name": "GAWD",
                "description": "General AI assistant",
                "required_mcp_servers": [],
                "env_vars": []
            }
        },
        "poets": {
            "metadata": {
                "name": "Poets",
                "description": "Creative writing assistant",
                "required_mcp_servers": [],
                "env_vars": []
            }
        }
    }


@pytest.fixture
def mock_blueprint_library():
    """Sample blueprint library structure."""
    return {
        "installed": ["codey", "gawd"],
        "custom": [
            {
                "id": "my_custom",
                "name": "My Custom Agent",
                "description": "A custom agent",
                "category": "ai_assistants",
                "tags": ["custom"],
                "code": "# custom code"
            }
        ]
    }


@pytest.fixture
def mock_active_config():
    """Sample active configuration."""
    return {
        "mcpServers": {
            "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]}
        }
    }


# =============================================================================
# Tests for blueprint_library view
# =============================================================================

@pytest.mark.django_db
class TestBlueprintLibraryView:
    """Tests for the main blueprint library page."""

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    def test_blueprint_library_get_success(
        self,
        mock_get_library,
        mock_discover,
        request_factory,
        mock_blueprints_discovered,
        mock_blueprint_library,
        test_user
    ):
        """Test successful GET request to blueprint library."""
        from swarm.views.blueprint_library_views import blueprint_library

        mock_discover.return_value = mock_blueprints_discovered
        mock_get_library.return_value = mock_blueprint_library

        request = request_factory.get("/blueprints/library/")
        request.session = {"dark_mode": True}
        _as_user(request, test_user)

        response = blueprint_library(request)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Blueprint Library" in content          # page actually rendered
        assert "Codey" in content                       # a discovered blueprint's name is shown

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    def test_blueprint_library_empty(
        self,
        mock_get_library,
        mock_discover,
        request_factory,
        test_user
    ):
        """Test blueprint library with no blueprints discovered."""
        from swarm.views.blueprint_library_views import blueprint_library

        mock_discover.return_value = {}
        mock_get_library.return_value = {"installed": [], "custom": []}

        request = request_factory.get("/blueprints/library/")
        request.session = {"dark_mode": True}
        _as_user(request, test_user)

        response = blueprint_library(request)

        assert response.status_code == 200
        # Renders the real library page even with nothing discovered.
        assert "Blueprint Library" in response.content.decode()

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    def test_blueprint_library_error(
        self,
        mock_get_library,
        mock_discover,
        request_factory,
        test_user
    ):
        """Test blueprint library handles errors gracefully."""
        from swarm.views.blueprint_library_views import blueprint_library

        mock_discover.side_effect = Exception("Discovery failed")

        request = request_factory.get("/blueprints/library/")
        request.session = {}
        _as_user(request, test_user)

        response = blueprint_library(request)

        assert response.status_code == 500

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    def test_blueprint_library_with_installed(
        self,
        mock_get_library,
        mock_discover,
        request_factory,
        mock_blueprints_discovered,
        test_user
    ):
        """Test blueprint library shows installed status correctly."""
        from swarm.views.blueprint_library_views import blueprint_library

        mock_discover.return_value = mock_blueprints_discovered
        mock_get_library.return_value = {
            "installed": ["codey"],
            "custom": []
        }

        request = request_factory.get("/blueprints/library/")
        request.session = {"dark_mode": True}
        _as_user(request, test_user)

        response = blueprint_library(request)

        assert response.status_code == 200

    def test_blueprint_library_anonymous_redirects_to_login(self, request_factory):
        """Anonymous browse is redirected to login (not 200)."""
        from swarm.views.blueprint_library_views import blueprint_library

        request = request_factory.get("/blueprint-library/")
        _as_anonymous(request)

        response = blueprint_library(request)

        assert response.status_code in (301, 302)
        assert "/login" in response.url


# =============================================================================
# Tests for blueprint_requirements_status view
# =============================================================================

class TestBlueprintRequirementsStatus:
    """Tests for the blueprint requirements status endpoint."""

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.load_active_config")
    @patch("swarm.views.blueprint_library_views.evaluate_mcp_compliance")
    def test_requirements_status_success(
        self,
        mock_evaluate,
        mock_load_config,
        mock_discover,
        request_factory,
        mock_blueprints_discovered,
        mock_active_config
    ):
        """Test successful requirements status check."""
        from swarm.views.blueprint_library_views import blueprint_requirements_status

        mock_discover.return_value = mock_blueprints_discovered
        mock_load_config.return_value = mock_active_config
        mock_evaluate.return_value = {"compliant": True, "missing": []}

        request = request_factory.get("/blueprints/requirements-status/")
        request.user = MagicMock(is_authenticated=True)

        response = blueprint_requirements_status(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert "blueprints" in data
        assert len(data["blueprints"]) == 3

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.load_active_config")
    @patch("swarm.views.blueprint_library_views.evaluate_mcp_compliance")
    def test_requirements_status_empty(
        self,
        mock_evaluate,
        mock_load_config,
        mock_discover,
        request_factory
    ):
        """Test requirements status with no blueprints."""
        from swarm.views.blueprint_library_views import blueprint_requirements_status

        mock_discover.return_value = {}
        mock_load_config.return_value = {}

        request = request_factory.get("/blueprints/requirements-status/")
        request.user = MagicMock(is_authenticated=True)

        response = blueprint_requirements_status(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["blueprints"] == []

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.load_active_config")
    def test_requirements_status_error(
        self,
        mock_load_config,
        mock_discover,
        request_factory
    ):
        """Test requirements status handles errors gracefully."""
        from swarm.views.blueprint_library_views import blueprint_requirements_status

        mock_discover.side_effect = Exception("Discovery error")

        request = request_factory.get("/blueprints/requirements-status/")
        request.user = MagicMock(is_authenticated=True)

        response = blueprint_requirements_status(request)

        assert response.status_code == 500
        data = json.loads(response.content)
        assert "error" in data


# =============================================================================
# Tests for add_blueprint_to_library view
# =============================================================================

@pytest.mark.django_db
class TestAddBlueprintToLibrary:
    """Tests for adding a blueprint to the user's library."""

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    @patch("swarm.views.blueprint_library_views.save_user_blueprint_library")
    def test_add_blueprint_success(
        self,
        mock_save,
        mock_get_library,
        mock_discover,
        request_factory,
        mock_blueprints_discovered,
        test_user
    ):
        """Test successfully adding a blueprint to library."""
        from swarm.views.blueprint_library_views import add_blueprint_to_library

        mock_discover.return_value = mock_blueprints_discovered
        mock_get_library.return_value = {"installed": [], "custom": []}
        mock_save.return_value = True

        request = request_factory.post("/blueprints/add/codey/")
        _as_user(request, test_user)

        response = add_blueprint_to_library(request, "codey")

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert "added to library" in data["message"]

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    def test_add_blueprint_not_found(
        self,
        mock_discover,
        request_factory,
        test_user
    ):
        """Test adding a non-existent blueprint returns 404."""
        from swarm.views.blueprint_library_views import add_blueprint_to_library

        mock_discover.return_value = {}

        request = request_factory.post("/blueprints/add/nonexistent/")
        _as_user(request, test_user)

        response = add_blueprint_to_library(request, "nonexistent")

        assert response.status_code == 404
        data = json.loads(response.content)
        assert "error" in data

    def test_add_blueprint_wrong_method(self, request_factory, test_user):
        """Test adding blueprint with wrong HTTP method."""
        from swarm.views.blueprint_library_views import add_blueprint_to_library

        request = request_factory.get("/blueprints/add/codey/")
        _as_user(request, test_user)

        response = add_blueprint_to_library(request, "codey")

        assert response.status_code == 405
        data = json.loads(response.content)
        assert data["error"] == "Method not allowed"

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    def test_add_blueprint_already_installed(
        self,
        mock_get_library,
        mock_discover,
        request_factory,
        mock_blueprints_discovered,
        test_user
    ):
        """Test adding a blueprint that's already installed."""
        from swarm.views.blueprint_library_views import add_blueprint_to_library

        mock_discover.return_value = mock_blueprints_discovered
        mock_get_library.return_value = {"installed": ["codey"], "custom": []}

        request = request_factory.post("/blueprints/add/codey/")
        _as_user(request, test_user)

        response = add_blueprint_to_library(request, "codey")

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert "already in library" in data["message"]

    @patch("swarm.views.blueprint_library_views.discover_blueprints")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    @patch("swarm.views.blueprint_library_views.save_user_blueprint_library")
    def test_add_blueprint_save_failure(
        self,
        mock_save,
        mock_get_library,
        mock_discover,
        request_factory,
        mock_blueprints_discovered,
        test_user
    ):
        """Test adding blueprint when save fails."""
        from swarm.views.blueprint_library_views import add_blueprint_to_library

        mock_discover.return_value = mock_blueprints_discovered
        mock_get_library.return_value = {"installed": [], "custom": []}
        mock_save.return_value = False

        request = request_factory.post("/blueprints/add/codey/")
        _as_user(request, test_user)

        response = add_blueprint_to_library(request, "codey")

        assert response.status_code == 500
        data = json.loads(response.content)
        assert data["error"] == "Failed to save library"

    def test_add_blueprint_anonymous_redirects_to_login(self, request_factory):
        """Anonymous mutators are redirected to login (not 200)."""
        from swarm.views.blueprint_library_views import add_blueprint_to_library

        request = request_factory.post("/blueprint-library/add/codey/")
        _as_anonymous(request)

        response = add_blueprint_to_library(request, "codey")

        assert response.status_code in (301, 302)
        assert "/login" in response.url


# =============================================================================
# Tests for remove_blueprint_from_library view
# =============================================================================

@pytest.mark.django_db
class TestRemoveBlueprintFromLibrary:
    """Tests for removing a blueprint from the user's library."""

    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    @patch("swarm.views.blueprint_library_views.save_user_blueprint_library")
    def test_remove_blueprint_success(
        self,
        mock_save,
        mock_get_library,
        request_factory,
        test_user
    ):
        """Test successfully removing a blueprint from library."""
        from swarm.views.blueprint_library_views import remove_blueprint_from_library

        mock_get_library.return_value = {"installed": ["codey", "gawd"], "custom": []}
        mock_save.return_value = True

        request = request_factory.post("/blueprints/remove/codey/")
        _as_user(request, test_user)

        response = remove_blueprint_from_library(request, "codey")

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert "removed from library" in data["message"]

    def test_remove_blueprint_wrong_method(self, request_factory, test_user):
        """Test removing blueprint with wrong HTTP method."""
        from swarm.views.blueprint_library_views import remove_blueprint_from_library

        request = request_factory.get("/blueprints/remove/codey/")
        _as_user(request, test_user)

        response = remove_blueprint_from_library(request, "codey")

        assert response.status_code == 405
        data = json.loads(response.content)
        assert data["error"] == "Method not allowed"

    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    def test_remove_blueprint_not_in_library(
        self,
        mock_get_library,
        request_factory,
        test_user
    ):
        """Test removing a blueprint that's not in library."""
        from swarm.views.blueprint_library_views import remove_blueprint_from_library

        mock_get_library.return_value = {"installed": ["gawd"], "custom": []}

        request = request_factory.post("/blueprints/remove/codey/")
        _as_user(request, test_user)

        response = remove_blueprint_from_library(request, "codey")

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert "not in library" in data["message"]

    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    @patch("swarm.views.blueprint_library_views.save_user_blueprint_library")
    def test_remove_blueprint_save_failure(
        self,
        mock_save,
        mock_get_library,
        request_factory,
        test_user
    ):
        """Test removing blueprint when save fails."""
        from swarm.views.blueprint_library_views import remove_blueprint_from_library

        mock_get_library.return_value = {"installed": ["codey"], "custom": []}
        mock_save.return_value = False

        request = request_factory.post("/blueprints/remove/codey/")
        _as_user(request, test_user)

        response = remove_blueprint_from_library(request, "codey")

        assert response.status_code == 500
        data = json.loads(response.content)
        assert data["error"] == "Failed to save library"

    def test_remove_blueprint_anonymous_redirects_to_login(self, request_factory):
        """Anonymous remove is redirected to login (not 200)."""
        from swarm.views.blueprint_library_views import remove_blueprint_from_library

        request = request_factory.post("/blueprint-library/remove/codey/")
        _as_anonymous(request)

        response = remove_blueprint_from_library(request, "codey")

        assert response.status_code in (301, 302)
        assert "/login" in response.url


# =============================================================================
# Tests for blueprint_creator view
# =============================================================================

@pytest.mark.django_db
class TestBlueprintCreator:
    """Tests for the blueprint creator form."""

    def test_blueprint_creator_get(self, request_factory, test_user):
        """Test GET request to blueprint creator."""
        from swarm.views.blueprint_library_views import blueprint_creator

        request = request_factory.get("/blueprints/creator/")
        request.session = {"dark_mode": True}
        _as_user(request, test_user)

        response = blueprint_creator(request)

        assert response.status_code == 200
        html = response.content.decode()
        assert "Blueprint interface spec" in html
        assert "class MyTeamBlueprint" in html
        assert "async def run" in html

    @patch("swarm.views.blueprint_library_views.generate_blueprint_code")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    @patch("swarm.views.blueprint_library_views.save_user_blueprint_library")
    @patch("swarm.views.blueprint_library_views.comfyui_client")
    def test_blueprint_creator_post_success(
        self,
        mock_comfyui,
        mock_save,
        mock_get_library,
        mock_generate_code,
        request_factory,
        test_user,
        tmp_path,
        monkeypatch,
    ):
        """Test successful POST to create a blueprint under get_user_blueprints_dir()."""

        from swarm.views.blueprint_library_views import blueprint_creator

        data_dir = tmp_path / "swarm_data"
        monkeypatch.setenv("SWARM_USER_DATA_DIR", str(data_dir))
        monkeypatch.delenv("SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY", raising=False)

        mock_generate_code.return_value = "# Generated blueprint code"
        mock_get_library.return_value = {"installed": [], "custom": []}
        mock_save.return_value = True
        mock_comfyui.is_available.return_value = False

        request = request_factory.post(
            "/blueprints/creator/",
            {
                "blueprint_name": "My Agent",
                "description": "A test agent",
                "category": "ai_assistants",
                "tags": "test, custom",
                "requirements": "",
                "generate_avatar": "false"
            }
        )
        request.session = {}
        _as_user(request, test_user)

        response = blueprint_creator(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert "created successfully" in data["message"]
        assert data["blueprint_id"] == "my_agent"
        assert "SWARM_ALLOW_USER_BLUEPRINT_DISCOVERY" in data["message"]
        saved = Path(data["path"])
        assert saved.is_file()
        assert saved.name == "blueprint_my_agent.py"
        assert str(saved).startswith(str((data_dir / "blueprints").resolve()))
        assert saved.read_text() == "# Generated blueprint code"

    def test_blueprint_creator_post_missing_name(self, request_factory, test_user):
        """Test POST with missing blueprint name."""
        from swarm.views.blueprint_library_views import blueprint_creator

        request = request_factory.post(
            "/blueprints/creator/",
            {
                "description": "A test agent",
                "category": "ai_assistants"
            }
        )
        request.session = {}
        _as_user(request, test_user)

        response = blueprint_creator(request)

        assert response.status_code == 400
        data = json.loads(response.content)
        assert "error" in data

    def test_blueprint_creator_post_missing_description(self, request_factory, test_user):
        """Test POST with missing description."""
        from swarm.views.blueprint_library_views import blueprint_creator

        request = request_factory.post(
            "/blueprints/creator/",
            {
                "blueprint_name": "My Agent",
                "category": "ai_assistants"
            }
        )
        request.session = {}
        _as_user(request, test_user)

        response = blueprint_creator(request)

        assert response.status_code == 400
        data = json.loads(response.content)
        assert "error" in data

    @patch("swarm.views.blueprint_library_views.generate_blueprint_code")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    @patch("swarm.views.blueprint_library_views.save_user_blueprint_library")
    @patch("swarm.views.blueprint_library_views.comfyui_client")
    def test_blueprint_creator_post_with_avatar(
        self,
        mock_comfyui,
        mock_save,
        mock_get_library,
        mock_generate_code,
        request_factory,
        test_user
    ):
        """Test POST to create a blueprint with avatar generation."""
        from swarm.views.blueprint_library_views import blueprint_creator

        mock_generate_code.return_value = "# Generated blueprint code"
        mock_get_library.return_value = {"installed": [], "custom": []}
        mock_save.return_value = True
        mock_comfyui.is_available.return_value = True
        mock_comfyui.generate_avatar.return_value = "/path/to/avatar.png"

        request = request_factory.post(
            "/blueprints/creator/",
            {
                "blueprint_name": "My Agent",
                "description": "A test agent",
                "category": "ai_assistants",
                "tags": "test",
                "requirements": "",
                "generate_avatar": "true",
                "avatar_style": "professional"
            }
        )
        request.session = {}
        _as_user(request, test_user)

        response = blueprint_creator(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        mock_comfyui.generate_avatar.assert_called_once()

    @patch("swarm.views.blueprint_library_views.generate_blueprint_code")
    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    @patch("swarm.views.blueprint_library_views.save_user_blueprint_library")
    def test_blueprint_creator_post_save_failure(
        self,
        mock_save,
        mock_get_library,
        mock_generate_code,
        request_factory,
        test_user
    ):
        """Test POST when save fails."""
        from swarm.views.blueprint_library_views import blueprint_creator

        mock_generate_code.return_value = "# Generated blueprint code"
        mock_get_library.return_value = {"installed": [], "custom": []}
        mock_save.return_value = False

        request = request_factory.post(
            "/blueprints/creator/",
            {
                "blueprint_name": "My Agent",
                "description": "A test agent",
                "category": "ai_assistants",
                "generate_avatar": "false"
            }
        )
        request.session = {}
        _as_user(request, test_user)

        response = blueprint_creator(request)

        assert response.status_code == 500
        data = json.loads(response.content)
        assert data["error"] == "Failed to save blueprint"

    def test_blueprint_creator_anonymous_redirects_to_login(self, request_factory):
        """Anonymous creator access is redirected to login (not 200)."""
        from swarm.views.blueprint_library_views import blueprint_creator

        request = request_factory.get("/blueprint-library/creator/")
        _as_anonymous(request)

        response = blueprint_creator(request)

        assert response.status_code in (301, 302)
        assert "/login" in response.url


# =============================================================================
# Tests for generate_avatar view
# =============================================================================

@pytest.mark.django_db
class TestGenerateAvatar:
    """Tests for avatar generation."""

    def test_generate_avatar_wrong_method(self, request_factory, test_user):
        """Test avatar generation with wrong HTTP method."""
        from swarm.views.blueprint_library_views import generate_avatar

        request = request_factory.get("/blueprints/avatar/codey/")
        _as_user(request, test_user)

        response = generate_avatar(request, "codey")

        assert response.status_code == 405
        data = json.loads(response.content)
        assert data["error"] == "Method not allowed"

    @patch("swarm.views.blueprint_library_views.comfyui_client")
    def test_generate_avatar_blueprint_not_found(
        self,
        mock_comfyui,
        request_factory,
        test_user
    ):
        """Test avatar generation for non-existent blueprint."""
        from swarm.views.blueprint_library_views import generate_avatar

        request = request_factory.post("/blueprints/avatar/nonexistent/")
        _as_user(request, test_user)

        response = generate_avatar(request, "nonexistent")

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["error"] == "Blueprint not found"

    @patch("swarm.views.blueprint_library_views.comfyui_client")
    def test_generate_avatar_success(
        self,
        mock_comfyui,
        request_factory,
        test_user
    ):
        """Test successful avatar generation."""
        from swarm.views.blueprint_library_views import (
            generate_avatar,
        )

        mock_comfyui.generate_avatar.return_value = "/path/to/avatar.png"

        # Use a blueprint that exists in BLUEPRINT_METADATA
        blueprint_name = "codey"
        request = request_factory.post(
            "/blueprints/avatar/codey/",
            {"avatar_style": "professional"}
        )
        _as_user(request, test_user)

        response = generate_avatar(request, blueprint_name)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert "avatar_path" in data

    @patch("swarm.views.blueprint_library_views.comfyui_client")
    def test_generate_avatar_failure(
        self,
        mock_comfyui,
        request_factory,
        test_user
    ):
        """Test avatar generation failure."""
        from swarm.views.blueprint_library_views import (
            generate_avatar,
        )

        mock_comfyui.generate_avatar.return_value = None

        blueprint_name = "codey"
        request = request_factory.post(
            "/blueprints/avatar/codey/",
            {"avatar_style": "professional"}
        )
        _as_user(request, test_user)

        response = generate_avatar(request, blueprint_name)

        assert response.status_code == 500
        data = json.loads(response.content)
        assert "error" in data

    def test_generate_avatar_anonymous_redirects_to_login(self, request_factory):
        """Anonymous avatar generation is redirected to login (not 200)."""
        from swarm.views.blueprint_library_views import generate_avatar

        request = request_factory.post("/blueprint-library/generate-avatar/codey/")
        _as_anonymous(request)

        response = generate_avatar(request, "codey")

        assert response.status_code in (301, 302)
        assert "/login" in response.url


# =============================================================================
# Tests for check_comfyui_status view
# =============================================================================

class TestCheckComfyUIStatus:
    """Tests for ComfyUI status check."""

    @patch("swarm.views.blueprint_library_views.comfyui_client")
    def test_comfyui_status_available(self, mock_comfyui, request_factory):
        """Test ComfyUI status when available."""
        from swarm.views.blueprint_library_views import check_comfyui_status

        mock_comfyui.is_available.return_value = True
        mock_comfyui.enabled = True

        request = request_factory.get("/blueprints/comfyui-status/")
        request.user = MagicMock(is_authenticated=True)

        response = check_comfyui_status(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["available"] is True
        assert data["enabled"] is True
        assert "styles" in data

    @patch("swarm.views.blueprint_library_views.comfyui_client")
    def test_comfyui_status_unavailable(self, mock_comfyui, request_factory):
        """Test ComfyUI status when unavailable."""
        from swarm.views.blueprint_library_views import check_comfyui_status

        mock_comfyui.is_available.return_value = False
        mock_comfyui.enabled = False

        request = request_factory.get("/blueprints/comfyui-status/")
        request.user = MagicMock(is_authenticated=True)

        response = check_comfyui_status(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["available"] is False
        assert data["enabled"] is False

    @patch("swarm.views.blueprint_library_views.comfyui_client")
    def test_comfyui_status_error(self, mock_comfyui, request_factory):
        """Test ComfyUI status handles errors gracefully."""
        from swarm.views.blueprint_library_views import check_comfyui_status

        mock_comfyui.is_available.side_effect = Exception("Connection error")

        request = request_factory.get("/blueprints/comfyui-status/")
        request.user = MagicMock(is_authenticated=True)

        response = check_comfyui_status(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["available"] is False
        assert data["enabled"] is False


# =============================================================================
# Tests for my_blueprints view
# =============================================================================

@pytest.mark.django_db
class TestMyBlueprints:
    """Tests for the user's blueprints page."""

    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    def test_my_blueprints_success(
        self,
        mock_get_library,
        request_factory,
        mock_blueprint_library,
        test_user
    ):
        """Test successful my blueprints page load."""
        from swarm.views.blueprint_library_views import my_blueprints

        mock_get_library.return_value = mock_blueprint_library

        request = request_factory.get("/blueprints/my/")
        request.session = {"dark_mode": True}
        _as_user(request, test_user)

        response = my_blueprints(request)

        assert response.status_code == 200
        assert "My Blueprints" in response.content.decode()

    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    def test_my_blueprints_empty(
        self,
        mock_get_library,
        request_factory,
        test_user
    ):
        """Test my blueprints with empty library."""
        from swarm.views.blueprint_library_views import my_blueprints

        mock_get_library.return_value = {"installed": [], "custom": []}

        request = request_factory.get("/blueprints/my/")
        request.session = {"dark_mode": True}
        _as_user(request, test_user)

        response = my_blueprints(request)

        assert response.status_code == 200
        assert "My Blueprints" in response.content.decode()

    @patch("swarm.views.blueprint_library_views.get_user_blueprint_library")
    def test_my_blueprints_error(
        self,
        mock_get_library,
        request_factory,
        test_user
    ):
        """Test my blueprints handles errors gracefully."""
        from swarm.views.blueprint_library_views import my_blueprints

        mock_get_library.side_effect = Exception("Library error")

        request = request_factory.get("/blueprints/my/")
        request.session = {}
        _as_user(request, test_user)

        response = my_blueprints(request)

        assert response.status_code == 500

    def test_my_blueprints_anonymous_redirects_to_login(self, request_factory):
        """Anonymous my-blueprints browse is redirected to login (not 200)."""
        from swarm.views.blueprint_library_views import my_blueprints

        request = request_factory.get("/blueprint-library/my-blueprints/")
        _as_anonymous(request)

        response = my_blueprints(request)

        assert response.status_code in (301, 302)
        assert "/login" in response.url


# =============================================================================
# Tests for helper functions
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    @patch("swarm.views.blueprint_library_views.get_user_config_dir_for_swarm")
    def test_get_user_blueprint_library_exists(
        self,
        mock_get_config_dir,
        tmp_path
    ):
        """Test getting user library when file exists."""
        from swarm.views.blueprint_library_views import get_user_blueprint_library

        # Create a temporary library file
        library_file = tmp_path / "blueprint_library.json"
        library_file.write_text('{"installed": ["codey"], "custom": []}')
        mock_get_config_dir.return_value = tmp_path

        result = get_user_blueprint_library()

        assert result["installed"] == ["codey"]
        assert result["custom"] == []

    @patch("swarm.views.blueprint_library_views.get_user_config_dir_for_swarm")
    def test_get_user_blueprint_library_not_exists(
        self,
        mock_get_config_dir,
        tmp_path
    ):
        """Test getting user library when file doesn't exist."""
        from swarm.views.blueprint_library_views import get_user_blueprint_library

        mock_get_config_dir.return_value = tmp_path

        result = get_user_blueprint_library()

        assert result == {"installed": [], "custom": []}

    @patch("swarm.views.blueprint_library_views.get_user_config_dir_for_swarm")
    def test_save_user_blueprint_library_success(
        self,
        mock_get_config_dir,
        tmp_path
    ):
        """Test saving user library successfully."""
        from swarm.views.blueprint_library_views import save_user_blueprint_library

        mock_get_config_dir.return_value = tmp_path

        result = save_user_blueprint_library(
            {"installed": ["codey"], "custom": []}
        )

        assert result is True
        library_file = tmp_path / "blueprint_library.json"
        assert library_file.exists()

    @patch("swarm.views.blueprint_library_views.get_user_config_dir_for_swarm")
    def test_save_user_blueprint_library_creates_dir(
        self,
        mock_get_config_dir,
        tmp_path
    ):
        """Test saving library creates directory if needed."""
        from swarm.views.blueprint_library_views import save_user_blueprint_library

        new_dir = tmp_path / "new_config_dir"
        mock_get_config_dir.return_value = new_dir

        result = save_user_blueprint_library(
            {"installed": [], "custom": []}
        )

        assert result is True
        assert new_dir.exists()


class TestGenerateBlueprintCode:
    """Tests for blueprint code generation."""

    def test_generate_blueprint_code_basic(self):
        """Test basic blueprint code generation."""
        from swarm.views.blueprint_library_views import generate_blueprint_code

        code = generate_blueprint_code(
            name="TestAgent",
            description="A test agent",
            category="ai_assistants",
            tags=["test", "custom"],
            _requirements=""
        )

        assert "TestAgent" in code
        assert "A test agent" in code
        assert "ai_assistants" in code
        # REQ-851: emitters default to a kind base (ApiKindBase for the
        # OpenAI-streaming template).
        assert "ApiKindBase" in code
        assert "AsyncGenerator" in code
        assert "yield" in code
        assert "async def run(" in code
        assert "-> AsyncGenerator" in code
        assert 'if __name__ == "__main__"' not in code
        assert "asyncio.run(" not in code
        # Must call a real OpenAI-compatible client API, not agents SDK fiction.
        assert "chat_completion_stream" not in code
        assert "AsyncOpenAI" in code
        assert "chat.completions.create" in code
        assert "get_llm_profile" in code
        assert "WARNING: LLM call failed" in code
        assert "falling back to echo" in code

    def test_generate_blueprint_code_with_spaces(self):
        """Test blueprint code generation with name containing spaces."""
        from swarm.views.blueprint_library_views import generate_blueprint_code

        code = generate_blueprint_code(
            name="My Test Agent",
            description="An agent with spaces in name",
            category="code_helpers",
            tags=["test"],
            _requirements=""
        )

        assert "MyTestAgent" in code  # Spaces should be removed in class name
        assert "My Test Agent" in code  # Original name in metadata
        assert "AsyncGenerator" in code
        assert "yield" in code
        assert "chat_completion_stream" not in code
        assert "chat.completions.create" in code


    def test_generate_blueprint_code_assist_keeps_validated_spec_class(self, monkeypatch):
        from swarm.core.blueprint_spec import BLUEPRINT_INTERFACE
        from swarm.views.blueprint_library_views import generate_blueprint_code

        monkeypatch.setattr(
            "swarm.core.llm_assist.generate_blueprint_class",
            lambda **kwargs: BLUEPRINT_INTERFACE,
        )
        code = generate_blueprint_code(
            name="Spec Team",
            description="spec",
            category="ai_assistants",
            tags=["spec"],
            _requirements="summarise the last user message",
            assist=True,
        )
        assert "class MyTeamBlueprint(ApiKindBase)" in code
        assert "async def run" in code
        assert "chat_completion_stream" not in code

    def test_generate_blueprint_code_assist_falls_back_when_draft_invalid(self, monkeypatch):
        from swarm.views.blueprint_library_views import generate_blueprint_code

        monkeypatch.setattr(
            "swarm.core.llm_assist.generate_blueprint_class",
            lambda **kwargs: "print('not a blueprint')\n",
        )
        code = generate_blueprint_code(
            name="Fallback Team",
            description="template path",
            category="ai_assistants",
            tags=["test"],
            _requirements="must handle JSON",
            assist=True,
        )
        assert "class FallbackTeamBlueprint(ApiKindBase)" in code
        assert "AsyncOpenAI" in code
        assert "must handle JSON" in code
        assert "chat_completion_stream" not in code

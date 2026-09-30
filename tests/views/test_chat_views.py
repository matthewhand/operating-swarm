"""
Unit tests for src/swarm/views/chat_views.py
=============================================

Tests for chat views covering:
- HealthCheckView: simple health check endpoint
- ChatCompletionsView: OpenAI-compatible chat completions API
- IndexView: main chat interface page

Uses mocks for blueprint discovery, LLM calls, and DB interactions; no network.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.test import RequestFactory
from django.urls import resolve
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory


def test_chat_completions_urls_accept_trailing_slash():
    """Slash + no-slash twins (same pattern as /v1/responses)."""
    assert resolve("/v1/chat/completions").url_name == "chat_completions"
    assert resolve("/v1/chat/completions/").url_name == "chat_completions_slash"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def api_client():
    """Return an API client for testing."""
    return APIClient()


@pytest.fixture
def request_factory():
    """Return a Django request factory."""
    return RequestFactory()


@pytest.fixture
def mock_blueprint_instance():
    """Create a mock blueprint instance for testing."""
    instance = MagicMock()
    instance.run = AsyncMock()
    instance.blueprint_id = "test_blueprint"
    return instance


@pytest.fixture
def valid_chat_request_data():
    """Valid chat completion request data."""
    return {
        "model": "test_blueprint",
        "messages": [
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "stream": False
    }


@pytest.fixture
def valid_streaming_request_data():
    """Valid streaming chat completion request data."""
    return {
        "model": "test_blueprint",
        "messages": [
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "stream": True
    }


# =============================================================================
# Tests for ChatCompletionsView - Sync tests (validation errors)
# =============================================================================

class TestChatCompletionsViewValidation:
    """Tests for the chat completions endpoint validation (sync tests)."""

    def test_post_invalid_json(self, api_client):
        """Test POST with invalid JSON body."""
        response = api_client.post(
            "/v1/chat/completions",
            "invalid json",
            content_type="application/json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_post_missing_model(self, api_client):
        """Test POST with missing model field."""
        data = {
            "messages": [{"role": "user", "content": "Hello"}]
        }

        response = api_client.post(
            "/v1/chat/completions",
            data,
            format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_post_missing_messages(self, api_client):
        """Test POST with missing messages field."""
        data = {
            "model": "test_blueprint"
        }

        response = api_client.post(
            "/v1/chat/completions",
            data,
            format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_post_empty_messages(self, api_client):
        """Test POST with empty messages list."""
        data = {
            "model": "test_blueprint",
            "messages": []
        }

        response = api_client.post(
            "/v1/chat/completions",
            data,
            format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


# =============================================================================
# Tests for ChatCompletionsView - Non-async tests using APIClient
# =============================================================================

class TestChatCompletionsViewAsync:
    """Tests for the chat completions endpoint (non-async tests via APIClient)."""

    def test_post_blueprint_not_found(
        self,
        api_client,
        valid_chat_request_data
    ):
        """Test POST when blueprint is not found."""
        with patch("swarm.views.chat_views.get_blueprint_instance") as mock_get_instance, \
             patch("swarm.views.chat_views.validate_model_access") as mock_validate_access:

            mock_validate_access.return_value = True
            mock_get_instance.return_value = None

            response = api_client.post(
                "/v1/chat/completions",
                valid_chat_request_data,
                format="json"
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_post_permission_denied(
        self,
        api_client,
        mock_blueprint_instance,
        valid_chat_request_data
    ):
        """Test POST when user lacks permission for the model."""
        with patch("swarm.views.chat_views.get_blueprint_instance") as mock_get_instance, \
             patch("swarm.views.chat_views.validate_model_access") as mock_validate_access:

            mock_validate_access.return_value = False
            mock_get_instance.return_value = mock_blueprint_instance

            response = api_client.post(
                "/v1/chat/completions",
                valid_chat_request_data,
                format="json"
            )

            assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_post_non_streaming_success(
        self,
        api_client,
        mock_blueprint_instance,
        valid_chat_request_data
    ):
        """Test successful non-streaming chat completion."""
        # Mock the blueprint run to return a valid response
        async def mock_run(*args, **kwargs):
            yield {"messages": [{"role": "assistant", "content": "I am doing well!"}]}
        mock_blueprint_instance.run = mock_run

        with patch("swarm.views.chat_views.get_blueprint_instance") as mock_get_instance, \
             patch("swarm.views.chat_views.validate_model_access") as mock_validate_access:

            mock_validate_access.return_value = True
            mock_get_instance.return_value = mock_blueprint_instance

            response = api_client.post(
                "/v1/chat/completions",
                valid_chat_request_data,
                format="json"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "id" in data
            assert data["object"] == "chat.completion"
            assert data["model"] == "test_blueprint"
            assert len(data["choices"]) == 1
            assert data["choices"][0]["message"]["role"] == "assistant"

    def test_post_streaming_success(
        self,
        api_client,
        mock_blueprint_instance,
        valid_streaming_request_data
    ):
        """Test successful streaming chat completion."""
        # Mock the blueprint run to yield streaming chunks
        async def mock_run(*args, **kwargs):
            yield {"messages": [{"content": "Hello"}]}
            yield {"messages": [{"content": " there"}]}
            yield {"messages": [{"content": "!"}]}
        mock_blueprint_instance.run = mock_run

        with patch("swarm.views.chat_views.get_blueprint_instance") as mock_get_instance, \
             patch("swarm.views.chat_views.validate_model_access") as mock_validate_access:

            mock_validate_access.return_value = True
            mock_get_instance.return_value = mock_blueprint_instance

            response = api_client.post(
                "/v1/chat/completions",
                valid_streaming_request_data,
                format="json"
            )

            assert response.status_code == status.HTTP_200_OK
            assert response["Content-Type"] == "text/event-stream"

    def test_post_blueprint_execution_error(
        self,
        api_client,
        mock_blueprint_instance,
        valid_chat_request_data
    ):
        """Test POST when blueprint execution fails."""
        # Mock blueprint to raise an error
        async def mock_run_error(*args, **kwargs):
            raise Exception("Blueprint execution failed")
            yield  # Make it a generator
        mock_blueprint_instance.run = mock_run_error

        with patch("swarm.views.chat_views.get_blueprint_instance") as mock_get_instance, \
             patch("swarm.views.chat_views.validate_model_access") as mock_validate_access:

            mock_validate_access.return_value = True
            mock_get_instance.return_value = mock_blueprint_instance

            response = api_client.post(
                "/v1/chat/completions",
                valid_chat_request_data,
                format="json"
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_post_blueprint_invalid_response(
        self,
        api_client,
        mock_blueprint_instance,
        valid_chat_request_data
    ):
        """Test POST when blueprint returns invalid response format."""
        # Mock blueprint to return invalid format
        async def mock_run_invalid(*args, **kwargs):
            yield {"invalid_key": "invalid_value"}
        mock_blueprint_instance.run = mock_run_invalid

        with patch("swarm.views.chat_views.get_blueprint_instance") as mock_get_instance, \
             patch("swarm.views.chat_views.validate_model_access") as mock_validate_access:

            mock_validate_access.return_value = True
            mock_get_instance.return_value = mock_blueprint_instance

            response = api_client.post(
                "/v1/chat/completions",
                valid_chat_request_data,
                format="json"
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_post_openai_format_response(
        self,
        api_client,
        mock_blueprint_instance,
        valid_chat_request_data
    ):
        """Test POST when blueprint returns OpenAI-style response."""
        # Mock blueprint to return OpenAI-style response
        async def mock_run_openai(*args, **kwargs):
            yield {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "OpenAI style response"
                    }
                }]
            }
        mock_blueprint_instance.run = mock_run_openai

        with patch("swarm.views.chat_views.get_blueprint_instance") as mock_get_instance, \
             patch("swarm.views.chat_views.validate_model_access") as mock_validate_access:

            mock_validate_access.return_value = True
            mock_get_instance.return_value = mock_blueprint_instance

            response = api_client.post(
                "/v1/chat/completions",
                valid_chat_request_data,
                format="json"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["choices"][0]["message"]["content"] == "OpenAI style response"


# =============================================================================
# Tests for IndexView
# =============================================================================

class TestIndexView:
    """Tests for the main chat interface page."""

    @pytest.mark.django_db
    @patch("swarm.views.chat_views.get_available_blueprints")
    def test_index_view_authenticated(self, mock_get_blueprints, request_factory, test_user):
        """Test index view with authenticated user."""
        from swarm.views.chat_views import IndexView

        mock_get_blueprints.return_value = {
            "assistant": {"metadata": {"name": "Assistant"}},
            "developer": {"metadata": {"name": "Developer"}}
        }

        request = request_factory.get("/")
        request.user = test_user

        view = IndexView.as_view()
        response = view(request)

        assert response.status_code == 200
        # Check that the response contains rendered content
        assert response.content is not None

    @pytest.mark.django_db
    @patch("swarm.views.chat_views.get_available_blueprints")
    def test_index_view_empty_blueprints(self, mock_get_blueprints, request_factory, test_user):
        """Test index view with no available blueprints."""
        from swarm.views.chat_views import IndexView

        mock_get_blueprints.return_value = {}

        request = request_factory.get("/")
        request.user = test_user

        view = IndexView.as_view()
        response = view(request)

        assert response.status_code == 200

    def test_index_view_unauthenticated_redirect(self, request_factory):
        """Test index view redirects unauthenticated users."""
        from django.contrib.auth.models import AnonymousUser

        from swarm.views.chat_views import IndexView

        request = request_factory.get("/")
        request.user = AnonymousUser()

        view = IndexView.as_view()
        response = view(request)

        # Should redirect to login due to @login_required decorator
        assert response.status_code in [302, 301]


# =============================================================================
# Tests for Authentication and Authorization
# =============================================================================

class TestChatAuthentication:
    """Tests for authentication and authorization in chat views."""

    def test_api_auth_enabled_no_credentials(
        self,
        api_client,
        mock_blueprint_instance,
        valid_chat_request_data
    ):
        """Test that API returns 401 when auth is enabled but no credentials provided."""
        with patch("swarm.views.chat_views.settings") as mock_settings, \
             patch("swarm.views.chat_views.get_blueprint_instance") as mock_get_instance, \
             patch("swarm.views.chat_views.validate_model_access") as mock_validate_access:

            mock_settings.ENABLE_API_AUTH = True

            response = api_client.post(
                "/v1/chat/completions",
                valid_chat_request_data,
                format="json"
            )

            # Should return 403 Forbidden when auth is required but not provided
            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN
            ]

    def test_api_auth_disabled(
        self,
        api_client,
        mock_blueprint_instance,
        valid_chat_request_data
    ):
        """Test that API works without auth when auth is disabled."""
        async def mock_run(*args, **kwargs):
            yield {"messages": [{"role": "assistant", "content": "Response"}]}
        mock_blueprint_instance.run = mock_run

        with patch("swarm.views.chat_views.settings") as mock_settings, \
             patch("swarm.views.chat_views.get_blueprint_instance") as mock_get_instance, \
             patch("swarm.views.chat_views.validate_model_access") as mock_validate_access:

            mock_settings.ENABLE_API_AUTH = False

            mock_validate_access.return_value = True
            mock_get_instance.return_value = mock_blueprint_instance

            response = api_client.post(
                "/v1/chat/completions",
                valid_chat_request_data,
                format="json"
            )

            assert response.status_code == status.HTTP_200_OK


# =============================================================================
# Tests for HealthCheckView
# =============================================================================

class TestHealthCheckView:
    """Tests for the health check endpoint."""

    def test_health_check_get(self, api_client):
        """Test GET request to health check returns ok status."""
        from swarm.views.chat_views import HealthCheckView

        view = HealthCheckView()
        factory_request = RequestFactory().get("/health/")

        # Create a proper DRF request
        factory = APIRequestFactory()
        request = factory.get("/health/")

        response = view.get(request)

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["status"] == "ok"
        from swarm.core.paths import config_root

        assert data["config_root"] == str(config_root())

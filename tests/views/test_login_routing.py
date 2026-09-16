"""Tests for the login/webui URL routing (ROADMAP §2 "Login routing").

These tests exercise the *routed* URLs via the Django test client (not the
view function directly) to lock in:

- /accounts/login/ and /login/ both resolve to ``custom_login``
  (Django's default LOGIN_URL is '/accounts/login/'; this project's
  settings.LOGIN_URL is '/login/').
- GET renders the login form; POST with bad credentials re-renders with an
  error; POST with good credentials redirects.
- Malicious ``?next=`` values are rejected (open-redirect hardening).
- The dev-only testuser auto-login stays gated behind
  ALLOW_TESTUSER_AUTOLOGIN + DJANGO_DEBUG.
- Legacy /webui/ redirects to '/' instead of 500ing with
  TemplateDoesNotExist.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse


@pytest.fixture
def no_autologin(monkeypatch):
    """Ensure the dev-only testuser auto-login path is disabled."""
    monkeypatch.delenv("ALLOW_TESTUSER_AUTOLOGIN", raising=False)


@pytest.fixture
def login_user(db):
    user = User.objects.create_user(username="routeuser", password="route-pass-123")
    return user


class TestLoginURLRouting:
    def test_login_name_reverses_to_accounts_login(self):
        assert reverse("login") == "/accounts/login/"

    def test_custom_login_name_reverses_to_login(self):
        # Matches settings.LOGIN_URL = '/login/' and the form action in
        # templates/account/login.html ({% url 'custom_login' %}).
        assert reverse("custom_login") == "/login/"

    @pytest.mark.django_db
    @pytest.mark.parametrize("url", ["/accounts/login/", "/login/"])
    def test_get_renders_login_form(self, client, url):
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "<form" in content
        assert 'name="username"' in content
        assert 'name="password"' in content
        assert 'class="os-login"' in content
        assert "os-shell" not in content
        assert "os-agent-sidebar" not in content

    @pytest.mark.django_db
    def test_post_bad_credentials_rerenders_with_error(self, client, no_autologin):
        response = client.post(
            "/accounts/login/", {"username": "nosuch", "password": "wrong"}
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Invalid username or password." in content
        assert "<form" in content

    @pytest.mark.django_db
    def test_post_good_credentials_redirects_to_default(
        self, client, login_user, no_autologin
    ):
        response = client.post(
            "/accounts/login/", {"username": "routeuser", "password": "route-pass-123"}
        )
        assert response.status_code == 302
        assert response.url == "/"

    @pytest.mark.django_db
    def test_post_good_credentials_honours_safe_next(
        self, client, login_user, no_autologin
    ):
        response = client.post(
            "/accounts/login/?next=/teams/",
            {"username": "routeuser", "password": "route-pass-123"},
        )
        assert response.status_code == 302
        assert response.url == "/teams/"

    @pytest.mark.django_db
    def test_post_preserves_nested_query_in_next(
        self, client, login_user, no_autologin
    ):
        get = client.get("/login/?next=/sessions/%3Flimit%3D10")
        assert get.status_code == 200
        html = get.content.decode()
        assert 'name="next"' in html
        assert 'value="/sessions/?limit=10"' in html
        assert "?next=" not in html.split("<form", 1)[1].split(">", 1)[0]
        response = client.post(
            "/login/",
            {
                "username": "routeuser",
                "password": "route-pass-123",
                "next": "/sessions/?limit=10",
            },
        )
        assert response.status_code == 302
        assert response.url == "/sessions/?limit=10"

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "malicious_next",
        [
            "http://malicious.example.com/",
            "https://evil.example.com/phish",
            "//evil.example.com",
        ],
    )
    def test_post_good_credentials_rejects_malicious_next(
        self, client, login_user, no_autologin, malicious_next
    ):
        response = client.post(
            f"/accounts/login/?next={malicious_next}",
            {"username": "routeuser", "password": "route-pass-123"},
        )
        assert response.status_code == 302
        assert response.url == "/"

    @pytest.mark.django_db
    def test_login_alias_post_good_credentials_redirects(
        self, client, login_user, no_autologin
    ):
        response = client.post(
            "/login/", {"username": "routeuser", "password": "route-pass-123"}
        )
        assert response.status_code == 302
        assert response.url == "/"


class TestTestuserAutologinGating:
    """The auto-login hardening must hold through the routed URL."""

    @pytest.mark.django_db
    def test_autologin_disabled_by_default(self, client, no_autologin):
        response = client.post(
            "/accounts/login/", {"username": "testuser", "password": "wrong"}
        )
        # No auto-login: bad credentials re-render the form with an error and
        # no session is established. (Don't assert on the testuser row itself:
        # other test modules legitimately create a 'testuser' fixture.)
        assert response.status_code == 200
        assert "Invalid username or password." in response.content.decode()
        assert "_auth_user_id" not in client.session

    @pytest.mark.django_db
    def test_autologin_with_debug_logs_in_and_validates_next(self, client, monkeypatch):
        monkeypatch.setenv("ALLOW_TESTUSER_AUTOLOGIN", "true")
        monkeypatch.setenv("DJANGO_DEBUG", "true")
        response = client.post(
            "/accounts/login/?next=http://malicious.example.com/",
            {"username": "anything", "password": "wrong"},
        )
        # Auto-login happened, but the malicious next was still rejected.
        assert response.status_code == 302
        assert response.url == "/"
        assert "_auth_user_id" in client.session
        assert User.objects.filter(username="testuser").exists()


class TestWebUIRedirect:
    @pytest.mark.django_db
    def test_webui_redirects_to_root(self, client):
        """Legacy /webui/ must not 500 (TemplateDoesNotExist); it redirects to /."""
        response = client.get("/webui/")
        assert response.status_code == 302
        assert response.url == "/"

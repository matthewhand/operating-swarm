"""End-to-end OAuth callback: provider response -> session -> ownership.

Only the HTTP transport is stubbed (`GithubOAuth2.get_json`). Everything above
it -- the real `complete` view, `auth_complete`, and the whole
SOCIAL_AUTH_PIPELINE -- runs for real, so this covers the step ordering that
matters most: the allowlist must halt *before* social_user/create_user, so a
refused sign-in leaves no account row behind.
"""

from __future__ import annotations

import pytest
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model

from swarm.auth import request_principal

User = get_user_model()

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        not getattr(django_settings, "SOCIAL_AUTH_AVAILABLE", False),
        reason="requires the `oauth`/`deploy` extra (social-auth-app-django)",
    ),
]

GITHUB_USER = {
    "id": 4242,
    "login": "octocat",
    "name": "Octo Cat",
    "email": "me@example.com",
    "avatar_url": "https://example.com/a.png",
}


def _fake_get_json(email="me@example.com", login="octocat"):
    """Stand in for every GitHub API call the backend makes."""
    def _inner(self, url, *args, **kwargs):
        url = str(url)
        if "access_token" in url:
            return {"access_token": "gho_testtoken", "token_type": "bearer", "scope": "user:email"}
        if "user/emails" in url:
            return [{"email": email, "primary": True, "verified": True}]
        if url.rstrip("/").endswith("/user"):
            payload = dict(GITHUB_USER)
            payload["email"] = email
            payload["login"] = login
            return payload
        return {}
    return _inner


@pytest.fixture
def github_api(monkeypatch, settings):
    """Configured GitHub backend + stubbed transport. Yields a setter for identity."""
    monkeypatch.setattr(
        "social_core.backends.oauth.BaseOAuth2.get_json",
        _fake_get_json(),
    )
    settings.SOCIAL_AUTH_GITHUB_KEY = "test-client-id"
    settings.SOCIAL_AUTH_GITHUB_SECRET = "test-client-secret"
    settings.AUTHENTICATION_BACKENDS = (
        "social_core.backends.github.GithubOAuth2",
        "django.contrib.auth.backends.ModelBackend",
    )
    settings.SOCIAL_AUTH_LOGIN_ERROR_URL = "/login/"

    def _as(email, login):
        monkeypatch.setattr(
            "social_core.backends.oauth.BaseOAuth2.get_json",
            _fake_get_json(email=email, login=login),
        )
    return _as


def _complete_github(client):
    """Walk the real flow, as a browser would.

    social-auth-app-django 6.x marks the begin view @require_POST, so the
    button is a form. The provider then redirects back to /complete/ with a
    `code` plus the `state` we must echo back -- social-auth validates it as
    CSRF protection, so the real value is read out of the 302 rather than
    invented.
    """
    from urllib.parse import parse_qs, urlparse

    start = client.post("/oauth/login/github/")
    assert start.status_code == 302, f"begin should redirect, got {start.status_code}"
    state = parse_qs(urlparse(start["Location"]).query).get("state", [""])[0]
    assert state, "begin must set an OAuth state parameter"
    return client.get(f"/oauth/complete/github/?process=oauth&code=fake-code&state={state}")


def test_approved_login_creates_user_and_session(github_api, monkeypatch, client):
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "me@example.com")
    _complete_github(client)

    user = User.objects.get(email="me@example.com")
    # stable_username pins the email localpart, not the mutable GitHub login.
    assert user.username == "me"
    assert client.session.get("_auth_user_id")


def test_unapproved_login_creates_no_user(github_api, monkeypatch, client):
    """The core security property: a refused sign-in leaves no account behind."""
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "someone-else@example.com")
    github_api(email="stranger@evil.net", login="stranger")

    resp = _complete_github(client)

    assert not User.objects.filter(email="stranger@evil.net").exists()
    assert not client.session.get("_auth_user_id")
    # Not "< 500": a 404 satisfies that, and so does a *successful* fail-open
    # login (302 -> "/"). The real guarantee is that the refusal is redirected
    # to the login page, which is where the user is told why.
    assert resp.status_code == 302
    assert resp["Location"] == "/login/"


def test_missing_email_is_refused(github_api, monkeypatch, client):
    """No verified email -> nothing to allowlist against -> refuse."""
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_DOMAINS", "example.com")
    github_api(email="", login="noemail")
    _complete_github(client)
    assert not client.session.get("_auth_user_id")


def test_domain_allowlist_admits_org_user(github_api, monkeypatch, client):
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_DOMAINS", "example.com")
    github_api(email="anyone@example.com", login="anyone")
    _complete_github(client)
    assert User.objects.filter(email="anyone@example.com").exists()


def test_lookalike_domain_is_refused(github_api, monkeypatch, client):
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_DOMAINS", "example.com")
    github_api(email="attacker@example.com.evil.net", login="attacker")
    _complete_github(client)
    assert not User.objects.filter(email="attacker@example.com.evil.net").exists()


def test_session_user_maps_to_user_principal(github_api, monkeypatch, client):
    """swarm.auth must resolve an OAuth session to the user:<username> principal."""
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "me@example.com")
    _complete_github(client)
    assert client.session.get("_auth_user_id")

    class _Req:
        pass

    req = _Req()
    req.user = User.objects.get(email="me@example.com")
    req.auth = None
    principal = request_principal(req)
    assert principal is not None
    assert principal.startswith("user:")


def test_env_credentials_reach_the_authorize_url(settings, monkeypatch):
    """The client id must reach the real provider authorize redirect.

    Guards the whole credential path end to end: settings -> social-core ->
    begin view -> provider URL. This is the step that was broken; without it
    the "set two secrets" instructions were a dead end.
    """
    from django.test import Client

    settings.SOCIAL_AUTH_GITHUB_KEY = "env_key_123"
    settings.SOCIAL_AUTH_GITHUB_SECRET = "env_secret_456"
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "me@example.com")

    resp = Client().post("/oauth/login/github/")
    assert resp.status_code == 302
    assert "client_id=env_key_123" in resp["Location"]

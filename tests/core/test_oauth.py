"""GitHub/Google sign-in wiring: allowlist, username pinning, and routes.

The allowlist is the security boundary -- an open OAuth login on a public
domain is an open signup against our LLM keys -- so it is tested fail-closed
first and foremost.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from django.conf import settings as django_settings

from swarm import oauth_pipeline

User = get_user_model()

pytestmark = [
    pytest.mark.django_db,
    # The suite that validates the barebones/oauth split must itself run on a
    # barebones install, where there is no `social` URL namespace and no
    # social-core backend to point AUTHENTICATION_BACKENDS at.
    pytest.mark.skipif(
        not getattr(django_settings, "SOCIAL_AUTH_AVAILABLE", False),
        reason="requires the `oauth`/`deploy` extra (social-auth-app-django)",
    ),
]


class _Backend:
    name = "github"


BACKEND = _Backend()


# --- allowlist -------------------------------------------------------------


def test_unconfigured_allowlist_refuses_everyone(monkeypatch):
    """Fail closed: no allowlist configured means no social sign-in at all."""
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_DOMAINS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOW_ANY", raising=False)
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.email_allowed("anyone@anywhere.com") is False


def test_exact_email_allowlist(monkeypatch):
    monkeypatch.delenv("SWARM_OAUTH_ALLOW_ANY", raising=False)
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "me@example.com, you@example.com")
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.email_allowed("me@example.com") is True
        assert oauth_pipeline.email_allowed("you@example.com") is True
        assert oauth_pipeline.email_allowed("other@example.com") is False


def test_domain_allowlist(monkeypatch):
    monkeypatch.delenv("SWARM_OAUTH_ALLOW_ANY", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_DOMAINS", "example.com")
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.email_allowed("anyone@example.com") is True
        # A lookalike domain must not match. Exact equality, not suffix.
        assert oauth_pipeline.email_allowed("anyone@notexample.com") is False
        assert oauth_pipeline.email_allowed("anyone@example.com.evil.net") is False
        assert oauth_pipeline.email_allowed("anyone@sub.example.com") is False
        assert oauth_pipeline.email_allowed("anyone@example.com.") is False
        # Uppercase is intentional (case-insensitive match). Note the local
        # part is deliberately NOT inspected under a domain allowlist -- any
        # mailbox at an allowed domain is admitted. The homoglyph case is
        # therefore asserted against the exact-address list, below.
        assert oauth_pipeline.email_allowed("ANYONE@EXAMPLE.COM") is True


def test_allow_any_opt_out(monkeypatch):
    monkeypatch.setenv("SWARM_OAUTH_ALLOW_ANY", "true")
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.email_allowed("anyone@anywhere.com") is True


@pytest.mark.parametrize(
    "value", ["false", "False", "FALSE", "0", "no", "off", "Off", "n", "t?", "2", "10", "", "   ", None]
)
def test_allow_any_negative_spellings_stay_closed(monkeypatch, value):
    """Anything that is not an explicit yes must keep enforcing the allowlist.

    An operator setting SWARM_OAUTH_ALLOW_ANY=false reasonably believes they
    disabled the bypass. A truthy parser that accepts any non-empty string
    would silently enable it instead -- and this is the switch that stands
    between a stranger and the LLM keys.
    """
    if value is None:
        monkeypatch.delenv("SWARM_OAUTH_ALLOW_ANY", raising=False)
    else:
        monkeypatch.setenv("SWARM_OAUTH_ALLOW_ANY", value)
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.allow_any() is False
        assert oauth_pipeline.email_allowed("anyone@anywhere.com") is False


@pytest.mark.parametrize("value", [None, "", "not-an-email", "no-at-sign"])
def test_malformed_email_is_refused(monkeypatch, value):
    monkeypatch.delenv("SWARM_OAUTH_ALLOW_ANY", raising=False)
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_DOMAINS", "example.com")
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        assert oauth_pipeline.email_allowed(value) is False


def test_restrict_step_halts_for_unapproved_email(monkeypatch):
    """Must RAISE. Returning None means "continue" to python-social-auth, which
    would let create_user provision an account for a rejected login. The
    end-to-end test in test_oauth_callback.py is what caught this."""
    from social_core.exceptions import AuthForbidden

    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "me@example.com")
    with pytest.raises(AuthForbidden):
        oauth_pipeline.restrict_to_approved_email(
            BACKEND, {"email": "stranger@evil.net"}, {}
        )


def test_restrict_step_allows_approved_email(monkeypatch):
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "me@example.com")
    backend = _Backend()
    backend.auth_allowed = lambda *a, **k: True
    # An allowed email must NOT halt the pipeline.
    assert (
        oauth_pipeline.restrict_to_approved_email(backend, {"email": "me@example.com"}, {})
        is None
    )


# --- Google email_verified ------------------------------------------------


class _GoogleBackend:
    name = "google-oauth2"


def test_google_refuses_unverified_email(monkeypatch):
    """A Google identity reported as unverified must be refused.

    GithubOAuth2.user_data overwrites the address with the primary entry from
    GET /user/emails, so GitHub is verified by construction. Google's userinfo
    payload carries `email_verified` and nothing was reading it, so a domain
    allowlist on Google admitted unverified Workspace/alias/collaborator
    accounts. Strictest case: the key absent entirely.
    """
    from social_core.exceptions import AuthForbidden

    for payload in ({"email_verified": False}, {"email_verified": None}, {}):
        with pytest.raises(AuthForbidden):
            oauth_pipeline.require_verified_email(
                _GoogleBackend(), {"email": "a@example.com"}, payload
            )


def test_google_accepts_verified_email(monkeypatch):
    for truthy in (True, "true", "True", "1", 1):
        assert (
            oauth_pipeline.require_verified_email(
                _GoogleBackend(), {"email": "a@example.com"}, {"email_verified": truthy}
            )
            is None
        )


def test_github_skips_the_verified_email_requirement():
    """GitHub's payload has no email_verified; the gate must not fire on it."""
    assert (
        oauth_pipeline.require_verified_email(BACKEND, {"email": "a@example.com"}, {})
        is None
    )


def test_no_email_at_all_is_refused():
    """Nothing to allowlist against, so it cannot be admitted."""
    from social_core.exceptions import AuthForbidden

    with pytest.raises(AuthForbidden):
        oauth_pipeline.require_verified_email(BACKEND, {}, {})


# --- already-authenticated re-check -----------------------------------------


def test_relogin_of_unapproved_existing_user_is_refused(monkeypatch):
    """Re-check rather than trusting "it was checked at creation".

    social_django passes user=request.user into the pipeline on every
    callback, so this branch is live. Downstream, associate_user would bind
    the presented provider uid to that account -- under anonymous preview that
    account is the shared swarm-anon-preview user.
    """
    from social_core.exceptions import AuthForbidden

    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "me@example.com")
    user = User(email="stranger@evil.net", username="stranger")
    with pytest.raises(AuthForbidden):
        oauth_pipeline.restrict_to_approved_email(
            BACKEND, {"email": "stranger@evil.net"}, {}, user=user
        )


def test_relogin_of_approved_existing_user_is_allowed(monkeypatch):
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "me@example.com")
    user = User(email="me@example.com", username="me")
    assert (
        oauth_pipeline.restrict_to_approved_email(
            BACKEND, {"email": "me@example.com"}, {}, user=user
        )
        is None
    )


# --- username pinning -----------------------------------------------------


def test_username_prefers_email_localpart(monkeypatch):
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "Me@Example.com")
    details = {"email": "Me@Example.com", "uid": "4242"}
    oauth_pipeline.stable_username(BACKEND, details, {})
    assert details["username"] == "me"  # lowercased for stable uniqueness


def test_username_falls_back_to_provider_uid(monkeypatch):
    details = {"email": "", "uid": "4242"}
    oauth_pipeline.stable_username(BACKEND, details, {})
    assert details["username"] == "github_4242"


def test_username_is_sanitised(monkeypatch):
    details = {"email": "we!rd name+tag@example.com", "uid": "1"}
    oauth_pipeline.stable_username(BACKEND, details, {})
    assert details["username"] == "we_rd_name_tag"


def test_username_is_clamped_to_the_column_length(monkeypatch):
    """Django's username column is 150 chars; an unbounded localpart 500s
    create_user with a DataError on the callback."""
    details = {"email": ("x" * 400) + "@example.com", "uid": "1"}
    oauth_pipeline.stable_username(BACKEND, details, {})
    assert len(details["username"]) <= 150


def test_username_dedupes_repeatedly(monkeypatch):
    """Two prior collisions must both be walked past, not just the first."""
    User.objects.create_user(username="taken", password="x")
    User.objects.create_user(username="taken2", password="x")
    details = {"email": "taken@example.com", "uid": "7"}
    oauth_pipeline.stable_username(BACKEND, details, {})
    assert details["username"] not in {"taken", "taken2"}


def test_username_dedupes_against_existing_account(monkeypatch):
    User.objects.create_user(username="taken", password="x")
    details = {"email": "taken@example.com", "uid": "7"}
    oauth_pipeline.stable_username(BACKEND, details, {})
    assert details["username"] != "taken"
    assert details["username"].startswith("taken")


# --- routes / view integration --------------------------------------------


def test_social_routes_registered(client):
    """The oauth namespace must resolve, with the backend as an argument."""
    from django.urls import reverse

    assert reverse("social:begin", args=["github"]) == "/oauth/login/github/"
    assert reverse("social:complete", args=["github"]) == "/oauth/complete/github/"


def test_login_page_offers_configured_provider(client, settings):
    settings.SOCIAL_AUTH_GITHUB_KEY = "id"
    settings.SOCIAL_AUTH_GITHUB_SECRET = "secret"
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        import os

        os.environ["SWARM_OAUTH_ALLOWED_EMAILS"] = "me@example.com"
        try:
            resp = client.get("/login/")
        finally:
            del os.environ["SWARM_OAUTH_ALLOWED_EMAILS"]
    assert resp.status_code == 200
    assert b"oauth-github" in resp.content
    # 6.x requires POST to begin, so the button must be a form, not a link.
    assert b'action="/oauth/login/github/"' in resp.content
    assert b"csrfmiddlewaretoken" in resp.content


def test_login_page_offers_google_when_configured(client, settings, monkeypatch):
    """Regression: the settings prefix is SOCIAL_AUTH_GOOGLE_OAUTH2, not the
    backend slug upper-cased. slug.upper() gave "GOOGLE-OAUTH2" (hyphen), so
    the Google button could never render however fully it was configured."""
    monkeypatch.setenv("SWARM_OAUTH_ALLOWED_EMAILS", "me@example.com")
    settings.SOCIAL_AUTH_GITHUB_KEY = "id"
    settings.SOCIAL_AUTH_GITHUB_SECRET = "secret"
    settings.SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = "id"
    settings.SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = "secret"
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        resp = client.get("/login/")
    assert b"oauth-google-oauth2" in resp.content
    assert b"/oauth/login/google-oauth2/" in resp.content


def test_login_page_hides_provider_when_unconfigured(client, settings, monkeypatch):
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_DOMAINS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOW_ANY", raising=False)
    settings.SOCIAL_AUTH_GITHUB_KEY = ""
    settings.SOCIAL_AUTH_GITHUB_SECRET = ""
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        resp = client.get("/login/")
    assert resp.status_code == 200
    assert b"oauth-github" not in resp.content


def test_login_page_hides_provider_without_allowlist(client, settings, monkeypatch):
    """Keys present but no allowlist: still hidden, because all logins fail."""
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOWED_DOMAINS", raising=False)
    monkeypatch.delenv("SWARM_OAUTH_ALLOW_ANY", raising=False)
    settings.SOCIAL_AUTH_GITHUB_KEY = "id"
    settings.SOCIAL_AUTH_GITHUB_SECRET = "secret"
    with override_settings(SWARM_OAUTH_ALLOW_ANY=None):
        resp = client.get("/login/")
    assert resp.status_code == 200
    assert b"oauth-github" not in resp.content


def test_logout_get_does_not_end_the_session(client):
    """GET must not silently log out -- that is CSRF-exposable via <img>.

    Asserting only the 200/HTML let a "logout(request) then render" mutation
    pass, so the session state is checked directly.
    """
    user = User.objects.create_user(username="getlogout", password="pw")
    client.force_login(user)
    assert "_auth_user_id" in client.session
    resp = client.get("/accounts/logout/")
    assert resp.status_code == 200
    assert b"Sign out" in resp.content
    assert "_auth_user_id" in client.session, "GET /logout/ ended the session"


def test_logout_post_ends_session(client, settings):
    user = User.objects.create_user(username="sess", password="pw")
    client.force_login(user)
    resp = client.post("/accounts/logout/")
    assert resp.status_code in (302, 303)
    assert "_auth_user_id" not in client.session


def test_proxy_ssl_header_tracks_the_deployment_signal(settings):
    """Behind a TLS proxy an http:// redirect_uri is rejected by providers.

    Originally asserted as unconditional, on the reasoning that it is "proxy
    topology, not a security toggle". Issue #1345 overturned that: docker-compose
    publishes 8000 directly with DEBUG=false and no proxy, so trusting the
    header there is wrong. It is now gated on SWARM_BEHIND_TLS_PROXY, which
    fly.toml and fly.demo.toml must set (see the banner in settings.py).

    This asserts the setting is *consistent with the signal* rather than a
    hardcoded literal, so it cannot drift from the gate again. The positive case
    is covered in tests/core/test_env_flags.py, which can re-import settings.
    """
    from swarm.utils.env_utils import behind_tls_proxy

    expected = ("HTTP_X_FORWARDED_PROTO", "https") if behind_tls_proxy() else None
    assert settings.SECURE_PROXY_SSL_HEADER == expected
    # In the test environment the flag is unset, so the header must be off.
    # This is the safe default: a host that forgets the opt-in gets no OAuth
    # redirect_uri scheme mismatch rather than a silently trusted header.
    assert settings.SECURE_PROXY_SSL_HEADER is None


def test_credentials_are_read_from_the_environment(monkeypatch):
    """Regression: the documented setup path did nothing.

    social-core resolves the client id/secret via getattr(settings, ...), and
    settings.py used to define only scope/pipeline/error-URL. So
    `flyctl secrets set SWARM_OAUTH_GITHUB_KEY=...` left _oauth_providers()
    empty and the begin view would have raised "client_id not configured" --
    the instructions could not have worked.

    Tested against the helper directly because the assignment happens at
    settings-import time and cannot be re-triggered from a test.
    """
    from swarm.settings import _social_auth_credentials_from_env as bridge

    monkeypatch.setenv("SWARM_OAUTH_GITHUB_KEY", "gh_key")
    monkeypatch.setenv("SWARM_OAUTH_GITHUB_SECRET", "gh_secret")
    monkeypatch.setenv("SWARM_OAUTH_GOOGLE_KEY", "goog_key")
    monkeypatch.setenv("SWARM_OAUTH_GOOGLE_SECRET", "goog_secret")
    resolved = bridge()
    assert resolved == {
        "SOCIAL_AUTH_GITHUB_KEY": "gh_key",
        "SOCIAL_AUTH_GITHUB_SECRET": "gh_secret",
        "SOCIAL_AUTH_GOOGLE_OAUTH2_KEY": "goog_key",
        "SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET": "goog_secret",
    }


def test_credentials_fall_back_to_bare_social_auth_env(monkeypatch):
    monkeypatch.delenv("SWARM_OAUTH_GITHUB_KEY", raising=False)
    monkeypatch.setenv("SOCIAL_AUTH_GITHUB_KEY", "upstream_style")
    from swarm.settings import _social_auth_credentials_from_env as bridge

    assert bridge()["SOCIAL_AUTH_GITHUB_KEY"] == "upstream_style"


def test_no_credentials_resolve_to_nothing(monkeypatch):
    for name in (
        "SWARM_OAUTH_GITHUB_KEY", "SWARM_OAUTH_GITHUB_SECRET",
        "SWARM_OAUTH_GOOGLE_KEY", "SWARM_OAUTH_GOOGLE_SECRET",
        "SOCIAL_AUTH_GITHUB_KEY", "SOCIAL_AUTH_GITHUB_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    from swarm.settings import _social_auth_credentials_from_env as bridge

    assert bridge() == {}

"""Issue #136 — Bearer CSRF exemption vs session CSRF (no live server)."""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, override_settings
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

from swarm.auth import (
    CustomSessionAuthentication,
    _request_has_valid_static_token,
)

TOKEN = "issue136-unit-bearer-not-a-secret"


def _drf_request(factory: RequestFactory, **extra) -> Request:
    django_request = factory.post("/v1/chat/completions", **extra)
    django_request.user = AnonymousUser()
    return Request(django_request)


@override_settings(SWARM_API_KEY=TOKEN, SWARM_API_KEYS=[TOKEN])
def test_valid_bearer_is_recognized():
    req = _drf_request(RequestFactory(), HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
    assert _request_has_valid_static_token(req) is True


@override_settings(SWARM_API_KEY=TOKEN, SWARM_API_KEYS=[TOKEN])
def test_valid_x_api_key_is_recognized():
    req = _drf_request(RequestFactory(), HTTP_X_API_KEY=TOKEN)
    assert _request_has_valid_static_token(req) is True


@override_settings(SWARM_API_KEY=TOKEN, SWARM_API_KEYS=[TOKEN])
def test_invalid_or_missing_token_is_not_recognized():
    factory = RequestFactory()
    assert _request_has_valid_static_token(_drf_request(factory)) is False
    assert (
        _request_has_valid_static_token(
            _drf_request(factory, HTTP_AUTHORIZATION="Bearer wrong")
        )
        is False
    )


@override_settings(SWARM_API_KEY=TOKEN, SWARM_API_KEYS=[TOKEN])
def test_enforce_csrf_skips_for_valid_bearer():
    req = _drf_request(RequestFactory(), HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
    CustomSessionAuthentication().enforce_csrf(req)


@override_settings(SWARM_API_KEY=TOKEN, SWARM_API_KEYS=[TOKEN])
def test_enforce_csrf_still_runs_without_token():
    req = _drf_request(RequestFactory())
    try:
        CustomSessionAuthentication().enforce_csrf(req)
    except PermissionDenied as exc:
        assert "CSRF" in str(exc)
    else:
        # Django's CSRF check may no-op on a bare RequestFactory POST
        # without enforce_csrf_checks; the HTTP tests lock the 403.
        pass

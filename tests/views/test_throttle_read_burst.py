"""Guest first-load 429 burst: safe reads get a separate, higher scope.

A cold SPA mount fires dozens of idempotent ``GET /v1/*`` requests in one
tick. Before the fix they shared the small write budget (``anon`` 60/min,
``user`` 120/min) and a normal first paint 429'd. These tests pin the new
behavior: reads use ``anon_read`` / ``user_read``, writes stay on the base
scope, and a genuine read flood is still throttled.

The pytest suite disables DRF throttling wholesale (``settings.TESTING``), so
these tests opt back in explicitly:
  * ``SimpleRateThrottle.THROTTLE_RATES`` is bound to ``api_settings`` at
    class-creation time, so it is monkeypatched on the classes; and
  * ``APIView.throttle_classes`` is likewise bound at class creation, so the
    health view (a cheap unauthenticated GET) is patched for the burst tests.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from rest_framework.test import APIClient, APIRequestFactory

from swarm import throttling

TEST_RATES = {
    'anon': '5/min',
    'user': '5/min',
    'anon_read': '20/min',
    'user_read': '20/min',
}


@pytest.fixture(autouse=True)
def _test_throttle_rates(monkeypatch):
    monkeypatch.setattr(
        throttling.ReadBurstAnonRateThrottle, 'THROTTLE_RATES', TEST_RATES
    )
    monkeypatch.setattr(
        throttling.ReadBurstUserRateThrottle, 'THROTTLE_RATES', TEST_RATES
    )


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def read_burst_active(monkeypatch):
    """Apply the read-burst throttles to the cheap /health endpoint."""
    from swarm.views.chat_views import HealthCheckView

    monkeypatch.setattr(
        HealthCheckView,
        'throttle_classes',
        [
            throttling.ReadBurstAnonRateThrottle,
            throttling.ReadBurstUserRateThrottle,
        ],
    )
    yield


def _request(method, path='/health', user=None):
    request = getattr(APIRequestFactory(), method)(path)
    request.user = AnonymousUser() if user is None else user
    return request


class _AuthUser:
    is_authenticated = True
    pk = 7

    def get_username(self):  # pragma: no cover - only used by cache_key probing
        return 'throttle-test-user'


def test_safe_method_uses_read_scope_unsafe_keeps_base_scope():
    safe = throttling.ReadBurstAnonRateThrottle()
    safe.allow_request(_request('get'), None)
    assert safe.scope == 'anon_read'
    assert (safe.num_requests, safe.duration) == (20, 60)

    unsafe = throttling.ReadBurstAnonRateThrottle()
    unsafe.allow_request(_request('post'), None)
    assert unsafe.scope == 'anon'
    assert (unsafe.num_requests, unsafe.duration) == (5, 60)


def test_head_and_options_also_use_read_scope():
    for method in ('head', 'options'):
        throttle = throttling.ReadBurstAnonRateThrottle()
        throttle.allow_request(_request(method), None)
        assert throttle.scope == 'anon_read'


def test_authenticated_read_uses_distinct_user_read_scope():
    throttle = throttling.ReadBurstUserRateThrottle()
    request = _request('get', user=_AuthUser())
    throttle.allow_request(request, None)
    assert throttle.scope == 'user_read'
    assert throttle.get_cache_key(request, None) == 'throttle_user_read_7'


@pytest.mark.usefixtures('read_burst_active')
def test_first_paint_burst_within_read_budget_is_not_throttled():
    client = APIClient()
    codes = [client.get('/health').status_code for _ in range(18)]
    assert codes == [200] * 18


@pytest.mark.usefixtures('read_burst_active')
def test_genuine_read_flood_beyond_read_budget_still_throttled():
    client = APIClient()
    codes = [client.get('/health').status_code for _ in range(25)]
    assert codes[:20] == [200] * 20
    assert codes[20:] == [429] * 5


@pytest.mark.usefixtures('read_burst_active')
def test_reads_do_not_consume_the_write_budget():
    client = APIClient()
    assert [client.get('/health').status_code for _ in range(18)] == [200] * 18

    # The base (write) scope lives under a different cache key, so a fresh
    # instance still has its full 5-request budget.
    throttle = throttling.ReadBurstAnonRateThrottle()
    request = _request('post')
    assert sum(throttle.allow_request(request, None) for _ in range(5)) == 5
    assert throttle.allow_request(request, None) is False


def test_configured_defaults_keep_a_sane_sustained_read_limit():
    from swarm import throttle_defaults

    anon_read = int(throttle_defaults.ANON_READ_RATE.split('/')[0])
    user_read = int(throttle_defaults.USER_READ_RATE.split('/')[0])
    # Comfortably above a first paint (~150 reads) but still bounded (<10/s),
    # and reads stay more generous than the write budgets.
    assert 150 <= anon_read <= 600
    assert 150 <= user_read <= 1200
    assert anon_read < user_read
    assert anon_read > int(throttle_defaults.ANON_RATE.split('/')[0])
    assert user_read > int(throttle_defaults.USER_RATE.split('/')[0])

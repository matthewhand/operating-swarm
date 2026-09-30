"""#1336 — the password sign-in form: cache directives + failed-login throttle.

`custom_login` is a plain Django function view, so DRF's `AnonRateThrottle`
never saw it. These tests pin the three properties the fix has to hold:

- the login/logout responses are not cacheable by an intermediary (an
  `/accounts/login/?next=...` page must not be replayed to the next visitor);
- a burst of failed password attempts from one caller is throttled, per
  (IP, username) and per IP, while a *different* username on the same IP is
  not collateral damage;
- every failure mode of the throttle itself fails OPEN, and the store it
  keeps is bounded.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.contrib.auth.models import User

from swarm.views import web_views
from swarm.views.web_views import (
    _DEFAULT_LOGIN_THROTTLE_MAX_ATTEMPTS,
    _DEFAULT_LOGIN_THROTTLE_MAX_IP_ATTEMPTS,
    _DEFAULT_LOGIN_THROTTLE_MAX_KEYS,
    _DEFAULT_LOGIN_THROTTLE_WINDOW_SECONDS,
    LOGIN_THROTTLE_ENABLED_ENV,
    LOGIN_THROTTLE_MAX_ATTEMPTS_ENV,
    LOGIN_THROTTLE_MAX_IP_ATTEMPTS_ENV,
    LOGIN_THROTTLE_MAX_KEYS_ENV,
    LOGIN_THROTTLE_TRUST_FORWARDED_ENV,
    LOGIN_THROTTLE_WINDOW_ENV,
    LoginFailureThrottle,
    _login_ip_key,
    _login_user_key,
    login_throttle_config,
    login_throttle_store,
)

# Nothing here may depend on ambient env (#1335): every knob is set explicitly.
THROTTLE_ENVS = (
    LOGIN_THROTTLE_ENABLED_ENV,
    LOGIN_THROTTLE_MAX_ATTEMPTS_ENV,
    LOGIN_THROTTLE_MAX_IP_ATTEMPTS_ENV,
    LOGIN_THROTTLE_WINDOW_ENV,
    LOGIN_THROTTLE_MAX_KEYS_ENV,
    LOGIN_THROTTLE_TRUST_FORWARDED_ENV,
)


@pytest.fixture(autouse=True)
def isolated_login_throttle(monkeypatch):
    """Clear the env knobs and the process-wide store around every test.

    The store is a module global (by design -- in-process, like
    `request_telemetry`), so without this a burst in one test would throttle a
    later one.
    """
    for name in THROTTLE_ENVS:
        monkeypatch.delenv(name, raising=False)
    web_views.reset_login_throttle()
    yield
    web_views.reset_login_throttle()


@pytest.fixture
def user_budget(monkeypatch):
    """Low per-username budget, effectively infinite per-IP budget.

    Isolates the per-username dimension: a 429 in these tests can only come
    from the username budget, never from the IP one.
    """
    monkeypatch.setenv(LOGIN_THROTTLE_MAX_ATTEMPTS_ENV, "3")
    monkeypatch.setenv(LOGIN_THROTTLE_MAX_IP_ATTEMPTS_ENV, "10000")
    monkeypatch.setenv(LOGIN_THROTTLE_WINDOW_ENV, "900")


@pytest.fixture
def ip_budget(monkeypatch):
    """Low per-IP budget, effectively infinite per-username budget."""
    monkeypatch.setenv(LOGIN_THROTTLE_MAX_ATTEMPTS_ENV, "10000")
    monkeypatch.setenv(LOGIN_THROTTLE_MAX_IP_ATTEMPTS_ENV, "3")
    monkeypatch.setenv(LOGIN_THROTTLE_WINDOW_ENV, "900")


class _FastTestHasher(PBKDF2PasswordHasher):
    """PBKDF2 with a tiny iteration count -- test-only speed-up.

    The stock hasher costs ~1s per verification, so a burst-of-failures test
    would take minutes. Never referenced outside this test module.
    """

    iterations = 1000


_FAST_HASHER_PATH = f"{__name__}._FastTestHasher"


@pytest.fixture
def operator(db, settings):
    settings.PASSWORD_HASHERS = [_FAST_HASHER_PATH]
    return User.objects.create_user(username="operator", password="correct-horse-battery")


def _post(client, username="operator", password="wrong", url="/login/", **extra):
    return client.post(url, {"username": username, "password": password}, **extra)


# ---------------------------------------------------------------------------
# cache directives
# ---------------------------------------------------------------------------


class TestCacheDirectives:
    @pytest.mark.django_db
    @pytest.mark.parametrize("url", ["/login/", "/accounts/login/"])
    def test_login_page_is_not_cacheable(self, client, url):
        response = client.get(url)
        assert response.status_code == 200
        assert "no-store" in response["Cache-Control"]
        assert "no-cache" in response["Cache-Control"]
        # Django's own LoginView does not send this for an anonymous GET, so
        # it is easy to lose; an intermediary keyed on Vary would otherwise
        # replay one visitor's page to the next.
        assert "Cookie" in response.get("Vary", "")

    @pytest.mark.django_db
    def test_login_page_with_next_is_not_cacheable(self, client):
        """The exact case from #1336: a cached `?next=` body reflects a
        previous visitor's next."""
        response = client.get("/accounts/login/?next=/teams/")
        assert response.status_code == 200
        assert "no-store" in response["Cache-Control"]
        assert "Cookie" in response.get("Vary", "")

    @pytest.mark.django_db
    def test_failed_login_response_is_not_cacheable(self, client):
        response = _post(client, username="nosuch")
        assert response.status_code == 200
        assert "no-store" in response["Cache-Control"]
        assert "Cookie" in response.get("Vary", "")

    @pytest.mark.django_db
    def test_login_redirect_is_not_cacheable(self, client, operator):
        response = _post(client, password="correct-horse-battery")
        assert response.status_code == 302
        assert "no-store" in response["Cache-Control"]
        assert "Cookie" in response.get("Vary", "")

    @pytest.mark.django_db
    def test_logout_confirm_page_is_not_cacheable(self, client):
        response = client.get("/accounts/logout/")
        assert response.status_code == 200
        assert "no-store" in response["Cache-Control"]
        assert "Cookie" in response.get("Vary", "")

    @pytest.mark.django_db
    def test_logout_redirect_is_not_cacheable(self, client, operator):
        client.force_login(operator)
        response = client.post("/accounts/logout/")
        assert response.status_code in (302, 303)
        assert "no-store" in response["Cache-Control"]
        assert "Cookie" in response.get("Vary", "")


# ---------------------------------------------------------------------------
# throttling
# ---------------------------------------------------------------------------


class TestFailedLoginThrottle:
    @pytest.mark.django_db
    def test_burst_of_failures_from_one_username_is_throttled(self, client, user_budget):
        for _ in range(3):
            response = _post(client)
            assert response.status_code == 200
            assert "Invalid username or password." in response.content.decode()

        throttled = _post(client)
        assert throttled.status_code == 429
        assert throttled["Retry-After"]

    @pytest.mark.django_db
    def test_throttled_response_does_not_enumerate(self, client, user_budget):
        for _ in range(3):
            _post(client, username="does-not-exist")
        throttled = _post(client, username="does-not-exist")
        body = throttled.content.decode()
        # Identical generic body to an ordinary failure: nothing here tells an
        # attacker whether the account exists.
        assert "Invalid username or password." in body
        assert "does-not-exist" not in body
        assert "no such user" not in body.lower()

    @pytest.mark.django_db
    def test_throttle_also_covers_the_accounts_alias(self, client, user_budget):
        for _ in range(3):
            _post(client, url="/accounts/login/")
        assert _post(client, url="/accounts/login/").status_code == 429

    @pytest.mark.django_db
    def test_per_ip_budget_blocks_username_spraying(self, client, ip_budget):
        """Distinct usernames, one IP: the per-user budget never trips, so it
        is the per-IP budget that has to stop the spray."""
        for index in range(3):
            response = _post(client, username=f"sprayed-{index}")
            assert response.status_code == 200
        assert _post(client, username="sprayed-3").status_code == 429

    @pytest.mark.django_db
    def test_other_username_on_same_ip_is_not_throttled(
        self, client, operator, user_budget
    ):
        """Per-username bucketing exists so one attacker hammering a guessed
        account cannot lock the real operator out of the same NAT/proxy IP."""
        for _ in range(3):
            assert _post(client, username="attacker-target").status_code == 200

        response = _post(client, password="correct-horse-battery")
        assert response.status_code == 302
        assert "_auth_user_id" in client.session

    @pytest.mark.django_db
    def test_throttled_attempt_does_not_call_authenticate(self, client, user_budget):
        """A throttled caller must not be able to make the process burn a
        password hash per attempt."""
        for _ in range(3):
            _post(client)
        with patch("swarm.views.web_views.authenticate") as mock_auth:
            assert _post(client).status_code == 429
        assert not mock_auth.called

    @pytest.mark.django_db
    def test_successful_login_forgives_the_username_budget(self, client, operator, user_budget):
        for _ in range(2):
            _post(client)
        assert _post(client, password="correct-horse-battery").status_code == 302

        key = _login_user_key("127.0.0.1", "operator")
        assert login_throttle_store().failure_count(key, window=900) == 0
        # ...and the operator gets the full allowance again.
        for _ in range(3):
            assert _post(client).status_code == 200
        assert _post(client).status_code == 429

    @pytest.mark.django_db
    def test_username_spelling_variants_share_one_budget(self, client, user_budget):
        for spelling in ("Operator", "operator", "  operator  "):
            assert _post(client, username=spelling).status_code == 200
        assert _post(client, username="operator").status_code == 429

    @pytest.mark.django_db
    def test_off_switch_never_throttles(self, client, monkeypatch):
        monkeypatch.setenv(LOGIN_THROTTLE_ENABLED_ENV, "false")
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_ATTEMPTS_ENV, "1")
        for _ in range(6):
            assert _post(client, username="ghost").status_code == 200
        assert len(login_throttle_store()) == 0

    @pytest.mark.django_db
    def test_forged_forwarded_header_cannot_reset_the_budget(self, client, user_budget):
        """X-Forwarded-For is attacker-controlled, so it is ignored unless the
        operator says they are behind a trusted proxy."""
        for index in range(3):
            response = _post(client, HTTP_X_FORWARDED_FOR=f"203.0.113.{index}")
            assert response.status_code == 200
        response = _post(client, HTTP_X_FORWARDED_FOR="203.0.113.99")
        assert response.status_code == 429

    @pytest.mark.django_db
    def test_trusted_proxy_buckets_by_forwarded_client(self, client, ip_budget, monkeypatch):
        """Behind a TLS proxy every request shares one REMOTE_ADDR, so the
        opt-in bucket has to key off the forwarded client or one attacker
        locks out the whole deployment."""
        monkeypatch.setenv(LOGIN_THROTTLE_TRUST_FORWARDED_ENV, "true")
        for index in range(3):
            _post(client, username=f"sprayed-{index}", HTTP_X_FORWARDED_FOR="198.51.100.7")
        # A new username from the same real client: per-IP budget spent.
        throttled = _post(client, username="sprayed-3", HTTP_X_FORWARDED_FOR="198.51.100.7")
        assert throttled.status_code == 429
        # A different real client behind the same proxy is unaffected.
        assert (
            _post(client, username="sprayed-3", HTTP_X_FORWARDED_FOR="198.51.100.8").status_code
            == 200
        )

    @pytest.mark.django_db
    def test_get_is_never_throttled(self, client, user_budget):
        for _ in range(5):
            assert client.get("/login/").status_code == 200


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


class TestThrottleConfig:
    def test_defaults_are_enabled_and_documented(self):
        config = login_throttle_config()
        assert config.enabled is True
        assert config.max_attempts_per_user == _DEFAULT_LOGIN_THROTTLE_MAX_ATTEMPTS == 10
        assert config.max_attempts_per_ip == _DEFAULT_LOGIN_THROTTLE_MAX_IP_ATTEMPTS == 60
        assert config.window_seconds == _DEFAULT_LOGIN_THROTTLE_WINDOW_SECONDS == 900
        assert config.max_keys == _DEFAULT_LOGIN_THROTTLE_MAX_KEYS

    def test_env_overrides_every_knob(self, monkeypatch):
        monkeypatch.setenv(LOGIN_THROTTLE_ENABLED_ENV, "yes")
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_ATTEMPTS_ENV, "2")
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_IP_ATTEMPTS_ENV, "4")
        monkeypatch.setenv(LOGIN_THROTTLE_WINDOW_ENV, "60")
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_KEYS_ENV, "8")
        config = login_throttle_config()
        assert config == web_views._LoginThrottleConfig(
            enabled=True,
            window_seconds=60.0,
            max_attempts_per_user=2,
            max_attempts_per_ip=4,
            max_keys=8,
        )

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", "", "  "])
    def test_only_an_explicit_yes_enables_the_throttle(self, monkeypatch, value):
        monkeypatch.setenv(LOGIN_THROTTLE_ENABLED_ENV, value)
        assert login_throttle_config().enabled is False

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("nonsense", _DEFAULT_LOGIN_THROTTLE_MAX_ATTEMPTS), ("", _DEFAULT_LOGIN_THROTTLE_MAX_ATTEMPTS)],
    )
    def test_junk_limits_fall_back_to_the_default(self, monkeypatch, raw, expected):
        """A typo must not become "limit 0" (locks everyone out) or a crash."""
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_ATTEMPTS_ENV, raw)
        assert login_throttle_config().max_attempts_per_user == expected

    def test_zero_or_negative_limits_are_clamped(self, monkeypatch):
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_ATTEMPTS_ENV, "0")
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_IP_ATTEMPTS_ENV, "-5")
        monkeypatch.setenv(LOGIN_THROTTLE_WINDOW_ENV, "0")
        config = login_throttle_config()
        assert config.max_attempts_per_user == 1
        assert config.max_attempts_per_ip == 1
        assert config.window_seconds == 1.0


# ---------------------------------------------------------------------------
# fail-open
# ---------------------------------------------------------------------------


class _ExplodingStore:
    """Every method raises, standing in for a broken throttle backend."""

    def __init__(self, method: str) -> None:
        self.method = method

    def __getattr__(self, name):
        if name != self.method:
            return lambda *a, **k: 0

        def _boom(*_args, **_kwargs):
            raise RuntimeError("throttle backend is on fire")

        return _boom


class _SaturatedStore:
    """A store that says "blocked" and then fails to answer how long to wait."""

    def failure_count(self, *args, **kwargs):
        return 99

    def retry_after_seconds(self, *args, **kwargs):
        raise RuntimeError("cannot compute Retry-After")


class TestThrottleFailsOpen:
    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "broken_method", ["failure_count", "register_failure", "clear", "retry_after_seconds"]
    )
    def test_login_still_works_when_the_throttle_raises(
        self, client, operator, user_budget, monkeypatch, broken_method
    ):
        monkeypatch.setattr(
            web_views, "login_throttle_store", lambda: _ExplodingStore(broken_method)
        )

        # Enough failures to be past any sane limit...
        for _ in range(3):
            assert _post(client).status_code == 200
        # ...and the correct password still logs in. A throttle bug must never
        # be able to lock an operator out of the sign-in surface.
        response = _post(client, password="correct-horse-battery")
        assert response.status_code == 302
        assert "_auth_user_id" in client.session

    @pytest.mark.django_db
    def test_broken_backend_still_returns_a_429_not_a_500_when_it_throws(
        self, client, user_budget, monkeypatch
    ):
        """`retry_after_seconds` blowing up must not take the 429 down with it."""
        monkeypatch.setattr(web_views, "login_throttle_store", lambda: _SaturatedStore())
        response = _post(client)
        assert response.status_code == 429
        assert response["Retry-After"] == "60"
        assert "Invalid username or password." in response.content.decode()

    @pytest.mark.django_db
    def test_broken_config_reader_fails_open(self, client, operator, monkeypatch):
        monkeypatch.setattr(
            web_views, "login_throttle_config", lambda: (_ for _ in ()).throw(RuntimeError("nope"))
        )
        assert _post(client).status_code == 200
        assert _post(client, password="correct-horse-battery").status_code == 302


# ---------------------------------------------------------------------------
# memory bound
# ---------------------------------------------------------------------------


class TestStoreIsBounded:
    def test_store_never_exceeds_its_key_cap(self):
        store = LoginFailureThrottle()
        for index in range(5000):
            store.register_failure(f"u:{index}", window=900, max_keys=128, now=float(index))
        assert len(store) <= 128

    @pytest.mark.django_db
    def test_the_view_does_not_grow_the_store_past_the_cap(self, client, monkeypatch):
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_KEYS_ENV, "8")
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_ATTEMPTS_ENV, "10000")
        monkeypatch.setenv(LOGIN_THROTTLE_MAX_IP_ATTEMPTS_ENV, "10000")
        for index in range(24):
            response = _post(
                client,
                username="sprayed",
                REMOTE_ADDR=f"10.0.0.{index}",
            )
            assert response.status_code == 200
        assert len(login_throttle_store()) <= 8

    def test_default_cap_is_a_bounded_number(self):
        # The whole point of the cap: an attacker-controlled key space must not
        # be able to grow the dict without limit.
        assert 0 < _DEFAULT_LOGIN_THROTTLE_MAX_KEYS <= 8192

    def test_expired_keys_are_swept(self):
        store = LoginFailureThrottle()
        store.register_failure("u:a", window=60, max_keys=16, now=1000.0)
        store.register_failure("u:b", window=60, max_keys=16, now=1000.0)
        assert store.failure_count("u:a", window=60, now=1000.0) == 1
        # 61s later both failures have slid out of the 60s window, and reading
        # an empty key drops it rather than leaking a dead dict entry.
        assert store.failure_count("u:a", window=60, now=1061.0) == 0
        assert store.failure_count("u:b", window=60, now=1061.0) == 0
        assert len(store) == 0

    def test_capacity_pressure_prefers_evicting_expired_keys(self):
        store = LoginFailureThrottle()
        for index in range(4):
            store.register_failure(f"old:{index}", window=60, max_keys=4, now=1000.0)
        # Two minutes later the four stale keys are all expired; the new one
        # must not have to evict a live counter to make room.
        store.register_failure("u:new", window=60, max_keys=4, now=1120.0)
        assert "u:new" in store
        assert "old:0" not in store
        assert len(store) == 1

    def test_capacity_pressure_evicts_oldest_keys(self):
        store = LoginFailureThrottle()
        for index in range(4):
            store.register_failure(f"live:{index}", window=600, max_keys=4, now=1000.0 + index)
        store.register_failure("u:new", window=600, max_keys=4, now=1004.0)
        assert len(store) <= 4
        assert "u:new" in store
        assert "live:0" not in store

    def test_window_slides(self):
        store = LoginFailureThrottle()
        for index in range(3):
            store.register_failure("u:a", window=60, max_keys=16, now=1000.0 + index)
        assert store.failure_count("u:a", window=60, now=1030.0) == 3
        # 1061 - 60 == 1001, so only the 1001 and 1002 stamps are still inside.
        assert store.failure_count("u:a", window=60, now=1061.0) == 2
        assert store.failure_count("u:a", window=60, now=1062.0) == 1
        assert store.failure_count("u:a", window=60, now=1100.0) == 0

    def test_retry_after_counts_down(self):
        store = LoginFailureThrottle()
        store.register_failure("u:a", window=60, max_keys=16, now=1000.0)
        assert store.retry_after_seconds("u:a", window=60, now=1000.0) == 60
        assert store.retry_after_seconds("u:a", window=60, now=1030.0) == 30
        # Never zero/negative: a client told "retry now" would hammer.
        assert store.retry_after_seconds("u:a", window=60, now=9999.0) >= 1

    def test_reset_clears_everything(self):
        store = LoginFailureThrottle()
        store.register_failure("u:a", window=60, max_keys=16, now=1.0)
        store.reset()
        assert len(store) == 0
        assert store.failure_count("u:a", window=60, now=1.0) == 0

    def test_keys_are_digests_not_raw_credentials(self):
        key = _login_user_key("192.0.2.1", "operator")
        assert key.startswith("u:")
        assert "operator" not in key
        assert "192.0.2.1" not in key
        assert len(key) == 66  # fixed width, whatever the username length
        assert _login_user_key("192.0.2.1", "x" * 10_000) is not None
        assert _login_ip_key("192.0.2.1").startswith("i:")
        # The two key spaces cannot collide with each other.
        assert _login_user_key("192.0.2.1", "a") != _login_ip_key("192.0.2.1")


# ---------------------------------------------------------------------------
# logout method predicate
# ---------------------------------------------------------------------------


class TestLogoutMethodPredicate:
    @pytest.mark.django_db
    @pytest.mark.parametrize("method", ["put", "delete", "patch", "head"])
    def test_non_post_non_get_method_renders_instead_of_logging_out(self, client, operator, method):
        """The predicate is now "POST logs out", not "!= POST logs in to the
        logout branch" -- so a method with unsafe semantics cannot end a
        session by accident."""
        client.force_login(operator)
        assert "_auth_user_id" in client.session

        response = getattr(client, method)("/accounts/logout/")
        assert response.status_code == 200
        assert "_auth_user_id" in client.session, f"{method.upper()} ended the session"
        if method != "head":
            assert "Sign out" in response.content.decode()

    @pytest.mark.django_db
    def test_get_renders_the_confirm_form(self, client, operator):
        client.force_login(operator)
        response = client.get("/accounts/logout/")
        assert response.status_code == 200
        assert b"Sign out" in response.content
        assert "_auth_user_id" in client.session

    @pytest.mark.django_db
    def test_post_still_logs_out(self, client, operator):
        client.force_login(operator)
        response = client.post("/accounts/logout/")
        assert response.status_code in (302, 303)
        assert "_auth_user_id" not in client.session

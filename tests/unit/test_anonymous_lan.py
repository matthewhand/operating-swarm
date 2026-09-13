"""Dev-mode LAN/loopback auth-free preview (HTTP + websocket)."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory

from swarm.middleware import (
    AllowAnonymousPreviewMiddleware,
    is_lan_or_loopback,
    swarm_allow_anonymous,
)


def test_lan_and_loopback_ips():
    assert is_lan_or_loopback("127.0.0.1")
    assert is_lan_or_loopback("172.16.0.199")
    assert is_lan_or_loopback("172.16.1.4")
    assert is_lan_or_loopback("::1")
    assert not is_lan_or_loopback("8.8.8.8")
    assert not is_lan_or_loopback("not-an-ip")
    assert not is_lan_or_loopback(None)


def test_explicit_env_on_any_ip():
    with patch.dict("os.environ", {"SWARM_ALLOW_ANONYMOUS": "1"}):
        assert swarm_allow_anonymous("8.8.8.8", debug=False, testing=False) is True


def test_explicit_env_off_blocks_lan_debug():
    with patch.dict("os.environ", {"SWARM_ALLOW_ANONYMOUS": "0"}):
        assert swarm_allow_anonymous("172.16.0.5", debug=True, testing=False) is False


def test_debug_lan_allows_when_not_pytest():
    with patch.dict("os.environ", {"SWARM_ALLOW_ANONYMOUS": ""}, clear=False):
        assert swarm_allow_anonymous("172.16.0.5", debug=True, testing=False) is True
        assert swarm_allow_anonymous("127.0.0.1", debug=True, testing=False) is True
        assert swarm_allow_anonymous("8.8.8.8", debug=True, testing=False) is False
        assert swarm_allow_anonymous("172.16.0.5", debug=False, testing=False) is False
        assert swarm_allow_anonymous("172.16.0.5", debug=True, testing=True) is False


@pytest.mark.django_db
def test_middleware_logs_in_lan_debug(monkeypatch):
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "")
    factory = RequestFactory()
    request = factory.get("/")
    request.META["REMOTE_ADDR"] = "172.16.0.199"
    request.user = MagicMock(is_authenticated=False)
    request.session = {}

    def _next(req):
        return MagicMock(status_code=200)

    with patch("swarm.middleware.swarm_allow_anonymous", return_value=True):
        with patch("swarm.middleware.get_or_create_preview_user") as mint:
            preview = MagicMock()
            mint.return_value = preview
            with patch("django.contrib.auth.login") as login:
                AllowAnonymousPreviewMiddleware(_next)(request)
                login.assert_called_once()
                assert login.call_args.args[1] is preview

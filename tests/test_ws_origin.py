"""REQ-849: LAN same-origin websocket Origin vs ALLOWED_HOSTS."""

from swarm.ws_origin import (
    hostname_from_host_header,
    hostname_from_origin,
    websocket_origin_allowed,
)

LOCAL = ["localhost", "127.0.0.1"]
STAR = ["*", "localhost", "127.0.0.1"]


def test_hostname_from_origin_strips_scheme_and_port():
    assert hostname_from_origin("http://10.0.0.30:8002") == "10.0.0.30"
    assert hostname_from_origin("http://[::1]:8002") == "::1"
    assert hostname_from_origin(None) is None


def test_hostname_from_host_header_strips_port():
    assert hostname_from_host_header("10.0.0.30:8002") == "10.0.0.30"
    assert hostname_from_host_header("[::1]:8002") == "::1"
    assert hostname_from_host_header("localhost") == "localhost"


def test_lan_same_origin_allowed_in_debug_without_star():
    assert websocket_origin_allowed(
        "http://10.0.0.30:8002",
        "10.0.0.30:8002",
        allowed_hosts=LOCAL,
        debug=True,
    )


def test_lan_same_origin_allowed_when_star_listed():
    assert websocket_origin_allowed(
        "http://10.0.0.30:8002",
        "10.0.0.30:8002",
        allowed_hosts=STAR,
        debug=False,
    )


def test_lan_denied_in_production_unless_listed():
    assert not websocket_origin_allowed(
        "http://10.0.0.30:8002",
        "10.0.0.30:8002",
        allowed_hosts=LOCAL,
        debug=False,
    )
    assert websocket_origin_allowed(
        "http://10.0.0.30:8002",
        "10.0.0.30:8002",
        allowed_hosts=["10.0.0.30", "localhost"],
        debug=False,
    )


def test_evil_origin_denied_even_with_star():
    assert not websocket_origin_allowed(
        "http://evil.example.com",
        "localhost",
        allowed_hosts=STAR,
        debug=True,
    )


def test_vite_localhost_origin_allowed_when_listed():
    assert websocket_origin_allowed(
        "http://localhost:3000",
        "127.0.0.1:8000",
        allowed_hosts=LOCAL,
        debug=True,
    )


def test_missing_origin_denied():
    assert not websocket_origin_allowed(
        None, "localhost", allowed_hosts=STAR, debug=True
    )

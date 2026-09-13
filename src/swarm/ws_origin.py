"""Websocket Origin checks for LAN same-origin chat (REQ-849)."""

from __future__ import annotations

from urllib.parse import urlparse

from channels.security.websocket import WebsocketDenier
from django.conf import settings
from django.utils.http import is_same_domain

from swarm.middleware import is_lan_or_loopback


def hostname_from_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    host = urlparse(origin.strip()).hostname
    return host.lower() if host else None


def hostname_from_host_header(host: str | None) -> str | None:
    if not host:
        return None
    host = host.strip()
    if host.startswith("["):
        end = host.find("]")
        if end == -1:
            return None
        return host[1:end].lower()
    if ":" in host:
        name, _, port = host.rpartition(":")
        if port.isdigit():
            return name.lower()
    return host.lower() or None


def _host_listed(name: str, allowed_hosts: list[str]) -> bool:
    needle = name.lower()
    for pattern in allowed_hosts:
        if not pattern or pattern == "*":
            continue
        if is_same_domain(needle, pattern.lower()):
            return True
    return False


def websocket_origin_allowed(
    origin: str | None,
    host: str | None,
    *,
    allowed_hosts: list[str],
    debug: bool = False,
) -> bool:
    """Allow same-origin LAN WS; deny cross-site even when ``*`` is listed.

    Channels ``AllowedHostsOriginValidator`` treats ``*`` as any Origin and
    snapshots ALLOWED_HOSTS at import. A phone at ``http://10.x.x.x:port``
    is same-origin with the Host header; ``http://evil.example.com`` is not.
    """
    origin_host = hostname_from_origin(origin)
    host_name = hostname_from_host_header(host)
    if not origin_host:
        return False

    def host_ok(name: str) -> bool:
        if _host_listed(name, allowed_hosts):
            return True
        if "*" in allowed_hosts:
            return True
        return bool(debug and is_lan_or_loopback(name))

    if host_name and origin_host == host_name and host_ok(host_name):
        return True
    # Vite / extra UI hosts: Origin hostname is an explicit ALLOWED_HOSTS entry
    # (not ``*``). Cross-site evil.com stays out.
    return _host_listed(origin_host, allowed_hosts)


def _header(scope: dict, name: bytes) -> str | None:
    for key, value in scope.get("headers") or []:
        if key == name:
            try:
                return value.decode("latin1")
            except UnicodeDecodeError:
                return None
    return None


class SwarmWebsocketOriginValidator:
    """Re-reads ALLOWED_HOSTS per connection; same-origin LAN is enough."""

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            raise ValueError("SwarmWebsocketOriginValidator is websocket-only")
        origin = _header(scope, b"origin")
        host = _header(scope, b"host")
        allowed = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        debug = bool(getattr(settings, "DEBUG", False))
        if websocket_origin_allowed(
            origin, host, allowed_hosts=allowed, debug=debug
        ):
            return await self.application(scope, receive, send)
        return await WebsocketDenier()(scope, receive, send)

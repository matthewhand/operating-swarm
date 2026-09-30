"""Shared fetch-outcome classification for marketplace catalog sources (#1327).

Every catalog source (Official MCP Registry, Composio, GitHub fallback) must
report *why* it stalled with a machine-readable reason instead of a bare
exception class name, and must never block indefinitely. The reason vocabulary
is stable so the UI can map it to copy:

``dns`` | ``timeout`` | ``tls`` | ``rate_limit`` | ``offline`` |
``http_<status>`` | ``payload`` | ``not_configured`` | ``unknown``

Classification is intentionally structural (exception type first, message
second) so a TLS stall, a DNS failure, a read timeout and a rate limit are
distinguishable without a live network.
"""

from __future__ import annotations

import socket
import ssl
from typing import Any

#: Stable, machine-readable stall reason vocabulary.
STALL_REASONS = (
    "dns",
    "timeout",
    "tls",
    "rate_limit",
    "offline",
    "payload",
    "not_configured",
    "unknown",
)


def classify_fetch_exception(exc: BaseException) -> str:
    """Map a transport exception to a stall reason.

    Order matters: ``socket.timeout`` / ``ssl.SSLError`` / ``socket.gaierror``
    are all ``OSError`` subclasses, so the specific checks must come before the
    generic ``offline`` fallback.
    """
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timeout" in name or "timed out" in text:
        return "timeout"
    if isinstance(exc, ssl.SSLError) or "ssl" in name or "certificate" in name or "certificate" in text:
        return "tls"
    if (
        isinstance(exc, socket.gaierror)
        or "gaierror" in name
        or "name or service not known" in text
        or "getaddrinfo" in text
        or "nodename nor servname" in text
    ):
        return "dns"
    if "connectionrefused" in name or "connection refused" in text:
        return "offline"
    if isinstance(exc, (ConnectionError, OSError)):
        return "offline"
    return "unknown"


def classify_fetch_status(status: int, payload: Any = None) -> str | None:
    """Map an HTTP status (plus payload) to a stall reason, or ``None`` for 2xx."""
    try:
        code = int(status)
    except (TypeError, ValueError):
        return "unknown"
    if 200 <= code < 300:
        return None
    if code == 429 or (code == 403 and "rate" in str(payload).lower()):
        return "rate_limit"
    if code == 0:
        return "offline"
    return f"http_{code}"


def stall_message(source_label: str, reason: str) -> str:
    """Human warning for a classified stall (never a secret, never a traceback)."""
    if reason == "rate_limit":
        return f"{source_label} rate limit reached — using cache if available."
    if reason == "timeout":
        return f"{source_label} timed out — using cache if available."
    if reason == "dns":
        return f"{source_label} could not resolve its host (DNS) — using cache if available."
    if reason == "tls":
        return f"{source_label} TLS handshake failed — using cache if available."
    if reason == "offline":
        return f"{source_label} is unreachable — using cache if available."
    if reason == "not_configured":
        return f"{source_label} is not configured."
    if reason.startswith("http_"):
        return f"{source_label} returned HTTP {reason.split('_', 1)[1]}."
    return f"{source_label} stalled ({reason})."

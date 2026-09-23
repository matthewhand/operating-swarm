"""#720 — honest sandbox display resolution for the computer pane.

The resolver turns the effective sandbox configuration into a display
payload the frontend can render without ever seeing a secret:

- provider ``none`` / ``bare_metal`` / anything not ``daytona`` → an empty
  state explaining why (``provider_not_daytona``);
- ``daytona`` with no reachable sandbox (missing key, SDK absent, API
  unreachable) → ``no_active_sandbox``;
- a live sandbox exposing a preview URL → ``{"kind": "iframe", "url": …}``.

Every failure path is a *reason*, never a fabricated screenshot. The
payload carries no credentials by construction: only provider names,
reasons, and preview URLs are echoed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

PROVIDER_NOT_DAYTONA = "provider_not_daytona"
NO_ACTIVE_SANDBOX = "no_active_sandbox"


def _provider_from_config(config: dict[str, Any]) -> str:
    settings = config.get("settings") if isinstance(config.get("settings"), dict) else {}
    block = settings.get("sandbox") if isinstance(settings.get("sandbox"), dict) else {}
    provider = str(block.get("provider") or "none").strip().lower()
    if provider in ("", "none"):
        # REQ-860 honesty: an absent block is the disabled default.
        return "none"
    return provider


def _preview_url_from_backend(backend: Any) -> str | None:
    """Extract a preview URL from a sandbox backend, when it exposes one."""
    url = getattr(backend, "preview_url", None)
    if callable(url):
        try:
            url = url()
        except Exception:  # pragma: no cover — defensive
            return None
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def resolve_sandbox_display(
    config: dict[str, Any] | None = None,
    *,
    manager: Any = None,
) -> dict[str, Any]:
    """Resolve the honest display payload for the effective sandbox.

    ``manager`` (test/endpoint injection) overrides construction from
    ``config``. Any backend failure degrades to ``no_active_sandbox`` —
    an operator sees an empty state, never an exception surface.
    """
    provider = _provider_from_config(config or {})
    payload: dict[str, Any] = {"provider": provider, "display": None}
    if provider != "daytona":
        payload["reason"] = PROVIDER_NOT_DAYTONA
        return payload

    if manager is None:
        try:
            from swarm.core.sandbox.manager import SandboxManager

            manager = SandboxManager.from_settings(config)
        except Exception as exc:  # SDK absent, config malformed
            logger.debug("sandbox manager construction failed: %s", exc)
            payload["reason"] = NO_ACTIVE_SANDBOX
            return payload

    backend = getattr(manager, "_backend", None)
    if backend is None:
        try:
            backend = manager.backend  # property; may raise
        except Exception:
            backend = None
    if backend is None or isinstance(backend, type(None)):
        payload["reason"] = NO_ACTIVE_SANDBOX
        return payload

    try:
        available = bool(backend.is_available())
    except Exception:
        available = False
    if not available:
        payload["reason"] = NO_ACTIVE_SANDBOX
        return payload

    url = _preview_url_from_backend(backend)
    if url:
        payload["display"] = {"kind": "iframe", "url": url}
    else:
        payload["reason"] = NO_ACTIVE_SANDBOX
    return payload

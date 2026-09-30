"""#720 — honest sandbox display resolution for the computer pane.

The resolver turns the effective sandbox configuration into a display
payload the frontend can render without ever seeing a secret:

- provider ``none`` / ``bare_metal`` / anything not ``daytona`` → an empty
  state explaining why (``provider_not_daytona``);
- ``daytona`` with no reachable sandbox (missing key, SDK absent, API
  unreachable) → ``no_active_sandbox`` — plus the credential env-var
  **name** and a cheap preflight diagnosis;
- a live sandbox (registered in-process) → ``available``, its ``id`` /
  ``status``, and, when it exposes a preview, ``{"kind": "iframe", ...}``.

Every failure path is a *reason*, never a fabricated screenshot. The
payload carries no credentials by construction: only provider names, reasons,
env-var names, and preview URLs are echoed.
"""

from __future__ import annotations

import logging
from typing import Any

from .daytona_sandbox import _resolve_api_key

logger = logging.getLogger(__name__)

PROVIDER_NOT_DAYTONA = "provider_not_daytona"
NO_ACTIVE_SANDBOX = "no_active_sandbox"
NO_PREVIEW_URL = "no_preview_url"

DEFAULT_KEY_ENV = "DAYTONA_API_KEY"


def _provider_from_config(config: dict[str, Any]) -> str:
    settings = config.get("settings") if isinstance(config.get("settings"), dict) else {}
    block = settings.get("sandbox") if isinstance(settings.get("sandbox"), dict) else {}
    provider = str(block.get("provider") or "none").strip().lower()
    if provider in ("", "none"):
        # REQ-860 honesty: an absent block is the disabled default.
        return "none"
    return provider


def _daytona_env_name(config: dict[str, Any]) -> str:
    """Configured env-var **name** (never a value) for the Daytona key."""
    settings = config.get("settings") if isinstance(config.get("settings"), dict) else {}
    block = settings.get("sandbox") if isinstance(settings.get("sandbox"), dict) else {}
    return str(block.get("daytona_api_key_env") or "").strip()


def _sdk_present() -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec("daytona") is not None
    except (ImportError, ValueError):  # pragma: no cover — defensive
        return False


def _credential_state(env_name: str) -> dict[str, Any]:
    """Which env-var name backs the key and whether a value resolves.

    The value is never returned — only the name and a boolean.
    """
    name = env_name or DEFAULT_KEY_ENV
    return {"env_var": name, "set": bool(_resolve_api_key(env_name))}


def _daytona_preflight(env_name: str) -> dict[str, Any]:
    """Cheap, offline diagnosis of the *server-side* Daytona prerequisites.

    Because it performs no network call it only distinguishes the two
    server-side classes (``sdk_missing`` / ``env_name_unset``) from ``ok``.
    The live round-trip and its ``auth`` / ``network`` classes live in the
    settings probe (``POST /v1/settings/sandbox/test``).
    """
    name = env_name or DEFAULT_KEY_ENV
    sdk_present = _sdk_present()
    key_set = bool(_resolve_api_key(env_name))
    if not sdk_present:
        return {
            "kind": "preflight",
            "ok": False,
            "classification": "sdk_missing",
            "detail": "The daytona SDK is not installed in the server environment.",
            "operator_hint": "Run: pip install daytona (inside the server's venv).",
        }
    if not key_set:
        return {
            "kind": "preflight",
            "ok": False,
            "classification": "env_name_unset",
            "detail": f"Environment variable {name} is not set in the server's environment.",
            "operator_hint": (
                f"Set {name} in the SERVER environment (a shell export in your own "
                f"session does not count): systemctl --user set-environment {name}=<key> "
                f"&& systemctl --user restart open-swarm-private-backend, or add "
                f"{name}=<key> to the unit's EnvironmentFile."
            ),
        }
    return {
        "kind": "preflight",
        "ok": True,
        "classification": None,
        "detail": (
            "SDK present and API key resolves. A live preview appears once the "
            "agent runs code in its sandbox."
        ),
        "operator_hint": None,
    }


def _has_live_sandbox(backend: Any) -> bool:
    if backend is None:
        return False
    if getattr(backend, "_sandbox", None) is not None:
        return True
    return bool(getattr(backend, "sandbox_id", None))


def _resolve_backend(manager: Any) -> Any:
    """Prefer the manager's backend, else the registered live sandbox.

    Agent turns and display requests hold separate ``SandboxManager``
    instances, so the display consults the process-wide registry to find the
    backend that actually created a VM.
    """
    backend = getattr(manager, "_backend", None)
    if backend is None:
        try:
            backend = manager.backend  # property; may raise
        except Exception:
            backend = None
    if _has_live_sandbox(backend):
        return backend
    try:
        from .registry import get_live_sandbox, live_sandbox_keys

        for key in live_sandbox_keys():
            live = get_live_sandbox(key)
            if _has_live_sandbox(live):
                return live
    except Exception:  # pragma: no cover — defensive
        logger.debug("live sandbox registry lookup failed", exc_info=True)
    return backend


def _sandbox_state(backend: Any) -> dict[str, Any] | None:
    """``{"id", "status"}`` for a live sandbox, else None. Never raises."""
    if backend is None:
        return None
    sandbox_id = getattr(backend, "sandbox_id", None)
    status = getattr(backend, "sandbox_status", None)
    if sandbox_id is None and status is None:
        inner = getattr(backend, "_sandbox", None)
        if inner is None:
            return None
        raw_id = getattr(inner, "id", None)
        sandbox_id = str(raw_id).strip() if raw_id else None
        raw_status = getattr(inner, "status", None) or getattr(inner, "state", None)
        status = str(getattr(raw_status, "value", raw_status)).strip() if raw_status else None
    if sandbox_id is None and status is None:
        return None
    return {"id": sandbox_id, "status": status}


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
    config = config or {}
    provider = _provider_from_config(config)
    payload: dict[str, Any] = {
        "provider": provider,
        "display": None,
        "available": False,
        "sandbox": None,
    }
    if provider != "daytona":
        payload["reason"] = PROVIDER_NOT_DAYTONA
        return payload

    env_name = _daytona_env_name(config)
    payload["credential"] = _credential_state(env_name)

    if manager is None:
        try:
            from swarm.core.sandbox.manager import SandboxManager

            manager = SandboxManager.from_settings(config)
        except Exception as exc:  # SDK absent, config malformed
            logger.debug("sandbox manager construction failed: %s", exc)
            payload["reason"] = NO_ACTIVE_SANDBOX
            payload["probe"] = _daytona_preflight(env_name)
            return payload

    backend = _resolve_backend(manager)
    if backend is None:
        payload["reason"] = NO_ACTIVE_SANDBOX
        payload["probe"] = _daytona_preflight(env_name)
        return payload

    try:
        available = bool(backend.is_available())
    except Exception:
        available = False
    payload["available"] = available
    payload["probe"] = _daytona_preflight(env_name)
    payload["sandbox"] = _sandbox_state(backend)

    if not available and payload["sandbox"] is None:
        payload["reason"] = NO_ACTIVE_SANDBOX
        return payload

    url = _preview_url_from_backend(backend)
    if url:
        payload["display"] = {"kind": "iframe", "url": url}
    else:
        payload["reason"] = (
            NO_PREVIEW_URL if payload["sandbox"] is not None else NO_ACTIVE_SANDBOX
        )
    return payload

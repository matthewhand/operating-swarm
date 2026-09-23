"""REST surface for the Sandboxes settings section (REQ-860 / #227).

GET   /v1/settings/sandbox/       current sandbox settings (secrets redacted)
PUT   /v1/settings/sandbox/       persist provider selection + options
POST  /v1/settings/sandbox/test   provider probe (honest result, nothing persisted)

Providers: ``none`` (default — no execution tools) | ``bare_metal`` (direct
host execution, requires ``confirm_dangerous``) | ``daytona`` (Daytona cloud
sandboxes). Persisted under ``settings.sandbox`` in swarm_config.json.
Secrets are env-var **names** — never tokens; GET never echoes key values.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from swarm.auth import api_permission_classes

logger = logging.getLogger(__name__)

SANDBOX_SETTINGS_KEY = "sandbox"
ALLOWED_PROVIDERS = ("none", "bare_metal", "daytona")
DANGEROUS_PROVIDERS = frozenset({"bare_metal"})

PROVIDER_DESCRIPTIONS: dict[str, str] = {
    "none": "No sandbox tools attached to agents (default).",
    "bare_metal": (
        "Execute directly on this host with swarm's privileges. "
        "No isolation. DANGEROUS — only for trusted, single-operator hosts."
    ),
    "daytona": (
        "Run code in isolated Daytona cloud sandboxes (microVMs). "
        "Requires the daytona SDK and DAYTONA_API_KEY."
    ),
}


def _loaded_config() -> dict[str, Any]:
    """Live swarm config (file-backed, ADR-002)."""
    from swarm.core.remotes import load_raw_config

    return load_raw_config()[0]


def sandbox_settings_block(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalized ``settings.sandbox`` block from the loaded app config."""
    cfg = config if isinstance(config, dict) else _loaded_config()
    settings = cfg.get("settings") if isinstance(cfg.get("settings"), dict) else {}
    raw = settings.get(SANDBOX_SETTINGS_KEY) if isinstance(settings.get(SANDBOX_SETTINGS_KEY), dict) else {}
    provider = str(raw.get("provider") or "none").strip().lower()
    if provider not in ALLOWED_PROVIDERS:
        provider = "none"
    tools_on = provider not in (None, "", "none")
    if "enable_sandbox_tools" in raw:
        tools_on = bool(raw.get("enable_sandbox_tools"))
    elif provider not in (None, "", "none"):
        tools_on = True
    inherit_default = provider == "bare_metal"
    return {
        "provider": provider,
        "enable_sandbox_tools": tools_on,
        "timeout_seconds": int(raw.get("timeout_seconds") or 30),
        "daytona_api_key_env": str(raw.get("daytona_api_key_env") or "").strip(),
        "daytona_api_url": str(raw.get("daytona_api_url") or "").strip(),
        "dangerous_confirmed": provider in DANGEROUS_PROVIDERS and bool(raw.get("dangerous_confirmed", False)),
        "inherit_env": bool(raw.get("inherit_env", inherit_default)),
        "auto_stop_interval": int(raw.get("auto_stop_interval") or 15),
        "sync_workspace": bool(raw.get("sync_workspace", False)),
    }


def persist_sandbox_settings(
    *,
    provider: str | None = None,
    enable_sandbox_tools: bool | None = None,
    timeout_seconds: int | None = None,
    daytona_api_key_env: str | None = None,
    daytona_api_url: str | None = None,
    confirm_dangerous: bool = False,
    inherit_env: bool | None = None,
    auto_stop_interval: int | None = None,
    sync_workspace: bool | None = None,
    config_path: str | None = None,
) -> tuple[dict[str, Any], Any]:
    """Merge the sandbox block into ``settings`` of swarm_config.json."""
    from swarm.core.config_ownership import refresh_app_config
    from swarm.core.remotes import load_raw_config

    cfg, path = load_raw_config(config_path)
    current = sandbox_settings_block(cfg)

    new_provider = current["provider"]
    if provider is not None:
        new_provider = str(provider).strip().lower()
        if new_provider not in ALLOWED_PROVIDERS:
            raise ValueError(
                f"Unknown sandbox provider '{provider}'. Allowed: {', '.join(ALLOWED_PROVIDERS)}"
            )
        if new_provider in DANGEROUS_PROVIDERS and not (
            confirm_dangerous or current.get("dangerous_confirmed")
        ):
            raise ValueError(
                f"Provider '{new_provider}' is dangerous (direct host execution). "
                "Set confirm_dangerous=true to accept."
            )
        if new_provider in DANGEROUS_PROVIDERS and confirm_dangerous:
            current["dangerous_confirmed"] = True
        elif new_provider not in DANGEROUS_PROVIDERS:
            current["dangerous_confirmed"] = False

    if daytona_api_key_env is not None:
        from swarm.core.config_ownership import looks_like_env_name

        name = str(daytona_api_key_env).strip()
        if name and not looks_like_env_name(name):
            raise ValueError("daytona_api_key_env must be an env-var NAME, not a token.")
        current["daytona_api_key_env"] = name
    if daytona_api_url is not None:
        current["daytona_api_url"] = str(daytona_api_url).strip()
    if enable_sandbox_tools is not None:
        current["enable_sandbox_tools"] = bool(enable_sandbox_tools)
    elif provider is not None:
        # Selecting a real provider attaches tools; none detaches them.
        current["enable_sandbox_tools"] = new_provider not in (None, "", "none")
    if inherit_env is not None:
        current["inherit_env"] = bool(inherit_env)
    elif provider is not None and new_provider == "bare_metal":
        current["inherit_env"] = True
    if auto_stop_interval is not None:
        try:
            current["auto_stop_interval"] = max(0, min(int(auto_stop_interval), 24 * 60))
        except (TypeError, ValueError):
            raise ValueError("auto_stop_interval must be an integer (minutes, 0..1440)") from None
    if sync_workspace is not None:
        current["sync_workspace"] = bool(sync_workspace)
    if timeout_seconds is not None:
        try:
            current["timeout_seconds"] = max(1, min(int(timeout_seconds), 600))
        except (TypeError, ValueError):
            raise ValueError("timeout_seconds must be an integer (1..600)") from None

    current["provider"] = new_provider
    settings = cfg.get("settings") if isinstance(cfg.get("settings"), dict) else {}
    settings = dict(settings)
    settings[SANDBOX_SETTINGS_KEY] = current
    cfg["settings"] = settings
    path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json

    path.write_text(_json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    refresh_app_config(cfg)
    logger.info("Persisted settings.sandbox (provider=%s) to %s", new_provider, path)
    return current, path


def probe_sandbox_provider(provider: str | None = None) -> dict[str, Any]:
    """Honest provider probe. Nothing persisted; no secrets returned."""
    from swarm.core.sandbox import SandboxManager

    provider = (provider or sandbox_settings_block()["provider"]).strip().lower()
    started = time.monotonic()
    if provider == "none":
        return {
            "provider": "none",
            "ok": True,
            "detail": "Sandboxing disabled — no execution tools are attached to agents.",
            "latency_ms": 0,
        }
    if provider == "bare_metal":
        manager = SandboxManager.from_config({"backend_type": "local"})
        result = manager.execute_python("print('ok')")
        return {
            "provider": "bare_metal",
            "ok": bool(result.success),
            "detail": (result.stdout or result.stderr or "").strip()[:200]
            or ("bare-metal execution ok" if result.success else "bare-metal execution failed"),
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
    if provider == "daytona":
        manager = SandboxManager.from_config(
            {
                "backend_type": "daytona",
                **_daytona_kwargs(),
            }
        )
        try:
            result = manager.execute_bash("echo ok")
            return {
                "provider": "daytona",
                "ok": bool(result.success),
                "detail": (result.stdout or result.stderr or "").strip()[:200]
                or ("daytona execution ok" if result.success else "daytona execution failed"),
                "latency_ms": round((time.monotonic() - started) * 1000),
            }
        finally:
            manager.cleanup()
    return {"provider": provider, "ok": False, "detail": f"Unknown provider '{provider}'", "latency_ms": 0}


def _daytona_kwargs() -> dict[str, Any]:
    block = sandbox_settings_block()
    kwargs: dict[str, Any] = {}
    if block.get("daytona_api_key_env"):
        kwargs["daytona_api_key_env"] = block["daytona_api_key_env"]
    if block.get("daytona_api_url"):
        kwargs["daytona_api_url"] = block["daytona_api_url"]
    return kwargs


class SandboxSettingsView(APIView):
    """GET/PUT /v1/settings/sandbox/ — Sandboxes settings section."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(responses={200: dict})
    def get(self, _request, *_args, **_kwargs):
        block = sandbox_settings_block()
        return Response(
            {
                "object": "sandbox_settings",
                "providers": [
                    {"id": pid, "label": label, "description": PROVIDER_DESCRIPTIONS[pid], "dangerous": pid in DANGEROUS_PROVIDERS}
                    for pid, label in (
                        ("none", "None (default)"),
                        ("bare_metal", "Bare metal host"),
                        ("daytona", "Daytona"),
                    )
                ],
                **block,
            }
        )

    @extend_schema(request=dict, responses={200: dict})
    def put(self, request, *_args, **_kwargs):
        return self._persist(request)

    @extend_schema(request=dict, responses={200: dict})
    def post(self, request, *_args, **_kwargs):
        return self._persist(request)

    def _persist(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            block, _path = persist_sandbox_settings(
                provider=body.get("provider"),
                enable_sandbox_tools=body.get("enable_sandbox_tools"),
                timeout_seconds=body.get("timeout_seconds"),
                daytona_api_key_env=body.get("daytona_api_key_env"),
                daytona_api_url=body.get("daytona_api_url"),
                confirm_dangerous=bool(body.get("confirm_dangerous")),
                inherit_env=body.get("inherit_env"),
                auto_stop_interval=body.get("auto_stop_interval"),
                sync_workspace=body.get("sync_workspace"),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # pragma: no cover — persistence failure
            logger.exception("Failed to persist sandbox settings")
            return Response({"error": f"failed to persist: {exc}"}, status=500)
        return Response({"object": "sandbox_settings", **block})


class SandboxSettingsTestView(APIView):
    """POST /v1/settings/sandbox/test — honest provider probe."""

    def get_permissions(self):
        return [perm() for perm in api_permission_classes()]

    @extend_schema(request=dict, responses={200: dict})
    def post(self, request, *_args, **_kwargs):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            return Response(probe_sandbox_provider(body.get("provider")))
        except Exception as exc:  # pragma: no cover — probe failure
            logger.exception("Sandbox provider probe failed")
            return Response({"error": f"probe failed: {exc}"}, status=500)

"""#719 — per-agent sandbox opt-in: param validation + resolution.

An agent may carry a ``sandbox`` param (persisted on the custom seat,
forwarded through ``set_params``) that overrides the *global* settings
provider for that agent alone:

- ``{"provider": "daytona", ...}`` opts the agent into sandbox tools even
  when the global provider is ``none``;
- ``{"provider": "none"}`` opts the agent *out* even when the global
  provider would attach tools;
- absent / invalid params fall back to the global settings unchanged.

Validation is deliberately strict — the param arrives from user-editable
surfaces, so key *material* is refused (only env-var *names* pass) and the
provider allow-list mirrors the settings surface (REQ-860).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

ALLOWED_PROVIDERS = ("none", "bare_metal", "daytona")

_ALLOWED_PARAM_KEYS = (
    "provider",
    "daytona_api_key_env",
    "daytona_api_url",
    "timeout_seconds",
    "auto_stop_interval",
    "sync_workspace",
    "work_dir",
)


def _looks_like_key_material(value: str) -> bool:
    text = value.strip()
    if "BEGIN" in text and "PRIVATE KEY" in text:
        return True
    return bool(text.startswith(("sk-", "dtn_", "dtna_")))


def normalize_sandbox_param(raw: Any) -> dict[str, Any]:
    """Validate a per-agent ``sandbox`` param; raise ``ValueError`` on abuse.

    Returns a clean dict containing only the recognized keys. ``provider``
    must be in the allow-list; ``daytona_api_key_env`` must be an env-var
    *name* (never key material, never an inline ``daytona_api_key`` value).
    """
    if not isinstance(raw, dict):
        raise ValueError("sandbox param must be an object like {'provider': 'daytona'}")
    provider = str(raw.get("provider") or "").strip().lower()
    if provider not in ALLOWED_PROVIDERS:
        raise ValueError(
            f"sandbox provider must be one of {', '.join(ALLOWED_PROVIDERS)}"
        )
    out: dict[str, Any] = {"provider": provider}

    if "daytona_api_key" in raw:
        raise ValueError(
            "sandbox refuses inline keys — use daytona_api_key_env (an env-var name)"
        )
    env_name = raw.get("daytona_api_key_env")
    if env_name is not None:
        text = str(env_name).strip()
        if not text:
            raise ValueError("daytona_api_key_env must be a non-empty env-var name")
        if _looks_like_key_material(text) or " " in text:
            raise ValueError(
                "daytona_api_key_env must be an env-var name, never key material"
            )
        out["daytona_api_key_env"] = text

    url = raw.get("daytona_api_url")
    if url is not None and str(url).strip():
        out["daytona_api_url"] = str(url).strip()

    for key in ("timeout_seconds", "auto_stop_interval"):
        if key in raw and raw[key] is not None:
            try:
                out[key] = max(0, int(raw[key]))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"sandbox {key} must be an integer") from exc

    if "sync_workspace" in raw:
        out["sync_workspace"] = bool(raw["sync_workspace"])

    work_dir = raw.get("work_dir")
    if work_dir is not None and str(work_dir).strip():
        out["work_dir"] = str(work_dir).strip()

    return {k: v for k, v in out.items() if k in _ALLOWED_PARAM_KEYS}


def effective_sandbox_config(
    settings_config: dict[str, Any] | None,
    params: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve the sandbox block ``make_agent`` should honour.

    The per-agent param wins when present and valid; an invalid param logs
    and falls back to settings (an agent misconfiguration must never take
    the seat down). Returns ``None`` when the resolved provider is ``none``.
    """
    settings = settings_config or {}
    settings_cfg = settings.get("settings") if isinstance(settings.get("settings"), dict) else {}
    block = settings_cfg.get("sandbox") if isinstance(settings_cfg.get("sandbox"), dict) else {}

    param_raw = (params or {}).get("sandbox")
    if param_raw is not None:
        try:
            param = normalize_sandbox_param(param_raw)
        except ValueError as exc:
            logger.warning("Ignoring invalid per-agent sandbox param: %s", exc)
        else:
            merged = dict(block)
            merged.update(param)
            return merged if str(merged.get("provider") or "none") != "none" else None

    provider = str(block.get("provider") or "none").strip().lower()
    if provider in ("", "none"):
        return None
    return dict(block)

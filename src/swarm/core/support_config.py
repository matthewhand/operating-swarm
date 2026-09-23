"""#854 — universal configuration assistant with self-preservation guardrails.

Support can now *perform* configuration across app domains, not just talk
about it, guarded by two mechanisms:

1. **Active inference identifier** — the system prompt carries the provider /
   endpoint / model this very session runs on, resolved from the blueprint's
   live LLM profile. Self-referential honesty: the agent knows what it runs
   on, and knows modifying it kills the session mid-turn.
2. **Approval interception** — :func:`update_config` classifies every write
   against :func:`classify_config_target`; a target that *is* the active
   provider requires the human approval gate (the chat's Allow/Always/Deny
   modal via ``elicit_fn``). Without an explicit approval the write is
   denied — fail-closed for self-touching configuration.

Secrets are never echoed: config reads go through :func:`redact_config`,
which keeps env-var *names* and drops key *values*.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SELF_PRESERVATION_DIRECTIVES = """
[SELF-PRESERVATION DIRECTIVES]
- You run on the provider/endpoint/model in [ACTIVE INFERENCE IDENTIFIER]
  below. That is *this* session's inference path.
- Do NOT modify, unset, or disable the active provider. A change to it can
  disconnect this Support session mid-turn — you would brick yourself.
- If the operator asks to change the active provider, explain the risk and
  attempt the write only through update_config: the approval gate will ask
  them to confirm ("Modifying this provider may disconnect this Support
  session"). Respect a denial; never retry around it.
- Passive domains (MCP servers, teams, blueprints, non-active settings,
  non-active providers) are safe to configure directly.
""".strip()

ACTIVE_IDENTIFIER_HEADER = "[ACTIVE INFERENCE IDENTIFIER]"

# Domains update_config can write. Each entry: (persist key in
# swarm_config.json, validation for the patch).
DOMAINS = ("provider", "settings", "mcp_servers", "teams", "blueprints")

_KEY_VALUE_HINTS = ("api_key", "token", "secret", "password", "cookie")


def _resolve_profile(source: Any) -> dict[str, Any] | None:
    """Pull the live LLM profile off whatever the caller handed us.

    Accepts a blueprint instance (resolves via ``_resolve_llm_profile``)
    or an already-resolved profile dict.
    """
    if source is None:
        return None
    if isinstance(source, dict):
        return source or None
    resolver = getattr(source, "_resolve_llm_profile", None)
    if callable(resolver):
        try:
            resolved = resolver()
        except Exception:  # pragma: no cover - defensive, resolver is ours
            logger.debug("_resolve_llm_profile failed", exc_info=True)
            return None
        return resolved if isinstance(resolved, dict) and resolved else None
    return None


def active_inference_identifier(source: Any) -> str:
    """Render the [ACTIVE INFERENCE IDENTIFIER] block from a live profile.

    Args:
        source: A blueprint instance (its ``_resolve_llm_profile`` supplies
            the profile) or an already-resolved profile dict; ``None`` when
            inference is not configured.

    Returns:
        A prompt block naming provider, endpoint, and model — or an honest
        "not configured" block. API key values are never echoed.
    """
    profile = _resolve_profile(source)
    lines = [ACTIVE_IDENTIFIER_HEADER]
    if not isinstance(profile, dict) or not (
        str(profile.get("provider") or "").strip()
        or str(profile.get("base_url") or "").strip()
        or str(profile.get("model") or "").strip()
    ):
        lines.append("Current Provider: not configured")
        lines.append("Endpoint: not configured")
        lines.append("Model: not configured")
        return "\n".join(lines)
    name = str(profile.get("name") or "").strip()
    lines.append(f"Current Provider: {profile.get('provider') or 'unknown'}")
    lines.append(f"Endpoint: {profile.get('base_url') or 'provider default'}")
    lines.append(f"Model: {profile.get('model') or 'provider default'}")
    if name and name != "default":
        lines.append(f"Profile: {name}")
    return "\n".join(lines)


def classify_config_target(
    *,
    domain: str,
    target_id: str,
    active: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify whether a config write touches the active inference path.

    Args:
        domain: One of :data:`DOMAINS`.
        target_id: The identifier being written (profile name, setting key…).
        active: The active inference descriptor
            (``{"provider": …, "profile": …}``).

    Returns:
        ``{"is_active_provider": bool, "requires_approval": bool}``.
    """
    active = active or {}
    is_active = domain == "provider" and (
        str(target_id or "").strip() == str(active.get("profile") or "").strip()
        or not str(active.get("profile") or "").strip()
    )
    return {"is_active_provider": is_active, "requires_approval": is_active}


def redact_config(blob: Any) -> Any:
    """Recursively drop secret *values*, keep env-var *names*.

    Args:
        blob: Any JSON-shaped config fragment.

    Returns:
        The same shape with ``api_key``-style values replaced by
        ``"[REDACTED — set via env name]"``. Keys whose names end in
        ``_env`` (e.g. ``api_key_env``) pass through: they hold env-var
        *names*, never credentials.
    """
    if isinstance(blob, dict):
        out: dict[str, Any] = {}
        for key, value in blob.items():
            key_text = str(key)
            if any(hint in key_text.lower() for hint in _KEY_VALUE_HINTS) and not key_text.lower().endswith("_env"):
                out[key] = "[REDACTED — set via env name]"
            else:
                out[key] = redact_config(value)
        return out
    if isinstance(blob, list):
        return [redact_config(item) for item in blob]
    return blob


def _load_config(config_path: str | None) -> tuple[dict[str, Any], Path | None]:
    if config_path:
        path = Path(config_path)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), path
        return {}, path
    from swarm.core.remotes import load_raw_config

    cfg, path = load_raw_config()
    return cfg, path


def _write_config(cfg: dict[str, Any], path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")


def list_config_targets(*, config_path: str | None = None) -> str:
    """Read-only survey of every configurable domain (secrets redacted)."""
    cfg, _path = _load_config(config_path)
    settings = cfg.get("settings") if isinstance(cfg.get("settings"), dict) else {}
    payload = {
        "provider": sorted((cfg.get("llm") or {}).keys()) if isinstance(cfg.get("llm"), dict) else [],
        "settings": sorted(settings.keys()),
        "mcp_servers": sorted((cfg.get("mcp_servers") or {}).keys()) if isinstance(cfg.get("mcp_servers"), dict) else [],
        "teams": sorted((cfg.get("team_rosters") or {}).keys()) if isinstance(cfg.get("team_rosters"), dict) else [],
        "blueprints": sorted((cfg.get("blueprints") or {}).keys()) if isinstance(cfg.get("blueprints"), dict) else [],
    }
    return json.dumps(redact_config(payload), indent=2)


def update_config(
    *,
    domain: str,
    target_id: str,
    patch: dict[str, Any],
    active: dict[str, Any] | None = None,
    approved: bool = False,
    config_path: str | None = None,
) -> dict[str, Any]:
    """Apply a configuration write with self-preservation interception.

    Args:
        domain: One of :data:`DOMAINS`.
        target_id: Profile name / setting key / server id being written.
        patch: The validated fields to merge.
        active: Active inference descriptor for the interception check.
        approved: ``True`` only after the chat's approval modal returned
            Allow. Never synthesized by the agent.
        config_path: Config file override (tests); live config otherwise.

    Returns:
        ``{"ok": bool, "applied"?: dict, "denied"?: bool, "error"?: str}``.
    """
    domain = str(domain or "").strip().lower()
    if domain not in DOMAINS:
        return {"ok": False, "error": f"unknown config domain '{domain}'. Valid: {', '.join(DOMAINS)}"}

    verdict = classify_config_target(domain=domain, target_id=str(target_id or ""), active=active)
    if verdict["requires_approval"] and not approved:
        logger.info("update_config denied: active-provider write needs human approval (#854)")
        return {
            "ok": False,
            "denied": True,
            "error": (
                "This write targets the ACTIVE provider that powers this Support "
                "session. Modifying it may disconnect this session mid-turn. "
                "It requires explicit human approval (Allow) before execution."
            ),
        }

    try:
        cfg, path = _load_config(config_path)
        if domain == "provider":
            profiles = cfg.setdefault("llm", {})
            if not isinstance(profiles, dict):
                profiles = {}
                cfg["llm"] = profiles
            row = profiles.setdefault(str(target_id or "default"), {})
            if not isinstance(row, dict):
                row = {}
                profiles[str(target_id or "default")] = row
            row.update(patch)
            applied = dict(patch)
        elif domain == "settings":
            settings = cfg.setdefault("settings", {})
            if not isinstance(settings, dict):
                settings = {}
                cfg["settings"] = settings
            key = str(target_id or "").strip()
            if not key:
                return {"ok": False, "error": "settings writes need a target_id key"}
            value = patch.get("value", patch) if isinstance(patch, dict) and set(patch) == {"value"} else patch
            settings[key] = value
            applied = {key: value}
        else:
            section = cfg.setdefault(domain, {})
            if not isinstance(section, dict):
                section = {}
                cfg[domain] = section
            row = section.setdefault(str(target_id or ""), {})
            if not isinstance(row, dict):
                row = {}
                section[str(target_id or "")] = row
            row.update(patch)
            applied = dict(patch)

        _write_config(cfg, path)
        return {"ok": True, "applied": redact_config(applied)}
    except Exception as exc:
        logger.warning("update_config failed for %s/%s: %s", domain, target_id, exc)
        return {"ok": False, "error": f"config write failed: {exc}"}


def active_provider_descriptor() -> dict[str, Any] | None:
    """Describe this session's active inference path for interception checks.

    Resolved from the live config's ``llm.default`` profile — the profile
    the API chat engine actually uses and the one ``update_config`` writes
    to. ``None`` when no default profile is configured: interception then
    has nothing to guard.
    """
    cfg, _path = _load_config(None)
    llm = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    profile = llm.get("default") if isinstance(llm.get("default"), dict) else None
    if not profile:
        return None
    return {
        "provider": str(profile.get("provider") or "unknown"),
        "profile": "default",
    }

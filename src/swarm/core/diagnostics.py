"""#904 — tech_support_dump(): the sanitized operator diagnostics payload.

Composes three layers — recent logs (#903), a masked config dump, and
server facts — into the single dict an operator hands to support.

Masking rules (non-negotiable): any value whose KEY looks secret-shaped is
masked to its first 3 characters + ``***`` (values shorter than 3 chars
become bare ``***``). Connection strings and SSH keys are never returned.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from swarm.core.local_store import local_store_facts, looks_like_connection_string

logger = logging.getLogger(__name__)

#: Key fragments that mark a value as secret-shaped.
_SECRET_KEY_NEEDLES = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "private_key",
    "credential",
    "bearer",
)

#: Config keys dropped outright — never returned in any shape.
_DROP_KEYS = ("connection_string", "ssh_key")

#: How many characters of a masked secret survive.
_MASK_SUFFIX = "...***"
_BARE_MASK = "***"
# Vendor-prefixed secrets keep their recognizable two-segment tag
# (sk-ant, gsk_abc) — but only when BOTH segments are short (≤ 4 alnum
# chars each), which is the vendor-tag shape. Anything longer or numeric
# (tok-1234…, hunter2-hunter2) falls back to the 3-char reveal.
_VENDOR_PREFIX_RE = re.compile(r"^[A-Za-z]{1,4}[-_][A-Za-z]{1,4}")


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(needle in lowered for needle in _SECRET_KEY_NEEDLES)


def mask_secret(value: Any) -> str:
    """Mask per the #904 examples.

    ``sk-ant-...`` → ``sk-ant...***``; ``gsk_abc...`` → ``gsk_abc...***``
    (short two-segment vendor tags preserved); ``Bearer xyz...`` →
    ``Ber...***`` (no tag → 3 chars); values under 3 chars → bare ``***``.
    """
    text = str(value or "")
    if len(text) < 3:
        return _BARE_MASK
    match = _VENDOR_PREFIX_RE.match(text)
    if match:
        prefix = match.group(0)
    else:
        prefix = text[:3]
    return f"{prefix}{_MASK_SUFFIX}"


def _host_only(value: Any) -> Any:
    """Reduce a URL to its hostname; non-URLs pass through."""
    text = str(value or "")
    if not text:
        return value
    try:
        parsed = urlparse(text)
        if parsed.hostname:
            return parsed.hostname
    except Exception:
        pass
    return value


def _sanitize(value: Any) -> Any:
    """Recursive masking: secret keys masked, drop-keys removed, hosts reduced."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if key_str.lower() in _DROP_KEYS:
                continue
            if looks_like_connection_string(item if isinstance(item, str) else None):
                continue
            if _is_secret_key(key_str):
                out[key_str] = mask_secret(item)
            else:
                out[key_str] = _sanitize(item)
        return out
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _collect_remotes(config: dict[str, Any]) -> dict[str, Any]:
    remotes = config.get("remotes")
    if not isinstance(remotes, dict):
        return {}
    out: dict[str, Any] = {}
    for remote_id, spec in remotes.items():
        if not isinstance(spec, dict):
            continue
        out[str(remote_id)] = {
            key: spec.get(key)
            for key in ("id", "kind", "mode", "display", "title", "host_label")
            if key in spec
        }
    return out


def _collect_llm_profiles(config: dict[str, Any]) -> dict[str, Any]:
    llm = config.get("llm")
    if not isinstance(llm, dict):
        return {}
    profiles: dict[str, Any] = {}
    raw: dict[str, Any] = {}
    for key, value in llm.items():
        if key == "profiles" and isinstance(value, dict):
            raw.update(value)
        elif isinstance(value, dict):
            raw[str(key)] = value
    for name, profile in raw.items():
        if not isinstance(profile, dict):
            continue
        row = dict(profile)
        if "base_url" in profile:
            row["base_url"] = _host_only(profile.get("base_url"))
        profiles[str(name)] = row
    return profiles


def _collect_routing(config: dict[str, Any]) -> dict[str, Any]:
    settings = config.get("settings")
    settings = settings if isinstance(settings, dict) else {}
    task_map = settings.get("task_llm_profiles")
    return {
        "default_llm_profile": settings.get("default_llm_profile"),
        "override_per_task": settings.get("override_per_task"),
        "task_llm_profiles": task_map if isinstance(task_map, dict) else {},
    }


def _config_dump(config: dict[str, Any]) -> dict[str, Any]:
    known = {"remotes", "llm", "settings"}
    rest = {
        k: v
        for k, v in config.items()
        if k not in known and not str(k).startswith("__")
    }
    dump = {
        "remotes": _sanitize(_collect_remotes(config)),
        "llm_profiles": _sanitize(_collect_llm_profiles(config)),
        "routing_models": _collect_routing(config),
        "config_path": config.get("__config_path__") or None,
    }
    # Unknown top-level sections are sanitized inline (no extra nesting),
    # so callers can reach e.g. dump["config_dump"]["database_password"].
    for key, value in rest.items():
        dump.setdefault(str(key), _sanitize(value))
    return dump


def _recent_logs(log_lines: int) -> dict[str, Any]:
    try:
        from swarm.core.log_capture import LogCapture

        lines = LogCapture.recent(limit=max(0, log_lines))
        counts = LogCapture.level_counts()
        if not LogCapture._installed:
            raise RuntimeError("no captures installed")
        return {"lines": lines, "counts": counts, "unavailable": False}
    except Exception:
        return {"lines": [], "counts": {}, "unavailable": True}


def _server_facts() -> dict[str, Any]:
    facts: dict[str, Any] = {}
    try:
        facts["local_store"] = local_store_facts(discover=True)
    except Exception:
        facts["local_store"] = {}
    try:
        from swarm import __version__

        facts["app_version"] = __version__
    except Exception:
        facts["app_version"] = None
    facts["log_levels"] = {
        "django": logging.getLevelName(logging.getLogger("django").getEffectiveLevel()),
        "swarm": logging.getLevelName(logging.getLogger("swarm").getEffectiveLevel()),
    }
    return facts


def tech_support_dump(
    *,
    log_lines: int = 100,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the sanitized tech-support payload. Never raises.

    ``config`` overrides the live swarm config (tests / callers that already
    hold it); when omitted the live config is resolved best-effort.
    """
    try:
        if config is None:
            try:
                from swarm.core.mcp_plugins import swarm_config

                config = swarm_config()
            except Exception:
                config = {}
        if not isinstance(config, dict):
            config = {}
        return {
            "recent_logs": _recent_logs(log_lines),
            "config_dump": _config_dump(config),
            "server_facts": _server_facts(),
        }
    except Exception:
        logger.debug("tech_support_dump degraded", exc_info=True)
        return {
            "recent_logs": {"lines": [], "counts": {}, "unavailable": True},
            "config_dump": {},
            "server_facts": {},
        }

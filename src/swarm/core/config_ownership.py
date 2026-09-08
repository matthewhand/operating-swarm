"""ADR-002 / #776 config ownership.

Decision: **Full** coverage of non-secret product settings via Settings.
Secrets and deploy flags stay env-only (explicit split). Precedence is
``force-env > persisted swarm_config > env bootstrap > built-in defaults``.

Machine-readable inventory lives here and is served by
``GET /v1/config-ownership/``. WebUI writes go through
``persist_webui_section`` (or the existing remotes / LLM helpers, which
call the same refuse + refresh hooks).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("swarm.config_ownership")

DECISION = "Full"
DECISION_NOTE = (
    "Full coverage of non-secret product settings via Settings; "
    "secrets and deploy flags stay env-only (ADR-002 hybrid)."
)
ISSUE = (
    "https://github.com/"
    + os.environ.get("SWARM_GITHUB_REPO", "matthewhand/open-swarm")
    + "/issues/776"
)
ADR = "docs/adr/002-config-ownership.md"

FORCE_ENV_VAR = "SWARM_CONFIG_FORCE_ENV"

# Top-level swarm_config.json sections Settings / the config API may write.
WEBUI_SECTIONS: tuple[str, ...] = (
    "llm",
    "settings",
    "mcpServers",
    "remotes",
    "cli_agents",
    "cli_fusion",
    "cli_map",
    "cli_orchestrator",
    "moa",
    "agent_team",
    "slashCommands",
    "blueprints",
    "memory",
    "speech",
)

# Dedicated Settings pane. Others appear under System as "advanced".
SETTINGS_PANES: dict[str, str] = {
    "llm": "llm-profiles",
    "settings": "llm-profiles",
    "mcpServers": "plugins",
    "remotes": "remotes",
    "cli_agents": "cli-agents",
    "agent_team": "remotes",
    "speech": "speech",
}

ADVANCED_SECTIONS: tuple[str, ...] = (
    "cli_fusion",
    "cli_map",
    "cli_orchestrator",
    "moa",
    "slashCommands",
    "blueprints",
    "memory",
)

# Keys that must never be persisted as plaintext SoT.
SECRET_KEY_NEEDLES: tuple[str, ...] = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "cookie",
    "authorization",
    "credential",
)

_PLACEHOLDER_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

_TRUTHY = frozenset({"1", "true", "yes", "on"})


class ConfigOwnershipError(Exception):
    """Refused write: out-of-partition, plaintext secret, or force-env."""

    def __init__(self, message: str, *, status: int = 400, code: str = "refused"):
        super().__init__(message)
        self.status = status
        self.code = code


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in _TRUTHY


def force_env_enabled() -> bool:
    """Global recovery: ``SWARM_CONFIG_FORCE_ENV=1`` ignores persisted topology."""
    return _truthy(os.environ.get(FORCE_ENV_VAR))


def field_is_forced(env_var: str) -> bool:
    """True when global force-env or ``SWARM_<ENV>_OVERRIDE`` / ``<ENV>_OVERRIDE`` is on."""
    name = (env_var or "").strip()
    if not name:
        return False
    if force_env_enabled():
        return True
    candidates = (f"SWARM_{name}_OVERRIDE", f"{name}_OVERRIDE")
    return any(_truthy(os.environ.get(key)) for key in candidates)


def is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(_PLACEHOLDER_RE.match(value.strip()))


def placeholder_env_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    match = _PLACEHOLDER_RE.match(value.strip())
    return match.group(1) if match else ""


def looks_like_env_name(value: Any) -> bool:
    return isinstance(value, str) and bool(_ENV_NAME_RE.match(value.strip()))


# REQ-88 numeric caps — "token" is a SECRET_KEY_NEEDLE, but these are not secrets.
RATE_LIMIT_SAFE_KEYS: frozenset[str] = frozenset(
    {
        "rate_limits",
        "messages_per_minute",
        "requests_per_minute",
        "tokens_per_minute",
        "tokens_per_day",
    }
)


def is_secret_key(key: str) -> bool:
    lowered = (key or "").lower()
    if lowered in RATE_LIMIT_SAFE_KEYS:
        return False
    return any(needle in lowered for needle in SECRET_KEY_NEEDLES)


def env_is_set(name: str) -> bool:
    return bool(name) and bool(os.environ.get(name, "").strip())


def badge_for(
    *,
    env_var: str = "",
    persisted: Any = None,
    secret: bool = False,
) -> dict[str, Any]:
    """One honesty badge for a field that may have an env twin.

    Copy matches ADR-002 §6. No secret *values* — names only.
    """
    env_name = (env_var or "").strip()
    persisted_empty = persisted is None or (isinstance(persisted, str) and not persisted.strip())
    bootstrap = os.environ.get(env_name, "").strip() if env_name else ""

    if secret:
        set_label = "set" if (env_is_set(env_name) or (is_placeholder(persisted) and env_is_set(placeholder_env_name(persisted)))) else "not set"
        return {
            "kind": "secret",
            "label": "Secret · env-only",
            "env_var": env_name or placeholder_env_name(persisted),
            "forced": False,
            "editable": False,
            "set": set_label == "set",
            "helper": "Not editable as plaintext. Rotate the env var, then reload.",
        }

    if env_name and field_is_forced(env_name) and bootstrap:
        return {
            "kind": "forced",
            "label": f"Forced by env {env_name} (read-only)",
            "env_var": env_name,
            "forced": True,
            "editable": False,
            "helper": f"Persist is ignored until you unset {FORCE_ENV_VAR} / the per-key override.",
        }

    if env_name and bootstrap and persisted_empty:
        return {
            "kind": "from_env",
            "label": f"From env {env_name} (not overridden)",
            "env_var": env_name,
            "forced": False,
            "editable": True,
            "helper": "Save keeps this value in swarm_config.json (then badge → Overrides…).",
        }

    if env_name and bootstrap and not persisted_empty and str(persisted).strip() != bootstrap:
        return {
            "kind": "overrides_env",
            "label": f"Overrides env {env_name}",
            "env_var": env_name,
            "forced": False,
            "editable": True,
            "helper": f".env still has {env_name}; this instance uses Settings.",
        }

    if not persisted_empty:
        return {
            "kind": "from_config",
            "label": "From config",
            "env_var": env_name,
            "forced": False,
            "editable": True,
            "helper": "",
        }

    return {
        "kind": "built_in",
        "label": "Built-in default",
        "env_var": env_name,
        "forced": False,
        "editable": True,
        "helper": "Neither file nor env.",
    }


# Human + machine inventory. Every product key is listed — zero silent gaps.
_INVENTORY: tuple[dict[str, Any], ...] = (
    {
        "key": "llm",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/llm/",
        "settings_section": "llm-profiles",
        "ui": "pane",
        "secret_fields": ["api_key"],
        "env_twins": {"api_key": "(per-profile ${VAR})", "base_url": "OPENAI_BASE_URL"},
        "notes": (
            "Named profiles. api_key must be ${VAR}. CRUD via Settings → LLM profiles. "
            "Optional user-defined rate_limits (messages/requests/tokens per minute or day) "
            "live on the profile — empty means unlimited. Local swarm_config, not Neon."
        ),
    },
    {
        "key": "settings.default_llm_profile",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/llm-profiles/",
        "settings_section": "llm-profiles",
        "ui": "pane",
        "secret_fields": [],
        "env_twins": {"settings.default_llm_profile": "DEFAULT_LLM"},
        "notes": "Default picker. Force-env uses DEFAULT_LLM read-only.",
    },
    {
        "key": "settings.override_per_task",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/llm-profiles/",
        "settings_section": "llm-profiles",
        "ui": "pane",
        "secret_fields": [],
        "env_twins": {},
        "notes": "Boolean; no env twin.",
    },
    {
        "key": "settings.task_llm_profiles",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/llm-profiles/",
        "settings_section": "llm-profiles",
        "ui": "pane",
        "secret_fields": [],
        "env_twins": {},
        "notes": "orchestration / auxiliary / delegation map.",
    },
    {
        "key": "mcpServers",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/mcpServers/",
        "settings_section": "mcp",
        "ui": "pane",
        "secret_fields": ["api_key", "env", "headers"],
        "env_twins": {},
        "notes": "MCP server map (Plugins manage). env/headers values must be ${VAR}.",
    },
    {
        "key": "remotes",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/remotes/",
        "settings_section": "remotes",
        "ui": "pane",
        "secret_fields": ["api_key", "cookie"],
        "env_twins": {
            "hermes.base_url": "HERMES_BASE_URL",
            "omb.base_url": "OMB_BASE_URL",
            "rakazo.base_url": "RAKAZO_BASE_URL",
            "herdr.base_url": "HERDR_BASE_URL",
            "swarm.base_url": "SWARM_REMOTE_BASE_URL",
        },
        "notes": (
            "Opt-in catalog. Auth is env-name / ${VAR} only. Hybrid precedence for URLs. "
            "Optional user-defined rate_limits on the remote inference row (empty = unlimited)."
        ),
    },
    {
        "key": "cli_agents",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/cli_agents/",
        "settings_section": "cli-agents",
        "ui": "pane",
        "secret_fields": [],
        "env_twins": {},
        "notes": (
            "Opt-in catalog (REQ-157). Empty until + Add. PATH discovery seeds suggestions "
            "only — never auth-check or store CLI secrets. Optional user-defined rate_limits "
            "on the catalog row (empty = unlimited; no baked vendor quotas)."
        ),
    },
    {
        "key": "agent_team",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/agent-team/",
        "settings_section": "remotes",
        "ui": "pane",
        "secret_fields": [],
        "env_twins": {},
        "notes": "Handoff Team roster (not /v1/teams/ aliases).",
    },
    {
        "key": "cli_fusion",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/cli_fusion/",
        "settings_section": "system",
        "ui": "advanced",
        "secret_fields": [],
        "env_twins": {},
        "notes": "MoA / fusion composition. Write API + CLI `cli-agents --init`; Settings lists as advanced.",
    },
    {
        "key": "cli_map",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/cli_map/",
        "settings_section": "system",
        "ui": "advanced",
        "secret_fields": [],
        "env_twins": {},
        "notes": "CLI map composition. Advanced — write via API or swarm-cli.",
    },
    {
        "key": "cli_orchestrator",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/cli_orchestrator/",
        "settings_section": "system",
        "ui": "advanced",
        "secret_fields": [],
        "env_twins": {},
        "notes": "CLI orchestrator composition. Advanced — write via API or swarm-cli.",
    },
    {
        "key": "moa",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/moa/",
        "settings_section": "system",
        "ui": "advanced",
        "secret_fields": [],
        "env_twins": {},
        "notes": "Mixture-of-Agents block. Advanced — `swarm-cli moa-init` or PATCH section.",
    },
    {
        "key": "slashCommands",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/slashCommands/",
        "settings_section": "system",
        "ui": "advanced",
        "secret_fields": [],
        "env_twins": {},
        "notes": "Interactive-shell slash templates. Advanced — write via API or hand-edit.",
    },
    {
        "key": "blueprints",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/blueprints/",
        "settings_section": "system",
        "ui": "advanced",
        "secret_fields": [],
        "env_twins": {},
        "notes": "Per-blueprint default_model map. Advanced — Settings Blueprints inspects recipes, not this map.",
    },
    {
        "key": "memory",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/config/sections/memory/",
        "settings_section": "system",
        "ui": "advanced",
        "secret_fields": ["api_key"],
        "env_twins": {},
        "notes": "Experimental mem0 block. Advanced. Secrets in this block must be ${VAR}.",
    },
    {
        "key": "speech",
        "partition": "webui",
        "sot": "swarm_config.json",
        "write_api": "/v1/speech/",
        "settings_section": "speech",
        "ui": "pane",
        "secret_fields": ["api_key"],
        "env_twins": {
            "stt.base_url": "SPEECH_STT_BASE_URL",
            "tts.base_url": "SPEECH_TTS_BASE_URL",
        },
        "notes": (
            "REQ-77 mic STT + read-aloud TTS. Default source is system/browser. "
            "Custom OpenAI-compat audio endpoints are opt-in. api_key must be ${VAR}."
        ),
    },
    {
        "key": "secrets.*",
        "partition": "env_only",
        "sot": "process env / .env",
        "write_api": None,
        "settings_section": "system",
        "ui": "inspector",
        "secret_fields": ["*"],
        "env_twins": {},
        "notes": "Provider keys, API_AUTH_TOKEN, DJANGO_SECRET_KEY. Settings shows set / not set only.",
    },
    {
        "key": "deploy.HOST",
        "partition": "env_only",
        "sot": "process env / .env",
        "write_api": None,
        "settings_section": None,
        "ui": "ops",
        "secret_fields": [],
        "env_twins": {"HOST": "HOST"},
        "notes": "Server bind. Ops-owned; WebUI refuses writes.",
    },
    {
        "key": "deploy.PORT",
        "partition": "env_only",
        "sot": "process env / .env",
        "write_api": None,
        "settings_section": None,
        "ui": "ops",
        "secret_fields": [],
        "env_twins": {"PORT": "PORT"},
        "notes": "Server bind. Ops-owned; WebUI refuses writes.",
    },
    {
        "key": "deploy.DJANGO_*",
        "partition": "env_only",
        "sot": "process env / .env",
        "write_api": None,
        "settings_section": "system",
        "ui": "ops",
        "secret_fields": ["DJANGO_SECRET_KEY"],
        "env_twins": {},
        "notes": "Django deploy flags. Inspector only.",
    },
    {
        "key": "deploy.DATABASE_URL",
        "partition": "env_only",
        "sot": "process env / .env",
        "write_api": None,
        "settings_section": None,
        "ui": "ops",
        "secret_fields": ["DATABASE_URL"],
        "env_twins": {"DATABASE_URL": "DATABASE_URL"},
        "notes": "DB DSN. Never written by Settings.",
    },
)


def inventory() -> list[dict[str, Any]]:
    """Copy of the ownership table (machine-readable)."""
    return [dict(row) for row in _INVENTORY]


def webui_section_names() -> tuple[str, ...]:
    return WEBUI_SECTIONS


def is_webui_section(section: str) -> bool:
    return section in WEBUI_SECTIONS


def refuse_out_of_partition(section: str) -> None:
    if is_webui_section(section):
        return
    raise ConfigOwnershipError(
        f"Section {section!r} is out of the WebUI partition "
        f"(secrets/deploy stay env-only; product keys: {', '.join(WEBUI_SECTIONS)}).",
        status=403,
        code="out_of_partition",
    )


def _walk_refuse_secrets(obj: Any, *, path: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else str(key)
            if is_secret_key(str(key)):
                _refuse_secret_value(str(key), value, path=child)
            _walk_refuse_secrets(value, path=child)
        return
    if isinstance(obj, list):
        for index, item in enumerate(obj):
            _walk_refuse_secrets(item, path=f"{path}[{index}]")


def _refuse_secret_value(key: str, value: Any, *, path: str) -> None:
    if value is None or value == "":
        return
    if isinstance(value, dict):
        # mcpServers.*.env — each secret-looking env *value* must be ${VAR}.
        for nested_key, nested_val in value.items():
            if is_secret_key(str(nested_key)) or is_secret_key(key):
                _refuse_secret_value(str(nested_key), nested_val, path=f"{path}.{nested_key}")
        return
    if not isinstance(value, str):
        raise ConfigOwnershipError(
            f"Refusing to persist plaintext secret at {path}: value must be a ${{VAR}} placeholder.",
            status=400,
            code="plaintext_secret",
        )
    trimmed = value.strip()
    if is_placeholder(trimmed) or looks_like_env_name(trimmed):
        return
    raise ConfigOwnershipError(
        f"Refusing to persist plaintext secret at {path}. Use ${{ENV_VAR}} or an env-var name.",
        status=400,
        code="plaintext_secret",
    )


def refuse_plaintext_secrets(payload: Any) -> None:
    _walk_refuse_secrets(payload)


def refresh_app_config(cfg: dict[str, Any] | None = None) -> None:
    """Keep Django ``AppConfig.config`` aligned with the live file (ADR-002 §3.1)."""
    try:
        from django.apps import apps

        if not apps.ready:
            return
        app = apps.get_app_config("swarm")
    except Exception:
        logger.debug("AppConfig refresh skipped (Django not ready)", exc_info=True)
        return
    if cfg is None:
        try:
            from swarm.apps import SwarmConfig

            cfg = SwarmConfig._load_swarm_config()
        except Exception:
            logger.debug("AppConfig reload skipped", exc_info=True)
            return
    else:
        try:
            from swarm.core.config_loader import _substitute_env_vars

            cfg = _substitute_env_vars(cfg)
        except Exception:
            pass
    app.config = cfg


def _load_raw(config_path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    from swarm.core.remotes import load_raw_config

    return load_raw_config(config_path)


def _write_cfg(cfg: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    refresh_app_config(cfg)
    return path


def persist_webui_section(
    section: str,
    *,
    entries: dict[str, Any] | None = None,
    upsert: dict[str, Any] | None = None,
    delete: list[str] | str | None = None,
    config_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Write one WebUI-owned top-level section. Refuses secrets / ops keys."""
    refuse_out_of_partition(section)
    if entries is not None:
        refuse_plaintext_secrets(entries)
    if upsert is not None:
        refuse_plaintext_secrets(upsert)

    cfg, path = _load_raw(config_path)
    current = cfg.get(section)
    if not isinstance(current, dict):
        current = {}
    current = dict(current)

    if entries is not None:
        if not isinstance(entries, dict):
            raise ConfigOwnershipError("entries must be an object.", status=400, code="bad_payload")
        current = dict(entries)
    if upsert:
        if not isinstance(upsert, dict):
            raise ConfigOwnershipError("upsert must be an object.", status=400, code="bad_payload")
        for name, value in upsert.items():
            key = str(name).strip()
            if not key:
                raise ConfigOwnershipError("upsert keys must be non-empty names.", status=400)
            current[key] = value
    if delete is not None:
        names = [delete] if isinstance(delete, str) else list(delete)
        for name in names:
            current.pop(str(name), None)

    refuse_plaintext_secrets(current)
    cfg[section] = current
    if "llm" not in cfg or not isinstance(cfg.get("llm"), dict):
        cfg.setdefault("llm", {})
    written = _write_cfg(cfg, path)
    logger.info("Persisted swarm_config section %s to %s", section, written)
    return current, written


def public_section(section: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Redacted view of one section (no secret values)."""
    refuse_out_of_partition(section)
    cfg = config if isinstance(config, dict) else _load_raw()[0]
    raw = cfg.get(section)
    if not isinstance(raw, dict):
        raw = {}
    return redact_for_api(raw)


def redact_for_api(obj: Any) -> Any:
    """Replace secret values with placeholder / env-name metadata."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if is_secret_key(str(key)):
                if isinstance(value, dict):
                    out[key] = redact_for_api(value)
                else:
                    env_name = placeholder_env_name(value) or (
                        value.strip() if looks_like_env_name(value) else ""
                    )
                    out[key] = f"${{{env_name}}}" if env_name else ""
                    out[f"{key}_env"] = env_name
                    out[f"{key}_set"] = env_is_set(env_name)
            else:
                out[key] = redact_for_api(value)
        return out
    if isinstance(obj, list):
        return [redact_for_api(item) for item in obj]
    return obj


def default_llm_provenance(config: dict[str, Any] | None = None) -> dict[str, Any]:
    from swarm.core.llm_task_routing import stored_default_profile

    cfg = config if isinstance(config, dict) else _load_raw()[0]
    stored = stored_default_profile(cfg)
    return badge_for(env_var="DEFAULT_LLM", persisted=stored, secret=False)


def ownership_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET /v1/config-ownership/ body. No secrets."""
    cfg = config if isinstance(config, dict) else _load_raw()[0]
    return {
        "object": "config_ownership",
        "decision": DECISION,
        "note": DECISION_NOTE,
        "issue": ISSUE,
        "adr": ADR,
        "force_env": force_env_enabled(),
        "force_env_var": FORCE_ENV_VAR,
        "precedence": [
            "force-env (SWARM_CONFIG_FORCE_ENV or SWARM_<KEY>_OVERRIDE)",
            "persisted swarm_config.json",
            "env bootstrap (empty persisted key)",
            "built-in defaults",
        ],
        "webui_sections": list(WEBUI_SECTIONS),
        "advanced_sections": list(ADVANCED_SECTIONS),
        "settings_panes": dict(SETTINGS_PANES),
        "inventory": inventory(),
        "default_llm_profile": default_llm_provenance(cfg),
        "sibling_775": (
            "Example file is swarm_config.example.json at repo root. "
            "#775 may move it; keep the filename *example* and gitignore live swarm_config.json."
        ),
    }

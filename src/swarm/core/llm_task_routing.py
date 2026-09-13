"""REQ-43 / #358 — default LLM + per-task-class routing.

Task classes (roles, not required model ids):

- ``orchestration`` — mid, user-facing chat
- ``auxiliary`` — cheapest / fastest (code summary, cheap analyse)
- ``delegation`` — smartest / most expensive (blueprint design / coding)

``orchestration`` / ``auxiliary`` / ``delegation`` are optional LiteLLM-style
aliases. Most catalogs use boring ids (``gpt-5.6-terra``). Auto-pick chooses
three models from whatever the user connected (CLI, API vendor, remote). If
the user never opens Settings, those auto-picks **are** the defaults. CLI
lists come from sibling #360 (`{cli, models}`) when that helper is present;
otherwise the picker stubs on ``/v1/models`` + fixtures and never scrapes
``--help``.

Persistence is the existing SoT: ``settings.default_llm_profile`` plus
``settings.override_per_task`` and ``settings.task_llm_profiles``. Do not
invent a parallel model list.

#356 hook: when the role/blueprint/team code summariser lands, call
:func:`resolve_summary_model` (auxiliary when override is on).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from swarm.core import cli_catalog, inference_profile, llm_list_models

logger = logging.getLogger("swarm.llm_task_routing")

TASK_CLASS_ORCHESTRATION = "orchestration"
TASK_CLASS_AUXILIARY = "auxiliary"
TASK_CLASS_DELEGATION = "delegation"

TASK_CLASSES: tuple[str, ...] = (
    TASK_CLASS_ORCHESTRATION,
    TASK_CLASS_AUXILIARY,
    TASK_CLASS_DELEGATION,
)

# #356 code-summary jobs honour this map (auxiliary when override on).
TASK_CLASS_SUMMARY = TASK_CLASS_AUXILIARY
# Blueprint design / coding-class work.
TASK_CLASS_DESIGN = TASK_CLASS_DELEGATION
# User chat / server default when override is on.
TASK_CLASS_CHAT = TASK_CLASS_ORCHESTRATION

SETTINGS_DEFAULT_KEY = "default_llm_profile"
SETTINGS_OVERRIDE_KEY = "override_per_task"
SETTINGS_TASK_MAP_KEY = "task_llm_profiles"

BUILTIN_FALLBACK = "default"

# Intent targets for auto-pick (cost = cheapness, matching inference_profile).
TASK_TARGETS: dict[str, dict[str, float]] = {
    TASK_CLASS_AUXILIARY: {"speed": 1.0, "cost": 1.0},
    TASK_CLASS_ORCHESTRATION: {"intelligence": 0.65, "speed": 0.60, "cost": 0.50},
    TASK_CLASS_DELEGATION: {"intelligence": 1.0},
}

# Pick extremes first so the leftover mid id becomes orchestration.
_PICK_ORDER: tuple[str, ...] = (
    TASK_CLASS_AUXILIARY,
    TASK_CLASS_DELEGATION,
    TASK_CLASS_ORCHESTRATION,
)

# Built-in preferred ids per known vendor/CLI. Boring ids are valid. No single
# cloud vendor is the only path — local OpenAI-compatible ids always participate.
VENDOR_PREFERRED: dict[str, dict[str, tuple[str, ...]]] = {
    "openai": {
        TASK_CLASS_AUXILIARY: (
            "gpt-4o-mini",
            "gpt-4.1-nano",
            "gpt-4.1-mini",
            "gpt-3.5-turbo-instruct",
            "gpt-3.5-turbo",
        ),
        TASK_CLASS_ORCHESTRATION: (
            "gpt-5.6-terra",
            "gpt-4o",
            "gpt-4.1",
            "gpt-4",
        ),
        TASK_CLASS_DELEGATION: ("o3", "o3-pro", "o1", "o1-pro", "o1-preview", "gpt-5"),
    },
    "anthropic": {
        TASK_CLASS_AUXILIARY: ("claude-haiku-4-5", "claude-3-haiku", "claude-haiku"),
        TASK_CLASS_ORCHESTRATION: (
            "claude-sonnet-4-6",
            "claude-3.5-sonnet",
            "claude-sonnet",
        ),
        TASK_CLASS_DELEGATION: ("claude-opus-4-8", "claude-3-opus", "claude-opus"),
    },
    "gemini": {
        TASK_CLASS_AUXILIARY: (
            "gemini-3-flash-preview",
            "gemini-2.0-flash",
            "gemini-flash",
        ),
        TASK_CLASS_ORCHESTRATION: ("gemini-2.5-pro", "gemini-1.5-pro", "gemini-pro"),
        TASK_CLASS_DELEGATION: ("gemini-3-pro-preview", "gemini-ultra"),
    },
    "groq": {
        TASK_CLASS_AUXILIARY: ("llama-3.1-8b", "llama3.2", "gemma"),
        TASK_CLASS_ORCHESTRATION: ("llama-3.1-70b", "mixtral"),
        TASK_CLASS_DELEGATION: ("llama-3.1-405b", "deepseek-r1"),
    },
    "openrouter": {
        TASK_CLASS_AUXILIARY: ("openrouter/gpt-4o-mini", "openrouter/haiku"),
        TASK_CLASS_ORCHESTRATION: ("openrouter/gpt-4o", "openrouter/sonnet"),
        TASK_CLASS_DELEGATION: ("openrouter/o3", "openrouter/opus"),
    },
    "litellm": {
        TASK_CLASS_AUXILIARY: ("auxiliary", "litellm-fast"),
        TASK_CLASS_ORCHESTRATION: ("orchestration", "litellm"),
        TASK_CLASS_DELEGATION: ("delegation", "litellm-reason"),
    },
    "grok": {
        TASK_CLASS_AUXILIARY: ("grok-3-mini", "grok-2-mini"),
        TASK_CLASS_ORCHESTRATION: ("grok-3", "grok-2", "grok"),
        TASK_CLASS_DELEGATION: ("grok-4", "grok-3-reasoning"),
    },
    "claude": {
        TASK_CLASS_AUXILIARY: ("claude-haiku-4-5", "claude-haiku"),
        TASK_CLASS_ORCHESTRATION: ("claude-sonnet-4-6", "claude-sonnet"),
        TASK_CLASS_DELEGATION: ("claude-opus-4-8", "claude-opus"),
    },
    "codex": {
        TASK_CLASS_AUXILIARY: ("codex-mini", "gpt-4o-mini"),
        TASK_CLASS_ORCHESTRATION: ("codex", "gpt-5.6-terra"),
        TASK_CLASS_DELEGATION: ("o3", "codex-pro"),
    },
    "opencode": {
        TASK_CLASS_AUXILIARY: ("litellm/orchestration",),
        TASK_CLASS_ORCHESTRATION: ("litellm/orchestration",),
        TASK_CLASS_DELEGATION: ("opencode/pro",),
    },
}

# Name / size hints. First match wins — cheap/fast needles before family names
# so ``gpt-4o-mini`` scores as auxiliary, not mid-tier gpt-4o.
_NAME_HINTS: tuple[tuple[str, dict[str, float]], ...] = (
    ("haiku", {"intelligence": 0.35, "speed": 0.95, "cost": 0.95}),
    ("flash", {"intelligence": 0.40, "speed": 0.95, "cost": 0.92}),
    ("nano", {"intelligence": 0.25, "speed": 0.96, "cost": 0.96}),
    ("mini", {"intelligence": 0.35, "speed": 0.90, "cost": 0.90}),
    ("lite", {"intelligence": 0.35, "speed": 0.88, "cost": 0.90}),
    ("instruct", {"intelligence": 0.30, "speed": 0.85, "cost": 0.88}),
    ("8b", {"intelligence": 0.30, "speed": 0.90, "cost": 0.92}),
    ("7b", {"intelligence": 0.30, "speed": 0.90, "cost": 0.92}),
    ("small", {"intelligence": 0.35, "speed": 0.85, "cost": 0.88}),
    ("fast", {"intelligence": 0.40, "speed": 0.90, "cost": 0.85}),
    ("o3-pro", {"intelligence": 0.99, "speed": 0.25, "cost": 0.10}),
    ("o1-pro", {"intelligence": 0.97, "speed": 0.28, "cost": 0.12}),
    ("opus", {"intelligence": 0.98, "speed": 0.40, "cost": 0.20}),
    ("ultra", {"intelligence": 0.95, "speed": 0.35, "cost": 0.20}),
    ("405b", {"intelligence": 0.93, "speed": 0.30, "cost": 0.25}),
    ("o3", {"intelligence": 0.96, "speed": 0.35, "cost": 0.18}),
    ("o1", {"intelligence": 0.94, "speed": 0.38, "cost": 0.22}),
    ("reason", {"intelligence": 0.90, "speed": 0.40, "cost": 0.30}),
    ("gpt-5.6-terra", {"intelligence": 0.70, "speed": 0.65, "cost": 0.50}),
    ("gpt-5.6", {"intelligence": 0.72, "speed": 0.62, "cost": 0.48}),
    ("sonnet", {"intelligence": 0.82, "speed": 0.70, "cost": 0.55}),
    ("gpt-4o", {"intelligence": 0.75, "speed": 0.70, "cost": 0.50}),
    ("gpt-4.1", {"intelligence": 0.78, "speed": 0.68, "cost": 0.48}),
    ("70b", {"intelligence": 0.70, "speed": 0.55, "cost": 0.50}),
    ("terra", {"intelligence": 0.68, "speed": 0.65, "cost": 0.52}),
    ("gpt-4", {"intelligence": 0.72, "speed": 0.55, "cost": 0.40}),
    ("pro", {"intelligence": 0.85, "speed": 0.50, "cost": 0.35}),
)

_SECRET_KEY_NEEDLES = ("api_key", "apikey", "token", "secret", "password", "cookie")
_PUBLIC_PROFILE_KEYS = (
    "provider",
    "model",
    "base_url",
    "intelligence",
    "speed",
    "cost",
    "temperature",
    "max_tokens",
    "description",
    "context_length",
    "context_window",
    "max_context",
)


@dataclass(frozen=True)
class CatalogEntry:
    """One pickable model / profile id. Never carries secrets."""

    id: str
    source: str
    owned_by: str
    model: str | None = None
    base_url: str | None = None
    traits: dict[str, float] = field(default_factory=dict)
    context_length: int | None = None

    def public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "object": "llm_profile",
            "source": self.source,
            "owned_by": self.owned_by,
        }
        if self.model:
            payload["model"] = self.model
        if self.base_url:
            payload["base_url"] = self.base_url
        if self.context_length:
            payload["context_length"] = self.context_length
        for axis in inference_profile.TRAITS:
            if axis in self.traits:
                payload[axis] = self.traits[axis]
        return payload


@dataclass(frozen=True)
class AutoPickResult:
    picks: dict[str, str]
    default: str
    warnings: list[str] = field(default_factory=list)
    aliases_used: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TaskRoute:
    """Resolved profile for one task class. Safe to log / return to the SPA."""

    profile: str
    task_class: str
    used_fallback: bool = False
    warning: str | None = None
    override_on: bool = False
    source: str = "default"

    def public_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "task_class": self.task_class,
            "used_fallback": self.used_fallback,
            "warning": self.warning,
            "override_on": self.override_on,
            "source": self.source,
        }


def is_task_class(value: object) -> bool:
    return isinstance(value, str) and value in TASK_CLASSES


def settings_block(config: dict[str, Any] | None) -> dict[str, Any]:
    block = (config or {}).get("settings")
    return block if isinstance(block, dict) else {}


def stored_default_profile(config: dict[str, Any] | None) -> str | None:
    settings = settings_block(config)
    for key in (SETTINGS_DEFAULT_KEY, "default_llm"):
        value = settings.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def override_per_task_enabled(config: dict[str, Any] | None) -> bool:
    value = settings_block(config).get(SETTINGS_OVERRIDE_KEY, False)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def stored_task_map(config: dict[str, Any] | None) -> dict[str, str]:
    raw = settings_block(config).get(SETTINGS_TASK_MAP_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if is_task_class(key) and isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(needle in lowered for needle in _SECRET_KEY_NEEDLES)


def public_profile_fields(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Copy non-secret profile fields for API / Settings display."""
    if not isinstance(profile, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in profile.items():
        if _is_secret_key(str(key)):
            continue
        if key not in _PUBLIC_PROFILE_KEYS:
            continue
        out[key] = value
    return out


def _llm_section(config: dict[str, Any] | None) -> dict[str, Any]:
    section = (config or {}).get("llm")
    return section if isinstance(section, dict) else {}


def iter_llm_profiles(config: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    """Yield ``(name, profile_dict)`` from ``llm`` and legacy ``llm.profiles``."""
    llm = _llm_section(config)
    rows: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for name, value in llm.items():
        if name == "profiles" and isinstance(value, dict):
            for nested_name, nested in value.items():
                if nested_name in seen or not isinstance(nested, dict):
                    continue
                seen.add(str(nested_name))
                rows.append((str(nested_name), nested))
            continue
        if name in seen or not isinstance(value, dict):
            continue
        seen.add(str(name))
        rows.append((str(name), value))
    return rows


def profile_exists(profile_id: str, config: dict[str, Any] | None) -> bool:
    if not profile_id:
        return False
    known = {name for name, _ in iter_llm_profiles(config)}
    if profile_id in known:
        return True
    for name, profile in iter_llm_profiles(config):
        model = profile.get("model")
        if isinstance(model, str) and model.strip() == profile_id:
            return True
        if name == profile_id:
            return True
    return False


def get_profile_dict(profile_id: str, config: dict[str, Any] | None) -> dict[str, Any] | None:
    for name, profile in iter_llm_profiles(config):
        if name == profile_id:
            return profile
    for _name, profile in iter_llm_profiles(config):
        model = profile.get("model")
        if isinstance(model, str) and model.strip() == profile_id:
            return profile
    return None


def model_id_for_profile(profile_id: str, config: dict[str, Any] | None) -> str:
    """Gateway model slug for a picked id. Env-template models stay as the id."""
    profile = get_profile_dict(profile_id, config)
    if not profile:
        return profile_id
    model = profile.get("model")
    if isinstance(model, str):
        trimmed = model.strip()
        if trimmed and not trimmed.startswith("${"):
            return trimmed
    return profile_id


def traits_from_name(model_id: str) -> dict[str, float] | None:
    lowered = model_id.lower()
    for needle, traits in _NAME_HINTS:
        if needle in lowered:
            return dict(traits)
    return None


def infer_vendor(entry_id: str, profile: dict[str, Any] | None = None, *, owned_by: str = "") -> str:
    blob = " ".join(
        part.lower()
        for part in (
            entry_id,
            owned_by,
            str((profile or {}).get("provider") or ""),
            str((profile or {}).get("base_url") or ""),
            str((profile or {}).get("model") or ""),
        )
        if part
    )
    checks = (
        ("anthropic", ("anthropic", "claude")),
        ("gemini", ("gemini", "googleapis", "google")),
        ("groq", ("groq",)),
        ("openrouter", ("openrouter",)),
        ("grok", ("grok", "x.ai")),
        ("codex", ("codex",)),
        ("opencode", ("opencode",)),
        ("litellm", ("litellm",)),
        ("openai", ("openai", "api.openai.com")),
    )
    for vendor, needles in checks:
        if any(needle in blob for needle in needles):
            return vendor
    return "local"


def resolve_traits(
    entry_id: str,
    profile: dict[str, Any] | None = None,
    *,
    owned_by: str = "",
) -> dict[str, float]:
    """Best available 0..1 traits: explicit tags, catalog, then name hints."""
    tagged: dict[str, float] = {}
    if isinstance(profile, dict):
        for axis in inference_profile.TRAITS:
            if axis in profile:
                tagged[axis] = inference_profile._clamp(profile.get(axis))
        if tagged:
            return inference_profile.normalize(tagged)

    catalog_model = cli_catalog.model_traits(entry_id)
    if catalog_model:
        return inference_profile.normalize(catalog_model)

    model_field = (profile or {}).get("model") if isinstance(profile, dict) else None
    if isinstance(model_field, str):
        catalog_model = cli_catalog.model_traits(model_field)
        if catalog_model:
            return inference_profile.normalize(catalog_model)

    cli_default = cli_catalog.cli_traits(entry_id) or cli_catalog.cli_traits(owned_by)
    if cli_default:
        hinted = traits_from_name(entry_id)
        if hinted:
            merged = dict(cli_default)
            merged.update(hinted)
            return inference_profile.normalize(merged)
        return inference_profile.normalize(cli_default)

    hinted = traits_from_name(entry_id)
    if hinted:
        return inference_profile.normalize(hinted)
    if isinstance(model_field, str):
        hinted = traits_from_name(model_field)
        if hinted:
            return inference_profile.normalize(hinted)
    return inference_profile.normalize(None)


def _preferred_for_class(task_class: str, vendor: str, available: Iterable[str]) -> str | None:
    preferred = VENDOR_PREFERRED.get(vendor, {}).get(task_class) or ()
    available_set = set(available)
    lowered = {name.lower(): name for name in available_set}
    for candidate in preferred:
        if candidate in available_set:
            return candidate
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
        needle = candidate.lower()
        for name in available_set:
            hay = name.lower()
            if (
                hay.startswith(f"{needle}-")
                or hay.startswith(f"{needle}/")
                or hay.endswith(f"-{needle}")
            ):
                return name
    return None


def auto_pick_task_models(
    catalog: Iterable[str] | Iterable[CatalogEntry],
    *,
    aliases: Iterable[str] | None = None,
    traits: dict[str, dict[str, float]] | None = None,
    vendors: dict[str, str] | None = None,
) -> AutoPickResult:
    """Pick three distinct class mappings from a catalog.

    Alias profiles named orchestration/auxiliary/delegation win when present.
    Empty catalog warns and falls back to ``default`` — never raises.
    """
    entries: list[CatalogEntry] = []
    for item in catalog:
        if isinstance(item, CatalogEntry):
            entries.append(item)
        elif isinstance(item, str) and item.strip():
            entries.append(
                CatalogEntry(
                    id=item.strip(),
                    source="catalog",
                    owned_by="unknown",
                    traits=resolve_traits(item.strip()),
                )
            )
    ids = [entry.id for entry in entries]
    warnings: list[str] = []
    if not ids:
        warning = "No models in catalog; falling back to 'default'."
        logger.warning(warning)
        return AutoPickResult(
            picks={cls: BUILTIN_FALLBACK for cls in TASK_CLASSES},
            default=BUILTIN_FALLBACK,
            warnings=[warning],
        )

    alias_set = {name for name in (aliases or ids) if name in TASK_CLASSES and name in ids}
    picks: dict[str, str] = {}
    aliases_used: list[str] = []
    remaining = list(dict.fromkeys(ids))

    for cls in TASK_CLASSES:
        if cls in alias_set and cls in remaining:
            picks[cls] = cls
            aliases_used.append(cls)
            remaining.remove(cls)

    trait_map: dict[str, dict[str, float]] = {}
    vendor_map: dict[str, str] = dict(vendors or {})
    for entry in entries:
        trait_map[entry.id] = entry.traits or resolve_traits(entry.id)
        vendor_map.setdefault(entry.id, infer_vendor(entry.id, owned_by=entry.owned_by))
    if traits:
        for name, value in traits.items():
            trait_map[name] = inference_profile.normalize(value)

    for cls in _PICK_ORDER:
        if cls in picks:
            continue
        if not remaining:
            reuse = picks.get(TASK_CLASS_ORCHESTRATION) or picks.get(TASK_CLASS_AUXILIARY) or ids[0]
            picks[cls] = reuse
            warnings.append(
                f"Not enough distinct models for {cls}; reusing {reuse!r}."
            )
            continue
        vendor_hit = None
        for candidate in list(remaining):
            preferred = _preferred_for_class(cls, vendor_map.get(candidate, "local"), remaining)
            if preferred and preferred in remaining:
                vendor_hit = preferred
                break
        if vendor_hit:
            picks[cls] = vendor_hit
            remaining.remove(vendor_hit)
            continue
        chosen = inference_profile.resolve(
            TASK_TARGETS[cls],
            {name: trait_map.get(name, inference_profile.normalize(None)) for name in remaining},
        )
        if chosen is None:
            chosen = remaining[0]
        picks[cls] = chosen
        remaining.remove(chosen)

    default = picks.get(TASK_CLASS_ORCHESTRATION) or ids[0]
    return AutoPickResult(
        picks=picks,
        default=default,
        warnings=warnings,
        aliases_used=aliases_used,
    )


def collect_catalog(
    config: dict[str, Any] | None,
    *,
    discovery_payloads: Iterable[Any] | None = None,
) -> list[CatalogEntry]:
    """Connected CLIs, API profiles, remotes, plus REQ-44 ``{cli, models}``.

    Does not scrape CLI ``--help``. Live lists come from #360's helper when
    present; otherwise OpenAI ``/v1/models`` + fixtures (see
    :mod:`swarm.core.llm_list_models`).
    """
    from swarm.core.context_compress_policy import context_length_from_mapping

    config = config or {}
    entries: list[CatalogEntry] = []
    seen: set[str] = set()

    def _add(entry: CatalogEntry) -> None:
        if not entry.id or entry.id in seen:
            return
        seen.add(entry.id)
        entries.append(entry)

    for name, profile in iter_llm_profiles(config):
        vendor = infer_vendor(name, profile)
        traits = resolve_traits(name, profile, owned_by=vendor)
        model = profile.get("model") if isinstance(profile.get("model"), str) else None
        model_id = model.strip() if isinstance(model, str) else None
        if model_id and model_id.startswith("${"):
            model_id = None
        window = context_length_from_mapping(profile)
        raw_base = profile.get("base_url")
        base_url = raw_base.strip() if isinstance(raw_base, str) and raw_base.strip() else None
        _add(
            CatalogEntry(
                id=name,
                source="config",
                owned_by=str(profile.get("provider") or vendor),
                model=model_id,
                base_url=base_url,
                traits=traits,
                context_length=window,
            )
        )
        if model_id and model_id != name:
            _add(
                CatalogEntry(
                    id=model_id,
                    source="config",
                    owned_by=str(profile.get("provider") or vendor),
                    model=model_id,
                    base_url=base_url,
                    traits=resolve_traits(model_id, profile, owned_by=vendor),
                    context_length=window,
                )
            )

    cli_agents = config.get("cli_agents")
    if isinstance(cli_agents, dict):
        for name in cli_agents:
            traits = resolve_traits(str(name), owned_by=str(name))
            _add(
                CatalogEntry(
                    id=str(name),
                    source="cli",
                    owned_by=str(name),
                    traits=traits,
                )
            )

    remotes = config.get("remotes")
    if isinstance(remotes, dict):
        for remote_id, spec in remotes.items():
            if not isinstance(spec, dict):
                continue
            if not spec.get("base_url"):
                continue
            rid = str(remote_id)
            _add(
                CatalogEntry(
                    id=rid,
                    source="remote",
                    owned_by=rid,
                    traits=resolve_traits(rid, owned_by=rid),
                )
            )
            models = spec.get("models")
            if isinstance(models, list):
                for model in models:
                    if isinstance(model, str) and model.strip():
                        mid = model.strip()
                        _add(
                            CatalogEntry(
                                id=mid,
                                source="remote",
                                owned_by=rid,
                                model=mid,
                                traits=resolve_traits(mid, owned_by=rid),
                            )
                        )

    if discovery_payloads is None:
        discovery_payloads = []
    for row in llm_list_models.normalize_list_models_payload(
        list(discovery_payloads) if not isinstance(discovery_payloads, list) else discovery_payloads
    ):
        cli = str(row.get("cli") or "catalog")
        for mid in row.get("models") or []:
            if not isinstance(mid, str) or not mid.strip():
                continue
            model_id = mid.strip()
            _add(
                CatalogEntry(
                    id=model_id,
                    source="list_models",
                    owned_by=cli,
                    model=model_id,
                    traits=resolve_traits(model_id, owned_by=cli),
                )
            )

    return entries


def discover_and_collect(
    config: dict[str, Any] | None,
    *,
    discovery_payloads: Iterable[Any] | None = None,
    probe: bool | None = None,
) -> tuple[list[CatalogEntry], list[dict[str, Any]], str, list[str]]:
    """One discovery pass, then catalog. Used so Settings does not re-probe."""
    warnings: list[str] = []
    source = llm_list_models.SOURCE_STUB
    if discovery_payloads is None:
        rows, source, warnings = llm_list_models.discover_cli_model_lists(
            config, probe=probe
        )
    else:
        rows = llm_list_models.normalize_list_models_payload(list(discovery_payloads))
        source = (
            llm_list_models.SOURCE_REQ44
            if llm_list_models.req44_helper_available()
            else llm_list_models.SOURCE_STUB
        )
    catalog = collect_catalog(config, discovery_payloads=rows)
    return catalog, rows, source, warnings


def effective_auto_picks(
    config: dict[str, Any] | None,
    *,
    catalog: Iterable[CatalogEntry] | None = None,
) -> AutoPickResult:
    entries = list(catalog) if catalog is not None else collect_catalog(config)
    aliases = [entry.id for entry in entries if entry.id in TASK_CLASSES]
    vendors = {entry.id: infer_vendor(entry.id, owned_by=entry.owned_by) for entry in entries}
    return auto_pick_task_models(entries, aliases=aliases, vendors=vendors)


def effective_default_profile(
    config: dict[str, Any] | None,
    *,
    catalog: Iterable[CatalogEntry] | None = None,
) -> tuple[str, list[str]]:
    """Stored default if present, else auto-pick. Empty catalog → ``default``."""
    warnings: list[str] = []
    from swarm.core import config_ownership as ownership

    if ownership.field_is_forced("DEFAULT_LLM"):
        forced = (os.environ.get("DEFAULT_LLM") or "").strip()
        if forced:
            return forced, warnings
    stored = stored_default_profile(config)
    entries = list(catalog) if catalog is not None else collect_catalog(config)
    auto = effective_auto_picks(config, catalog=entries)
    warnings.extend(auto.warnings)
    if stored:
        if profile_exists(stored, config) or any(entry.id == stored for entry in entries):
            return stored, warnings
        warning = (
            f"LLM profile {stored!r} not found; falling back to "
            f"{auto.default!r}."
        )
        logger.warning(warning)
        warnings.append(warning)
        return auto.default, warnings
    return auto.default, warnings


def resolve_for_task(
    task_class: str,
    config: dict[str, Any] | None = None,
    *,
    catalog_ids: Iterable[str] | None = None,
    catalog: Iterable[CatalogEntry] | None = None,
) -> TaskRoute:
    """Resolve the profile id for a task class.

    Override off → everything uses Default. Override on → mapped id, else
    alias, else auto-pick, else Default + visible warning.
    """
    config = config if config is not None else load_swarm_config()
    if catalog is not None:
        entries = list(catalog)
    else:
        entries, _rows, _source, _warnings = discover_and_collect(config)
    known_ids = set(catalog_ids) if catalog_ids is not None else {e.id for e in entries}
    default, warnings = effective_default_profile(config, catalog=entries)
    cls = task_class if is_task_class(task_class) else TASK_CLASS_ORCHESTRATION
    override = override_per_task_enabled(config)
    if not override:
        extra = warnings[0] if warnings else None
        return TaskRoute(
            profile=default,
            task_class=cls,
            used_fallback=bool(extra),
            warning=extra,
            override_on=False,
            source="default",
        )

    mapped = stored_task_map(config).get(cls)
    if mapped:
        if mapped in known_ids or profile_exists(mapped, config):
            return TaskRoute(
                profile=mapped,
                task_class=cls,
                override_on=True,
                source="map",
            )
        warning = (
            f"Task profile {mapped!r} for {cls} not found; "
            f"falling back to default {default!r}."
        )
        logger.warning(warning)
        return TaskRoute(
            profile=default,
            task_class=cls,
            used_fallback=True,
            warning=warning,
            override_on=True,
            source="fallback",
        )

    auto = effective_auto_picks(config, catalog=entries)
    picked = auto.picks.get(cls)
    if picked and (picked in known_ids or profile_exists(picked, config)):
        source = "alias" if picked in TASK_CLASSES and picked in known_ids else "auto"
        return TaskRoute(
            profile=picked,
            task_class=cls,
            override_on=True,
            source=source,
        )

    warning = (
        f"No {cls} profile available; falling back to default {default!r}."
    )
    logger.warning(warning)
    return TaskRoute(
        profile=default,
        task_class=cls,
        used_fallback=True,
        warning=warning,
        override_on=True,
        source="fallback",
    )


def resolve_chat_model(config: dict[str, Any] | None = None) -> TaskRoute:
    """User chat / server default model (orchestration when override is on)."""
    return resolve_for_task(TASK_CLASS_CHAT, config)


def resolve_summary_model(config: dict[str, Any] | None = None) -> TaskRoute:
    """#356 hook — role/blueprint/team code summary uses auxiliary when override on."""
    return resolve_for_task(TASK_CLASS_SUMMARY, config)


def resolve_design_model(config: dict[str, Any] | None = None) -> TaskRoute:
    """Blueprint design / coding-class work uses delegation when override on."""
    return resolve_for_task(TASK_CLASS_DESIGN, config)


def load_swarm_config(config_path: str | Path | None = None) -> dict[str, Any]:
    from swarm.core.remotes import load_raw_config

    return load_raw_config(config_path)[0]


def persist_llm_settings(
    *,
    default_llm_profile: str | None = None,
    override_per_task: bool | None = None,
    task_llm_profiles: dict[str, str] | None = None,
    config_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Write default + override map into ``settings`` of swarm_config.json."""
    from swarm.core import config_ownership as ownership
    from swarm.core.remotes import load_raw_config

    if default_llm_profile is not None and ownership.field_is_forced("DEFAULT_LLM"):
        raise ownership.ConfigOwnershipError(
            "DEFAULT_LLM is forced by env (read-only).",
            status=409,
            code="forced_env",
        )

    cfg, path = load_raw_config(config_path)
    settings = cfg.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    settings = dict(settings)
    if default_llm_profile is not None:
        trimmed = default_llm_profile.strip()
        if trimmed:
            settings[SETTINGS_DEFAULT_KEY] = trimmed
        else:
            settings.pop(SETTINGS_DEFAULT_KEY, None)
    if override_per_task is not None:
        settings[SETTINGS_OVERRIDE_KEY] = bool(override_per_task)
    if task_llm_profiles is not None:
        cleaned = stored_task_map({ "settings": {SETTINGS_TASK_MAP_KEY: task_llm_profiles} })
        settings[SETTINGS_TASK_MAP_KEY] = cleaned
    cfg["settings"] = settings
    if "llm" not in cfg or not isinstance(cfg.get("llm"), dict):
        cfg.setdefault("llm", {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    from swarm.core.config_ownership import refresh_app_config

    refresh_app_config(cfg)
    logger.info("Persisted settings.default_llm_profile to %s", path)
    return cfg, path


def persist_named_llm_profile(
    *,
    profile_id: str,
    spec: dict[str, Any],
    set_default: bool = False,
    config_path: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Upsert one named ``llm.<id>`` profile (model + optional base_url). No secrets plaintext."""
    from swarm.core import config_ownership as ownership
    from swarm.core.remotes import load_raw_config

    pid = str(profile_id or "").strip()
    if not pid:
        raise ownership.ConfigOwnershipError(
            "profile id is required.", status=400, code="bad_payload"
        )
    if not isinstance(spec, dict):
        raise ownership.ConfigOwnershipError(
            "profile must be an object.", status=400, code="bad_payload"
        )
    model = str(spec.get("model") or "").strip()
    if not model:
        raise ownership.ConfigOwnershipError(
            "profile model is required.", status=400, code="bad_payload"
        )
    cleaned = public_profile_fields(spec)
    cleaned["model"] = model
    provider = str(spec.get("provider") or cleaned.get("provider") or "openai").strip()
    cleaned["provider"] = provider or "openai"
    if "api_key" in spec:
        cleaned["api_key"] = spec.get("api_key")
    ownership.persist_webui_section("llm", upsert={pid: cleaned}, config_path=config_path)
    if set_default:
        return persist_llm_settings(default_llm_profile=pid, config_path=config_path)
    return load_raw_config(config_path)


def settings_public_payload(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """SPA / API payload. Auto-picks fill unsaved defaults. No secrets."""
    from swarm.core import config_ownership as ownership

    config = config if config is not None else load_swarm_config()
    catalog, cli_lists, list_source, discover_warnings = discover_and_collect(config)
    auto = effective_auto_picks(config, catalog=catalog)
    default, warnings = effective_default_profile(config, catalog=catalog)
    warnings = list(discover_warnings) + list(warnings)
    stored_default = stored_default_profile(config)
    override = override_per_task_enabled(config)
    stored_map = stored_task_map(config)
    task_map = {cls: stored_map.get(cls) or auto.picks.get(cls, default) for cls in TASK_CLASSES}
    missing: list[str] = []
    known = {entry.id for entry in catalog}
    if stored_default and stored_default not in known and not profile_exists(stored_default, config):
        missing.append(stored_default)
    for cls, name in stored_map.items():
        if name not in known and not profile_exists(name, config):
            missing.append(name)
            warning = (
                f"Task profile {name!r} for {cls} not found; "
                f"falling back to default {default!r}."
            )
            if warning not in warnings:
                warnings.append(warning)
    routes = {
        cls: resolve_for_task(cls, config, catalog=catalog).public_dict()
        for cls in TASK_CLASSES
    }
    return {
        "object": "llm_profiles",
        "profiles": [entry.public_dict() for entry in catalog],
        "default_llm_profile": default,
        "default_is_auto": stored_default is None,
        "override_per_task": override,
        "task_llm_profiles": task_map,
        "auto_picks": {
            **auto.picks,
            "default": auto.default,
        },
        "aliases_used": auto.aliases_used,
        "warnings": llm_list_models.sanitize_ui_warnings(
            warnings + ([f"Missing profile {mid!r}." for mid in missing] if missing else [])
        ),
        "routes": routes,
        "task_classes": list(TASK_CLASSES),
        "list_models_source": list_source,
        "cli_model_lists": cli_lists,
        "force_env": ownership.force_env_enabled(),
        "provenance": {
            "default_llm_profile": ownership.default_llm_provenance(config),
        },
    }

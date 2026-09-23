"""Registry + get/set helpers for per-user UI preferences (REQ-144).

Known first-class keys live in ``PREF_REGISTRY``. Extra keys may be stored in
the same JSON bag later without a migration. Secret-shaped keys are rejected.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings as django_settings

from swarm.auth import request_principal, token_principal
from swarm.core.context_compress_policy import (
    AUTO_COMPRESS_PCT_KEY,
    CONTEXT_COMPRESS_API_ONLY,
    DEFAULT_AUTO_COMPRESS_PCT,
    normalize_auto_compress_pct,
)
from swarm.core.context_cull_policy import (
    CONTEXT_STRATEGY_KEY,
    CULL_FRACTION_PCT_KEY,
    CULL_TRIGGER_PCT_KEY,
    DEFAULT_CONTEXT_STRATEGY,
    DEFAULT_CULL_FRACTION_PCT,
    DEFAULT_CULL_TRIGGER_PCT,
    normalize_context_strategy,
    normalize_cull_fraction_pct,
    normalize_cull_trigger_pct,
)

# First-class rail chrome. More knobs (theme, …) can join this registry
# without a new table — they persist in UserPreference.values.
PREF_REGISTRY: dict[str, dict[str, str]] = {
    "favourites": {
        "type": "pin_list",
        "description": "Ordered favourite tiles (id + display name).",
    },
    "hidden_agents": {
        "type": "id_list",
        "description": "Hidden rail / Hidden Bots agent ids.",
    },
    "hostname_override": {
        "type": "hostname_string",
        "description": "Display / system-name hostname override (not a secret).",
    },
    AUTO_COMPRESS_PCT_KEY: {
        "type": "percent_1_99",
        "description": "Auto-compress context at this percent of known max (default 80).",
    },
    CONTEXT_STRATEGY_KEY: {
        "type": "enum_compress_cull",
        "description": "API context strategy: compress (summarise) or cull (drop oldest slice).",
    },
    CULL_TRIGGER_PCT_KEY: {
        "type": "percent_1_99",
        "description": "Auto-cull context at this percent of known max (default 90).",
    },
    CULL_FRACTION_PCT_KEY: {
        "type": "percent_1_99",
        "description": "Oldest fraction to drop on auto-cull (default 50).",
    },
    CONTEXT_COMPRESS_API_ONLY: {
        "type": "boolean",
        "description": "Enable API-only mode — skip compression/culling for CLI agents.",
    },
    "theme": {
        "type": "enum_theme",
        "description": "UI theme preference (system, light, dark).",
    },
    "theme_navbar_mode": {
        "type": "enum_navbar_mode",
        "description": "Top navbar theme toggle visibility mode (if_not_system, always, never).",
    },
    "bubble_theme": {
        "type": "bubble_theme_string",
        "description": "Chat message bubble styling theme.",
    },
    "rail_sections": {
        "type": "rail_sections",
        "description": "Sidepane custom sections, agent membership, and collapsed states (#786).",
    },
}

SECRET_KEY_FRAGMENTS = (
    "secret",
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)

FAVOURITES_KEY = "favourites"
HIDDEN_KEY = "hidden_agents"
HOSTNAME_KEY = "hostname_override"
AUTO_COMPRESS_KEY = AUTO_COMPRESS_PCT_KEY
CONTEXT_STRATEGY = CONTEXT_STRATEGY_KEY
CULL_TRIGGER_KEY = CULL_TRIGGER_PCT_KEY
CULL_FRACTION_KEY = CULL_FRACTION_PCT_KEY
THEME_KEY = "theme"
THEME_NAVBAR_MODE_KEY = "theme_navbar_mode"
BUBBLE_THEME_KEY = "bubble_theme"
RAIL_SECTIONS_KEY = "rail_sections"

DEFAULT_THEME = "system"
VALID_THEMES = ("system", "light", "dark")

DEFAULT_NAVBAR_THEME_MODE = "if_not_system"
VALID_NAVBAR_THEME_MODES = ("if_not_system", "always", "never")

BUBBLE_THEME_MAX_LEN = 64
AGENT_DROPDOWNS_KEY = "agent_dropdowns"
HOSTNAME_MAX_LEN = 255
AGENT_DROPDOWN_FIELDS = ("cli", "model", "remote", "blueprint", "api")


def is_secret_key(name: str) -> bool:
    lowered = (name or "").strip().lower()
    return any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS)


def primary_operator_principal() -> str:
    """Principal of the primary installation operator (#786).

    The first active superuser's username when one exists, else ``admin``.
    Used as the guest fallback so an operator's rail layout follows them
    across browsers/devices instead of fragmenting per ephemeral session.
    """
    username = "admin"
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        operator = (
            User.objects.filter(is_superuser=True, is_active=True)
            .order_by("pk")
            .only("username")
            .first()
        )
        if operator is not None and operator.get_username().strip():
            username = operator.get_username().strip()
    except Exception:
        # Any DB problem falls back to the static 'admin' principal — the
        # preferences row must never fail to resolve because of this lookup.
        pass
    return f"user:{username}"


def preference_identity(request) -> tuple[object | None, str, bool]:
    """Return ``(user_or_None, principal, is_guest)`` for this request.

    Logged-in Django user (including ``swarm-anon-preview``) → ``user:<name>``.
    Bearer / X-API-Key → ``token:<hash>``.
    Otherwise a Django session principal (guest). A session is minted if needed
    so the same browser can round-trip GET then PATCH.
    """
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user, f"user:{user.get_username()}", False

    principal = request_principal(request)
    if principal:
        return None, principal, False

    # #786: when API auth is not configured, guests resolve to the primary
    # installation operator (first active superuser, else 'admin') instead of
    # minting disjoint ephemeral session keys — an operator's rail layout
    # follows them across browsers/devices. Authenticated user/token rows
    # still win above; with auth enabled, session guests stay isolated.
    if not bool(getattr(django_settings, "ENABLE_API_AUTH", False)):
        return None, primary_operator_principal(), True

    session = getattr(request, "session", None)
    if session is not None:
        if not session.session_key:
            session.save()
        if session.session_key:
            return None, f"session:{session.session_key}", True

    # No session middleware — still land on the shared operator bag.
    return None, primary_operator_principal(), True


def normalize_favourite(value: Any) -> dict[str, str] | None:
    if isinstance(value, str) and value.strip():
        ident = value.strip()
        return {"id": ident, "name": ident}
    if not isinstance(value, dict):
        return None
    ident = value.get("id")
    if not isinstance(ident, str) or not ident.strip():
        return None
    ident = ident.strip()
    name = value.get("name")
    label = name.strip() if isinstance(name, str) and name.strip() else ident
    return {"id": ident, "name": label}


def normalize_favourites(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    pins: list[dict[str, str]] = []
    for item in raw:
        pin = normalize_favourite(item)
        if pin is None or pin["id"] in seen:
            continue
        seen.add(pin["id"])
        pins.append(pin)
    return pins


def normalize_id_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    ids: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        ident = item.strip()
        if ident in seen:
            continue
        seen.add(ident)
        ids.append(ident)
    return ids


def normalize_agent_dropdown_choice(raw: Any) -> dict[str, str] | None:
    """Non-secret CLI / API / remote / blueprint ids only."""
    if not isinstance(raw, dict):
        return None
    choice: dict[str, str] = {}
    for field in AGENT_DROPDOWN_FIELDS:
        value = raw.get(field)
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if trimmed:
            choice[field] = trimmed
    return choice or None


def normalize_agent_dropdowns(raw: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for agent_id, value in raw.items():
        if not isinstance(agent_id, str) or not agent_id.strip():
            continue
        if is_secret_key(agent_id):
            continue
        choice = normalize_agent_dropdown_choice(value)
        if choice is None:
            continue
        out[agent_id.strip()] = choice
    return out


def normalize_hostname_override(raw: Any) -> str:
    """Display label only — strip controls and cap length.

    Does **not** run ``is_secret_key`` on the *value*: names like ``token-box``
    are valid hostnames. Secret-shaped *keys* are still dropped elsewhere.
    """
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raw = str(raw)
    cleaned = "".join(ch for ch in raw if ch.isprintable() and ch not in "\r\n\t")
    cleaned = cleaned.strip()
    if len(cleaned) > HOSTNAME_MAX_LEN:
        cleaned = cleaned[:HOSTNAME_MAX_LEN].rstrip()
    return cleaned


def normalize_theme(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip().lower() in VALID_THEMES:
        return raw.strip().lower()
    return DEFAULT_THEME


def normalize_theme_navbar_mode(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip().lower() in VALID_NAVBAR_THEME_MODES:
        return raw.strip().lower()
    return DEFAULT_NAVBAR_THEME_MODE


def normalize_bubble_theme(raw: Any) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raw = str(raw)
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in "-_").strip().lower()
    return cleaned[:BUBBLE_THEME_MAX_LEN]


def normalize_rail_sections(raw: Any) -> dict[str, Any]:
    """Shape-validating normalizer for the sidepane layout bag (#786).

    Keeps only well-formed sections (id + optional name/collapsed/internalOnly),
    an id→id membership map, and the unassigned-collapsed flag. Anything
    malformed is dropped, never raised — a corrupt client payload must not
    wedge the whole preferences row.
    """
    if not isinstance(raw, dict):
        return {"sections": [], "membership": {}, "unassignedCollapsed": False}
    sections: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw.get("sections") or []:
        if not isinstance(item, dict):
            continue
        section_id = item.get("id")
        if not isinstance(section_id, str) or not section_id.strip():
            continue
        section_id = section_id.strip()
        if section_id in seen or section_id == "unassigned":
            continue
        seen.add(section_id)
        name = item.get("name")
        sections.append(
            {
                "id": section_id,
                "name": name.strip() if isinstance(name, str) else "",
                "collapsed": bool(item.get("collapsed")),
                "internalOnly": bool(item.get("internalOnly")),
            }
        )
    valid_ids = {s["id"] for s in sections}
    membership: dict[str, str] = {}
    raw_membership = raw.get("membership")
    if isinstance(raw_membership, dict):
        for agent_id, section_id in raw_membership.items():
            if (
                isinstance(agent_id, str)
                and agent_id.strip()
                and isinstance(section_id, str)
                and section_id.strip() in valid_ids
            ):
                membership[agent_id.strip()] = section_id.strip()
    return {
        "sections": sections,
        "membership": membership,
        "unassignedCollapsed": bool(raw.get("unassignedCollapsed")),
    }


def empty_values() -> dict[str, Any]:
    return {
        FAVOURITES_KEY: [],
        HIDDEN_KEY: [],
        HOSTNAME_KEY: "",
        AUTO_COMPRESS_KEY: DEFAULT_AUTO_COMPRESS_PCT,
        CONTEXT_STRATEGY: DEFAULT_CONTEXT_STRATEGY,
        CULL_TRIGGER_KEY: DEFAULT_CULL_TRIGGER_PCT,
        CULL_FRACTION_KEY: DEFAULT_CULL_FRACTION_PCT,
        THEME_KEY: DEFAULT_THEME,
        THEME_NAVBAR_MODE_KEY: DEFAULT_NAVBAR_THEME_MODE,
        BUBBLE_THEME_KEY: "",
        RAIL_SECTIONS_KEY: {"sections": [], "membership": {}, "unassignedCollapsed": False},
    }


def coerce_values(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return empty_values()
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key or is_secret_key(key):
            continue
        if key == FAVOURITES_KEY:
            out[key] = normalize_favourites(value)
        elif key == HIDDEN_KEY:
            out[key] = normalize_id_list(value)
        elif key == HOSTNAME_KEY:
            out[key] = normalize_hostname_override(value)
        elif key == AUTO_COMPRESS_KEY:
            out[key] = normalize_auto_compress_pct(value)
        elif key == CONTEXT_STRATEGY:
            out[key] = normalize_context_strategy(value)
        elif key == CULL_TRIGGER_KEY:
            out[key] = normalize_cull_trigger_pct(value)
        elif key == CULL_FRACTION_KEY:
            out[key] = normalize_cull_fraction_pct(value)
        elif key == THEME_KEY:
            out[key] = normalize_theme(value)
        elif key == THEME_NAVBAR_MODE_KEY:
            out[key] = normalize_theme_navbar_mode(value)
        elif key == BUBBLE_THEME_KEY:
            out[key] = normalize_bubble_theme(value)
        elif key == RAIL_SECTIONS_KEY:
            out[key] = normalize_rail_sections(value)
        elif key == AGENT_DROPDOWNS_KEY:
            out[key] = normalize_agent_dropdowns(value)
        else:
            out[key] = value
    out.setdefault(FAVOURITES_KEY, [])
    out.setdefault(HIDDEN_KEY, [])
    out.setdefault(HOSTNAME_KEY, "")
    out.setdefault(AUTO_COMPRESS_KEY, DEFAULT_AUTO_COMPRESS_PCT)
    out.setdefault(CONTEXT_STRATEGY, DEFAULT_CONTEXT_STRATEGY)
    out.setdefault(CULL_TRIGGER_KEY, DEFAULT_CULL_TRIGGER_PCT)
    out.setdefault(CULL_FRACTION_KEY, DEFAULT_CULL_FRACTION_PCT)
    out.setdefault(THEME_KEY, DEFAULT_THEME)
    out.setdefault(THEME_NAVBAR_MODE_KEY, DEFAULT_NAVBAR_THEME_MODE)
    out.setdefault(BUBBLE_THEME_KEY, "")
    return out


def merge_values(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = coerce_values(current)
    incoming = patch if isinstance(patch, dict) else {}
    for key, value in incoming.items():
        if not isinstance(key, str) or not key or is_secret_key(key):
            continue
        if key == FAVOURITES_KEY:
            merged[key] = normalize_favourites(value)
        elif key == HIDDEN_KEY:
            merged[key] = normalize_id_list(value)
        elif key == HOSTNAME_KEY:
            merged[key] = normalize_hostname_override(value)
        elif key == AUTO_COMPRESS_KEY:
            merged[key] = normalize_auto_compress_pct(value)
        elif key == CONTEXT_STRATEGY:
            merged[key] = normalize_context_strategy(value)
        elif key == CULL_TRIGGER_KEY:
            merged[key] = normalize_cull_trigger_pct(value)
        elif key == CULL_FRACTION_KEY:
            merged[key] = normalize_cull_fraction_pct(value)
        elif key == THEME_KEY:
            merged[key] = normalize_theme(value)
        elif key == THEME_NAVBAR_MODE_KEY:
            merged[key] = normalize_theme_navbar_mode(value)
        elif key == BUBBLE_THEME_KEY:
            merged[key] = normalize_bubble_theme(value)
        elif key == RAIL_SECTIONS_KEY:
            merged[key] = normalize_rail_sections(value)
        elif key == AGENT_DROPDOWNS_KEY:
            merged[key] = normalize_agent_dropdowns(value)
        else:
            merged[key] = value
    return merged


def extras_bag(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if key not in PREF_REGISTRY
    }


def public_payload(
    *,
    principal: str,
    guest: bool,
    empty: bool,
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bag = coerce_values(values or {})
    return {
        "object": "user_preferences",
        "principal": principal,
        "guest": guest,
        "empty": empty,
        "favourites": bag[FAVOURITES_KEY],
        "hidden_agents": bag[HIDDEN_KEY],
        "hostname_override": bag[HOSTNAME_KEY],
        AUTO_COMPRESS_KEY: normalize_auto_compress_pct(bag.get(AUTO_COMPRESS_KEY)),
        CONTEXT_STRATEGY: normalize_context_strategy(bag.get(CONTEXT_STRATEGY)),
        CULL_TRIGGER_KEY: normalize_cull_trigger_pct(bag.get(CULL_TRIGGER_KEY)),
        CULL_FRACTION_KEY: normalize_cull_fraction_pct(bag.get(CULL_FRACTION_KEY)),
        THEME_KEY: normalize_theme(bag.get(THEME_KEY)),
        THEME_NAVBAR_MODE_KEY: normalize_theme_navbar_mode(bag.get(THEME_NAVBAR_MODE_KEY)),
        BUBBLE_THEME_KEY: normalize_bubble_theme(bag.get(BUBBLE_THEME_KEY)),
        RAIL_SECTIONS_KEY: normalize_rail_sections(bag.get(RAIL_SECTIONS_KEY)),
        "values": extras_bag(bag),
        "registry": [
            {"key": key, **meta} for key, meta in PREF_REGISTRY.items()
        ],
    }


# Re-export so views can stamp token principals without importing auth twice.
__all__ = [
    "AGENT_DROPDOWNS_KEY",
    "AUTO_COMPRESS_KEY",
    "BUBBLE_THEME_KEY",
    "CONTEXT_STRATEGY",
    "CULL_FRACTION_KEY",
    "CULL_TRIGGER_KEY",
    "DEFAULT_NAVBAR_THEME_MODE",
    "DEFAULT_THEME",
    "FAVOURITES_KEY",
    "HIDDEN_KEY",
    "HOSTNAME_KEY",
    "PREF_REGISTRY",
    "RAIL_SECTIONS_KEY",
    "THEME_KEY",
    "THEME_NAVBAR_MODE_KEY",
    "coerce_values",
    "empty_values",
    "extras_bag",
    "is_secret_key",
    "merge_values",
    "normalize_agent_dropdowns",
    "normalize_bubble_theme",
    "normalize_favourites",
    "normalize_hostname_override",
    "normalize_id_list",
    "normalize_rail_sections",
    "normalize_theme",
    "normalize_theme_navbar_mode",
    "preference_identity",
    "primary_operator_principal",
    "public_payload",
    "token_principal",
]

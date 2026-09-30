"""Per-agent storefront / rail identity (#1388).

Display name, short description, optional title/role, and avatar chrome
live beside REQ-65 agent settings. This module is validation + pack
projection only — persistence stays on ``agent_settings.json``.

Template packs expose a ``profile`` section. Session ids, live tokens,
env values, and local folders never belong in that section.
"""

from __future__ import annotations

import re
from typing import Any

from swarm.core.agent_roles import ROLE_ALIASES, ROLE_DEFAULT
from swarm.core.roles.registry import ROLE_REGISTRY

SCHEMA = 1
PACK_KIND = "agent_template"

KEY_DISPLAY_NAME = "display_name"
KEY_DESCRIPTION = "description"
KEY_TITLE = "title"
KEY_ROLE = "role"
KEY_AVATAR_SHAPE = "avatar_shape"
KEY_AVATAR_COLOR = "avatar_color"
KEY_AVATAR_PATH = "avatar_path"

PROFILE_FIELD_KEYS = (
    KEY_DISPLAY_NAME,
    KEY_DESCRIPTION,
    KEY_TITLE,
    KEY_ROLE,
    KEY_AVATAR_SHAPE,
    KEY_AVATAR_COLOR,
    KEY_AVATAR_PATH,
)
PROFILE_FIELD_KEY_SET = frozenset(PROFILE_FIELD_KEYS)

# Flat aliases accepted on PATCH /v1/agents/<id>/settings/ and folded into profile.
PROFILE_BODY_ALIASES = frozenset({*PROFILE_FIELD_KEYS, "profile", "storefront_description"})

AVATAR_SHAPE_CIRCLE = "circle"
AVATAR_SHAPE_ROUNDED = "rounded"
AVATAR_SHAPE_SQUARE = "square"
AVATAR_SHAPE_HEXAGON = "hexagon"
AVATAR_SHAPES = (
    AVATAR_SHAPE_CIRCLE,
    AVATAR_SHAPE_ROUNDED,
    AVATAR_SHAPE_SQUARE,
    AVATAR_SHAPE_HEXAGON,
)
AVATAR_SHAPE_SET = frozenset(AVATAR_SHAPES)
DEFAULT_AVATAR_SHAPE = AVATAR_SHAPE_CIRCLE

MAX_DISPLAY_NAME = 80
MAX_DESCRIPTION = 200
MAX_TITLE = 80
MAX_ROLE = 40
MAX_AVATAR_PATH = 256

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_AVATAR_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ROLE_SLUG_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_PUBLIC_AVATAR_PREFIXES = ("/avatars/", "/static/img/avatars/")

# Keys that must never appear on a template-pack profile (or leak in from settings).
PACK_SECRET_KEYS = frozenset(
    {
        "api_key",
        "stt_api_key",
        "tts_api_key",
        "token",
        "secret",
        "password",
        "authorization",
        "credentials",
        "cli_session_id",
        "remote_session_id",
        "stt_api_key_env",
        "tts_api_key_env",
        "folder",
        "speech_mode",
        "tts_voice",
        "tts_voice_instruction",
        "stt_base_url",
        "tts_base_url",
        "stt_model",
        "tts_model",
        "auto_speak_replies",
        "new_chat_per_task",
        "use_suggestions",
        "active_sessions",
    }
)

DEFAULT_PROFILE: dict[str, Any] = {
    KEY_DISPLAY_NAME: "",
    KEY_DESCRIPTION: "",
    KEY_TITLE: "",
    KEY_ROLE: "",
    KEY_AVATAR_SHAPE: DEFAULT_AVATAR_SHAPE,
    KEY_AVATAR_COLOR: "",
    KEY_AVATAR_PATH: None,
}


def default_profile() -> dict[str, Any]:
    return dict(DEFAULT_PROFILE)


def _clip_text(value: Any, *, limit: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _normalize_hex_color(value: str) -> str:
    raw = value.strip()
    if len(raw) == 4:
        return "#" + "".join(ch * 2 for ch in raw[1:]).lower()
    return raw.lower()


def normalize_avatar_color(value: Any) -> str:
    """Accept ``#RGB`` / ``#RRGGBB`` or empty. Raise ValueError otherwise."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if not _HEX_COLOR_RE.fullmatch(text):
        raise ValueError(
            f"{KEY_AVATAR_COLOR} must be a hex color (#RGB or #RRGGBB), or empty."
        )
    return _normalize_hex_color(text)


def normalize_avatar_shape(value: Any) -> str:
    """Accept a known shape, or empty → circle. Raise ValueError otherwise."""
    if value is None:
        return DEFAULT_AVATAR_SHAPE
    text = str(value).strip().lower()
    if not text:
        return DEFAULT_AVATAR_SHAPE
    if text not in AVATAR_SHAPE_SET:
        allowed = ", ".join(AVATAR_SHAPES)
        raise ValueError(f"{KEY_AVATAR_SHAPE} must be one of {allowed}.")
    return text


def _role_token(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


# Built-in alias keys, snapshotted before ``/v1/roles/`` mutates ROLE_ALIASES.
_BUILTIN_ROLE_ALIAS_KEYS = frozenset(
    token
    for alias in ROLE_ALIASES
    for token in (str(alias), _role_token(alias))
    if token
)


def _registered_alias_target(key: str) -> str | None:
    """Map a normalized alias onto a live registry id.

    The roles API stores custom aliases with strip/lower only, and
    ``register_role`` keeps aliases on the ``Role`` object rather than
    copying them into ``ROLE_ALIASES``. Both forms count.
    """
    direct = ROLE_ALIASES.get(key)
    if direct in ROLE_REGISTRY:
        return str(direct)
    for alias, target in ROLE_ALIASES.items():
        if _role_token(alias) == key and target in ROLE_REGISTRY:
            return str(target)
    for role_id, role in ROLE_REGISTRY.items():
        for alias in getattr(role, "aliases", ()) or ():
            if _role_token(alias) == key:
                return str(role_id)
    return None


def normalize_profile_role(value: Any) -> str:
    """Optional rail/header role. Empty stays empty; aliases become canonical.

    Unknown slugs are rejected so a write cannot invent a badge. A
    registered id wins over an alias, so a custom role named ``helper``
    is stored as that id. ``/v1/roles/`` adds custom roles to the live
    registry after ``CANONICAL_ROLES`` was snapshotted.
    """
    if value is None:
        return ""
    key = _role_token(value)
    if not key:
        return ""
    if len(key) > MAX_ROLE:
        raise ValueError(f"{KEY_ROLE} is too long (max {MAX_ROLE}).")
    if key in ROLE_REGISTRY:
        resolved = key
    else:
        resolved = _registered_alias_target(key)
        if resolved is None:
            known = ", ".join(ROLE_REGISTRY)
            raise ValueError(
                f"{KEY_ROLE} must be empty or a known agent role ({known})."
            )
    if resolved == ROLE_DEFAULT:
        return ""
    return resolved


def stored_profile_role(value: Any) -> str:
    """Role to show from disk.

    Writes store a canonical slug. A slug that is not a built-in alias is
    kept when it is no longer in the live registry, so a restart does not
    blank ``storefront_liaison`` on GET or on the next settings save.
    Built-in alias forms (``cos``, ``worker``) still canonicalize. A custom
    id that collides with one of those aliases does too, once it leaves
    the registry.
    """
    key = _role_token(value)
    if not key or not _ROLE_SLUG_RE.fullmatch(key):
        return ""
    if key in ROLE_REGISTRY:
        return "" if key == ROLE_DEFAULT else key
    if key in _BUILTIN_ROLE_ALIAS_KEYS:
        target = _registered_alias_target(key)
        if not target or target == ROLE_DEFAULT:
            return ""
        return target
    return key


def normalize_avatar_path(value: Any) -> str | None:
    """Optional public avatar path. Missing files are allowed (non-blocking)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > MAX_AVATAR_PATH:
        raise ValueError(f"{KEY_AVATAR_PATH} is too long (max {MAX_AVATAR_PATH}).")
    lowered = text.lower()
    if any(token in lowered for token in ("://", "file:", "\\", "..")):
        raise ValueError(
            f"{KEY_AVATAR_PATH} must be a site-relative /avatars/ path, never a URL or filesystem path."
        )
    prefix = next((item for item in _PUBLIC_AVATAR_PREFIXES if text.startswith(item)), "")
    if not prefix:
        raise ValueError(
            f"{KEY_AVATAR_PATH} must start with /avatars/ or /static/img/avatars/."
        )
    rest = text[len(prefix) :]
    parts = [part for part in rest.split("/") if part]
    if not parts or any(not _AVATAR_SEGMENT_RE.fullmatch(part) for part in parts):
        raise ValueError(f"{KEY_AVATAR_PATH} has an unsafe path segment.")
    return text


def _incoming_profile_dict(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("profile must be an object.")
    incoming = dict(raw)
    if "storefront_description" in incoming and KEY_DESCRIPTION not in incoming:
        incoming[KEY_DESCRIPTION] = incoming.pop("storefront_description")
    else:
        incoming.pop("storefront_description", None)
    secret = [key for key in incoming if key in PACK_SECRET_KEYS]
    if secret:
        raise ValueError(
            "Profile must not include secrets or session settings "
            f"({', '.join(sorted(secret))})."
        )
    unknown = [key for key in incoming if key not in PROFILE_FIELD_KEY_SET]
    if unknown:
        raise ValueError(f"Unknown profile field(s): {', '.join(sorted(unknown))}.")
    return incoming


def public_profile(raw: Any = None) -> dict[str, Any]:
    """Stable JSON shape for rail/header GET and pack export.

    Unknown or invalid fields fall back to defaults so a corrupt stored
    shape/color cannot 500 a GET. A slug-shaped role is kept so a custom
    id still round-trips after it leaves the in-memory registry. Writes
    still go through ``normalize_profile``.
    """
    if raw is None:
        return default_profile()
    if not isinstance(raw, dict):
        return default_profile()
    incoming = dict(raw)
    if "storefront_description" in incoming and KEY_DESCRIPTION not in incoming:
        incoming[KEY_DESCRIPTION] = incoming.get("storefront_description")
    merged = default_profile()
    for key in PROFILE_FIELD_KEYS:
        if key not in incoming:
            continue
        if key == KEY_ROLE:
            merged[key] = stored_profile_role(incoming[key])
            continue
        try:
            merged[key] = normalize_profile({key: incoming[key]})[key]
        except ValueError:
            continue
    return merged


def normalize_profile(raw: Any = None) -> dict[str, Any]:
    """Validate and fill defaults. Raises ValueError on bad shape/color/role/path."""
    incoming = _incoming_profile_dict(raw)
    merged = default_profile()
    for key in PROFILE_FIELD_KEYS:
        if key not in incoming:
            continue
        value = incoming[key]
        if key == KEY_DISPLAY_NAME:
            merged[key] = _clip_text(value, limit=MAX_DISPLAY_NAME)
        elif key == KEY_DESCRIPTION:
            merged[key] = _clip_text(value, limit=MAX_DESCRIPTION)
        elif key == KEY_TITLE:
            merged[key] = _clip_text(value, limit=MAX_TITLE)
        elif key == KEY_ROLE:
            merged[key] = normalize_profile_role(value)
        elif key == KEY_AVATAR_SHAPE:
            merged[key] = normalize_avatar_shape(value)
        elif key == KEY_AVATAR_COLOR:
            merged[key] = normalize_avatar_color(value)
        elif key == KEY_AVATAR_PATH:
            merged[key] = normalize_avatar_path(value)
    return {
        KEY_DISPLAY_NAME: str(merged[KEY_DISPLAY_NAME] or ""),
        KEY_DESCRIPTION: str(merged[KEY_DESCRIPTION] or ""),
        KEY_TITLE: str(merged[KEY_TITLE] or ""),
        KEY_ROLE: str(merged[KEY_ROLE] or ""),
        KEY_AVATAR_SHAPE: merged[KEY_AVATAR_SHAPE] or DEFAULT_AVATAR_SHAPE,
        KEY_AVATAR_COLOR: str(merged[KEY_AVATAR_COLOR] or ""),
        KEY_AVATAR_PATH: merged[KEY_AVATAR_PATH] if merged[KEY_AVATAR_PATH] else None,
    }


def apply_profile_patch(current: Any, patch: Any) -> dict[str, Any]:
    """Merge ``patch`` onto ``current`` and re-validate.

    When the patch does not change the role, the stored slug is written
    back as ``public_profile`` reported it. A new role value still goes
    through ``normalize_profile_role``, and unknown slugs still fail.
    """
    incoming = _incoming_profile_dict(patch)
    base = public_profile(current)
    stored_role = str(base.get(KEY_ROLE) or "")
    role_in_patch = KEY_ROLE in incoming
    proposed = _role_token(incoming.get(KEY_ROLE)) if role_in_patch else stored_role
    base.update(incoming)
    if role_in_patch and proposed != stored_role:
        return normalize_profile(base)
    normalized = normalize_profile({**base, KEY_ROLE: ""})
    normalized[KEY_ROLE] = stored_role
    return normalized


def profile_for_replace(current: Any, raw: Any) -> dict[str, Any]:
    """Full profile for PUT. Omitted fields reset; an unchanged role slug is kept.

    ``normalize_profile`` rejects a custom id that is no longer registered.
    Repeating the slug already stored on the agent is not a new assignment.
    """
    incoming = raw if isinstance(raw, dict) else {}
    stored_role = str(public_profile(current).get(KEY_ROLE) or "")
    if KEY_ROLE in incoming and _role_token(incoming.get(KEY_ROLE)) == stored_role:
        normalized = normalize_profile({**incoming, KEY_ROLE: ""})
        normalized[KEY_ROLE] = stored_role
        return normalized
    return normalize_profile(incoming)


def extract_profile_patch(body: dict[str, Any] | None) -> dict[str, Any] | None:
    """Pull nested ``profile`` plus flat identity fields from an API body."""
    incoming = body if isinstance(body, dict) else {}
    patch: dict[str, Any] = {}
    nested = incoming.get("profile")
    if isinstance(nested, dict):
        patch.update(nested)
    if "storefront_description" in incoming and KEY_DESCRIPTION not in incoming:
        patch[KEY_DESCRIPTION] = incoming.get("storefront_description")
    for key in PROFILE_FIELD_KEYS:
        if key in incoming:
            patch[key] = incoming[key]
    return patch or None


def profile_section_for_pack(raw: Any = None) -> dict[str, Any]:
    """Secret-free ``profile`` object for template packs.

    Local filesystem paths and any leftover secret keys are dropped. A
    missing custom avatar file is non-blocking — the path is omitted when
    it is not a public site-relative avatar URL.
    """
    profile = public_profile(raw)
    path = profile.get(KEY_AVATAR_PATH)
    if path and not str(path).startswith(_PUBLIC_AVATAR_PREFIXES):
        profile[KEY_AVATAR_PATH] = None
    for key in list(profile):
        if key in PACK_SECRET_KEYS or key not in PROFILE_FIELD_KEY_SET:
            profile.pop(key, None)
    return profile


def serialize_template_pack(
    agent_id: str,
    raw_profile: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Template-pack envelope with a ``profile`` section and no secrets."""
    from swarm.core.chat_store import normalize_agent_id

    pack: dict[str, Any] = {
        "schema": SCHEMA,
        "kind": PACK_KIND,
        "agent_id": normalize_agent_id(agent_id),
        "profile": profile_section_for_pack(raw_profile),
    }
    if isinstance(extra, dict) and extra:
        safe_extra = {
            key: value
            for key, value in extra.items()
            if key not in PACK_SECRET_KEYS
            and key not in {"profile", "schema", "kind", "agent_id"}
            and not any(token in str(key).lower() for token in ("secret", "token", "password", "api_key"))
        }
        if safe_extra:
            pack["extra"] = safe_extra
    return pack


def rail_header_fields(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """Flat fields the rail / chat header and pack export need from GET."""
    public = public_profile(profile)
    return {
        KEY_DISPLAY_NAME: public[KEY_DISPLAY_NAME],
        KEY_DESCRIPTION: public[KEY_DESCRIPTION],
        KEY_TITLE: public[KEY_TITLE],
        KEY_ROLE: public[KEY_ROLE],
        KEY_AVATAR_SHAPE: public[KEY_AVATAR_SHAPE],
        KEY_AVATAR_COLOR: public[KEY_AVATAR_COLOR],
        KEY_AVATAR_PATH: public[KEY_AVATAR_PATH],
        "profile": public,
    }

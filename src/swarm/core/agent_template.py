"""Unified agent template packs (#1398).

A template is a recipe, not a clone. The envelope composes secret-free
profile (#1388), memory (#1390), skills (#1392), routines (#1394),
plugins (#1396), and gettingStarted. Routine and plugin sections are the
domain packs: export reads ``routines_section_for_pack`` and
``plugins_section_for_pack``; import writes through those modules and
leaves routines inactive until an operator enables them.

Grok interop is a file mapper (``kind: grok_bot_template``). Live Grok
calls are skipped when no XAI_API_KEY or GROK_API_KEY is set. Share ids
and deep links are refused (``grok_share_unsupported``). This module does
not call xAI or scrape grok.com.

No SPA (#1399). No secrets in packs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from swarm.core.agent_memory import (
    export_pack_fragment as export_memory_fragment,
    replace_pack_fragment as replace_memory_fragment,
)
from swarm.core.agent_pack import PackValidationError, _reject_binaries, _skill_prose
from swarm.core.agent_plugin_pack import PluginPackError, plugins_section_for_pack
from swarm.core.agent_plugin_pack import STATUS_ENABLED as PLUGIN_STATUS_ENABLED
from swarm.core.agent_plugin_pack import import_pack as import_plugins_pack
from swarm.core.agent_plugin_pack import validate_pack as validate_plugin_pack
from swarm.core.agent_profile import (
    PACK_SECRET_KEYS,
    profile_section_for_pack,
)
from swarm.core.agent_settings import get_profile, replace_profile
from swarm.core.agent_skills import (
    getting_started as stored_getting_started,
)
from swarm.core.agent_skills import (
    list_skills,
    public_getting_started,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.core.memory_scrubber import contains_credentials, scrub_for_pack
from swarm.core.routine_pack import PackValidationError as RoutinePackError
from swarm.core.routine_pack import import_pack as import_routines_pack
from swarm.core.routine_pack import routines_section_for_pack
from swarm.core.routine_pack import validate_pack as validate_routines_pack
from swarm.core.template_fragments import (
    FragmentError,
    allocate_agent_id,
    assert_json_schema,
    connect_checklist,
    read_fragments,
    write_fragments,
)

SCHEMA = 1
PACK_KIND = "agent_template"
PACK_OBJECT = "agent_template"
GROK_KIND = "grok_bot_template"
GROK_OBJECT = "grok_bot_template"

# xAI does not publish a stable "import this share id" API. A share URL
# sits on a logged-in product surface. Fetching it would be a scrape.
GROK_SHARE_FINDING = (
    "Grok Bot share ids and deep links are not imported. "
    "xAI does not publish a stable pack-import API, and fetching a share "
    "URL would scrape a logged-in product surface. Interop is file-only: "
    "kind grok_bot_template JSON via POST /v1/agent-templates/from-grok/."
)
_SHARE_KEYS = frozenset(
    {"share_id", "share_url", "deep_link", "deeplink", "share_link"}
)
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

RESERVED_KEYS = frozenset(
    {
        "object",
        "schema",
        "kind",
        "agent_id",
        "source_agent_id",
        "profile",
        "memories",
        "memory",
        "skills",
        "gettingStarted",
        "getting_started",
        "routines",
        "plugins",
        "name",
        "description",
        "title",
        "role",
        "avatar",
        "instructions",
    }
)

_SECRET_KEY_TOKENS = (
    "secret",
    "token",
    "password",
    "api_key",
    "authorization",
    "credentials",
)

# Routine keys the canonical pack carries, in schema order. The domain pack
# also emits ``enabled`` and ``slug``; see ``_template_routine``.
_TEMPLATE_ROUTINE_KEYS = (
    "name",
    "instruction",
    "description",
    "key",
    "role",
    "trigger",
)


class TemplateValidationError(PackValidationError):
    """Invalid agent template. ``code`` is stable for API clients."""

    def __init__(self, message: str, *, code: str = "template_invalid") -> None:
        super().__init__(message, code=code)


def _reject_secret_keys(raw: Any, *, where: str) -> None:
    if isinstance(raw, dict):
        hits = []
        for key in raw:
            lowered = str(key).strip().lower()
            secret_key = lowered in PACK_SECRET_KEYS or any(
                token in lowered for token in _SECRET_KEY_TOKENS
            )
            if secret_key and lowered not in RESERVED_KEYS:
                hits.append(str(key))
        if hits:
            raise TemplateValidationError(
                f"{where} must not include secret keys: {', '.join(sorted(hits))}",
                code="template_secrets",
            )
        for key, value in raw.items():
            _reject_secret_keys(value, where=f"{where}.{key}")
    elif isinstance(raw, list):
        for index, item in enumerate(raw):
            _reject_secret_keys(item, where=f"{where}[{index}]")


def _walk_strings(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, dict):
        out: list[str] = []
        for value in raw.values():
            out.extend(_walk_strings(value))
        return out
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            out.extend(_walk_strings(item))
        return out
    return []


def _reject_credential_strings(raw: Any, *, where: str) -> None:
    for text in _walk_strings(raw):
        if contains_credentials(text):
            raise TemplateValidationError(
                f"{where} must not contain credential-shaped strings",
                code="template_secrets",
            )


def reject_grok_share_reference(raw: Any) -> None:
    """Refuse share ids and deep links. File JSON is the only Grok path."""
    if isinstance(raw, str) and _URL_RE.match(raw.strip()):
        raise TemplateValidationError(GROK_SHARE_FINDING, code="grok_share_unsupported")
    if not isinstance(raw, dict):
        return
    for key, value in raw.items():
        lowered = str(key).strip().lower()
        if lowered not in _SHARE_KEYS:
            continue
        if str(value or "").strip():
            raise TemplateValidationError(
                GROK_SHARE_FINDING, code="grok_share_unsupported"
            )


def _connect_from_plugin_import(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Report host attach status. Missing plugins stay on the connect checklist."""
    checklist: list[dict[str, Any]] = []
    for row in result.get("plugins") or []:
        if not isinstance(row, dict) or not str(row.get("pluginId") or "").strip():
            continue
        # The plugin pack keeps its own vocabulary (STATUS_ENABLED,
        # "missing-plugin", "missing-auth"). The connect checklist only draws
        # one line: attached on this host, or still to connect.
        attached = str(row.get("status") or "") == PLUGIN_STATUS_ENABLED
        item: dict[str, Any] = {
            "pluginId": row["pluginId"],
            "name": row.get("name") or row["pluginId"],
            "description": row.get("description") or "",
            "status": PLUGIN_STATUS_ENABLED if attached else "pending",
        }
        if not attached:
            item["detail"] = (
                "Connect this plugin on the host before the agent can use it."
            )
        env_names = [
            str(name) for name in (row.get("required_env") or []) if str(name).strip()
        ]
        if env_names:
            item["required_env"] = env_names
        checklist.append(item)
    return checklist


def _pending_fill_ins(slots: list[Any]) -> list[dict[str, Any]]:
    stamped: list[dict[str, Any]] = []
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        row = dict(slot)
        row["status"] = "pending"
        stamped.append(row)
    return stamped


def _domain_error_code(exc: Exception, *, fallback: str) -> str:
    code = str(getattr(exc, "code", "") or "")
    if "secret" in code:
        return "template_secrets"
    return fallback


def _normalize_domain_routines(
    raw: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize routines through the #1394 pack. Empty stays empty."""
    if isinstance(raw, dict):
        raw = raw.get("routines")
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        raise TemplateValidationError(
            "routines must be a list", code="template_routines_invalid"
        )
    if not raw:
        return [], []
    try:
        pack = validate_routines_pack({"kind": "agent_routines_pack", "routines": raw})
    except RoutinePackError as exc:
        raise TemplateValidationError(
            str(exc),
            code=_domain_error_code(exc, fallback="template_routines_invalid"),
        ) from exc
    routines = [_template_routine(row) for row in pack["routines"]]
    return routines, _pending_fill_ins(list(pack.get("fill_ins") or []))


def _template_routine(row: dict[str, Any]) -> dict[str, Any]:
    """Project a #1394 domain routine row onto the canonical pack shape.

    The routines pack is the domain's own store view: it always stamps
    ``enabled: false`` (import leaves routines pending enable) and mirrors a
    routine's slug into ``slug`` and ``key``. Neither belongs in the umbrella
    pack, whose routine schema is ``name``, ``instruction``, ``description``,
    ``key``, ``role``, ``trigger``, and ``fill_ins`` — so the section is
    projected here instead of widening the shipped schema.
    """
    item: dict[str, Any] = {
        key: row[key] for key in _TEMPLATE_ROUTINE_KEYS if key in row
    }
    item["fill_ins"] = _pending_fill_ins(list(row.get("fill_ins") or []))
    return item


def _normalize_domain_plugins(raw: Any) -> list[dict[str, str]]:
    """Normalize plugins through the #1396 id-only pack. Empty stays empty."""
    if isinstance(raw, dict):
        raw = raw.get("plugins") or raw.get("pluginIds") or raw.get("ids")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise TemplateValidationError(
            "plugins must be a list", code="template_plugins_invalid"
        )
    if not raw:
        return []
    try:
        pack = validate_plugin_pack({"kind": "agent_plugin_pack", "plugins": raw})
    except PluginPackError as exc:
        raise TemplateValidationError(
            str(exc),
            code=_domain_error_code(exc, fallback="template_plugins_invalid"),
        ) from exc
    return list(pack["plugins"])


def _normalize_memories(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        items = raw.get("memories")
        if items is None:
            items = raw.get("items") or raw.get("data")
        if items is None and raw.get("kind"):
            items = [raw]
    else:
        items = raw
    if not isinstance(items, list):
        raise TemplateValidationError(
            "memories must be a list of {kind, title, body} objects",
            code="template_memories_invalid",
        )
    from swarm.core.agent_memory import KIND_PROFILE, PACK_KINDS, normalize_kind

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise TemplateValidationError(
                f"memories[{index}] must be an object",
                code="template_memories_invalid",
            )
        try:
            kind = normalize_kind(item.get("kind"), default=KIND_PROFILE)
        except ValueError as exc:
            raise TemplateValidationError(
                str(exc), code="template_memories_invalid"
            ) from exc
        if kind not in PACK_KINDS:
            continue
        title = scrub_for_pack(str(item.get("title") or ""))
        body = item.get("body")
        if body is None:
            body = item.get("content") or item.get("text") or ""
        body = scrub_for_pack(str(body))
        if not title and not body:
            continue
        rows.append({"kind": kind, "title": title, "body": body})
    kind_order = {KIND_PROFILE: 0, "log": 1}
    rows.sort(
        key=lambda row: (
            kind_order.get(row["kind"], 9),
            row.get("title") or "",
            row.get("body") or "",
        )
    )
    return rows


def _normalize_skills(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TemplateValidationError(
            "skills must be a list", code="template_skills_invalid"
        )
    return [_skill_prose(item, index=index) for index, item in enumerate(raw)]


def _require_supported_schema(raw: dict[str, Any]) -> None:
    """Accept a missing schema or schema 1. Reject every other version."""
    if "schema" not in raw or raw.get("schema") is None:
        return
    schema = raw.get("schema")
    if isinstance(schema, bool) or schema != SCHEMA:
        raise TemplateValidationError(
            f"unsupported template schema {schema!r}; expected {SCHEMA}",
            code="template_schema_unsupported",
        )


def _coerce_incoming(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        reject_grok_share_reference(raw)
    if not isinstance(raw, dict):
        raise TemplateValidationError(
            "template must be a JSON object", code="template_invalid"
        )
    reject_grok_share_reference(raw)
    kind = str(raw.get("kind") or "").strip()
    obj = str(raw.get("object") or "").strip()
    if kind == GROK_KIND or obj == GROK_OBJECT:
        return _grok_to_raw(raw)
    if kind:
        return raw
    if "name" in raw and "avatar" in raw and "profile" not in raw:
        return _grok_to_raw(raw)
    return raw


def _grok_to_raw(raw: dict[str, Any]) -> dict[str, Any]:
    nested = raw.get("profile") if isinstance(raw.get("profile"), dict) else {}
    avatar = raw.get("avatar") if isinstance(raw.get("avatar"), dict) else {}
    profile = {
        "display_name": raw.get("name")
        or raw.get("display_name")
        or nested.get("display_name")
        or "",
        "description": raw.get("description") or nested.get("description") or "",
        "title": raw.get("title") or nested.get("title") or "",
        "role": raw.get("role") or nested.get("role") or "",
        "avatar_shape": avatar.get("shape") or nested.get("avatar_shape") or "",
        "avatar_color": avatar.get("color") or nested.get("avatar_color") or "",
        "avatar_path": avatar.get("path") or nested.get("avatar_path"),
    }
    memories = raw.get("memories")
    if memories is None:
        memories = raw.get("memory")
    schema = raw.get("schema", SCHEMA)
    if schema is None:
        schema = SCHEMA
    return {
        "schema": schema,
        "kind": PACK_KIND,
        "profile": profile,
        "memories": memories,
        "skills": raw.get("skills"),
        "gettingStarted": raw.get("gettingStarted") or raw.get("getting_started"),
        "routines": raw.get("routines"),
        "plugins": raw.get("plugins"),
        "fill_ins": raw.get("fill_ins"),
    }


def validate_template(raw: Any) -> dict[str, Any]:
    """Normalize a template pack. Raises :class:`TemplateValidationError`."""
    incoming = _coerce_incoming(raw)
    _require_supported_schema(incoming)
    try:
        _reject_binaries(incoming, where="template")
    except PackValidationError as exc:
        raise TemplateValidationError(
            str(exc), code=getattr(exc, "code", "pack_binaries")
        ) from exc
    _reject_secret_keys(incoming, where="template")
    _reject_credential_strings(incoming, where="template")
    try:
        profile = profile_section_for_pack(incoming.get("profile"))
    except ValueError as exc:
        raise TemplateValidationError(
            str(exc), code="template_profile_invalid"
        ) from exc
    memories = _normalize_memories(
        incoming.get("memories") if "memories" in incoming else incoming.get("memory")
    )
    try:
        skills = _normalize_skills(incoming.get("skills"))
    except PackValidationError as exc:
        raise TemplateValidationError(
            str(exc), code=getattr(exc, "code", "template_skills_invalid")
        ) from exc
    started_raw = incoming.get("gettingStarted", incoming.get("getting_started"))
    try:
        started = public_getting_started(started_raw)
    except ValueError as exc:
        raise TemplateValidationError(
            str(exc), code="template_getting_started_invalid"
        ) from exc
    skill_names = {row["name"] for row in skills}
    if skills:
        if not started or not started.get("skill"):
            raise TemplateValidationError(
                "gettingStarted.skill must name a packed skill",
                code="template_getting_started_missing",
            )
        if started["skill"] not in skill_names:
            raise TemplateValidationError(
                f"gettingStarted.skill {started['skill']!r} must name a packed skill",
                code="template_getting_started_missing",
            )
    elif started and started.get("skill"):
        raise TemplateValidationError(
            f"gettingStarted.skill {started['skill']!r} must name a packed skill",
            code="template_getting_started_missing",
        )
    routines, fill_ins = _normalize_domain_routines(incoming.get("routines"))
    plugins = _normalize_domain_plugins(incoming.get("plugins"))
    try:
        _reject_binaries({"routines": routines, "plugins": plugins}, where="template")
    except PackValidationError as exc:
        raise TemplateValidationError(
            str(exc), code=getattr(exc, "code", "pack_binaries")
        ) from exc
    _reject_secret_keys({"routines": routines, "plugins": plugins}, where="template")
    _reject_credential_strings(
        {"routines": routines, "plugins": plugins}, where="template"
    )
    pack = {
        "object": PACK_OBJECT,
        "schema": SCHEMA,
        "kind": PACK_KIND,
        "profile": profile,
        "memories": memories,
        "skills": skills,
        "gettingStarted": started,
        "routines": routines,
        "plugins": plugins,
        "fill_ins": fill_ins,
    }
    try:
        assert_json_schema(pack)
    except FragmentError as exc:
        raise TemplateValidationError(str(exc), code=exc.code) from exc
    return pack


def to_grok_template(raw: Any) -> dict[str, Any]:
    """Project a validated template into the Grok Bot dogfood shape."""
    pack = validate_template(raw)
    profile = pack["profile"]
    return {
        "object": GROK_OBJECT,
        "schema": SCHEMA,
        "kind": GROK_KIND,
        "name": profile.get("display_name") or "",
        "description": profile.get("description") or "",
        "title": profile.get("title") or "",
        "role": profile.get("role") or "",
        "avatar": {
            "shape": profile.get("avatar_shape") or "",
            "color": profile.get("avatar_color") or "",
            "path": profile.get("avatar_path"),
        },
        "memories": pack["memories"],
        "skills": pack["skills"],
        "gettingStarted": pack["gettingStarted"],
        "routines": pack["routines"],
        "plugins": pack["plugins"],
        "fill_ins": pack["fill_ins"],
    }


def from_grok_template(raw: Any) -> dict[str, Any]:
    """Accept a Grok Bot template file and return the canonical pack."""
    if isinstance(raw, str):
        reject_grok_share_reference(raw)
    if not isinstance(raw, dict):
        raise TemplateValidationError(
            "grok template must be a JSON object", code="template_invalid"
        )
    reject_grok_share_reference(raw)
    incoming = dict(raw)
    incoming["kind"] = GROK_KIND
    return validate_template(incoming)


def _stored_routines(agent_id: str) -> list[Any]:
    """Domain routines first. Fragments cover packs imported before #1394."""
    section = routines_section_for_pack(agent_id)
    rows = list(section.get("routines") or [])
    if rows:
        return rows
    return list(read_fragments(agent_id).get("routines") or [])


def _stored_plugins(agent_id: str) -> list[Any]:
    """Domain plugin ids first. Fragments cover packs imported before #1396."""
    rows = list(plugins_section_for_pack(agent_id) or [])
    if rows:
        return rows
    return list(read_fragments(agent_id).get("plugins") or [])


def export_template(agent_id: str) -> dict[str, Any]:
    """Compose profile, memory, skills, routines, plugins, and gettingStarted."""
    agent = normalize_agent_id(agent_id)
    skills = [
        {
            "name": row["name"],
            "description": row.get("description") or "",
            "instructions": row["instructions"],
        }
        for row in list_skills(agent)
    ]
    started = stored_getting_started(agent)
    if skills and (not started or not started.get("skill")):
        started = {"skill": skills[0]["name"]}
    raw = {
        "schema": SCHEMA,
        "kind": PACK_KIND,
        "profile": get_profile(agent),
        "memories": export_memory_fragment(agent).get("memories") or [],
        "skills": skills,
        "gettingStarted": started,
        "routines": _stored_routines(agent),
        "plugins": _stored_plugins(agent),
    }
    return validate_template(raw)


def _replace_pack_memories(agent_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace pack-tier memories. Episode and note rows stay on the seat."""
    return replace_memory_fragment(agent_id, {"memories": rows})


def _replace_skills(agent_id: str, pack: dict[str, Any]) -> int:
    """Install the packed skill list, including an empty list (clears the seat)."""
    if pack["skills"]:
        from swarm.core.agent_pack import import_pack

        import_pack(
            agent_id,
            {
                "kind": "swarm-agent-pack",
                "skills": pack["skills"],
                "gettingStarted": pack["gettingStarted"],
            },
        )
        return len(pack["skills"])
    from swarm.core.agent_skills import replace_skills

    replace_skills(agent_id, [], getting_started_raw=None)
    return 0


def import_template(agent_id: str, raw: Any) -> dict[str, Any]:
    """Write a validated template onto *agent_id*.

    Routines are created inactive (pending enable) through the routines
    pack. An already-enabled duplicate is left as-is. Plugin ids are stored
    through the plugin pack, with no tokens. Fill-in tokens stay pending.
    The legacy fragment shadow is cleared so export follows the domain stores.
    """
    agent = normalize_agent_id(agent_id)
    pack = validate_template(raw)
    memories = _replace_pack_memories(agent, pack["memories"])
    replace_profile(agent, pack["profile"])
    skills_imported = _replace_skills(agent, pack)
    pending_enable = False
    if pack["routines"]:
        try:
            routine_result = import_routines_pack(
                agent,
                {
                    "kind": "agent_routines_pack",
                    "routines": pack["routines"],
                    "fill_ins": pack["fill_ins"],
                },
            )
        except RoutinePackError as exc:
            raise TemplateValidationError(
                str(exc),
                code=_domain_error_code(exc, fallback="template_routines_invalid"),
            ) from exc
        pending_enable = int(routine_result.get("created_count") or 0) > 0
    connect: list[dict[str, Any]] = []
    if pack["plugins"]:
        try:
            plugin_result = import_plugins_pack(
                agent,
                {"kind": "agent_plugin_pack", "plugins": pack["plugins"]},
            )
        except PluginPackError as exc:
            raise TemplateValidationError(
                str(exc),
                code=_domain_error_code(exc, fallback="template_plugins_invalid"),
            ) from exc
        connect = _connect_from_plugin_import(plugin_result)
        if not connect:
            connect = connect_checklist(pack["plugins"])
    # Fragments are only a pre-domain fallback. This import owns the recipe.
    write_fragments(agent, routines=[], plugins=[])
    started = pack["gettingStarted"]
    return {
        "object": "agent_template_import",
        "created": False,
        "agent_id": agent,
        "template": pack,
        "applied": {
            "profile": True,
            "memories": len(memories),
            "skills": skills_imported,
            "routines": len(pack["routines"]),
            "plugins": len(pack["plugins"]),
        },
        "pending_enable": pending_enable,
        "fill_ins": pack["fill_ins"],
        "connect": connect,
        "gettingStarted": (
            {"skill": started["skill"], "status": "pending"} if started else None
        ),
    }


def create_agent_from_template(
    raw: Any, *, agent_id: str | None = None
) -> dict[str, Any]:
    """Validate a pack and create a new agent from it."""
    pack = validate_template(raw)
    display = str(pack["profile"].get("display_name") or "")
    try:
        agent = allocate_agent_id(display, agent_id)
    except FragmentError as exc:
        raise TemplateValidationError(str(exc), code=exc.code) from exc
    result = import_template(agent, pack)
    result["created"] = True
    return result


def load_template_file(path: str | Path) -> dict[str, Any]:
    """Read and validate a JSON template file (file dogfood)."""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise TemplateValidationError(
            f"could not read template file: {target.name}",
            code="template_file_unreadable",
        ) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TemplateValidationError(
            f"template file is not valid JSON: {exc.msg}",
            code="template_file_invalid",
        ) from exc
    return validate_template(payload)


def write_template_file(path: str | Path, raw: Any) -> Path:
    """Write a validated template as JSON (file dogfood). Never writes secrets."""
    pack = validate_template(raw)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(pack, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return target


def fixture_blob_is_secret_free(text: str) -> bool:
    """True when *text* has no credential-shaped or secret-key needles."""
    lowered = text.lower()
    if contains_credentials(text):
        return False
    needles = (
        "sk-",
        "api_key",
        "ghp_",
        "bearer ",
        "password=",
        "cli_session_id",
        "remote_session_id",
    )
    return not any(needle in lowered for needle in needles)

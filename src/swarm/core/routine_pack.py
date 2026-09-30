"""Routines-domain template pack (#1394).

A pack is a recipe, not a clone. Export strips concrete repo, channel, and
mailbox sender ids to named fill-in tokens (``{{owner_repo}}``,
``{{channel}}``, ``{{sender}}``) and lists those slots. History, next_run,
routine ids, binaries, and secrets are refused. Slug, trigger-intent
description, tool ids, and the model id travel with the row (#1668): a
recipe whose tools were chosen by an operator must not import stripped.

Only an operator's *explicit* tool list is pack content. Defaults are a
function of the trigger, which already travels, so a routine that never
had a tools choice keeps following the trigger on the importing seat
instead of having today's defaults frozen into a shared file.

Import always writes rows inactive. Fill-in values may be applied at
import or through POST ``.../fill/``. Leftover slots stay as placeholders.
Enable (POST ``.../enable/`` or PATCH ``active`` / ``enabled``) is refused
while any ``{{fill_in}}`` remains. No SPA in this slice.
"""

from __future__ import annotations

import re
from typing import Any

from swarm.core.chat_store import normalize_agent_id
from swarm.core.routine_tools import normalize_routine_tools, tools_explicit_from
from swarm.core.routines import (
    FILL_IN_SCAN_RE,
    OWNER_REPO_FILL_IN,
    TRIGGER_GITHUB_EVENT,
    TRIGGER_GITHUB_PR_MERGED,
    TRIGGER_MAILBOX_MESSAGE,
    DuplicateRoutineError,
    _coerce_owner_repo,
    create_routine,
    fill_in_token,
    list_routines,
    normalize_slug,
    public_routine,
    public_trigger,
    reject_secrets,
    routine_presets,
)
from swarm.core.schedule_triggers import reject_secrets as reject_secret_text

PACK_KIND = "agent_routines_pack"
PACK_OBJECT = "agent_routines_pack"
PACK_IMPORT_OBJECT = "agent_routines_pack_import"
PACK_SCHEMA = 1

_BINARY_KEYS = frozenset(
    {
        "assets",
        "files",
        "scripts",
        "binary",
        "binaries",
        "content_b64",
        "base64",
        "attachment",
        "attachments",
        "path",
        "paths",
    }
)
FILL_IN_LABELS = {
    "owner_repo": "GitHub owner/repo",
    "repo": "GitHub owner/repo",
    "repository": "GitHub owner/repo",
    "sender": "Mailbox sender",
    "channel": "Channel",
    "channel_id": "Channel",
    "schedule": "Schedule",
    "cron": "Cron expression",
}
_OPEN_SENDERS = frozenset({"", "anyone", "*"})


class PackValidationError(ValueError):
    """Invalid routines pack. ``code`` is stable for API clients."""

    def __init__(self, message: str, *, code: str = "pack_invalid") -> None:
        super().__init__(message)
        self.code = code


def _reject_binaries(raw: Any, *, where: str) -> None:
    if isinstance(raw, dict):
        hits = sorted(key for key in raw if str(key).strip().lower() in _BINARY_KEYS)
        if hits:
            raise PackValidationError(
                f"{where} must be prose only; refused binary field(s): {', '.join(hits)}",
                code="pack_binaries",
            )
        for key, value in raw.items():
            _reject_binaries(value, where=f"{where}.{key}")
    elif isinstance(raw, list):
        for index, item in enumerate(raw):
            _reject_binaries(item, where=f"{where}[{index}]")


def _fill_in_label(key: str) -> str:
    return FILL_IN_LABELS.get(key, key.replace("_", " "))


def _fill_in_row(key: str, *, locations: list[str] | None = None, required: bool = True) -> dict[str, Any]:
    row: dict[str, Any] = {
        "key": key,
        "label": _fill_in_label(key),
        "required": bool(required),
    }
    if locations:
        row["locations"] = list(locations)
    return row


def scan_fill_ins(text: Any, *, location: str) -> list[tuple[str, str]]:
    """Return ``(key, location)`` pairs for each ``{{key}}`` in *text*."""
    found: list[tuple[str, str]] = []
    for match in FILL_IN_SCAN_RE.finditer(str(text or "")):
        found.append((match.group(1), location))
    return found


def _collect_fill_ins(
    name: str,
    instruction: str,
    trigger: dict[str, Any],
    description: str = "",
) -> list[dict[str, Any]]:
    locations: dict[str, list[str]] = {}

    def _add(key: str, location: str) -> None:
        locations.setdefault(key, [])
        if location not in locations[key]:
            locations[key].append(location)

    for key, location in scan_fill_ins(name, location="name"):
        _add(key, location)
    for key, location in scan_fill_ins(description, location="description"):
        _add(key, location)
    for key, location in scan_fill_ins(instruction, location="instruction"):
        _add(key, location)

    def _walk(value: Any, prefix: str) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                _walk(child, f"{prefix}.{child_key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _walk(item, f"{prefix}[{index}]")
        else:
            token = fill_in_token(value)
            if token:
                match = FILL_IN_SCAN_RE.search(token)
                if match:
                    _add(match.group(1), prefix)
                return
            for key, location in scan_fill_ins(value, location=prefix):
                _add(key, location)

    _walk(trigger, "trigger")
    return [_fill_in_row(key, locations=locs) for key, locs in locations.items()]


def _merge_fill_ins(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        current = merged.setdefault(key, _fill_in_row(key, locations=[], required=bool(row.get("required", True))))
        if row.get("required"):
            current["required"] = True
        for location in row.get("locations") or []:
            locs = current.setdefault("locations", [])
            if location not in locs:
                locs.append(location)
    return list(merged.values())


def apply_fill_ins(value: Any, mapping: dict[str, str]) -> Any:
    """Substitute ``{{key}}`` tokens in strings; walk dicts/lists."""
    if isinstance(value, dict):
        return {key: apply_fill_ins(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [apply_fill_ins(item, mapping) for item in value]
    text = value if isinstance(value, str) else value
    if not isinstance(text, str):
        return value

    def _replace(match: Any) -> str:
        key = match.group(1)
        if key not in mapping:
            return match.group(0)
        return mapping[key]

    return FILL_IN_SCAN_RE.sub(_replace, text)


def _normalize_fill_in_mapping(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise PackValidationError("fill_ins must be an object of key → value", code="pack_fill_ins_invalid")
    out: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            text = reject_secret_text(str(value if value is not None else "").strip(), f"fill_ins.{name}")
        except ValueError as exc:
            raise PackValidationError(str(exc), code="pack_secret") from exc
        out[name] = text
    return out


def _github_needs_owner_repo(trigger: dict[str, Any]) -> bool:
    kind = str(trigger.get("kind") or "")
    return kind in {TRIGGER_GITHUB_EVENT, TRIGGER_GITHUB_PR_MERGED, ""}


def _pack_trigger(raw: Any, *, index: int) -> dict[str, Any]:
    incoming = dict(raw) if isinstance(raw, dict) else {}
    coerced = _coerce_owner_repo(incoming)
    token = fill_in_token(coerced) if coerced and not isinstance(coerced, dict) else None
    if token:
        incoming["owner_repo"] = token
    elif _github_needs_owner_repo(incoming) and not str(coerced or "").strip():
        incoming["owner_repo"] = OWNER_REPO_FILL_IN
    try:
        return public_trigger(incoming)
    except ValueError as exc:
        code = "pack_secret" if "secret" in str(exc).lower() else "pack_trigger_invalid"
        raise PackValidationError(
            f"routines[{index}].trigger: {exc}",
            code=code,
        ) from exc


def _pack_tools(raw: dict[str, Any], *, index: int) -> list[str] | None:
    """Normalized tool ids, or ``None`` when the row records no choice.

    ``None`` is meaningful: a routine with no explicit tools follows
    ``default_tools_for_trigger`` on the importing seat, and freezing today's
    defaults into a shared pack would silently pin them. An explicit empty
    list is a choice (the operator turned every tool off) and does travel.
    """
    if "tools" not in raw:
        return None
    value = raw.get("tools")
    if not isinstance(value, (list, tuple)):
        raise PackValidationError(
            f"routines[{index}].tools: tools must be a list of tool ids.",
            code="pack_tools_invalid",
        )
    try:
        return normalize_routine_tools(value)
    except ValueError as exc:
        code = "pack_secret" if "secret" in str(exc).lower() else "pack_tools_invalid"
        raise PackValidationError(f"routines[{index}].tools: {exc}", code=code) from exc


def _pack_model(raw: dict[str, Any]) -> str:
    """The routine's model id, carried verbatim (#1668).

    A model id is an id, not prose: the pack has no provider field, so the
    importer cannot translate it, and rewriting it would be a guess. The same
    value is dropped as a secret if it looks like a token, and a
    ``{{fill_in}}`` token is refused because ``model`` is not a scanned slot —
    only prose and the trigger are, so a token here could never be filled or
    reported as pending. An id the target host does not publish is ignored by
    ``model_namespace``, exactly like an uninstalled tool id.
    """
    value = str(raw.get("model") or "").strip()
    if not value:
        return ""
    if FILL_IN_SCAN_RE.search(value):
        raise PackValidationError(
            "routines[].model: model must be a model id, not a {{fill_in}} token.",
            code="pack_model_invalid",
        )
    try:
        return reject_secret_text(value, "model")
    except ValueError as exc:
        raise PackValidationError(str(exc), code="pack_secret") from exc


def _pack_routine(raw: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise PackValidationError(
            f"routines[{index}] must be an object with name, instruction, and trigger",
            code="pack_routine_invalid",
        )
    _reject_binaries(raw, where=f"routines[{index}]")
    try:
        name = reject_secrets(str(raw.get("name") or "").strip() or "New routine", "name")
        instruction = reject_secrets(str(raw.get("instruction") or ""), "instruction")
        raw_slug = str(raw.get("slug") or raw.get("key") or "").strip()
        slug = normalize_slug(reject_secret_text(raw_slug, "slug")) if raw_slug else ""
        role = str(raw.get("role") or "").strip()
        if role:
            role = reject_secret_text(role, "role")
        description = str(raw.get("description") or "").strip()
        if description:
            description = reject_secrets(description, "description")
    except ValueError as exc:
        raise PackValidationError(str(exc), code="pack_secret") from exc
    trigger = _pack_trigger(raw.get("trigger") if isinstance(raw.get("trigger"), dict) else {}, index=index)
    tools = _pack_tools(raw, index=index)
    model = _pack_model(raw)
    fill_ins = _collect_fill_ins(name, instruction, trigger, description)
    row: dict[str, Any] = {
        "name": name,
        "description": description,
        "instruction": instruction,
        "enabled": False,
        "trigger": trigger,
        "fill_ins": fill_ins,
    }
    if tools is not None:
        row["tools"] = tools
    if model:
        row["model"] = model
    if slug:
        row["slug"] = slug
        row["key"] = slug
    if role:
        row["role"] = role
    return row


def validate_pack(raw: Any) -> dict[str, Any]:
    """Normalize a routines pack fragment. Raises :class:`PackValidationError`."""
    if not isinstance(raw, dict):
        raise PackValidationError("pack must be a JSON object", code="pack_invalid")
    _reject_binaries(raw, where="pack")
    routines_raw = raw.get("routines")
    if routines_raw is None:
        raise PackValidationError("pack must include routines[]", code="pack_routines_missing")
    if not isinstance(routines_raw, list) or not routines_raw:
        raise PackValidationError("pack routines must be a non-empty list", code="pack_routines_missing")
    routines = [_pack_routine(item, index=index) for index, item in enumerate(routines_raw)]
    fill_ins = _merge_fill_ins([slot for row in routines for slot in row["fill_ins"]])
    declared = raw.get("fill_ins")
    if isinstance(declared, list):
        extra = []
        for item in declared:
            if isinstance(item, dict) and item.get("key"):
                extra.append(_fill_in_row(str(item["key"]), required=bool(item.get("required", True))))
            elif isinstance(item, str) and item.strip():
                extra.append(_fill_in_row(item.strip()))
        fill_ins = _merge_fill_ins(fill_ins + extra)
    kind = str(raw.get("kind") or PACK_KIND).strip() or PACK_KIND
    pack: dict[str, Any] = {
        "object": PACK_OBJECT,
        "kind": kind,
        "schema": PACK_SCHEMA,
        "routines": routines,
        "fill_ins": fill_ins,
    }
    agent = str(raw.get("agent_id") or "").strip()
    if agent:
        pack["agent_id"] = normalize_agent_id(agent)
    return pack


def _owner_repo_text(value: Any) -> str:
    if isinstance(value, dict):
        owner = str(value.get("owner") or "").strip()
        repo = str(value.get("repo") or "").strip()
        return f"{owner}/{repo}" if owner and repo else ""
    return str(value or "").strip()


def _replace_concrete(text: str, pairs: list[tuple[str, str]]) -> str:
    """Replace id strings without eating a longer owner/repo or address."""
    for concrete, token in pairs:
        if not concrete:
            continue
        if "/" in concrete:
            # A dot ends a sentence or an ellipsis on either side.
            # "notes.owner" and ".docs" are still another repo.
            pattern = (
                rf"(?<![\w-])(?<![\w-][.])"
                rf"{re.escape(concrete)}"
                rf"(?![\w-]|[.][\w-])"
            )
        else:
            # A dot ends an address or an ellipsis on either side.
            # "team.ops@" and ".com" are still a longer address.
            pattern = (
                rf"(?<![\w+-])(?<![\w+-][.])"
                rf"{re.escape(concrete)}"
                rf"(?![\w+-]|[.][\w+-])"
            )
        text = re.sub(pattern, lambda _match, replacement=token: replacement, text, flags=re.IGNORECASE)
    return text


def _replace_concrete_tree(value: Any, pairs: list[tuple[str, str]]) -> Any:
    if isinstance(value, str):
        return _replace_concrete(value, pairs)
    if isinstance(value, dict):
        return {key: _replace_concrete_tree(child, pairs) for key, child in value.items()}
    if isinstance(value, list):
        return [_replace_concrete_tree(child, pairs) for child in value]
    return value


def _strip_concrete_ids(raw: dict[str, Any]) -> dict[str, Any]:
    """Rewrite live repo and mailbox sender ids to fill-in tokens.

    Named tokens (``{{owner_repo}}``, ``{{channel}}``, ``{{sender}}``) are
    the pack's ``{{FILL_IN}}`` slots. The same concrete strings are replaced
    in name, description, instruction, and the rest of the trigger (including
    a mailbox pattern) so the recipe does not leak them. Matching is
    case-insensitive and stops at an owner/repo or address boundary.
    """
    row = dict(raw)
    trigger = dict(row.get("trigger") if isinstance(row.get("trigger"), dict) else {})
    kind = str(trigger.get("kind") or "").strip()
    replacements: list[tuple[str, str]] = []
    github = kind in {TRIGGER_GITHUB_EVENT, TRIGGER_GITHUB_PR_MERGED, ""}
    owner_text = _owner_repo_text(trigger.get("owner_repo"))
    if not owner_text:
        owner_text = _owner_repo_text(trigger.get("repository") or trigger.get("repo"))
    if github and owner_text and not fill_in_token(owner_text) and "/" in owner_text:
        trigger["owner_repo"] = OWNER_REPO_FILL_IN
        trigger.pop("repository", None)
        trigger.pop("repo", None)
        replacements.append((owner_text, OWNER_REPO_FILL_IN))
    if kind == TRIGGER_MAILBOX_MESSAGE:
        sender = str(trigger.get("sender") or "").strip()
        if sender and sender.lower() not in _OPEN_SENDERS and not fill_in_token(sender):
            trigger["sender"] = "{{sender}}"
            replacements.append((sender, "{{sender}}"))
    channel = str(trigger.get("channel") or trigger.get("channel_id") or trigger.get("channelId") or "").strip()
    if channel and not fill_in_token(channel):
        trigger["channel"] = "{{channel}}"
        trigger.pop("channel_id", None)
        trigger.pop("channelId", None)
        replacements.append((channel, "{{channel}}"))
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    row["trigger"] = _replace_concrete_tree(trigger, replacements)
    for field in ("name", "instruction", "description"):
        text = row.get(field)
        if not isinstance(text, str) or not text:
            continue
        row[field] = _replace_concrete(text, replacements)
    return row


def _routine_to_pack_row(routine: dict[str, Any]) -> dict[str, Any]:
    source: dict[str, Any] = {
        "name": routine.get("name"),
        "instruction": routine.get("instruction"),
        "trigger": routine.get("trigger") if isinstance(routine.get("trigger"), dict) else {},
        "key": routine.get("key"),
        "slug": routine.get("slug") or routine.get("key"),
        "role": routine.get("role"),
        "description": routine.get("description"),
    }
    model = str(routine.get("model") or "").strip()
    if model:
        source["model"] = model
    if tools_explicit_from(routine):
        # An operator's list is content. Trigger defaults are not: they follow
        # the trigger, which already travels with the row.
        source["tools"] = list(routine.get("tools") or [])
    return _pack_routine(_strip_concrete_ids(source), index=0)


def build_pack(
    agent_id: str,
    *,
    routine_ids: list[str] | None = None,
    include_presets: bool = False,
) -> dict[str, Any]:
    """Pack selected (or all) seat routines as a secret-free fragment.

    Concrete GitHub ``owner_repo`` values and mailbox senders become required
    fill-ins. Empty GitHub ``owner_repo`` values become ``{{owner_repo}}`` too.
    Built-in presets can be folded in with *include_presets*.
    """
    selected: list[dict[str, Any]] = []
    existing = list_routines(agent_id)
    if routine_ids is None:
        selected.extend(existing)
    else:
        wanted = {str(item).strip() for item in routine_ids if str(item).strip()}
        by_id = {row["id"]: row for row in existing}
        missing = sorted(wanted - set(by_id))
        if missing:
            raise PackValidationError(
                f"unknown routine id(s): {', '.join(missing)}",
                code="pack_routine_missing",
            )
        selected.extend(by_id[rid] for rid in routine_ids if str(rid).strip() in by_id)
    if include_presets:
        selected.extend(routine_presets())
    if not selected:
        raise PackValidationError("pack routines must be a non-empty list", code="pack_routines_missing")
    return validate_pack(
        {
            "kind": PACK_KIND,
            "agent_id": normalize_agent_id(agent_id),
            "routines": [_routine_to_pack_row(row) for row in selected],
        }
    )


def routines_section_for_pack(agent_id: str) -> dict[str, Any]:
    """Secret-free ``routines`` section for an umbrella template pack (#1398)."""
    try:
        pack = build_pack(agent_id)
    except PackValidationError:
        return {"routines": [], "fill_ins": []}
    return {"routines": pack["routines"], "fill_ins": pack["fill_ins"]}


def _remaining_fill_ins(routines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _merge_fill_ins([slot for row in routines for slot in row.get("fill_ins") or []])


def _prepare_import_row(row: dict[str, Any], mapping: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply fill-ins and validate one row before any routine is written."""
    filled = {
        "name": apply_fill_ins(row["name"], mapping),
        "description": apply_fill_ins(row.get("description") or "", mapping),
        "instruction": apply_fill_ins(row["instruction"], mapping),
        "trigger": apply_fill_ins(row["trigger"], mapping),
    }
    leftover = _collect_fill_ins(
        filled["name"],
        filled["instruction"],
        filled["trigger"],
        filled["description"],
    )
    payload = {
        "name": filled["name"],
        "description": filled["description"],
        "instruction": filled["instruction"],
        "slug": row.get("slug") or row.get("key") or "",
        "trigger": filled["trigger"],
        "active": False,
    }
    # ``create_routine`` only marks tools explicit when the key is present, so
    # an absent key keeps the trigger's defaults and an explicit empty list
    # keeps the operator's "no tools" choice.
    if "tools" in row:
        payload["tools"] = list(row.get("tools") or [])
    if row.get("model"):
        payload["model"] = row["model"]
    try:
        public_routine({**payload, "id": "pack-preview", "history": []})
    except ValueError as exc:
        raise PackValidationError(str(exc), code="pack_import_invalid") from exc
    return payload, {**filled, "fill_ins": leftover}


def import_pack(
    agent_id: str,
    raw: Any,
    *,
    fill_ins: Any = None,
) -> dict[str, Any]:
    """Recreate packed routines on *agent_id*, always inactive (pending enable)."""
    pack = validate_pack(raw)
    if isinstance(raw, dict) and fill_ins is None:
        fill_ins = raw.get("fill_in_values")
    mapping = _normalize_fill_in_mapping(fill_ins)
    prepared = [_prepare_import_row(row, mapping) for row in pack["routines"]]
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    applied_rows: list[dict[str, Any]] = []
    created_count = 0
    for payload, applied in prepared:
        applied_rows.append(applied)
        try:
            routine = create_routine(agent_id, payload)
        except DuplicateRoutineError as exc:
            existing = exc.existing or {}
            skipped.append(
                {
                    "name": payload["name"],
                    "existing_routine_id": exc.existing_id,
                    "reason": "duplicate",
                }
            )
            if existing:
                imported.append(public_routine(existing))
            continue
        except ValueError as exc:
            raise PackValidationError(str(exc), code="pack_import_invalid") from exc
        if routine.get("active"):
            raise PackValidationError(
                "import must leave routines pending enable (active=false)",
                code="pack_pending_enable",
            )
        imported.append(routine)
        created_count += 1
    remaining = _remaining_fill_ins(applied_rows)
    return {
        "object": PACK_IMPORT_OBJECT,
        "agent_id": normalize_agent_id(agent_id),
        "pending_enable": True,
        "routines": imported,
        "created_count": created_count,
        "skipped": skipped,
        "fill_ins_applied": sorted(mapping),
        "fill_ins_remaining": remaining,
        "pack": pack,
    }

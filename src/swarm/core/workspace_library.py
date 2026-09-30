"""Scoped workspace library (issue #1311).

``personal | team | org`` recipes live in ``SharedLibraryItem``. The on-disk
blueprint library stays the default personal catalog. Org and team rows are
visible to other principals on this server; a personal row is visible only
to its owner.
"""

from __future__ import annotations

from typing import Any

from swarm.core.config_ownership import (
    ConfigOwnershipError,
    redact_for_api,
    refuse_plaintext_secrets,
)

SCOPES = ("personal", "team", "org")
KINDS = ("blueprint", "plugin", "team")
OBJECT_ITEM = "shared_library.item"


class LibraryError(ValueError):
    """User-facing library failure with an HTTP status."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.status = status


class LibraryPermissionError(LibraryError):
    """Caller may not read or change this row."""

    def __init__(self, message: str = "Not allowed to access that library item.", *, status: int = 403):
        super().__init__(message, status=status)


def _model():
    from swarm.models import SharedLibraryItem

    return SharedLibraryItem


def _clean_key(raw: Any, *, label: str) -> str:
    text = str(raw or "").strip()
    if not text or len(text) > 128:
        raise LibraryError(f"{label} is required.")
    if any(ch in text for ch in ("/", "\\", "\x00")):
        raise LibraryError(f"{label} must be a plain id.")
    return text


def _require_principal(principal: str | None) -> str:
    text = str(principal or "").strip()
    if not text:
        raise LibraryPermissionError("Authentication required.", status=401)
    return text


def resolve_scope(
    scope: str | None,
    *,
    principal: str | None,
    team_id: str | None = None,
) -> dict[str, str]:
    """Normalize a library scope. Default is personal."""
    value = str(scope or "personal").strip().lower() or "personal"
    if value not in SCOPES:
        raise LibraryError("scope must be personal, team, or org.")
    actor = _require_principal(principal)
    team = str(team_id or "").strip()
    if value == "team":
        if not team:
            raise LibraryError("team_id is required for team scope.")
        # Team scope is a roster id (chat ``?team=``), not an LLM-profile alias.
        from swarm.core.team_rosters import get_roster

        roster = get_roster(team)
        if not isinstance(roster, dict):
            raise LibraryError(f"Team '{team}' was not found.", status=404)
        team = str(roster.get("id") or team)
    else:
        team = ""
    return {"scope": value, "principal": actor, "team_id": team}


def _public(row) -> dict[str, Any]:
    payload = row.payload if isinstance(row.payload, dict) else {}
    return {
        "id": str(row.pk),
        "object": OBJECT_ITEM,
        "scope": row.scope,
        "kind": row.kind,
        "item_key": row.item_key,
        "title": row.title,
        "owner_principal": row.owner_principal,
        "owner_team": row.owner_team or "",
        "published": bool(row.published),
        "payload": payload,
    }


def _guard_payload(payload: Any) -> dict[str, Any]:
    body = dict(payload or {}) if isinstance(payload, dict) else {}
    try:
        refuse_plaintext_secrets(body)
    except ConfigOwnershipError as exc:
        raise LibraryError(str(exc), status=getattr(exc, "status", 400)) from exc
    redacted = redact_for_api(body)
    return redacted if isinstance(redacted, dict) else {}


def list_items(
    *,
    scope: str | None,
    principal: str | None,
    team_id: str | None = None,
    kind: str | None = None,
    include_unpublished: bool = False,
) -> list[dict[str, Any]]:
    """List shared rows visible to *principal* in *scope*."""
    resolved = resolve_scope(scope, principal=principal, team_id=team_id)
    SharedLibraryItem = _model()
    qs = SharedLibraryItem.objects.filter(scope=resolved["scope"])
    if resolved["scope"] == "personal":
        qs = qs.filter(owner_principal=resolved["principal"])
    elif resolved["scope"] == "team":
        qs = qs.filter(owner_team=resolved["team_id"])
    if not include_unpublished:
        qs = qs.filter(published=True)
    if kind:
        want = str(kind).strip().lower()
        if want not in KINDS:
            raise LibraryError("kind must be blueprint, plugin, or team.")
        qs = qs.filter(kind=want)
    return [_public(row) for row in qs.order_by("kind", "item_key", "id")]


def _lookup_owned(*, scope: str, kind: str, item_key: str, principal: str, team_id: str):
    SharedLibraryItem = _model()
    return SharedLibraryItem.objects.filter(
        scope=scope,
        kind=kind,
        item_key=item_key,
        owner_principal=principal,
        owner_team=team_id,
    ).first()


def publish(
    *,
    kind: str,
    item_key: str,
    principal: str | None,
    scope: str | None = "personal",
    team_id: str | None = None,
    title: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish a recipe into personal, team, or org scope."""
    kind_key = str(kind or "").strip().lower()
    if kind_key not in KINDS:
        raise LibraryError("kind must be blueprint, plugin, or team.")
    resolved = resolve_scope(scope, principal=principal, team_id=team_id)
    key = _clean_key(item_key, label="id")
    stored_payload = _guard_payload(payload)
    label = str(title or stored_payload.get("name") or key).strip()[:200]
    SharedLibraryItem = _model()
    row = _lookup_owned(
        scope=resolved["scope"],
        kind=kind_key,
        item_key=key,
        principal=resolved["principal"],
        team_id=resolved["team_id"],
    )
    if row is None:
        row = SharedLibraryItem(
            scope=resolved["scope"],
            kind=kind_key,
            item_key=key,
            owner_principal=resolved["principal"],
            owner_team=resolved["team_id"],
        )
    row.title = label
    row.payload = stored_payload
    row.published = True
    row.save()
    return _public(row)


def unpublish(*, item_id: str, principal: str | None) -> dict[str, Any]:
    """Hide a row. Only the publishing principal may unpublish it."""
    actor = _require_principal(principal)
    row = _get_row(item_id)
    if row.owner_principal != actor:
        raise LibraryPermissionError("Only the publisher can unpublish this item.")
    row.published = False
    row.save(update_fields=["published", "updated_at"])
    return _public(row)


def _get_row(item_id: str):
    SharedLibraryItem = _model()
    ident = str(item_id or "").strip()
    if not ident.isdigit():
        raise LibraryError("Library item id is required.")
    row = SharedLibraryItem.objects.filter(pk=int(ident)).first()
    if row is None:
        raise LibraryError("Library item was not found.", status=404)
    return row


def _visible(row, principal: str, *, team_id: str | None = None) -> None:
    if not row.published:
        raise LibraryError("Library item was not found.", status=404)
    if row.scope == "personal" and row.owner_principal != principal:
        raise LibraryPermissionError("Personal library items are visible only to their owner.")
    if row.scope == "team" and str(team_id or "").strip() != (row.owner_team or ""):
        raise LibraryPermissionError("Team library items require that team's id.")


def _install_blueprint(name: str) -> None:
    from swarm.views.blueprint_library_views import (
        get_user_blueprint_library,
        save_user_blueprint_library,
    )

    library = get_user_blueprint_library()
    if not isinstance(library, dict):
        library = {"installed": [], "custom": []}
    installed = library.setdefault("installed", [])
    if name not in installed:
        installed.append(name)
        if not save_user_blueprint_library(library):
            raise LibraryError("Failed to save the personal blueprint library.", status=500)


def import_item(
    *,
    item_id: str,
    principal: str | None,
    team_id: str | None = None,
) -> dict[str, Any]:
    """Copy a visible shared row into the caller personal library or roster.

    Team rows are not importable by primary key alone. The caller must pass
    the same ``team_id`` the row was published under. Org rows stay visible
    to every principal on this install.
    """
    actor = _require_principal(principal)
    row = _get_row(item_id)
    _visible(row, actor, team_id=team_id)
    if row.kind == "team":
        from swarm.core.team_rosters import import_roster

        preview = import_roster(row.payload if isinstance(row.payload, dict) else {})
        copied = publish(
            kind="team",
            item_key=row.item_key,
            principal=actor,
            scope="personal",
            title=row.title,
            payload=row.payload if isinstance(row.payload, dict) else {},
        )
        return {
            "object": "shared_library.import",
            "imported": True,
            "item": copied,
            "roster": preview,
            "needs_configuration": preview.get("needs_configuration") or [],
        }
    if row.kind == "blueprint":
        _install_blueprint(row.item_key)
    copied = publish(
        kind=row.kind,
        item_key=row.item_key,
        principal=actor,
        scope="personal",
        title=row.title,
        payload=row.payload if isinstance(row.payload, dict) else {},
    )
    return {"object": "shared_library.import", "imported": True, "item": copied}


def build_roster_pack(
    roster: dict[str, Any],
    *,
    skill_ids: list[str] | None = None,
    mcp_server_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Roster pack: member kind/role, blueprint ids, MCP server ids, skill ids."""
    from swarm.core.team_rosters import serialize_roster

    serialized = serialize_roster(roster)
    raw_members = roster.get("members") if isinstance(roster.get("members"), list) else []
    members: list[dict[str, Any]] = []
    blueprint_ids: list[str] = []
    skills: list[str] = []
    for index, member in enumerate(serialized.get("members") or []):
        if not isinstance(member, dict):
            continue
        raw = raw_members[index] if index < len(raw_members) and isinstance(raw_members[index], dict) else {}
        source = str(member.get("source") or "")
        blueprint_id = ""
        if source.startswith("blueprint:"):
            blueprint_id = source.split(":", 1)[1]
        elif str(member.get("kind") or "") == "blueprint":
            blueprint_id = str(member.get("id") or "")
        skill_id = str(raw.get("skill_id") or "").strip()
        if source.startswith("skill:"):
            skill_id = source.split(":", 1)[1]
        row = {
            "id": member.get("id"),
            "name": member.get("name") or member.get("id"),
            "kind": member.get("kind"),
            "role": member.get("role"),
            "source": source,
        }
        if blueprint_id:
            row["blueprint_id"] = blueprint_id
            if blueprint_id not in blueprint_ids:
                blueprint_ids.append(blueprint_id)
        if skill_id and skill_id not in skills:
            skills.append(skill_id)
        members.append(row)
    roster_blueprint = str(serialized.get("blueprint_id") or roster.get("blueprint_id") or "").strip()
    if roster_blueprint and roster_blueprint not in blueprint_ids:
        blueprint_ids.append(roster_blueprint)
    servers: list[str] = []
    for tool in serialized.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "mcp":
            server = str(tool.get("server") or "").strip()
            if server and server not in servers:
                servers.append(server)
    for extra in mcp_server_ids or roster.get("mcp_server_ids") or []:
        server = str(extra or "").strip()
        if server and server not in servers:
            servers.append(server)
    for extra in skill_ids or roster.get("skill_ids") or []:
        skill = str(extra or "").strip()
        if skill and skill not in skills:
            skills.append(skill)
    return {
        "object": "team_roster_pack",
        "id": serialized["id"],
        "name": serialized.get("name") or serialized["id"],
        "members": members,
        "blueprint_ids": blueprint_ids,
        "mcp_server_ids": servers,
        "skill_ids": skills,
        "tools": serialized.get("tools") or [],
        "wires": serialized.get("wires") or {},
    }


def share_team(
    *,
    roster_id: str,
    principal: str | None,
    scope: str | None = "org",
    team_id: str | None = None,
    skill_ids: list[str] | None = None,
    mcp_server_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Publish a whole roster pack to org or team scope."""
    from swarm.core.team_rosters import get_roster

    rid = _clean_key(roster_id, label="roster_id")
    roster = get_roster(rid)
    if roster is None:
        raise LibraryError(f"Roster '{rid}' was not found.", status=404)
    pack = build_roster_pack(roster, skill_ids=skill_ids, mcp_server_ids=mcp_server_ids)
    return publish(
        kind="team",
        item_key=rid,
        principal=principal,
        scope=scope or "org",
        team_id=team_id,
        title=str(pack.get("name") or rid),
        payload=pack,
    )

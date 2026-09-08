"""Support/CoS roster tools — create + archive + restore + purge (REQ-154 / #562).

Support and Chief of Staff (API-kind) can grow or trim the rail via tools + NL.
Ordinary roles do **not** get these tools. Created seats always stamp
``role=default`` so this path cannot mint another Support/CoS/gate/skeptic.

Archive is a soft-delete (``archived`` + ``archived_at``). The seat drops off
the default AGENTS rail and mailbox discoverability. Restore works until a
purge. ``manage.py purge_archived_agents`` hard-deletes archived rows older
than ~30 days (``SWARM_ARCHIVED_AGENT_RETENTION_DAYS``).

No secrets. Env-var **names** only. No Neon. No live demo-port seed.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

from swarm.core.agent_kind import AgentKind, classify_agent_kind
from swarm.core.agent_roles import (
    can_manage_agent_lifecycle,
    normalize_agent_role,
)
from swarm.core.rail_seats import (
    ADD_AGENT_SOURCE,
    DEMO_CATALOG_IDS,
    RAIL_ROLE_IDS,
    CustomSeatError,
    already_hidden,
    build_custom_rail_item,
    infer_custom_kind,
    is_seed_demo_row,
    row_id,
)
from swarm.core.team_isolation import role_of_member
from swarm.core.cli_session_hop import redact_injection_text
from swarm.core.transcript_roles import append_event
from swarm.tool_executor import redact_sensitive_data

logger = logging.getLogger(__name__)

CREATE_TOOL_NAME = "create_agent"
ARCHIVE_TOOL_NAME = "archive_agent"
RESTORE_TOOL_NAME = "restore_agent"
LIST_ARCHIVED_TOOL_NAME = "list_archived_agents"

V1_KIND: AgentKind = "api"
CREATE_KINDS = frozenset({"api", "cli", "remote", "blueprint"})
LIFECYCLE_SOURCE = "support-lifecycle"
DEFAULT_RETENTION_DAYS = 30
RETENTION_ENV = "SWARM_ARCHIVED_AGENT_RETENTION_DAYS"
STARTER_SUPPORT_ID = "starter-support"

ERROR_ROLE = "role_forbidden"
ERROR_CALLER_KIND = "caller_kind_unsupported"
ERROR_UNKNOWN_ID = "unknown_id"
ERROR_PROTECTED = "protected_seat"
ERROR_ALREADY_EXISTS = "already_exists"
ERROR_ALREADY_ARCHIVED = "already_archived"
ERROR_NOT_ARCHIVED = "not_archived"
ERROR_INVALID_KIND = "invalid_kind"
ERROR_INVALID_ID = "invalid_id"
ERROR_SECRET = "secret_refused"
ERROR_CLI_COMMAND = "cli_command_required"
ERROR_REMOTE = "remote_error"
ERROR_PERSIST = "persist_failed"
ERROR_TEAM = "team_error"

StoreKind = Literal["custom", "remote"]

_ID_SAFE = re.compile(r"[^a-z0-9_-]+")

PROTECTED_LIFECYCLE_IDS = frozenset(RAIL_ROLE_IDS) | {STARTER_SUPPORT_ID, "support"}

STARTER_BLUEPRINT_CODE = '''from typing import Any, ClassVar

from agents import Agent

from swarm.core.kind_bases import ApiKindBase


class {class_name}(ApiKindBase):
    """Safe Support/CoS starter seat. No secrets. No live host."""

    metadata: ClassVar[dict[str, Any]] = {{
        "name": "{ident}",
        "title": "{title}",
        "description": "{description}",
        "version": "0.1.0",
        "tags": ["user", "lifecycle"],
        "rail": True,
    }}

    def create_starting_agent(self, mcp_servers):
        return Agent(
            name="{title}",
            instructions="Do the work the operator asked for.",
        )
'''


class LifecycleError(Exception):
    """Tool-safe lifecycle failure with a stable reason code."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "error": self.reason, "message": self.message}


def retention_days(raw: Any = None) -> int:
    """Days an archived seat stays recoverable. Default 30. ``<=0`` disables purge."""
    if raw is None:
        raw = os.environ.get(RETENTION_ENV, "")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_RETENTION_DAYS
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_RETENTION_DAYS
    return value


def slugify_agent_id(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    text = _ID_SAFE.sub("_", text).strip("_-")
    return text[:64]


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def looks_like_secret(value: Any) -> bool:
    text = str(value or "")
    if not text.strip():
        return False
    redacted = redact_injection_text(text)
    return redacted != text


def refuse_secrets(*values: Any) -> None:
    for value in values:
        if looks_like_secret(value):
            raise LifecycleError(
                ERROR_SECRET,
                "Refusing secret-shaped text. Use env var names only.",
            )


def is_lifecycle_protected_id(ident: str) -> bool:
    key = slugify_agent_id(ident).replace("-", "_")
    return key in PROTECTED_LIFECYCLE_IDS or key in {item.replace("-", "_") for item in DEMO_CATALOG_IDS}


def catalog_archived_ids(
    *,
    library: dict[str, Any] | None = None,
    remotes: dict[str, Any] | None = None,
) -> frozenset[str]:
    """Ids stamped ``archived: true`` on custom-library and remotes stores."""
    found: set[str] = set()
    lib = library if isinstance(library, dict) else _load_library()
    for raw in lib.get("custom") or []:
        if isinstance(raw, dict) and raw.get("archived") is True:
            ident = row_id(raw)
            if ident:
                found.add(ident)
    remote_map = remotes if isinstance(remotes, dict) else _load_remotes_map()
    for key, entry in remote_map.items():
        if isinstance(entry, dict) and entry.get("archived") is True:
            found.add(str(key))
    return frozenset(found)


def remote_entry_is_archived(entry: Any) -> bool:
    return isinstance(entry, dict) and entry.get("archived") is True


@dataclass
class LifecycleStores:
    """In-memory or disk-backed stores for one tool session."""

    library: dict[str, Any] = field(default_factory=lambda: {"installed": [], "custom": []})
    remotes: dict[str, Any] = field(default_factory=dict)
    remotes_cfg: dict[str, Any] | None = None
    remotes_path: Path | None = None
    rosters: dict[str, Any] | None = None
    persist_library: bool = False
    persist_remotes: bool = False
    persist_rosters: bool = False


def _load_library() -> dict[str, Any]:
    try:
        from swarm.views.blueprint_library_views import get_user_blueprint_library

        lib = get_user_blueprint_library()
        if isinstance(lib, dict):
            lib.setdefault("custom", [])
            lib.setdefault("installed", [])
            return lib
    except Exception:
        logger.debug("lifecycle library load unavailable", exc_info=True)
    return {"installed": [], "custom": []}


def _save_library(library: dict[str, Any]) -> bool:
    try:
        from swarm.views.blueprint_library_views import save_user_blueprint_library

        return bool(save_user_blueprint_library(library))
    except Exception:
        logger.debug("lifecycle library save unavailable", exc_info=True)
        return False


def _load_remotes_bundle() -> tuple[dict[str, Any], dict[str, Any], Path | None]:
    try:
        from swarm.core.remotes import load_raw_config

        cfg, path = load_raw_config()
        remotes = cfg.get("remotes") if isinstance(cfg.get("remotes"), dict) else {}
        return cfg, dict(remotes), path
    except Exception:
        logger.debug("lifecycle remotes load unavailable", exc_info=True)
        return {}, {}, None


def _load_remotes_map() -> dict[str, Any]:
    return _load_remotes_bundle()[1]


def _save_remotes(cfg: dict[str, Any], remotes: dict[str, Any], path: Path | None) -> bool:
    if path is None:
        return False
    try:
        import json

        cfg = dict(cfg)
        cfg["remotes"] = remotes
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
        try:
            from swarm.core.config_ownership import refresh_app_config

            refresh_app_config()
        except Exception:
            logger.debug("lifecycle remotes refresh skipped", exc_info=True)
        return True
    except Exception:
        logger.debug("lifecycle remotes save unavailable", exc_info=True)
        return False


def default_stores() -> LifecycleStores:
    cfg, remotes, path = _load_remotes_bundle()
    rosters = None
    try:
        from swarm.core.team_rosters import load_team_rosters

        rosters = load_team_rosters()
    except Exception:
        logger.debug("lifecycle rosters load unavailable", exc_info=True)
    return LifecycleStores(
        library=_load_library(),
        remotes=remotes,
        remotes_cfg=cfg,
        remotes_path=path,
        rosters=rosters,
        persist_library=True,
        persist_remotes=True,
        persist_rosters=True,
    )


@dataclass
class LifecycleContext:
    """Bound caller + stores for one Support/CoS tool session."""

    caller_id: str
    caller_kind: AgentKind = V1_KIND
    caller_role: str = "default"
    user_key: str = ""
    chat_base_dir: Path | None = None
    stores: LifecycleStores = field(default_factory=LifecycleStores)
    now: datetime | None = None

    def current_time(self) -> datetime:
        return self.now or utc_now()

    def eligible(self) -> None:
        if self.caller_kind != V1_KIND:
            raise LifecycleError(
                ERROR_CALLER_KIND,
                "create/archive tools are API-kind only in v1 (Support / API CoS).",
            )
        if not can_manage_agent_lifecycle(self.caller_role):
            raise LifecycleError(
                ERROR_ROLE,
                "Only Support and Chief of Staff can create or archive agents.",
            )

    def create_agent(
        self,
        name: str,
        kind: str,
        command: str = "",
        description: str = "",
        blueprint_code: str = "",
        remote_kind: str = "",
        base_url: str = "",
        api_key_env: str = "",
        team_id: str = "",
    ) -> dict[str, Any]:
        try:
            self.eligible()
            refuse_secrets(name, kind, command, description, blueprint_code, remote_kind, base_url, api_key_env, team_id)
            ident, created = self._create(
                name=name,
                kind=kind,
                command=command,
                description=description,
                blueprint_code=blueprint_code,
                remote_kind=remote_kind,
                base_url=base_url,
                api_key_env=api_key_env,
                team_id=team_id,
            )
            self._audit(f"Created agent {ident} ({created.get('kind') or kind})")
            logger.info(
                "lifecycle create caller=%s id=%s kind=%s",
                self.caller_id,
                ident,
                created.get("kind") or kind,
            )
            return {"ok": True, "agent": created, "audit": f"Created agent {ident}"}
        except LifecycleError as exc:
            logger.info("lifecycle create rejected %s (%s)", self.caller_id, exc.reason)
            return exc.as_dict()

    def archive_agent(self, agent_id: str) -> dict[str, Any]:
        try:
            self.eligible()
            refuse_secrets(agent_id)
            ident, row = self._archive(agent_id)
            self._audit(f"Archived agent {ident}")
            logger.info("lifecycle archive caller=%s id=%s", self.caller_id, ident)
            return {
                "ok": True,
                "agent": _public_row(row),
                "recoverable_until": row.get("archived_at"),
                "retention_days": retention_days(),
                "audit": f"Archived agent {ident}",
            }
        except LifecycleError as exc:
            logger.info("lifecycle archive rejected %s (%s)", self.caller_id, exc.reason)
            return exc.as_dict()

    def restore_agent(self, agent_id: str) -> dict[str, Any]:
        try:
            self.eligible()
            refuse_secrets(agent_id)
            ident, row = self._restore(agent_id)
            self._audit(f"Restored agent {ident}")
            logger.info("lifecycle restore caller=%s id=%s", self.caller_id, ident)
            return {"ok": True, "agent": _public_row(row), "audit": f"Restored agent {ident}"}
        except LifecycleError as exc:
            logger.info("lifecycle restore rejected %s (%s)", self.caller_id, exc.reason)
            return exc.as_dict()

    def list_archived_agents(self) -> dict[str, Any]:
        try:
            self.eligible()
            rows = self._list_archived()
            return {"ok": True, "agents": rows, "retention_days": retention_days()}
        except LifecycleError as exc:
            return exc.as_dict()

    def as_callables(self) -> list[Any]:
        def create_agent(
            name: str,
            kind: str,
            command: str = "",
            description: str = "",
            blueprint_code: str = "",
            remote_kind: str = "",
            base_url: str = "",
            api_key_env: str = "",
            team_id: str = "",
        ) -> dict[str, Any]:
            """Create a CLI, API, remote, or blueprint seat with safe defaults."""
            return self.create_agent(
                name=name,
                kind=kind,
                command=command,
                description=description,
                blueprint_code=blueprint_code,
                remote_kind=remote_kind,
                base_url=base_url,
                api_key_env=api_key_env,
                team_id=team_id,
            )

        def archive_agent(agent_id: str) -> dict[str, Any]:
            """Soft-delete an agent. Hidden from the default rail; recoverable ~30 days."""
            return self.archive_agent(agent_id)

        def restore_agent(agent_id: str) -> dict[str, Any]:
            """Un-archive an agent before the purge window elapses."""
            return self.restore_agent(agent_id)

        def list_archived_agents() -> dict[str, Any]:
            """List archived seats still inside the ~30 day recovery window."""
            return self.list_archived_agents()

        create_agent.name = CREATE_TOOL_NAME
        create_agent.description = (
            "Create a rail seat. kind=cli|api|remote|blueprint. Safe defaults "
            "(role=default, no secrets). CLI needs command. Remote: env var names only."
        )
        archive_agent.name = ARCHIVE_TOOL_NAME
        archive_agent.description = (
            "Archive (soft-delete) an agent. Hides it from the default rail. "
            "Recoverable for about 30 days, then a purge job hard-deletes it."
        )
        restore_agent.name = RESTORE_TOOL_NAME
        restore_agent.description = "Restore an archived agent before the ~30 day purge."
        list_archived_agents.name = LIST_ARCHIVED_TOOL_NAME
        list_archived_agents.description = "List archived agents and their archived_at stamps."
        return [create_agent, archive_agent, restore_agent, list_archived_agents]

    def as_function_tools(self) -> list[Any]:
        try:
            from agents import function_tool
        except Exception:
            logger.debug("agents SDK not available; lifecycle as_function_tools() -> []")
            return []

        def create_agent(
            name: str,
            kind: str,
            command: str = "",
            description: str = "",
            blueprint_code: str = "",
            remote_kind: str = "",
            base_url: str = "",
            api_key_env: str = "",
            team_id: str = "",
        ) -> dict[str, Any]:
            """Create a CLI, API, remote, or blueprint seat with safe defaults."""
            return self.create_agent(
                name=name,
                kind=kind,
                command=command,
                description=description,
                blueprint_code=blueprint_code,
                remote_kind=remote_kind,
                base_url=base_url,
                api_key_env=api_key_env,
                team_id=team_id,
            )

        def archive_agent(agent_id: str) -> dict[str, Any]:
            """Soft-delete an agent. Hidden from the default rail; recoverable ~30 days."""
            return self.archive_agent(agent_id)

        def restore_agent(agent_id: str) -> dict[str, Any]:
            """Un-archive an agent before the purge window elapses."""
            return self.restore_agent(agent_id)

        def list_archived_agents() -> dict[str, Any]:
            """List archived seats still inside the ~30 day recovery window."""
            return self.list_archived_agents()

        return [
            function_tool(create_agent),
            function_tool(archive_agent),
            function_tool(restore_agent),
            function_tool(list_archived_agents),
        ]

    def as_swarm_tools(self) -> list[Any]:
        from swarm.types import Tool

        tools = []
        for fn in self.as_callables():
            tools.append(
                Tool(
                    name=getattr(fn, "name", fn.__name__),
                    func=fn,
                    description=getattr(fn, "description", "") or "",
                )
            )
        return tools

    def tool_objects(self) -> list[Any]:
        if not can_manage_agent_lifecycle(self.caller_role) or self.caller_kind != V1_KIND:
            return []
        return self.as_function_tools() or self.as_swarm_tools()

    def _create(
        self,
        *,
        name: str,
        kind: str,
        command: str,
        description: str,
        blueprint_code: str,
        remote_kind: str,
        base_url: str,
        api_key_env: str,
        team_id: str,
    ) -> tuple[str, dict[str, Any]]:
        kind_key = str(kind or "").strip().lower()
        if kind_key not in CREATE_KINDS:
            raise LifecycleError(
                ERROR_INVALID_KIND,
                "kind must be cli, api, remote, or blueprint.",
            )
        ident = slugify_agent_id(name)
        if not ident:
            raise LifecycleError(ERROR_INVALID_ID, "name is required.")
        if is_lifecycle_protected_id(ident):
            raise LifecycleError(
                ERROR_PROTECTED,
                f"'{ident}' is a reserved Support/role/catalog id.",
            )
        if kind_key == "remote":
            row = self._create_remote(
                ident=ident,
                remote_kind=remote_kind or ident,
                base_url=base_url,
                api_key_env=api_key_env,
                description=description or name,
            )
        else:
            row = self._create_custom(
                ident=ident,
                name=name.strip() or ident,
                kind=kind_key,
                command=command,
                description=description,
                blueprint_code=blueprint_code,
            )
        if team_id:
            self._add_to_team(team_id, row)
            row["team_id"] = slugify_agent_id(team_id) or team_id
        return ident, _public_row(row)

    def _create_custom(
        self,
        *,
        ident: str,
        name: str,
        kind: str,
        command: str,
        description: str,
        blueprint_code: str,
    ) -> dict[str, Any]:
        custom = self._custom_list()
        if any(row_id(item) == ident for item in custom):
            raise LifecycleError(ERROR_ALREADY_EXISTS, f"Agent '{ident}' already exists.")
        if kind == "cli" and not str(command or "").strip():
            raise LifecycleError(ERROR_CLI_COMMAND, "CLI command is required.")
        code = str(blueprint_code or "").strip()
        if kind == "blueprint" and not code:
            class_name = "".join(part.title() for part in ident.replace("-", "_").split("_") if part) or "NewSeat"
            if not class_name.endswith("Blueprint"):
                class_name += "Blueprint"
            title = name.replace("_", " ").strip() or ident
            desc = (description or f"Starter API seat {ident}.").replace('"', "'")
            code = STARTER_BLUEPRINT_CODE.format(
                class_name=class_name,
                ident=ident,
                title=title,
                description=desc,
            )
        refuse_secrets(code)
        seat_kind = "api" if kind == "blueprint" else kind
        try:
            item = build_custom_rail_item(
                {
                    "id": ident,
                    "name": name,
                    "description": description or "",
                    "category": "blueprint" if kind == "blueprint" else seat_kind,
                    "tags": ["lifecycle", kind],
                    "code": code,
                    "kind": seat_kind,
                    "command": command,
                    "cli": command if seat_kind == "cli" else "",
                    "rail": True,
                    "source": LIFECYCLE_SOURCE,
                    "user_created": True,
                    "role": "default",
                    "created_by": self.caller_id,
                    "created_at": self.current_time().isoformat(),
                }
            )
        except CustomSeatError as exc:
            raise LifecycleError(ERROR_CLI_COMMAND, str(exc)) from exc
        item["role"] = "default"
        item["source"] = LIFECYCLE_SOURCE
        item["user_created"] = True
        item["created_by"] = self.caller_id
        item.setdefault("created_at", self.current_time().isoformat())
        custom.append(item)
        self.stores.library["custom"] = custom
        if self.stores.persist_library and not _save_library(self.stores.library):
            custom.pop()
            raise LifecycleError(ERROR_PERSIST, "failed to persist the new seat.")
        return item

    def _create_remote(
        self,
        *,
        ident: str,
        remote_kind: str,
        base_url: str,
        api_key_env: str,
        description: str,
    ) -> dict[str, Any]:
        from swarm.core.config_ownership import looks_like_env_name
        from swarm.core.remotes import RemoteError, persist_remote

        kind_id = slugify_agent_id(remote_kind or ident)
        existing = self.stores.remotes.get(kind_id)
        if isinstance(existing, dict) and existing.get("archived") is not True:
            raise LifecycleError(ERROR_ALREADY_EXISTS, f"Remote '{kind_id}' already exists.")
        env_name = str(api_key_env or "").strip()
        if env_name and not looks_like_env_name(env_name) and not env_name.startswith("${"):
            raise LifecycleError(ERROR_SECRET, "api_key_env must be an env-var name, not a token.")
        refuse_secrets(env_name, base_url)
        if self.stores.persist_remotes:
            try:
                kwargs: dict[str, Any] = {}
                if base_url:
                    kwargs["base_url"] = base_url
                if env_name:
                    kwargs["api_key_env"] = env_name
                spec, _path = persist_remote(kind_id, **kwargs)
                entry = dict(self.stores.remotes.get(kind_id) or {})
                entry["kind"] = spec.id
                entry["id"] = spec.id
                if base_url:
                    entry["base_url"] = str(getattr(spec, "base_url", "") or base_url)
                if env_name:
                    entry["api_key_env"] = env_name
                entry.pop("archived", None)
                entry.pop("archived_at", None)
                entry.pop("archived_by", None)
                entry["source"] = LIFECYCLE_SOURCE
                entry["created_by"] = self.caller_id
                entry["created_at"] = self.current_time().isoformat()
                entry["description"] = description
                self.stores.remotes[kind_id] = entry
                if self.stores.remotes_cfg is not None:
                    self.stores.remotes_cfg.setdefault("remotes", {})
                    if isinstance(self.stores.remotes_cfg.get("remotes"), dict):
                        self.stores.remotes_cfg["remotes"][kind_id] = entry
                    _save_remotes(self.stores.remotes_cfg, self.stores.remotes, self.stores.remotes_path)
                return entry
            except RemoteError as exc:
                raise LifecycleError(ERROR_REMOTE, str(exc)) from exc
        entry = {
            "id": kind_id,
            "kind": kind_id,
            "base_url": base_url,
            "api_key_env": env_name,
            "source": LIFECYCLE_SOURCE,
            "created_by": self.caller_id,
            "created_at": self.current_time().isoformat(),
            "description": description,
            "user_created": True,
        }
        if env_name:
            entry["api_key"] = f"${{{env_name}}}"
        self.stores.remotes[kind_id] = entry
        return entry

    def _archive(self, agent_id: str) -> tuple[str, dict[str, Any]]:
        ident = slugify_agent_id(agent_id)
        if not ident:
            raise LifecycleError(ERROR_INVALID_ID, "agent_id is required.")
        if ident == slugify_agent_id(self.caller_id) or is_lifecycle_protected_id(ident):
            raise LifecycleError(ERROR_PROTECTED, f"Cannot archive protected seat '{ident}'.")
        store, row = self._find(ident)
        if row is None:
            raise LifecycleError(ERROR_UNKNOWN_ID, f"Unknown agent '{ident}'.")
        if is_seed_demo_row(row) and store == "custom":
            raise LifecycleError(ERROR_PROTECTED, "Demo catalog leftovers are not Support-archive targets.")
        if row.get("archived") is True:
            raise LifecycleError(ERROR_ALREADY_ARCHIVED, f"'{ident}' is already archived.")
        stamp = self.current_time().isoformat()
        row["archived"] = True
        row["archived_at"] = stamp
        row["archived_by"] = self.caller_id
        row["archived_reason"] = "req-154-support-cos"
        self._write_row(store, ident, row)
        return ident, row

    def _restore(self, agent_id: str) -> tuple[str, dict[str, Any]]:
        ident = slugify_agent_id(agent_id)
        if not ident:
            raise LifecycleError(ERROR_INVALID_ID, "agent_id is required.")
        store, row = self._find(ident)
        if row is None:
            raise LifecycleError(ERROR_UNKNOWN_ID, f"Unknown agent '{ident}'.")
        if row.get("archived") is not True:
            raise LifecycleError(ERROR_NOT_ARCHIVED, f"'{ident}' is not archived.")
        row["archived"] = False
        row.pop("archived_at", None)
        row.pop("archived_by", None)
        row.pop("archived_reason", None)
        self._write_row(store, ident, row)
        return ident, row

    def _list_archived(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in self._custom_list():
            if isinstance(raw, dict) and raw.get("archived") is True:
                rows.append(_public_row(raw, store="custom"))
        for key, raw in self.stores.remotes.items():
            if isinstance(raw, dict) and raw.get("archived") is True:
                item = dict(raw)
                item.setdefault("id", key)
                item.setdefault("kind", "remote")
                rows.append(_public_row(item, store="remote"))
        rows.sort(key=lambda item: str(item.get("archived_at") or ""), reverse=True)
        return rows

    def _custom_list(self) -> list[dict[str, Any]]:
        custom = self.stores.library.get("custom")
        if not isinstance(custom, list):
            custom = []
            self.stores.library["custom"] = custom
        return custom

    def _find(self, ident: str) -> tuple[StoreKind | None, dict[str, Any] | None]:
        for raw in self._custom_list():
            if isinstance(raw, dict) and row_id(raw) == ident:
                return "custom", raw
        remote = self.stores.remotes.get(ident)
        if isinstance(remote, dict):
            return "remote", remote
        return None, None

    def _write_row(self, store: StoreKind | None, ident: str, row: dict[str, Any]) -> None:
        if store == "custom":
            if self.stores.persist_library and not _save_library(self.stores.library):
                raise LifecycleError(ERROR_PERSIST, "failed to persist archive state.")
            return
        if store == "remote":
            self.stores.remotes[ident] = row
            if self.stores.persist_remotes:
                cfg = self.stores.remotes_cfg if isinstance(self.stores.remotes_cfg, dict) else {"remotes": {}}
                if not _save_remotes(cfg, self.stores.remotes, self.stores.remotes_path):
                    raise LifecycleError(ERROR_PERSIST, "failed to persist remote archive state.")

    def _add_to_team(self, team_id: str, row: dict[str, Any]) -> None:
        roster_id = slugify_agent_id(team_id) or str(team_id).strip()
        rosters = self.stores.rosters
        if not isinstance(rosters, dict):
            raise LifecycleError(ERROR_TEAM, f"Team '{roster_id}' not found.")
        roster = rosters.get(roster_id)
        if not isinstance(roster, dict):
            raise LifecycleError(ERROR_TEAM, f"Team '{roster_id}' not found.")
        members = list(roster.get("members") or [])
        member_id = row_id(row) or slugify_agent_id(row.get("id"))
        if any(str(item.get("id") or "") == member_id for item in members if isinstance(item, dict)):
            return
        kind = str(row.get("kind") or infer_custom_kind(row) or "api")
        if kind not in ("api", "cli", "remote", "herdr", "blueprint"):
            kind = "api"
        members.append(
            {
                "id": member_id,
                "name": row.get("name") or member_id,
                "kind": kind,
                "role": "default",
                "source": LIFECYCLE_SOURCE,
            }
        )
        roster["members"] = members
        rosters[roster_id] = roster
        if self.stores.persist_rosters:
            try:
                from swarm.core.team_rosters import upsert_roster

                upsert_roster(roster)
            except Exception as exc:
                raise LifecycleError(ERROR_TEAM, f"Could not add '{member_id}' to team '{roster_id}'.") from exc

    def _audit(self, line: str) -> None:
        text = str(redact_sensitive_data(line) or line)
        if not self.user_key:
            logger.info("lifecycle audit (no user_key) %s: %s", self.caller_id, text)
            return
        try:
            from swarm.core import chat_store

            record = chat_store.load(self.user_key, self.caller_id, base_dir=self.chat_base_dir)
            if record is None:
                record = chat_store.empty_record(user_key=self.user_key, agent_id=self.caller_id)
            turns = list(record.get("messages") or [])
            events = list(record.get("ui_events") or [])
            append_event(turns, events, "status", text, kind="status")
            chat_store.save(
                self.user_key,
                self.caller_id,
                turns,
                conversation_id=str(record.get("conversation_id") or ""),
                ui_events=events,
                base_dir=self.chat_base_dir,
            )
        except Exception:
            logger.debug("lifecycle audit write failed", exc_info=True)


def _public_row(row: MappingLike, store: str | None = None) -> dict[str, Any]:
    item = dict(row) if isinstance(row, dict) else {}
    kind = str(item.get("kind") or infer_custom_kind(item) or "")
    payload = {
        "id": row_id(item) or item.get("id") or "",
        "name": item.get("name") or row_id(item),
        "kind": kind or ("remote" if store == "remote" else "api"),
        "role": "default",
        "archived": item.get("archived") is True,
        "archived_at": item.get("archived_at") or "",
        "source": item.get("source") or LIFECYCLE_SOURCE,
        "rail": item.get("rail") is True or (store != "remote" and not already_hidden(item)),
    }
    if store:
        payload["store"] = store
    if item.get("command") or item.get("cli"):
        payload["command"] = item.get("command") or item.get("cli")
    if item.get("api_key_env"):
        payload["api_key_env"] = item.get("api_key_env")
    if item.get("base_url"):
        payload["base_url"] = item.get("base_url")
    if item.get("team_id"):
        payload["team_id"] = item.get("team_id")
    # Never leak secret-shaped leftovers.
    payload = {key: value for key, value in payload.items() if not looks_like_secret(value)}
    return payload


MappingLike = dict[str, Any]


def purge_due_rows(
    *,
    library: dict[str, Any] | None = None,
    remotes: dict[str, Any] | None = None,
    now: datetime | None = None,
    days: int | None = None,
    include_unstamped: bool = False,
) -> dict[str, Any]:
    """Plan hard-deletes for archived seats older than *days*. Does not write."""
    when = now or utc_now()
    keep_days = retention_days() if days is None else int(days)
    cutoff = when - timedelta(days=keep_days) if keep_days > 0 else when
    lib = library if isinstance(library, dict) else {"custom": []}
    remote_map = remotes if isinstance(remotes, dict) else {}
    due: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []

    def _consider(ident: str, store: str, raw: dict[str, Any]) -> None:
        if raw.get("archived") is not True:
            return
        if is_lifecycle_protected_id(ident) or (store == "custom" and is_seed_demo_row(raw)):
            kept.append({"id": ident, "store": store, "reason": "protected_or_demo"})
            return
        stamped = parse_iso(raw.get("archived_at"))
        if stamped is None:
            if include_unstamped:
                due.append({"id": ident, "store": store, "archived_at": "", "reason": "unstamped"})
            else:
                kept.append({"id": ident, "store": store, "reason": "missing_archived_at"})
            return
        if stamped <= cutoff or keep_days <= 0:
            due.append({"id": ident, "store": store, "archived_at": raw.get("archived_at"), "reason": "expired"})
        else:
            kept.append({"id": ident, "store": store, "reason": "inside_retention"})

    for raw in lib.get("custom") or []:
        if isinstance(raw, dict):
            _consider(row_id(raw), "custom", raw)
    for key, raw in remote_map.items():
        if isinstance(raw, dict):
            _consider(str(key), "remote", raw)
    return {
        "ok": True,
        "retention_days": keep_days,
        "cutoff": cutoff.isoformat(),
        "due": due,
        "kept": kept,
    }


def apply_purge(
    plan: dict[str, Any],
    *,
    library: dict[str, Any] | None = None,
    remotes: dict[str, Any] | None = None,
    remotes_cfg: dict[str, Any] | None = None,
    remotes_path: Path | None = None,
    persist: bool = False,
    strip_rosters: bool = True,
    strip_prefs: bool = True,
) -> dict[str, Any]:
    """Hard-delete due rows. Chats stay on SWARM_CHAT_MAX_AGE_DAYS (not deleted here)."""
    due_ids = {row["id"] for row in (plan.get("due") or []) if row.get("id")}
    removed: list[dict[str, Any]] = []
    lib = library if isinstance(library, dict) else None
    if lib is not None:
        custom = [item for item in (lib.get("custom") or []) if row_id(item) not in due_ids]
        dropped = [item for item in (lib.get("custom") or []) if row_id(item) in due_ids]
        lib["custom"] = custom
        for item in dropped:
            removed.append({"id": row_id(item), "store": "custom"})
        if persist and dropped:
            _save_library(lib)
    remote_map = remotes if isinstance(remotes, dict) else None
    if remote_map is not None:
        for ident in list(remote_map):
            if ident in due_ids:
                remote_map.pop(ident, None)
                removed.append({"id": ident, "store": "remote"})
        if persist and any(row.get("store") == "remote" for row in removed):
            cfg = remotes_cfg if isinstance(remotes_cfg, dict) else {"remotes": {}}
            _save_remotes(cfg, remote_map, remotes_path)
    if strip_rosters and due_ids:
        _strip_roster_members(due_ids, persist=persist)
    if strip_prefs and due_ids:
        _strip_preference_ids(due_ids)
    return {"ok": True, "removed": removed, "chats": "retained_until_SWARM_CHAT_MAX_AGE_DAYS"}


def _strip_roster_members(ids: set[str], *, persist: bool) -> None:
    try:
        from swarm.core.team_rosters import load_team_rosters, upsert_roster

        rosters = load_team_rosters()
    except Exception:
        logger.debug("lifecycle roster strip skipped", exc_info=True)
        return
    for roster in list(rosters.values()):
        if not isinstance(roster, dict):
            continue
        members = [m for m in (roster.get("members") or []) if str((m or {}).get("id") or "") not in ids]
        if len(members) == len(roster.get("members") or []):
            continue
        roster["members"] = members
        if persist:
            try:
                upsert_roster(roster)
            except Exception:
                logger.debug("lifecycle roster upsert skipped", exc_info=True)


def _strip_preference_ids(ids: set[str]) -> None:
    """Drop purged ids from Hidden Bots / favourites. Best-effort; no Neon."""
    try:
        from swarm.core.user_preferences import HIDDEN_KEY
        from swarm.models.preferences import UserPreference
    except Exception:
        logger.debug("lifecycle prefs strip skipped (no Django)", exc_info=True)
        return
    try:
        for row in UserPreference.objects.all():
            values = dict(row.values or {})
            hidden = [item for item in (values.get(HIDDEN_KEY) or []) if str(item) not in ids]
            favs = values.get("favourites")
            if isinstance(favs, list):
                values["favourites"] = [
                    item
                    for item in favs
                    if str(item if not isinstance(item, dict) else item.get("id") or "") not in ids
                ]
            values[HIDDEN_KEY] = hidden
            row.values = values
            row.save(update_fields=["values"])
    except Exception:
        logger.debug("lifecycle prefs strip failed", exc_info=True)


def _iter_agents(blueprint: Any) -> list[Any]:
    agents: list[Any] = []
    raw = getattr(blueprint, "agents", None)
    if isinstance(raw, dict):
        agents.extend(raw.values())
    elif isinstance(raw, list):
        agents.extend(raw)
    starting = getattr(blueprint, "starting_agent", None)
    if starting is not None and not callable(starting) and starting not in agents:
        agents.append(starting)
    return agents


def _tool_names(current: Iterable[Any] | None) -> set[str]:
    names: set[str] = set()
    for fn in current or []:
        name = getattr(fn, "name", None) or getattr(fn, "__name__", None)
        if name:
            names.add(str(name))
    return names


def attach_to_agent(agent: Any, ctx: LifecycleContext) -> list[str]:
    extras = ctx.tool_objects()
    if not extras:
        return []
    attached: list[str] = []
    for attr in ("tools", "functions"):
        current = getattr(agent, attr, None)
        if current is None:
            try:
                setattr(agent, attr, [])
                current = getattr(agent, attr)
            except Exception:
                continue
        if not isinstance(current, list):
            continue
        have = _tool_names(current)
        for tool in extras:
            name = str(getattr(tool, "name", None) or getattr(tool, "__name__", "") or "")
            if not name or name in have:
                continue
            current.append(tool)
            have.add(name)
            attached.append(name)
    return attached


def attach_lifecycle_tools(blueprint: Any, ctx: LifecycleContext) -> list[str]:
    attached: list[str] = []
    for agent in _iter_agents(blueprint):
        attached.extend(attach_to_agent(agent, ctx))
    return attached


def install_lifecycle_on_blueprint(blueprint: Any, ctx: LifecycleContext) -> list[str]:
    """Stamp context, wrap ``create_starting_agent``, attach to existing agents."""
    role = ctx.caller_role
    meta = getattr(blueprint, "metadata", None)
    if (not role or role == "default") and isinstance(meta, dict) and meta.get("role"):
        ctx.caller_role = normalize_agent_role(meta.get("role"))
    blueprint._lifecycle_context = ctx
    if ctx.caller_kind != V1_KIND or not can_manage_agent_lifecycle(ctx.caller_role):
        return []

    original = getattr(blueprint, "create_starting_agent", None)
    if callable(original) and not getattr(blueprint, "_lifecycle_wrapped", False):
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            agent = original(*args, **kwargs)
            attach_to_agent(agent, ctx)
            return agent

        blueprint.create_starting_agent = wrapped
        blueprint._lifecycle_wrapped = True

    return attach_lifecycle_tools(blueprint, ctx)


def context_from_runtime(
    *,
    caller_id: str,
    user: Any = None,
    params: dict[str, Any] | None = None,
    blueprint: Any = None,
    stores: LifecycleStores | None = None,
    chat_base_dir: Path | None = None,
) -> LifecycleContext:
    params = params if isinstance(params, dict) else {}
    explicit_kind = params.get("kind") or params.get("agent_type")
    if isinstance(explicit_kind, str):
        explicit_kind = explicit_kind.strip().lower()
    else:
        explicit_kind = None
    kind = classify_agent_kind(
        caller_id,
        explicit=explicit_kind if explicit_kind in ("api", "cli", "remote", "blueprint") else None,
    )
    role = role_of_member(caller_id, None, fallback=params.get("role"))
    meta = getattr(blueprint, "metadata", None) if blueprint is not None else None
    if (not role or role == "default") and isinstance(meta, dict) and meta.get("role"):
        role = normalize_agent_role(meta.get("role"))

    user_key = ""
    if user is not None and getattr(user, "is_authenticated", False):
        try:
            from swarm.core import chat_store

            user_key = chat_store.user_key_for(user)
        except Exception:
            logger.debug("lifecycle user_key unavailable", exc_info=True)

    return LifecycleContext(
        caller_id=str(caller_id or "").strip(),
        caller_kind=kind,
        caller_role=normalize_agent_role(role),
        user_key=user_key,
        chat_base_dir=chat_base_dir,
        stores=stores or default_stores(),
    )


def install_lifecycle_for_runtime(
    blueprint: Any,
    *,
    caller_id: str,
    user: Any = None,
    params: dict[str, Any] | None = None,
) -> LifecycleContext:
    """Attach create/archive tools when the caller is Support or CoS (API-kind)."""
    ctx = context_from_runtime(
        caller_id=caller_id,
        user=user,
        params=params,
        blueprint=blueprint,
    )
    install_lifecycle_on_blueprint(blueprint, ctx)
    return ctx


__all__ = [
    "ARCHIVE_TOOL_NAME",
    "CREATE_KINDS",
    "CREATE_TOOL_NAME",
    "DEFAULT_RETENTION_DAYS",
    "ERROR_ALREADY_ARCHIVED",
    "ERROR_ALREADY_EXISTS",
    "ERROR_CALLER_KIND",
    "ERROR_CLI_COMMAND",
    "ERROR_INVALID_KIND",
    "ERROR_NOT_ARCHIVED",
    "ERROR_PROTECTED",
    "ERROR_ROLE",
    "ERROR_SECRET",
    "ERROR_UNKNOWN_ID",
    "LIST_ARCHIVED_TOOL_NAME",
    "RESTORE_TOOL_NAME",
    "RETENTION_ENV",
    "LifecycleContext",
    "LifecycleError",
    "LifecycleStores",
    "apply_purge",
    "attach_lifecycle_tools",
    "attach_to_agent",
    "catalog_archived_ids",
    "context_from_runtime",
    "default_stores",
    "install_lifecycle_for_runtime",
    "install_lifecycle_on_blueprint",
    "looks_like_secret",
    "purge_due_rows",
    "remote_entry_is_archived",
    "retention_days",
    "slugify_agent_id",
]

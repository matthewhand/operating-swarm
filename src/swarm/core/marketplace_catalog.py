"""Teams / Plugins / Skills marketplace catalog (REQ-887 / #292).

Three sources of truth — do not invent a second store:

* Plugins — Official MCP Registry (cached) + GitHub topic fallback
* Skills  — Agent Skills ``SKILL.md`` (``parse_skill_md``) from curated
  GitHub sources + local ``skills/`` dirs
* Teams   — OS ``team_rosters`` packs from GitHub ``swarm-team-pack``

There is no industry team-pack standard. CrewAI / A2A Agent Cards are
not install formats.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from swarm.core import marketplace, mcp_plugins, mcp_registry, skills, team_rosters
from swarm.core.cli_catalog import installed_catalog_clis
from swarm.core.team_agents import list_blueprint_ids, list_team_agents

logger = logging.getLogger(__name__)

FetchJson = Callable[[str, dict[str, str], dict[str, str]], tuple[int, Any]]

CATALOG_KINDS = ("plugins", "skills", "teams")
TEAM_PACK_FILES = ("team-pack.json", "team_rosters.json", "open-swarm-team.json")
_FORBIDDEN_TEAM_KEYS = frozenset(
    {"binary", "binaries", "download_url", "install_script", "exe", "wheel"}
)
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
MAX_SKILL_FILES = 16
MAX_SKILL_FILE_BYTES = 256 * 1024

CURATED_SKILL_SOURCES = (
    {
        "id": "anthropics/skills",
        "owner": "anthropics",
        "repo": "skills",
        "html_url": "https://github.com/anthropics/skills",
        "description": "Anthropic Agent Skills examples (SKILL.md open standard).",
    },
)

COMMUNITY_NOTE = "Community / external content — not vetted by open-swarm."


class MarketplaceCatalogError(Exception):
    def __init__(self, message: str, *, code: str = "marketplace_error", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _fetch(fetch_json: FetchJson | None) -> FetchJson:
    return fetch_json or marketplace.fetch_json_urllib


def _github_headers() -> dict[str, str]:
    return marketplace.github_headers()


def _decode_github_file(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    encoding = str(payload.get("encoding") or "").lower()
    content = payload.get("content")
    if encoding == "base64" and isinstance(content, str) and content.strip():
        try:
            return base64.b64decode(content).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    return None


def _github_get(fetch: FetchJson, url: str, params: dict[str, str] | None = None) -> tuple[int, Any]:
    try:
        return fetch(url, _github_headers(), params or {})
    except Exception as exc:
        logger.warning("Marketplace GitHub fetch failed %s: %s", url, exc)
        return 0, {"message": exc.__class__.__name__}


# --------------------------------------------------------------------------- plugins


def _installed_plugin_ids() -> set[str]:
    try:
        servers = mcp_plugins.load_mcp_servers()
    except Exception:
        return set()
    names = {str(name).strip().lower() for name in servers}
    return {n for n in names if n}


def _mark_plugin_installed(item: dict[str, Any], installed: set[str]) -> dict[str, Any]:
    spec = item.get("plugin") if isinstance(item.get("plugin"), dict) else {}
    slug = str(spec.get("name") or item.get("name") or "").strip().lower()
    if slug and slug in installed:
        item = dict(item)
        item["installed"] = True
        item["installable"] = False
        item["install_hint"] = "Already installed."
    return item


def _github_plugin_item(row: dict[str, Any]) -> dict[str, Any]:
    full_name = str(row.get("full_name") or "").strip()
    return {
        "id": f"github:{full_name}",
        "kind": "plugins",
        "name": marketplace.public_item_name(row),
        "summary": mcp_registry.public_text(row.get("description")),
        "source": "github",
        "source_label": "GitHub topic",
        "external": True,
        "installable": False,
        "installed": False,
        "install_hint": (
            "GitHub topic scan has no MCP command or URL. "
            "Open the repo, or add it in Manage."
        ),
        "html_url": str(row.get("html_url") or ""),
        "stars": row.get("stars") if isinstance(row.get("stars"), int) else 0,
        "topics": list(row.get("topics") or []),
        "required_env": [],
        "tools_provided": [],
        "danger_notes": [COMMUNITY_NOTE],
    }


def catalog_plugins(*, fetch_json: FetchJson | None = None, **registry_kw: Any) -> dict[str, Any]:
    installed = _installed_plugin_ids()
    registry = mcp_registry.fetch_registry_servers(fetch_json=fetch_json, **registry_kw)
    items = [_mark_plugin_installed(dict(row), installed) for row in registry.get("items") or []]
    seen = {item["id"] for item in items}
    seen_names = {
        str((item.get("plugin") or {}).get("name") or item.get("name") or "").lower()
        for item in items
    }
    scan = marketplace.scan_marketplace("plugins", fetch_json=fetch_json)
    warnings = list(registry.get("warnings") or []) + list(scan.get("warnings") or [])
    for row in scan.get("items") or []:
        item = _github_plugin_item(row)
        name_key = str(item.get("name") or "").lower()
        if item["id"] in seen or (name_key and name_key in seen_names):
            continue
        seen.add(item["id"])
        items.append(item)
    if not items and not warnings:
        warnings.append("No plugins in the Official MCP Registry cache or GitHub topic scan.")
    return _catalog_payload("plugins", items, warnings, sources=["mcp_registry", "github"])


# --------------------------------------------------------------------------- skills


def _local_skill_item(skill: skills.Skill) -> dict[str, Any]:
    return {
        "id": f"skill:{skill.name}",
        "kind": "skills",
        "name": skill.name,
        "summary": mcp_registry.public_text(skill.description),
        "source": "local",
        "source_label": "Installed",
        "external": False,
        "installable": False,
        "installed": True,
        "install_hint": "Already installed.",
        "html_url": "",
        "required_env": [],
        "tools_provided": list(skill.assets),
        "danger_notes": [],
        "skill": {
            "name": skill.name,
            "assets": list(skill.assets),
            "origin": "local",
            "path": skills.skill_relpath(skill),
        },
    }


def _list_skill_md_from_tree(payload: Any) -> list[str]:
    tree = payload.get("tree") if isinstance(payload, dict) else None
    if not isinstance(tree, list):
        return []
    paths: list[str] = []
    for node in tree:
        if not isinstance(node, dict):
            continue
        path = str(node.get("path") or "").strip()
        if path.endswith("/SKILL.md") or path == "SKILL.md":
            if ".." in path.split("/"):
                continue
            paths.append(path)
    return paths


def _curated_skill_items(*, fetch_json: FetchJson | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    fetch = _fetch(fetch_json)
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    for source in CURATED_SKILL_SOURCES:
        owner = source["owner"]
        repo = source["repo"]
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD"
        status, payload = _github_get(fetch, url, {"recursive": "1"})
        if status == 403 and "rate" in str(payload).lower():
            warnings.append("GitHub rate limit reached while listing Agent Skills — try again later.")
            continue
        if status != 200:
            warnings.append(
                f"Could not list Agent Skills from {owner}/{repo} "
                f"(HTTP {status or 'offline'}). Local skills still listed."
            )
            continue
        for md_path in _list_skill_md_from_tree(payload):
            parent = str(Path(md_path).parent)
            name_hint = "root" if parent in (".", "") else Path(parent).name
            skill_id = f"skill-gh:{owner}/{repo}/{parent if parent not in ('.', '') else '.'}"
            items.append(
                {
                    "id": skill_id,
                    "kind": "skills",
                    "name": name_hint,
                    "summary": mcp_registry.public_text(source.get("description")),
                    "source": "curated",
                    "source_label": "Agent Skills",
                    "external": True,
                    "installable": True,
                    "installed": False,
                    "html_url": f"{source['html_url']}/tree/HEAD/{parent if parent not in ('.', '') else ''}".rstrip("/"),
                    "required_env": [],
                    "tools_provided": [],
                    "danger_notes": [COMMUNITY_NOTE],
                    "skill": {
                        "name": name_hint,
                        "origin": "github",
                        "owner": owner,
                        "repo": repo,
                        "path": parent if parent not in (".", "") else "",
                    },
                }
            )
    return items, warnings


def catalog_skills(*, fetch_json: FetchJson | None = None) -> dict[str, Any]:
    local = [_local_skill_item(s) for s in skills.discover_skills().values()]
    installed_names = {item["name"] for item in local}
    remote, warnings = _curated_skill_items(fetch_json=fetch_json)
    items = list(local)
    for item in remote:
        name = str(item.get("name") or "")
        if name in installed_names:
            item = dict(item)
            item["installed"] = True
            item["installable"] = False
            item["install_hint"] = "Already installed."
        items.append(item)
    if not items and not warnings:
        warnings.append("No Agent Skills found locally or in curated sources.")
    return _catalog_payload("skills", items, warnings, sources=["agent_skills", "local"])


# --------------------------------------------------------------------------- teams


def _installed_roster_ids() -> set[str]:
    try:
        return set(team_rosters.load_team_rosters())
    except Exception:
        return set()


def _github_team_item(row: dict[str, Any], installed: set[str]) -> dict[str, Any]:
    full_name = str(row.get("full_name") or "").strip()
    slug = team_rosters.slugify_roster_name(str(row.get("name") or full_name.split("/")[-1]))
    already = slug in installed
    return {
        "id": f"team:{full_name}",
        "kind": "teams",
        "name": str(row.get("name") or full_name),
        "summary": mcp_registry.public_text(row.get("description")) or "OS team pack (team_rosters JSON).",
        "source": "github",
        "source_label": "GitHub swarm-team-pack",
        "external": True,
        "installable": not already,
        "installed": already,
        "install_hint": "Already installed." if already else "",
        "html_url": str(row.get("html_url") or ""),
        "stars": row.get("stars") if isinstance(row.get("stars"), int) else 0,
        "topics": list(row.get("topics") or []),
        "required_env": [],
        "tools_provided": [],
        "danger_notes": [COMMUNITY_NOTE],
        "team": {
            "full_name": full_name,
            "owner": str(row.get("owner") or ""),
            "repo": str(row.get("name") or ""),
        },
    }


def catalog_teams(*, fetch_json: FetchJson | None = None) -> dict[str, Any]:
    installed = _installed_roster_ids()
    scan = marketplace.scan_marketplace("teams", fetch_json=fetch_json)
    items = [_github_team_item(row, installed) for row in scan.get("items") or []]
    warnings = list(scan.get("warnings") or [])
    if not items and not warnings:
        warnings.append("No community team packs found for topic swarm-team-pack.")
    return _catalog_payload("teams", items, warnings, sources=["os_team_pack", "github"])


def _catalog_payload(kind: str, items: list[dict[str, Any]], warnings: list[str], *, sources: list[str]) -> dict[str, Any]:
    return {
        "object": "marketplace_catalog",
        "kind": kind,
        "sources": sources,
        "external": True,
        "items": items,
        "warnings": warnings,
    }


def build_catalog(kind: str, *, fetch_json: FetchJson | None = None, **kwargs: Any) -> dict[str, Any]:
    if kind == "plugins":
        return catalog_plugins(fetch_json=fetch_json, **kwargs)
    if kind == "skills":
        return catalog_skills(fetch_json=fetch_json)
    if kind == "teams":
        return catalog_teams(fetch_json=fetch_json)
    raise MarketplaceCatalogError(
        "query param 'kind' must be 'teams', 'plugins', or 'skills'.",
        code="invalid_kind",
    )


# --------------------------------------------------------------------------- preview / install helpers


def _split_github_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise MarketplaceCatalogError("Invalid GitHub full_name.", code="bad_payload")
    return parts[0], parts[1]


def _contains_forbidden_team_keys(raw: Any) -> bool:
    if isinstance(raw, dict):
        for key, value in raw.items():
            if str(key).lower() in _FORBIDDEN_TEAM_KEYS:
                return True
            if _contains_forbidden_team_keys(value):
                return True
    elif isinstance(raw, list):
        return any(_contains_forbidden_team_keys(item) for item in raw)
    return False


def parse_team_pack(raw: Any, *, fallback_id: str, fallback_name: str) -> list[dict[str, Any]]:
    """Parse OS team-pack JSON. Roster documents only — no binaries."""
    if _contains_forbidden_team_keys(raw):
        raise MarketplaceCatalogError(
            "Team pack must be roster JSON only — it must not pull binaries.",
            code="team_pack_binaries",
        )
    rosters: list[dict[str, Any]] = []
    if isinstance(raw, dict) and isinstance(raw.get("rosters"), list):
        candidates = raw["rosters"]
    elif isinstance(raw, dict) and (
        "members" in raw or "agent_team" in raw or raw.get("object") == "team_roster"
    ):
        candidates = [raw]
    elif isinstance(raw, dict) and all(isinstance(v, dict) for v in raw.values()):
        candidates = []
        for key, value in raw.items():
            if key in ("object", "kind", "schema"):
                continue
            entry = dict(value)
            entry.setdefault("id", key)
            candidates.append(entry)
    elif isinstance(raw, list):
        candidates = raw
    else:
        raise MarketplaceCatalogError("Team pack JSON is not an OS team roster.", code="bad_payload")

    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        rid = team_rosters.slugify_roster_name(str(entry.get("id") or fallback_id))
        if not rid:
            continue
        payload = dict(entry)
        payload.setdefault("id", rid)
        payload.setdefault("name", fallback_name or rid)
        try:
            rosters.append(team_rosters.normalize_roster(payload, roster_id=rid))
        except ValueError as exc:
            raise MarketplaceCatalogError(str(exc), code="bad_payload") from exc
    if not rosters:
        raise MarketplaceCatalogError("Team pack contained no valid OS rosters.", code="bad_payload")
    return rosters


def _fetch_team_pack_json(owner: str, repo: str, *, fetch_json: FetchJson | None = None) -> dict[str, Any]:
    fetch = _fetch(fetch_json)
    last_status = 0
    for filename in TEAM_PACK_FILES:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(filename)}"
        status, payload = _github_get(fetch, url)
        last_status = status
        if status == 403 and "rate" in str(payload).lower():
            raise MarketplaceCatalogError(
                "GitHub rate limit reached — cannot preview this team pack.",
                code="rate_limit",
                status=429,
            )
        if status != 200:
            continue
        text = _decode_github_file(payload)
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MarketplaceCatalogError("Team pack JSON is invalid.", code="bad_payload") from exc
        return data
    if last_status == 0:
        raise MarketplaceCatalogError(
            "GitHub is unreachable — cannot preview this team pack.",
            code="offline",
            status=502,
        )
    raise MarketplaceCatalogError(
        "No OS team pack JSON found (team-pack.json / team_rosters.json).",
        code="not_found",
        status=404,
    )


def _member_needs_configuration(
    member: dict[str, Any],
    *,
    blueprint_ids: set[str],
    installed_clis: set[str],
    remote_ids: set[str],
) -> dict[str, str] | None:
    kind = str(member.get("kind") or "")
    source = str(member.get("source") or "")
    member_id = str(member.get("id") or "")
    if kind == "cli":
        cli = source.split(":", 1)[-1] if source.startswith("cli:") else member_id
        if cli not in installed_clis:
            return {"id": member_id, "reason": "CLI not installed — needs configuration."}
    elif kind in ("api", "blueprint"):
        bp = ""
        if source.startswith("blueprint:"):
            bp = source.split(":", 1)[-1]
        elif kind == "blueprint":
            bp = member_id
        else:
            bp = member_id
        if bp and bp not in blueprint_ids:
            return {"id": member_id, "reason": "Blueprint not available — needs configuration."}
    elif kind == "remote":
        rid = source.split(":", 1)[-1] if source.startswith("remote:") else member_id
        if rid not in remote_ids:
            return {"id": member_id, "reason": "Remote not configured — needs configuration."}
    return None


def annotate_team_preview(roster: dict[str, Any]) -> dict[str, Any]:
    serialized = team_rosters.serialize_roster(roster)
    try:
        palette = list_team_agents()
    except Exception:
        palette = []
    if palette:
        blueprint_ids = {row["id"] for row in palette if row.get("kind") == "api"}
        installed_clis = {
            row["id"] for row in palette if row.get("kind") == "cli" and not row.get("placeholder")
        }
        remote_ids = {row["id"] for row in palette if row.get("kind") == "remote"}
    else:
        blueprint_ids = set(list_blueprint_ids())
        try:
            installed_clis = set(installed_catalog_clis())
        except Exception:
            installed_clis = set()
        remote_ids = set()
    needs: list[dict[str, str]] = []
    for member in serialized.get("members") or []:
        hit = _member_needs_configuration(
            member,
            blueprint_ids=blueprint_ids,
            installed_clis=installed_clis,
            remote_ids=remote_ids,
        )
        if hit:
            needs.append(hit)
    serialized["needs_configuration"] = needs
    return serialized


def _find_catalog_item(kind: str, item_id: str, *, fetch_json: FetchJson | None = None) -> dict[str, Any]:
    catalog = build_catalog(kind, fetch_json=fetch_json)
    for item in catalog.get("items") or []:
        if item.get("id") == item_id:
            return item
    raise MarketplaceCatalogError("Marketplace item not found.", code="not_found", status=404)


def _github_dir_files(
    owner: str,
    repo: str,
    path: str,
    *,
    fetch_json: FetchJson | None = None,
) -> dict[str, str]:
    fetch = _fetch(fetch_json)
    rel = path.strip("/")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{quote(rel)}" if rel else (
        f"https://api.github.com/repos/{owner}/{repo}/contents"
    )
    status, payload = _github_get(fetch, url)
    if status == 403 and "rate" in str(payload).lower():
        raise MarketplaceCatalogError(
            "GitHub rate limit reached — cannot install this skill.",
            code="rate_limit",
            status=429,
        )
    if status != 200 or not isinstance(payload, list):
        raise MarketplaceCatalogError(
            "Could not read the skill folder from GitHub.",
            code="offline" if status in (0, 502) else "not_found",
            status=502 if status in (0, 502) else 404,
        )
    files: dict[str, str] = {}
    for entry in payload:
        if not isinstance(entry, dict) or entry.get("type") != "file":
            continue
        name = str(entry.get("name") or "")
        if not name or name.startswith(".") or "/" in name:
            continue
        file_url = str(entry.get("url") or "")
        if not file_url:
            continue
        st, body = _github_get(fetch, file_url)
        if st != 200:
            continue
        text = _decode_github_file(body)
        if text is None:
            continue
        if len(text.encode("utf-8")) > MAX_SKILL_FILE_BYTES:
            continue
        files[name] = text
        if len(files) >= MAX_SKILL_FILES:
            break
    return files


def preview_item(kind: str, item_id: str, *, fetch_json: FetchJson | None = None) -> dict[str, Any]:
    if kind not in CATALOG_KINDS:
        raise MarketplaceCatalogError(
            "query param 'kind' must be 'teams', 'plugins', or 'skills'.",
            code="invalid_kind",
        )
    item_id = str(item_id or "").strip()
    if not item_id:
        raise MarketplaceCatalogError("query param 'id' is required.", code="bad_payload")

    if kind == "teams" and item_id.startswith("team:"):
        full_name = item_id.split(":", 1)[1]
        owner, repo = _split_github_full_name(full_name)
        raw = _fetch_team_pack_json(owner, repo, fetch_json=fetch_json)
        rosters = parse_team_pack(raw, fallback_id=repo, fallback_name=repo)
        previews = [annotate_team_preview(r) for r in rosters]
        return {
            "object": "marketplace_preview",
            "kind": "teams",
            "id": item_id,
            "external": True,
            "danger_notes": [COMMUNITY_NOTE],
            "rosters": previews,
            "roster": previews[0],
        }

    if kind == "skills" and item_id.startswith("skill-gh:"):
        item = _find_catalog_item("skills", item_id, fetch_json=fetch_json)
        meta = item.get("skill") or {}
        files = _github_dir_files(
            str(meta.get("owner") or ""),
            str(meta.get("repo") or ""),
            str(meta.get("path") or ""),
            fetch_json=fetch_json,
        )
        md = files.get(skills.SKILL_FILE)
        if not md:
            raise MarketplaceCatalogError("No SKILL.md in this pack.", code="not_found", status=404)
        parsed = skills.parse_skill_md(md, name_hint=str(meta.get("name") or ""))
        return {
            "object": "marketplace_preview",
            "kind": "skills",
            "id": item_id,
            "external": True,
            "danger_notes": [COMMUNITY_NOTE],
            "skill": {
                "name": parsed.name,
                "description": parsed.description,
                "assets": [name for name in files if name != skills.SKILL_FILE],
            },
        }

    item = _find_catalog_item(kind, item_id, fetch_json=fetch_json)
    return {
        "object": "marketplace_preview",
        "kind": kind,
        "id": item_id,
        "external": bool(item.get("external")),
        "item": item,
        "danger_notes": list(item.get("danger_notes") or []),
        "required_env": list(item.get("required_env") or []),
        "plugin": item.get("plugin"),
        "skill": item.get("skill"),
        "team": item.get("team"),
    }


def _install_plugin(item: dict[str, Any], *, connect: bool = True) -> dict[str, Any]:
    spec_raw = item.get("plugin")
    if not isinstance(spec_raw, dict):
        raise MarketplaceCatalogError(
            item.get("install_hint") or "This plugin is not installable from the catalog.",
            code="not_installable",
        )
    if item.get("installed"):
        return {
            "object": "marketplace_install",
            "kind": "plugins",
            "id": item["id"],
            "installed": True,
            "already_installed": True,
            "health": "unknown",
            "message": "Already installed.",
            "required_env": list(item.get("required_env") or []),
        }
    spec = mcp_plugins.normalize_plugin_spec(spec_raw, name=str(spec_raw.get("name") or item.get("name") or ""))
    from swarm.core import config_ownership as ownership

    ownership.persist_webui_section(
        "mcpServers",
        upsert={spec["name"]: mcp_plugins.spec_to_config_entry(spec)},
    )
    health = "unknown"
    message = "Saved to the plugin list."
    tools: list[dict[str, str]] = []
    if connect:
        try:
            tools, _stored = mcp_plugins.discover_and_store(spec["name"], spec, persist=True)
            health = "up"
            count = len(tools)
            message = (
                f"Connected — {count} tool{'s' if count != 1 else ''}."
                if count
                else "Connected — no tools listed."
            )
        except Exception as exc:
            health = "down"
            message = f"Saved, but could not connect: {exc}"
    return {
        "object": "marketplace_install",
        "kind": "plugins",
        "id": item["id"],
        "installed": True,
        "already_installed": False,
        "health": health,
        "message": message,
        "name": spec["name"],
        "required_env": mcp_registry.required_env_names(spec),
        "tools": tools,
    }


def _install_skill(item: dict[str, Any], *, fetch_json: FetchJson | None = None) -> dict[str, Any]:
    if item.get("installed"):
        return {
            "object": "marketplace_install",
            "kind": "skills",
            "id": item["id"],
            "installed": True,
            "already_installed": True,
            "message": "Already installed.",
        }
    meta = item.get("skill") if isinstance(item.get("skill"), dict) else {}
    if meta.get("origin") != "github":
        raise MarketplaceCatalogError("This skill is not installable from the catalog.", code="not_installable")
    files = _github_dir_files(
        str(meta.get("owner") or ""),
        str(meta.get("repo") or ""),
        str(meta.get("path") or ""),
        fetch_json=fetch_json,
    )
    skill = skills.install_skill_files(files, dest_root=skills.user_skills_root())
    return {
        "object": "marketplace_install",
        "kind": "skills",
        "id": item["id"],
        "installed": True,
        "already_installed": False,
        "message": f"Copied SKILL.md pack '{skill.name}' (not executed).",
        "skill": {"name": skill.name, "assets": list(skill.assets)},
    }


def _install_team(item: dict[str, Any], *, fetch_json: FetchJson | None = None) -> dict[str, Any]:
    if item.get("installed"):
        return {
            "object": "marketplace_install",
            "kind": "teams",
            "id": item["id"],
            "installed": True,
            "already_installed": True,
            "message": "Already installed.",
        }
    full_name = str((item.get("team") or {}).get("full_name") or "")
    owner, repo = _split_github_full_name(full_name)
    raw = _fetch_team_pack_json(owner, repo, fetch_json=fetch_json)
    rosters = parse_team_pack(raw, fallback_id=repo, fallback_name=str(item.get("name") or repo))
    stored: list[dict[str, Any]] = []
    existing = team_rosters.load_team_rosters()
    for roster in rosters:
        rid = roster["id"]
        if rid in existing:
            stored.append(annotate_team_preview(existing[rid]))
            continue
        stored.append(annotate_team_preview(team_rosters.upsert_roster(roster)))
    first = stored[0]
    already = all(r["id"] in existing for r in rosters)
    return {
        "object": "marketplace_install",
        "kind": "teams",
        "id": item["id"],
        "installed": True,
        "already_installed": already,
        "message": "Roster JSON saved. Members that need a CLI/API/remote stay visible as needs configuration.",
        "roster": first,
        "rosters": stored,
        "needs_configuration": first.get("needs_configuration") or [],
    }


def install_item(kind: str, item_id: str, *, fetch_json: FetchJson | None = None) -> dict[str, Any]:
    if kind not in CATALOG_KINDS:
        raise MarketplaceCatalogError(
            "body 'kind' must be 'teams', 'plugins', or 'skills'.",
            code="invalid_kind",
        )
    item = _find_catalog_item(kind, str(item_id or "").strip(), fetch_json=fetch_json)
    if kind == "plugins":
        return _install_plugin(item)
    if kind == "skills":
        return _install_skill(item, fetch_json=fetch_json)
    return _install_team(item, fetch_json=fetch_json)

"""REQ-887 marketplace catalog: plugins / skills / teams. Hermetic. No secrets."""

from __future__ import annotations

import base64
import json

import pytest

from swarm.core import marketplace_catalog as catalog
from swarm.core import skills


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def test_unknown_kind_is_rejected():
    with pytest.raises(catalog.MarketplaceCatalogError) as exc:
        catalog.build_catalog("crewai")
    assert exc.value.code == "invalid_kind"


def test_plugins_catalog_prefers_registry_and_falls_back_to_github(tmp_path, monkeypatch):
    cache = tmp_path / "reg.json"
    monkeypatch.setattr(catalog.mcp_plugins, "load_mcp_servers", lambda: {"fetch": {}})

    def fetch(url, headers, params):
        if "registry.modelcontextprotocol.io" in url:
            return 200, {
                "servers": [
                    {
                        "server": {
                            "name": "io.example/fetch",
                            "title": "Fetch",
                            "description": "HTTP fetch",
                            "packages": [
                                {
                                    "registryType": "npm",
                                    "identifier": "@ex/fetch",
                                    "runtimeHint": "npx",
                                    "environmentVariables": [{"name": "FETCH_TOKEN"}],
                                }
                            ],
                        }
                    }
                ],
                "metadata": {},
            }
        if "api.github.com/search/repositories" in url:
            return 200, {
                "items": [
                    {
                        "full_name": "alice/cool-mcp",
                        "name": "cool-mcp",
                        "owner": {"login": "alice"},
                        "description": "community plugin",
                        "html_url": "https://github.com/alice/cool-mcp",
                        "stargazers_count": 9,
                        "topics": ["swarm-mcp-plugin"],
                    }
                ]
            }
        raise OSError(url)

    result = catalog.catalog_plugins(fetch_json=fetch, cache_file=cache, now=1.0, ttl=1.0)
    ids = [row["id"] for row in result["items"]]
    assert "mcp:io.example/fetch" in ids
    assert "github:alice/cool-mcp" in ids
    fetch_row = next(row for row in result["items"] if row["id"] == "mcp:io.example/fetch")
    assert fetch_row["installed"] is True
    assert fetch_row["installable"] is False
    assert fetch_row["required_env"] == ["FETCH_TOKEN"]
    gh = next(row for row in result["items"] if row["id"].startswith("github:"))
    assert gh["installable"] is False
    assert "sk-" not in json.dumps(result)


def test_plugins_offline_registry_keeps_github_fallback(tmp_path):
    cache = tmp_path / "reg.json"

    def fetch(url, headers, params):
        if "registry.modelcontextprotocol.io" in url:
            raise OSError("offline")
        if "api.github.com/search/repositories" in url:
            return 403, {"message": "API rate limit exceeded"}
        raise OSError(url)

    result = catalog.catalog_plugins(fetch_json=fetch, cache_file=cache, now=1.0, ttl=1.0)
    assert result["items"] == []
    blob = " ".join(result["warnings"]).lower()
    assert "rate limit" in blob or "failed" in blob


def test_team_pack_parse_rejects_binaries():
    with pytest.raises(catalog.MarketplaceCatalogError) as exc:
        catalog.parse_team_pack(
            {"id": "ops", "members": [], "binary": "https://evil.example/team.exe"},
            fallback_id="ops",
            fallback_name="ops",
        )
    assert exc.value.code == "team_pack_binaries"


def test_team_pack_parse_normalizes_os_roster():
    rosters = catalog.parse_team_pack(
        {
            "id": "ops-pack",
            "name": "Ops Pack",
            "members": [
                {"id": "jeeves", "kind": "api", "role": "chief_of_staff", "source": "blueprint:jeeves"},
                {"id": "grok", "kind": "cli", "role": "skeptic", "source": "cli:grok"},
            ],
            "wires": {"handoff": True, "as_tool": False},
            "chief_of_staff_id": "jeeves",
        },
        fallback_id="ops-pack",
        fallback_name="Ops Pack",
    )
    assert rosters[0]["id"] == "ops-pack"
    assert rosters[0]["wires"]["as_tool"] is False
    assert rosters[0]["chief_of_staff_id"] == "jeeves"


def test_team_preview_marks_missing_cli(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "list_team_agents",
        lambda: [
            {"id": "jeeves", "kind": "api", "placeholder": False},
            {"id": "grok", "kind": "cli", "placeholder": True},
        ],
    )
    roster = catalog.parse_team_pack(
        {
            "id": "ops",
            "members": [
                {"id": "jeeves", "kind": "api", "source": "blueprint:jeeves"},
                {"id": "grok", "kind": "cli", "source": "cli:grok"},
            ],
        },
        fallback_id="ops",
        fallback_name="ops",
    )[0]
    preview = catalog.annotate_team_preview(roster)
    assert preview["needs_configuration"][0]["id"] == "grok"
    assert "needs configuration" in preview["needs_configuration"][0]["reason"].lower()


def test_teams_catalog_empty_is_honest():
    result = catalog.catalog_teams(fetch_json=lambda *a: (200, {"items": []}))
    assert result["items"] == []
    assert any("No community" in w or "not found" in w.lower() or "swarm-team-pack" in w for w in result["warnings"])


def test_skills_catalog_lists_local_and_curated(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    skill_dir = bundled / "haiku"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: haiku\ndescription: Write a haiku.\n---\nWrite three lines.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(skills, "skills_root", lambda: bundled)
    monkeypatch.setattr(skills, "user_skills_root", lambda: user)

    tree = {
        "tree": [
            {"path": "docx/SKILL.md", "type": "blob"},
            {"path": "README.md", "type": "blob"},
        ]
    }

    def fetch(url, headers, params):
        if "git/trees" in url:
            return 200, tree
        raise OSError(url)

    result = catalog.catalog_skills(fetch_json=fetch)
    names = {row["name"] for row in result["items"]}
    assert "haiku" in names
    remote = next(row for row in result["items"] if row["id"].startswith("skill-gh:"))
    assert remote["installable"] is True
    assert remote["source"] == "curated"


def test_skill_install_is_copy_not_exec(tmp_path, monkeypatch):
    dest = tmp_path / "skills"
    monkeypatch.setattr(skills, "user_skills_root", lambda: dest)
    files = {
        "SKILL.md": "---\nname: haiku\ndescription: Write a haiku.\n---\nWrite three lines.\n",
        "note.txt": "helper",
    }
    skill = skills.install_skill_files(files, dest_root=dest)
    assert skill.name == "haiku"
    assert (dest / "haiku" / "SKILL.md").is_file()
    assert (dest / "haiku" / "note.txt").read_text(encoding="utf-8") == "helper"
    discovered = skills.discover_skills(dest)
    assert "haiku" in discovered


def test_preview_team_pack_from_github(monkeypatch):
    pack = {
        "id": "ops-pack",
        "name": "Ops Pack",
        "members": [{"id": "jeeves", "kind": "api", "source": "blueprint:jeeves"}],
        "wires": {"handoff": True, "as_tool": True},
        "chief_of_staff_id": "jeeves",
    }

    def fetch(url, headers, params):
        if url.endswith("/contents/team-pack.json"):
            return 200, {"encoding": "base64", "content": _b64(json.dumps(pack))}
        raise OSError(url)

    monkeypatch.setattr(
        catalog,
        "list_team_agents",
        lambda: [{"id": "jeeves", "kind": "api", "placeholder": False}],
    )
    preview = catalog.preview_item("teams", "team:alice/ops-pack", fetch_json=fetch)
    assert preview["object"] == "marketplace_preview"
    assert preview["roster"]["id"] == "ops-pack"
    assert preview["roster"]["chief_of_staff_id"] == "jeeves"
    assert preview["roster"]["members"][0]["id"] == "jeeves"


def test_install_plugin_already_installed(monkeypatch):
    item = {
        "id": "mcp:io.example/fetch",
        "kind": "plugins",
        "name": "Fetch",
        "installed": True,
        "installable": False,
        "required_env": ["FETCH_TOKEN"],
        "plugin": {"name": "fetch", "kind": "local", "command": "npx"},
    }
    monkeypatch.setattr(catalog, "_find_catalog_item", lambda *a, **k: item)
    result = catalog.install_item("plugins", "mcp:io.example/fetch")
    assert result["already_installed"] is True
    assert result["installed"] is True
    assert "FETCH_TOKEN" in result["required_env"]


def test_install_plugin_uses_injected_registry_cache(tmp_path, monkeypatch):
    item = {
        "id": "mcp:io.example/new",
        "kind": "plugins",
        "name": "New",
        "installed": False,
        "installable": True,
        "required_env": ["FETCH_TOKEN"],
        "plugin": {
            "name": "new",
            "kind": "local",
            "command": "npx",
            "args": ["-y", "@ex/new"],
            "env": {"FETCH_TOKEN": "${FETCH_TOKEN}"},
            "note": "HTTP fetch",
        },
    }
    monkeypatch.setattr(catalog, "_find_catalog_item", lambda *a, **k: item)
    persisted = {}

    def fake_persist(section, upsert=None, **_k):
        persisted.update(upsert or {})

    monkeypatch.setattr("swarm.core.config_ownership.persist_webui_section", fake_persist)
    monkeypatch.setattr(
        catalog.mcp_plugins,
        "discover_and_store",
        lambda *a, **k: ([{"name": "fetch", "description": "Get a URL"}], item["plugin"]),
    )
    result = catalog.install_item("plugins", "mcp:io.example/new")
    assert result["installed"] is True
    assert result["already_installed"] is False
    assert result["health"] == "up"
    assert "new" in persisted
    assert persisted["new"]["env"]["FETCH_TOKEN"] == "${FETCH_TOKEN}"
    assert "sk-" not in json.dumps(result)

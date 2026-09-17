"""REQ-887 — source lock for Teams + Plugins marketplaces.

Spec of record: docs/qa/REQ-887-teams-plugins-marketplaces.md
Behaviour tests: tests/unit/test_mcp_registry.py,
tests/unit/test_marketplace_catalog.py,
webui/frontend/src/lib/__tests__/installCatalog.test.ts,
webui/frontend/src/components/__tests__/InstallCatalog.test.tsx
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "qa" / "REQ-887-teams-plugins-marketplaces.md"
DOCS = REPO / "docs" / "MARKETPLACE.md"
REGISTRY = REPO / "src" / "swarm" / "core" / "mcp_registry.py"
CATALOG = REPO / "src" / "swarm" / "core" / "marketplace_catalog.py"
SKILLS = REPO / "src" / "swarm" / "core" / "skills.py"
VIEWS = REPO / "src" / "swarm" / "views" / "marketplace_api.py"
URLS = REPO / "src" / "swarm" / "urls.py"
FRONTEND = REPO / "webui" / "frontend" / "src" / "lib" / "installCatalog.ts"
POPUP = REPO / "webui" / "frontend" / "src" / "components" / "PluginsPopup.tsx"
COMPOSER = REPO / "webui" / "frontend" / "src" / "components" / "TeamComposer.tsx"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_req887_spec_and_sources_of_truth_docs():
    assert SPEC.is_file()
    spec = _text(SPEC)
    assert "REQ-887" in spec
    assert "Official MCP Registry" in spec
    assert "Agent Skills" in spec
    assert "team_rosters" in spec
    assert "no industry team-pack standard" in spec.lower() or "no widely adopted" in spec.lower()
    docs = _text(DOCS)
    assert "registry.modelcontextprotocol.io" in docs
    assert "SKILL.md" in docs
    assert "swarm-team-pack" in docs
    assert "CrewAI" in docs
    assert "A2A" in docs


def test_req887_registry_is_cached_not_live_per_keystroke():
    text = _text(REGISTRY)
    assert "CACHE_TTL_S" in text
    assert "last-good" in text
    assert "registry.modelcontextprotocol.io" in text
    assert "${" in text
    assert "do not query" in text.lower() or "keystroke" in text.lower()


def test_req887_catalog_kinds_and_install_semantics():
    text = _text(CATALOG)
    assert "CATALOG_KINDS = (\"plugins\", \"skills\", \"teams\")" in text
    assert "parse_skill_md" in text or "skills.parse_skill_md" in text
    assert "upsert_roster" in text
    assert "must not pull binaries" in text
    assert "needs configuration" in text
    assert "discover_and_store" in text
    skills = _text(SKILLS)
    assert "def user_skills_root" in skills
    assert "def install_skill_files" in skills
    assert "Does not execute" in skills or "not execute" in skills.lower()


def test_req887_api_routes_exist():
    urls = _text(URLS)
    assert "v1/marketplace/catalog" in urls
    assert "v1/marketplace/preview" in urls
    assert "v1/marketplace/install" in urls
    views = _text(VIEWS)
    assert "class MarketplaceCatalogView" in views
    assert "class MarketplaceInstallView" in views


def test_req887_frontend_reuses_install_catalog():
    lib = _text(FRONTEND)
    assert "backendToCatalogItem" in lib
    assert "mcp_registry" in lib
    assert "usesBackendInstall" in lib
    popup = _text(POPUP)
    assert "InstallCatalog" in popup
    composer = _text(COMPOSER)
    assert "InstallCatalog" in composer
    assert 'surface="teams"' in composer

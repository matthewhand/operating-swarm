"""REQ-862 — source lock for the Operating Swarm (OS) identity.

Spec of record: docs/qa/REQ-862-rebrand-swarm-bot.md
Issue: https://github.com/matthewhand/open-swarm-private/issues/252

Pins the locked names in the *shipped* chrome files so a later edit cannot
quietly restore Open Swarm / Swarm Bot / op-swarm-* as the product identity,
or drop the README hero tagline.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
PACKAGE_JSON = REPO / "webui" / "frontend" / "package.json"
INDEX_HTML = REPO / "webui" / "frontend" / "index.html"
BASE_HTML = REPO / "src" / "swarm" / "templates" / "base.html"
SWARM_CLI = REPO / "src" / "swarm" / "core" / "swarm_cli.py"
SWARM_API = REPO / "src" / "swarm" / "core" / "swarm_api.py"
README = REPO / "README.md"
HERO_SVG = REPO / "assets" / "brand" / "operating-swarm-hero-diagram.svg"
INDEX_CSS = REPO / "webui" / "frontend" / "src" / "index.css"
SPEC = REPO / "docs" / "qa" / "REQ-862-rebrand-swarm-bot.md"
UV_LOCK = REPO / "uv.lock"
SETTINGS_DASHBOARD = REPO / "src" / "swarm" / "templates" / "settings_dashboard.html"
SETTINGS_DASHBOARD_JS = REPO / "src" / "swarm" / "static" / "js" / "settings_dashboard.js"
LOGIN_HTML = REPO / "src" / "swarm" / "templates" / "account" / "login.html"
DJANGO_TEMPLATES = REPO / "src" / "swarm" / "templates"
SETTINGS_SHEET = REPO / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx"
UPDATE_CHROME = REPO / "webui" / "frontend" / "src" / "components" / "UpdateChrome.tsx"
AGENT_ROUTER = REPO / "webui" / "frontend" / "src" / "pages" / "AgentRouterPage.tsx"
CLI_AGENTS_PANE = (
    REPO / "webui" / "frontend" / "src" / "components" / "CliAgentsSettingsPane.tsx"
)

LOCKED_COMPONENTS = (
    "os-core",
    "os-api",
    "os-webui",
    "os-cli",
    "os-adapter-hermes",
    "os-adapter-truforge",
    "os-peer",
)

TAGLINE = "Treat external harnesses and peer instances as one common abstraction."

CHROME = (PYPROJECT, PACKAGE_JSON, INDEX_HTML, BASE_HTML, SWARM_CLI, SWARM_API, README)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_req862_pyproject_is_os_core_not_a_component_named_operating_swarm():
    text = _text(PYPROJECT)
    assert 'name = "os-core"' in text
    assert "Operating Swarm" in text
    assert 'os-cli = "swarm.core.swarm_cli:app"' in text
    assert 'os = "swarm.core.swarm_cli:app"' in text
    assert 'os-api = "swarm.core.swarm_api:main"' in text
    assert "swarm-cli =" not in text
    assert "swarm-api =" not in text
    assert "[tool.hatch.build.targets.wheel]" in text
    assert 'packages = ["src/swarm"]' in text
    assert "op-swarm-" not in text
    assert 'name = "operating-swarm"' not in text
    assert 'name = "open-swarm"' not in text


def test_req862_uv_lock_editable_root_is_os_core():
    """CI runs ``uv lock --check``; the lockfile must match pyproject name."""
    text = _text(UV_LOCK)
    idx = text.index('source = { editable = "." }')
    window = text[max(0, idx - 80) : idx]
    assert 'name = "os-core"' in window
    assert 'name = "open-swarm"' not in window


def test_req862_frontend_package_is_os_webui():
    text = _text(PACKAGE_JSON)
    assert '"name": "os-webui"' in text
    assert "Operating Swarm" in text
    assert "open-swarm-webui" not in text
    assert "op-swarm-" not in text
    assert "operating-swarm-webui" not in text


def test_req862_html_titles_are_operating_swarm():
    assert "<title>Operating Swarm</title>" in _text(INDEX_HTML)
    assert "{% block title %}Operating Swarm{% endblock %}" in _text(BASE_HTML)


def test_req862_cli_and_api_banners_name_operating_swarm():
    cli = _text(SWARM_CLI)
    api = _text(SWARM_API)
    assert "Operating Swarm CLI (OS CLI)" in cli
    assert "Operating Swarm API (OS Server)" in api
    assert "Launching Operating Swarm API (OS Server)" in api
    assert "Swarm CLI tool" not in cli
    assert "Open Swarm OpenAI-compatible API server" not in api


def test_req862_readme_hero_title_tagline_and_diagram():
    text = _text(README)
    assert text.startswith("# Operating Swarm (OS)\n")
    assert f"> {TAGLINE}" in text.split("## ", 1)[0]
    assert "assets/brand/operating-swarm-hero-diagram.svg" in text.split("## ", 1)[0]
    assert HERO_SVG.is_file()
    # Not "only a UI / wrapper / …"
    hero = text.split("## ", 1)[0]
    assert "not only a ui, wrapper, gateway, adapter, or supervisor" in hero.lower()
    for name in LOCKED_COMPONENTS:
        assert name in text, f"README must name architecture component {name}"
    assert "operating-swarm" in text
    assert "Swarm Bot" not in text


def test_req862_chrome_has_no_swarm_bot_or_op_swarm_packages():
    for path in CHROME:
        blob = _text(path)
        assert "Swarm Bot" not in blob, f"{path.relative_to(REPO)} still says Swarm Bot"
        assert "op-swarm-" not in blob, f"{path.relative_to(REPO)} still uses op-swarm-*"


def test_req862_css_prefix_and_python_import_unchanged():
    css = _text(INDEX_CSS)
    assert ".os-agent-sidebar" in css
    cli = _text(SWARM_CLI)
    assert "import swarm" in cli
    assert "from swarm.core import paths" in cli


def test_req862_spec_doc_is_shipped():
    assert SPEC.is_file()
    text = _text(SPEC)
    assert "REQ-862" in text
    assert "os-core" in text
    assert "test_req862_operating_swarm_rebrand.py" in text


def test_req862_operator_chrome_no_longer_says_open_swarm():
    login = _text(LOGIN_HTML)
    assert '<h1 class="brand-name">Operating Swarm</h1>' in login
    assert "<title>Login &middot; Operating Swarm</title>" in login
    assert "Open Swarm" not in login

    dashboard = _text(SETTINGS_DASHBOARD)
    assert "{% block title %}Settings - Operating Swarm{% endblock %}" in dashboard
    assert "Configuration management for Operating Swarm (OS)" in dashboard
    assert "Open Swarm" not in dashboard

    dashboard_js = _text(SETTINGS_DASHBOARD_JS)
    assert "open-swarm-settings" not in dashboard_js
    assert "operating-swarm-settings" in dashboard_js

    leftover = [
        str(path.relative_to(REPO))
        for path in DJANGO_TEMPLATES.rglob("*.html")
        if "Open Swarm" in _text(path)
    ]
    assert leftover == [], f"Django templates still say Open Swarm: {leftover}"

    readme = _text(README)
    assert "(and nested Operating Swarm / OS instance)" in readme
    # Historical OpenAI Swarm lineage — not product chrome.
    assert "Operating Swarm began as **Open Swarm**" in readme
    assert "extension of OpenAI" in readme

    sheet = _text(SETTINGS_SHEET)
    assert ">Operating Swarm</span>" in sheet
    assert "Open Swarm" not in sheet

    for path in (UPDATE_CHROME, AGENT_ROUTER, CLI_AGENTS_PANE):
        blob = _text(path)
        assert "Open Swarm" not in blob, f"{path.relative_to(REPO)} still says Open Swarm"
        assert "Operating Swarm" in blob

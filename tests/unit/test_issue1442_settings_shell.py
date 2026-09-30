"""#1442: Settings from Chat keeps the operator shell; logo and sidebar use tokens.

The Django ``/settings/`` page is the same rail/header shell as the rest of
the operator chrome. Catalog seats must paint (the sidebar used to throw
before appending the mark), and the brand mark follows theme tokens instead
of a baked charcoal plate.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "src" / "swarm" / "templates" / "base.html"
SETTINGS = REPO / "src" / "swarm" / "templates" / "settings_dashboard.html"
SIDEBAR = REPO / "src" / "swarm" / "static" / "js" / "agent_sidebar.js"
PIN = REPO / "src" / "swarm" / "static" / "js" / "agent_pin_grid.js"
THEME = REPO / "src" / "swarm" / "static" / "js" / "chrome_theme.js"
CSS = REPO / "src" / "swarm" / "static" / "css" / "rest_mode_style.css"


def _make_link_source() -> str:
    js = SIDEBAR.read_text(encoding="utf-8")
    match = re.search(r"function makeLink\(agent, hidden\) \{([\s\S]*?)\n    function makeTeamLink", js)
    assert match, "makeLink must stay ahead of makeTeamLink"
    return match.group(1)


def test_make_link_appends_the_dot_it_creates():
    body = _make_link_source()
    assert "var dot = document.createElement" in body
    assert "link.appendChild(dot)" in body
    assert "appendChild(mark)" not in body


def test_shell_logo_uses_theme_tokens_not_a_charcoal_plate():
    css = CSS.read_text(encoding="utf-8")
    html = BASE.read_text(encoding="utf-8")
    assert "--os-chrome-sidebar" in css
    assert "--os-chrome-header" in css
    assert "background: var(--os-chrome-sidebar)" in css
    assert "background: var(--os-chrome-header)" in css
    assert "color: var(--os-text-strong)" in css
    assert 'fill="currentColor"' in html
    assert "brand/webui-geometric.svg" in html
    assert "os-brand-mark-geometric" in html
    assert "os-brand-mark-asset" in html
    assert 'class="os-brand-mark-asset" aria-hidden="true"' in html
    assert "navbar-dark" not in html


def test_pin_grid_seeds_support_without_a_second_face():
    """Chat's pin grid is a mark dot plus a name. An extra <img> stacks under it."""
    js = PIN.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    assert 'id: "support"' in js
    assert 'createElement("img")' not in js
    assert "os-agent-tile__face" not in js
    assert "os-agent-tile__face" not in css


def test_theme_script_honors_system_without_overwriting_it():
    js = THEME.read_text(encoding="utf-8")
    assert 'stored === "system"' in js
    assert "prefers-color-scheme: dark" in js
    assert "applyTheme(resolveTheme(readStored()), false)" in js
    assert 'readStored() !== "system"' in js
    assert 'media.addEventListener("change"' in js
    assert "btn.textContent" in js


def test_settings_env_modal_is_not_a_permanent_loader():
    html = SETTINGS.read_text(encoding="utf-8")
    assert 'id="envContent">Loading' not in html
    assert 'id="envContent"' in html


def test_settings_page_extends_the_shared_shell():
    """Chat and Django Settings share base.html (rail, header, theme script)."""
    settings = SETTINGS.read_text(encoding="utf-8")
    shell = BASE.read_text(encoding="utf-8")
    assert "{% extends 'base.html' %}" in settings
    assert 'id="os-agent-sidebar"' in shell
    assert 'class="os-header' in shell
    assert 'id="os-main"' in shell
    assert 'id="os-agent-status">Loading agents' in shell
    assert "agent_sidebar.js" in shell
    assert "chrome_theme.js" in shell
    assert "agent_pin_grid.js" in shell

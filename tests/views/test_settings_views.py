"""REQ-864 / #254: Django /settings/ renders cleanly and points at the SPA sheet."""

from __future__ import annotations

from pathlib import Path

from helpers.source_surface import chat_surface

import pytest

REPO = Path(__file__).resolve().parents[2]
OPERATOR_CSS = REPO / "src" / "swarm" / "static" / "css" / "operator.css"
SETTINGS_HTML = REPO / "src" / "swarm" / "templates" / "settings_dashboard.html"
CHAT_PAGE = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"


def test_settings_page_css_has_container_and_card_tokens():
    css = OPERATOR_CSS.read_text(encoding="utf-8")
    assert ".settings-page" in css
    assert "max-width: 1200px" in css
    assert "padding: 1.5rem" in css
    assert ".dashboard-header-card" in css
    assert ".stat-card" in css
    assert ".chat-retention-card" in css
    assert ".configuration-progress" in css
    assert ".settings-spa-banner" in css
    assert "var(--os-panel)" in css
    assert "var(--os-border)" in css
    assert "var(--os-text-strong)" in css


def test_settings_dashboard_template_has_spa_banner():
    html = SETTINGS_HTML.read_text(encoding="utf-8")
    assert "Looking for WebUI settings?" in html
    assert 'href="/chat?settings=true"' in html
    assert 'href="/chat"' in html
    assert 'data-testid="settings-spa-banner"' in html
    assert 'class="settings-page"' in html


def test_chat_page_manage_cli_opens_in_app_sheet():
    # #681/#836: the manage action moved to the composer picker's footer,
    # which opens the unified Providers hub — no page navigation anywhere.
    src = chat_surface()
    assert "window.location.assign(MANAGE_CLI_HREF)" not in src
    assert "Manage Cli" not in src


def test_composer_picker_manage_opens_providers_hub():
    # #836: the two-stage picker's footer opens the unified Providers hub.
    src = chat_surface()
    assert "section: 'providers'" in src
    assert "openSettingsSheet" in src


@pytest.mark.django_db
def test_settings_dashboard_renders_200_with_spa_banner_and_page_shell():
    from django.contrib.auth import get_user_model
    from django.test import Client

    User = get_user_model()
    User.objects.create_user(username="u-254", password="p")
    client = Client()
    client.login(username="u-254", password="p")
    resp = client.get("/settings/")
    assert resp.status_code == 200
    html = resp.content.decode()
    assert 'class="settings-page"' in html
    assert "Looking for WebUI settings?" in html
    assert 'href="/chat?settings=true"' in html
    assert 'href="/chat"' in html
    assert "Settings Dashboard" in html
    assert "dashboard-header-card" in html
    assert "stat-card" in html
    assert "configuration-progress" in html

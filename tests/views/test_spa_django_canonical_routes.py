"""UX fleet: bare SPA dual-paths redirect to canonical Django operator UI.

These exercise the *shipped* urlpatterns (RedirectView entries in swarm.urls)
via the Django test client — not a reimplementation of the map.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.urls import reverse

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def webui_on(settings, monkeypatch):
    """Ensure Web UI views are not gated off (env + settings)."""
    monkeypatch.setenv("ENABLE_WEBUI", "true")
    settings.ENABLE_WEBUI = True
    return settings


@pytest.mark.django_db
class TestSpaToDjangoCanonicalRedirects:
    """Bare paths that used to dual-mount the React shell must 302 to Django."""

    @pytest.mark.parametrize(
        "path,expected_location",
        [
            ("/teams", "/teams/launch/"),
            ("/blueprints", "/blueprint-library/"),
            ("/settings", "/settings/"),
            ("/agent-creator", "/agent-creator/"),
            ("/sessions", "/sessions/"),
            ("/login", "/login/"),
            ("/blueprint-library", "/blueprint-library/"),
            ("/profiles", "/profiles/"),
        ],
    )
    def test_bare_spa_path_redirects_to_django(self, client, path, expected_location):
        response = client.get(path)
        assert response.status_code == 302, (
            f"{path} should redirect to canonical Django UI, got {response.status_code}"
        )
        assert response.url == expected_location

    def test_query_string_preserved_on_teams_redirect(self, client):
        response = client.get("/teams?blueprint=hybrid_team")
        assert response.status_code == 302
        assert response.url.startswith("/teams/launch/")
        assert "blueprint=hybrid_team" in response.url

    def test_named_redirect_routes_exist(self):
        assert reverse("spa_teams_to_django") == "/teams"
        assert reverse("spa_blueprints_to_django") == "/blueprints"
        assert reverse("spa_settings_to_django") == "/settings"
        assert reverse("spa_agent_creator_to_django") == "/agent-creator"
        assert reverse("spa_sessions_to_django") == "/sessions"
        assert reverse("spa_login_to_django") == "/login"
        assert reverse("spa_blueprint_library_to_django") == "/blueprint-library"
        assert reverse("spa_profiles_to_django") == "/profiles"
        assert reverse("spa_agents") == "/agents"
        assert reverse("spa_chat") == "/chat"

    def test_trailing_slash_django_routes_not_redirect_loops(self, client, webui_on):
        """Canonical Django routes keep working (no redirect-to-self loops)."""
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxcanon", password="ux-canon-pass")
        client.force_login(user)
        for path in ("/teams/", "/teams/launch/", "/settings/", "/blueprint-library/"):
            response = client.get(path)
            assert response.status_code in (200, 302, 301), (
                f"{path} unexpected status {response.status_code}: "
                f"{response.content[:120]!r}"
            )
            if response.status_code in (301, 302):
                assert response.url != path


@pytest.mark.django_db
class TestSpaChatStaysChat:
    """REQ-5d follow-up: GET /chat must not land on /agents."""

    @pytest.mark.parametrize("path", ("/chat", "/chat/"))
    def test_chat_does_not_redirect_to_agents(self, client, path):
        response = client.get(path, follow=False)
        location = response.get("Location", "")
        assert "/agents" not in location
        if response.status_code in (301, 302):
            assert "/chat" in response.url
        else:
            assert response.status_code in (200, 404)

    @pytest.mark.parametrize("path", ("/agents", "/agents/"))
    def test_agents_does_not_redirect_to_chat(self, client, path):
        response = client.get(path, follow=False)
        location = response.get("Location", "")
        assert "/chat" not in location
        assert response.status_code in (200, 404)

    def test_agents_preserves_query_string(self, client):
        response = client.get("/agents?blueprint=codey", follow=False)
        location = response.get("Location") or ""
        assert "/chat" not in location
        assert response.status_code in (200, 404)

    def test_chat_serves_spa_when_dist_exists(self, client, tmp_path, monkeypatch):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text(
            "<html><body>spa-chat-composer Connected</body></html>",
            encoding="utf-8",
        )
        monkeypatch.setattr("swarm.views.web_views._get_frontend_path", lambda: dist)
        response = client.get("/chat", follow=False)
        assert response.status_code == 200
        # #428 / #425: SPA HTML is a buffered HttpResponse (not FileResponse.streaming_content).
        assert getattr(response, "streaming", False) is False
        body = response.content
        assert b"spa-chat-composer" in body
        assert b"Connected" in body
        assert response.get("Location") is None

    def test_django_chat_nav_href_is_chat_not_agents(self):
        from pathlib import Path

        base = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "swarm"
            / "templates"
            / "base.html"
        ).read_text(encoding="utf-8")
        assert 'href="/chat"' in base
        assert 'href="/agents"' in base
        assert 'id="moreNavDropdown"' in base
        # Chat is under More, not a primary peer of Agents.
        assert 'href="/chat">Chat</a>' in base
        assert 'href="/agents"' in base
        assert ">Agents</a>" in base


@pytest.mark.django_db
class TestUxShellTemplateContracts:
    """Structural contracts for shell IA / density shipped in templates."""

    def test_base_shell_has_five_primary_destinations_and_more(self, client):
        # base.html is extended by many pages; settings requires login often.
        # Use login page which extends base, or force_login.
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxshell", password="ux-shell-pass")
        client.force_login(user)
        response = client.get("/settings/")
        assert response.status_code == 200
        html = response.content.decode()
        for label in ("Home", "Chat", "Blueprints", "Teams", "Sessions", "Settings"):
            assert label in html
        assert "More" in html
        assert "os-bottom-nav" in html
        assert "Skip to main content" in html
        assert 'id="os-main"' in html
        assert 'id="os-agent-sidebar"' in html
        assert 'id="os-theme-toggle"' in html
        # GitHub not a bare primary peer string next to Settings as sole link —
        # demoted under More dropdown.
        assert 'id="moreNavDropdown"' in html

    @pytest.mark.parametrize(
        "path",
        ("/teams/", "/sessions/", "/settings/", "/blueprint-library/"),
    )
    def test_operator_pages_use_chat_matched_shell(self, client, path):
        """REQ-5d: Django tabs share Chat chrome — header then AGENTS+main, no login body."""
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username="uxreq5d" + path.strip("/").replace("/", "_"),
            password="ux-req5d-pass",
        )
        client.force_login(user)
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.content.decode()
        assert 'class="os-app"' in html
        assert 'class="os-header sticky-top"' in html
        assert 'class="os-shell"' in html
        assert 'id="os-agent-sidebar"' in html
        assert 'id="os-main"' in html
        header_at = html.find('class="os-header sticky-top"')
        shell_at = html.find('class="os-shell"')
        sidebar_at = html.find('id="os-agent-sidebar"')
        main_at = html.find('id="os-main"')
        assert 0 <= header_at < shell_at < sidebar_at < main_at
        assert "os-login" not in html
        for label in ("Home", "Chat", "Blueprints", "Teams", "Sessions", "Settings"):
            assert label in html

    def test_profiles_marks_profiles_item_active_not_teams(self, client):
        import re

        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxprof", password="ux-prof-pass")
        client.force_login(user)
        response = client.get("/profiles/")
        assert response.status_code == 200
        html = response.content.decode()
        # Settings is the parent chrome item for /profiles/ (More popup).
        settings_link = re.search(
            r'<a class="dropdown-item active"[^>]*href="/settings/"',
            html,
        )
        assert settings_link, "expected active Settings dropdown item on /profiles/"
        teams_link = re.search(
            r'<a class="dropdown-item([^"]*)"[^>]*href="/teams/launch/"',
            html,
        )
        assert teams_link, "expected Teams dropdown item"
        assert "active" not in teams_link.group(1)
        # Mobile bottom: Agents + More; Teams is not a primary dock tab.
        assert 'os-bottom-nav__label">Teams</span>' not in html
        assert 'os-bottom-nav__label">Agents</span>' in html
        assert 'id="moreNavDropdownMobile"' in html

    def test_sessions_marks_sessions_nav_active(self, client):
        import re

        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxsessnav", password="ux-sess-nav")
        client.force_login(user)
        response = client.get("/sessions/")
        assert response.status_code == 200
        html = response.content.decode()
        sessions_link = re.search(
            r'<a class="dropdown-item active"[^>]*href="/sessions/"',
            html,
        )
        assert sessions_link, "expected active Sessions dropdown item"
        teams_link = re.search(
            r'<a class="dropdown-item([^"]*)"[^>]*href="/teams/launch/"',
            html,
        )
        assert teams_link and "active" not in teams_link.group(1)

    def test_blueprint_library_ships_client_pagination(self, client):
        from pathlib import Path

        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxlib", password="ux-lib-pass")
        client.force_login(user)
        response = client.get("/blueprint-library/")
        assert response.status_code == 200
        html = response.content.decode()
        assert "blueprint_library.js" in html
        assert "<script>\n// Client-side page size" not in html
        assert "Show more" in html
        assert "bpShowMore" in html
        js = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "swarm"
            / "static"
            / "js"
            / "blueprint_library.js"
        ).read_text(encoding="utf-8")
        assert "BP_PAGE_SIZE" in js

    def test_session_explorer_ships_scroll_containment(self, client):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxsess", password="ux-sess-pass")
        client.force_login(user)
        response = client.get("/sessions/")
        assert response.status_code == 200
        html = response.content.decode()
        assert "se-list-scroll" in html
        assert "session_explorer.js" in html
        assert "<script>\n(function(){" not in html
        assert "os-launch-btn" in html
        assert reverse("teams_launch") == "/teams/launch/"

    def test_session_explorer_empty_paths_include_launch_cta(self):
        template = (REPO / "src" / "swarm" / "templates" / "session_explorer.html").read_text(
            encoding="utf-8"
        )
        js = (REPO / "src" / "swarm" / "static" / "js" / "session_explorer.js").read_text(
            encoding="utf-8"
        )
        assert "{% url 'teams_launch' %}" in template
        assert "os-launch-btn" in template
        assert "Launch a team" in template
        assert "/teams/launch/" in js
        assert "os-launch-btn" in js
        assert "Launch a team" in js

    def test_chrome_teams_labels_share_one_href(self):
        html = (REPO / "src" / "swarm" / "templates" / "base.html").read_text(encoding="utf-8")
        anchors = re.findall(
            r"<a\b([^>]*)>\s*(?:<i\b[^>]*>\s*</i>\s*)?Teams\s*</a>",
            html,
        )
        hrefs = []
        for attrs in anchors:
            match = re.search(r'href="([^"]+)"', attrs)
            assert match, attrs
            hrefs.append(match.group(1))
        assert hrefs, "expected Teams links in operator chrome"
        assert set(hrefs) == {"/teams/launch/"}, hrefs

    def test_agent_creator_progressive_disclosure(self, client):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxac", password="ux-ac-pass")
        client.force_login(user)
        response = client.get("/agent-creator/")
        assert response.status_code == 200
        html = response.content.decode()
        # Persona / Tags optional panels collapsed by default
        assert 'data-bs-target="#acc-persona"' in html
        assert "accordion-button collapsed" in html
        assert 'id="acc-persona" class="accordion-collapse collapse"' in html
        assert 'id="acc-behavior" class="accordion-collapse collapse"' in html
        # Essentials open
        assert 'id="acc-identity" class="accordion-collapse collapse show"' in html
        assert "Blueprint interface spec" in html
        assert "class MyTeamBlueprint" in html

    def test_issue406_library_my_library_counts_custom(self, client):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxlib", password="ux-lib-pass")
        client.force_login(user)
        html = client.get("/blueprint-library/").content.decode()
        assert "Installed and custom blueprints (" not in html
        assert "Installed " in html and " · custom " in html

    def test_issue405_library_card_title_uses_id_not_truncate_class(self, client):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxcard", password="ux-card-pass")
        client.force_login(user)
        html = client.get("/blueprint-library/").content.decode()
        assert "remote_harness" in html
        assert "card-title mb-0 text-truncate" not in html

    def test_issue407_herdr_location_option_fully_visible(self, client):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxherd", password="ux-herd-pass")
        client.force_login(user)
        html = client.get("/settings/").content.decode()
        assert ">Local (no SSH)</option>" in html
        assert 'placeholder="http://127.0.0.1"' in html
        assert "only if you chose localhost" not in html

    def test_issue409_save_hidden_until_code_exists(self, client):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxsave", password="ux-save-pass")
        client.force_login(user)
        html = client.get("/agent-creator/").content.decode()
        save_bit = html.split('id="saveBtn"', 1)[1][:200]
        pre = html.split('id="saveBtn"', 1)[0][-120:]
        assert "d-none" in pre + save_bit
        assert "btn-success" not in pre + save_bit

    def test_agent_creator_uses_data_action_not_onclick(self, client):
        """Static creator actions bind via data-action delegation (no inline onclick)."""
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxac2", password="ux-ac-pass")
        client.force_login(user)
        response = client.get("/agent-creator/")
        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-action="generate-agent"' in html
        assert 'data-action="clear-form"' in html
        assert 'data-action="validate-code"' in html
        assert 'data-action="save-agent"' in html
        assert "onclick=" not in html
        assert "agent_creator.js" in html
        assert "<script>\nlet generatedCode" not in html
        from pathlib import Path
        ac_js = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "swarm"
            / "static"
            / "js"
            / "agent_creator.js"
        ).read_text(encoding="utf-8")
        assert "AGENT_CREATOR_ACTIONS" in ac_js

    def test_team_creator_uses_data_action_not_onclick(self, client):
        from pathlib import Path

        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxteam", password="ux-team-pass")
        client.force_login(user)
        response = client.get("/team-creator/")
        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-action="add-member"' in html
        assert 'data-action="generate-team"' in html
        assert 'data-action="clear-team"' in html
        assert 'data-action="validate-team"' in html
        assert 'data-action="save-team"' in html
        assert "onclick=" not in html
        assert "team_creator.js" in html
        assert 'id="team-creator-profiles"' in html
        assert "<script>\nlet teamMemberCount" not in html
        js = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "swarm"
            / "static"
            / "js"
            / "team_creator.js"
        ).read_text(encoding="utf-8")
        assert "TEAM_CREATOR_ACTIONS" in js
        assert 'data-action="remove-member"' in js

    def test_agent_creator_pro_redirects_to_canonical(self, client):
        """Unwired Pro UI soft-redirects to /agent-creator/ (preserve query)."""
        response = client.get("/agent-creator-pro/?from=nav")
        assert response.status_code in (301, 302)
        assert response["Location"].endswith("/agent-creator/?from=nav") or \
            response["Location"] == "/agent-creator/?from=nav"

    def test_my_blueprints_runner_posts_chat_completions(self, client):
        from pathlib import Path

        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxmb", password="ux-mb-pass")
        client.force_login(user)
        response = client.get("/blueprint-library/my-blueprints/")
        assert response.status_code == 200
        html = response.content.decode()
        assert "Simulate run (demo)" not in html
        assert "Client-side demo only" not in html
        assert "my_blueprints.js" in html
        assert "<script>\ndocument.addEventListener('DOMContentLoaded'" not in html
        assert "Run via API" in html
        assert "/teams/launch/" in html
        js = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "swarm"
            / "static"
            / "js"
            / "my_blueprints.js"
        ).read_text(encoding="utf-8")
        assert "/v1/chat/completions" in js
        assert "X-CSRFToken" in js
        assert "/chat?blueprint=" in js

    def test_settings_unwired_actions_are_disabled(self, client):
        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxset", password="ux-set-pass")
        client.force_login(user)
        response = client.get("/settings/")
        assert response.status_code == 200
        html = response.content.decode()
        assert "Validate Config (not available)" not in html
        assert "Export (not available)" in html
        assert "(soon)" not in html
        assert "btn-check-path" not in html
        assert "onclick=\"validateConfiguration()\"" not in html
        assert "onclick=\"exportEnvVars()\"" not in html
        assert "onclick=\"checkPath(" not in html

    def test_settings_dashboard_uses_data_action_not_onclick(self, client):
        from pathlib import Path

        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxset2", password="ux-set-pass")
        client.force_login(user)
        response = client.get("/settings/")
        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-action="export-settings"' in html
        assert 'data-action="refresh-settings"' in html
        assert 'data-action="view-environment"' in html
        assert 'data-action="copy-object-content"' in html
        assert "onclick=" not in html
        assert "settings_dashboard.js" in html
        js = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "swarm"
            / "static"
            / "js"
            / "settings_dashboard.js"
        ).read_text(encoding="utf-8")
        assert "SETTINGS_DASHBOARD_ACTIONS" in js

    def test_blueprint_library_uses_data_action_not_onclick(self, client):
        from pathlib import Path

        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxbplib", password="ux-bp-pass")
        client.force_login(user)
        response = client.get("/blueprint-library/")
        assert response.status_code == 200
        html = response.content.decode()
        assert 'data-action="show-more-blueprints"' in html
        assert 'data-action="clear-blueprint-search"' in html
        assert "onclick=" not in html
        assert "oninput=" not in html
        assert "blueprint_library.js" in html
        js = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "swarm"
            / "static"
            / "js"
            / "blueprint_library.js"
        ).read_text(encoding="utf-8")
        assert "BLUEPRINT_LIBRARY_ACTIONS" in js
        assert 'data-action="load-github-marketplace"' in html or "load-github-marketplace" in js

    def test_blueprint_creator_uses_data_action_not_onclick(self, client):
        from pathlib import Path

        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxbpcr", password="ux-bp-pass")
        client.force_login(user)
        response = client.get("/blueprint-library/creator/")
        assert response.status_code == 200
        html = response.content.decode()
        assert "Blueprint interface spec" in html
        assert "class MyTeamBlueprint" in html
        assert 'data-action="reset-form"' in html
        assert "onclick=" not in html
        assert "blueprint_creator.js" in html
        js = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "swarm"
            / "static"
            / "js"
            / "blueprint_creator.js"
        ).read_text(encoding="utf-8")
        assert "BLUEPRINT_CREATOR_ACTIONS" in js

    def test_team_creator_validate_marked_unavailable(self, client):
        from pathlib import Path

        from django.contrib.auth.models import User

        user = User.objects.create_user(username="uxtd", password="ux-td-pass")
        client.force_login(user)
        response = client.get("/team-creator/")
        assert response.status_code == 200
        html = response.content.decode()
        assert "Validate (not available)" in html
        assert "Validate (demo)" not in html
        assert "Preview Draft" in html
        js = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "swarm"
            / "static"
            / "js"
            / "team_creator.js"
        ).read_text(encoding="utf-8")
        assert "no server-side team validation" in js

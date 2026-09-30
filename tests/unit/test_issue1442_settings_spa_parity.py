"""#1442 — leftover Settings hops use the SPA sheet, not the Django dump."""

from __future__ import annotations

from pathlib import Path

from swarm.core.support_context import CREATE_PATHS, SPA_SETTINGS_INFERENCE_HREF, create_paths_markdown

REPO = Path(__file__).resolve().parents[2]
SETTINGS_LINKS = REPO / "webui" / "frontend" / "src" / "lib" / "settingsLinks.ts"
RETENTION_PANE = REPO / "webui" / "frontend" / "src" / "components" / "settings" / "panes" / "RetentionPane.tsx"
SUPPORT_PILL = REPO / "webui" / "frontend" / "src" / "components" / "SupportBriefingPill.tsx"
BRIEFING = REPO / "webui" / "frontend" / "src" / "lib" / "support-briefing.ts"
CLI_CTX = REPO / "webui" / "frontend" / "src" / "lib" / "cliAgentContext.ts"
CHAT_STATUS = REPO / "webui" / "frontend" / "src" / "lib" / "chatStatus.ts"
DJANGO_SETTINGS = REPO / "src" / "swarm" / "templates" / "settings_dashboard.html"


def test_set_inference_chip_is_spa_deeplink():
    assert CREATE_PATHS["settings"] == "/chat?settings=llm-profiles"
    assert SPA_SETTINGS_INFERENCE_HREF == "/chat?settings=llm-profiles"
    assert "[Set inference](/chat?settings=llm-profiles)" in create_paths_markdown()
    assert "](/settings/)" not in create_paths_markdown()


def test_frontend_settings_hrefs_are_spa_deeplinks():
    links = SETTINGS_LINKS.read_text(encoding="utf-8")
    assert "export const SPA_SETTINGS_HREF = '/chat?settings=true'" in links
    assert "export const SPA_SETTINGS_INFERENCE_HREF = '/chat?settings=llm-profiles'" in links
    assert "export const MANAGE_CLI_HREF = '/chat?settings=cli-agents'" in links

    assert "href: SPA_SETTINGS_INFERENCE_HREF" in SUPPORT_PILL.read_text(encoding="utf-8")
    briefing = BRIEFING.read_text(encoding="utf-8")
    assert "](/chat?settings=llm-profiles)" in briefing
    assert "](/chat?settings=true)" in briefing
    assert "](/settings/)" not in briefing

    assert "MANAGE_CLI_HREF = '/chat?settings=cli-agents'" in CLI_CTX.read_text(encoding="utf-8")
    assert "MANAGE_CLI_HREF = '/chat?settings=cli-agents'" in CHAT_STATUS.read_text(encoding="utf-8")


def test_retention_pane_does_not_eject_to_django_dump():
    src = RETENTION_PANE.read_text(encoding="utf-8")
    assert "Server retention dashboard" not in src
    assert "/settings/#chat-retention-title" not in src
    assert "settings-retention-pane" in src


def test_django_dump_stays_and_points_at_spa_sheet():
    html = DJANGO_SETTINGS.read_text(encoding="utf-8")
    assert "Looking for WebUI settings?" in html
    assert 'href="/chat?settings=true"' in html
    assert "Settings Dashboard" in html

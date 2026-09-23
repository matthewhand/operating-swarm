"""Screenshot tour registry consistency (USERGUIDE / GUIDED_TOUR honesty).

Drives real files in the repo: every PNG embedded by tour docs must exist,
and every stem in scripts/capture_user_journey.PAGES must be listed in
docs/SCREENSHOTS.md.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCREENSHOTS_DIR = REPO / "docs" / "screenshots"
SCREENSHOTS_MD = REPO / "docs" / "SCREENSHOTS.md"
GUIDED_TOUR = REPO / "docs" / "GUIDED_TOUR.md"
USER_JOURNEY = REPO / "docs" / "USER_JOURNEY.md"
CAPTURE_SCRIPT = REPO / "scripts" / "capture_user_journey.py"


def _png_embeds(md_text: str) -> set[str]:
    """Return basenames referenced as ./screenshots/<file>.png or screenshots/…"""
    found = set()
    for m in re.finditer(
        r"(?:\./)?screenshots/(?:mobile/)?([a-z0-9_-]+\.png)",
        md_text,
        re.I,
    ):
        found.add(m.group(1))
    return found


def _non_archive_screenshot_pngs() -> list[Path]:
    """Every PNG under docs/screenshots/ except archive/ and ephemeral _* crops."""
    out: list[Path] = []
    for p in SCREENSHOTS_DIR.rglob("*.png"):
        rel_parts = p.relative_to(SCREENSHOTS_DIR).parts
        if "archive" in rel_parts:
            continue
        # Ephemeral OCR crops: docs/screenshots/_*/… or any _*.png basename.
        if any(part.startswith("_") for part in rel_parts):
            continue
        out.append(p)
    return sorted(out)


def _registry_rel(path: Path) -> str:
    return path.relative_to(SCREENSHOTS_DIR).as_posix()


def _docs_png_embed_targets() -> set[str]:
    """Relative paths under docs/screenshots/ that markdown under docs/ (+ README) embeds."""
    embed_re = re.compile(r"!\[[^\]]*\]\(([^)]+\.png)\)")
    found: set[str] = set()
    md_files = list((REPO / "docs").rglob("*.md")) + [REPO / "README.md"]
    for path in md_files:
        if not path.is_file():
            continue
        text = path.read_text(errors="ignore")
        for m in embed_re.finditer(text):
            rel = m.group(1)
            if rel.startswith("http"):
                continue
            target = (path.parent / rel).resolve()
            try:
                found.add(target.relative_to(SCREENSHOTS_DIR.resolve()).as_posix())
            except ValueError:
                continue
    return found


def _ast_str(node: ast.AST) -> str | None:
    """Constant string, or the literal prefix of an f-string / JoinedStr."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        # Path may be f"/sessions/{SESSION_DETAIL_ID}/" — stem is still plain.
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                break
        return "".join(parts) if parts else None
    return None


def _capture_script_stems() -> list[str]:
    """Parse PAGES list from capture_user_journey.py without reimplementing it.

    Rows may use f-strings for the path (e.g. session-detail); only the stem
    (tuple element 0) must be a plain string constant.
    """
    src = CAPTURE_SCRIPT.read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "PAGES":
                    if not isinstance(node.value, ast.List):
                        raise AssertionError("PAGES must be a list literal")
                    stems: list[str] = []
                    for elt in node.value.elts:
                        if not isinstance(elt, ast.Tuple) or not elt.elts:
                            raise AssertionError(f"PAGES row must be a tuple: {ast.dump(elt)}")
                        stem = _ast_str(elt.elts[0])
                        if stem is None:
                            raise AssertionError(
                                f"PAGES stem must be a string constant: {ast.dump(elt.elts[0])}"
                            )
                        stems.append(stem)
                    return stems
    raise AssertionError("PAGES list not found in capture_user_journey.py")


def test_guided_tour_and_journey_embeds_exist_on_disk():
    embeds = _png_embeds(GUIDED_TOUR.read_text()) | _png_embeds(USER_JOURNEY.read_text())
    assert embeds, "tour docs should embed at least one screenshot"
    missing = []
    for name in sorted(embeds):
        desktop = SCREENSHOTS_DIR / name
        # embeds may be mobile/foo.png basename only — check desktop registry
        if not desktop.is_file():
            # allow only mobile path references if present under mobile/
            mobile = SCREENSHOTS_DIR / "mobile" / name
            if not mobile.is_file():
                missing.append(name)
    assert not missing, f"PNG embeds missing from docs/screenshots/: {missing}"


def test_capture_pages_covered_by_registry():
    stems = _capture_script_stems()
    registry = SCREENSHOTS_MD.read_text()
    missing = [s for s in stems if f"`{s}.png`" not in registry and f"{s}.png" not in registry]
    assert not missing, f"capture stems missing from SCREENSHOTS.md: {missing}"


def test_capture_pages_png_files_exist_desktop_and_mobile():
    stems = _capture_script_stems()
    missing = []
    for s in stems:
        if not (SCREENSHOTS_DIR / f"{s}.png").is_file():
            missing.append(f"desktop:{s}.png")
        if not (SCREENSHOTS_DIR / "mobile" / f"{s}.png").is_file():
            missing.append(f"mobile:{s}.png")
    assert not missing, f"capture outputs missing: {missing}"


def test_registry_does_not_claim_spa_dual_product_for_redirects():
    """Docs must not describe bare /teams as a separate SPA product."""
    tour = GUIDED_TOUR.read_text()
    # Honest redirect language expected.
    assert "redirect" in tour.lower()
    assert "/teams/launch/" in tour
    # Old dual-product phrasing should be gone.
    assert "Team management, wired to the JSON Teams API" not in tour
    assert "API-token form, read-only server settings by category" not in tour


def test_userguide_points_to_visual_tour_and_django_operator_truth():
    ug = (REPO / "USERGUIDE.md").read_text()
    assert "GUIDED_TOUR.md" in ug
    assert "SCREENSHOTS.md" in ug
    assert "Django" in ug
    assert "redirect" in ug.lower() or "trailing-slash" in ug or "trailing slash" in ug


def test_capture_script_parks_django_and_spa_mobile_bottom_navs():
    """Full-page stitch must not leave fixed SPA/Django bars painting over content."""
    src = CAPTURE_SCRIPT.read_text()
    assert ".os-bottom-nav" in src
    assert "fixed.bottom-0" in src or "bottom-0" in src
    assert "position = 'static'" in src or 'position = "static"' in src or "position='static'" in src
    # Desktop lg:hidden docks must stay hidden — only park visible bars.
    assert "getComputedStyle" in src
    assert 'display === \'none\'' in src or 'display === "none"' in src
    assert 'aria-label="Mobile primary"' in src or "Mobile primary" in src


def test_docs_admit_parked_mobile_dock_artifact():
    """Tour/registry must not imply mobile PNGs show a live viewport-fixed dock."""
    shots = SCREENSHOTS_MD.read_text().lower()
    tour = GUIDED_TOUR.read_text().lower()
    assert "parked-dock" in shots or "parked dock" in shots
    assert "position:static" in shots or "position: static" in shots
    assert "after scrolled" in shots or "end of the png" in shots
    assert "parked-dock" in tour or "parked" in tour
    assert "viewport-fixed" in tour or "viewport fixed" in tour


def test_capture_script_injects_redirect_banner_for_spa_stems():
    """spa-* redirect captures must be distinct from canonical pages (banner)."""
    src = CAPTURE_SCRIPT.read_text()
    assert "os-capture-redirect-banner" in src
    assert "Redirected:" in src
    assert "urlparse" in src
    assert "SPA_REDIRECT_STEMS" in src
    assert "banner_injected" in src
    # Insert above sticky Django header so full-page PNGs show the banner.
    assert "document.body.insertBefore" in src


def _capture_pages_rows() -> list[tuple[str, str]]:
    """Return (stem, path_prefix) for each PAGES row (path may be f-string prefix)."""
    src = CAPTURE_SCRIPT.read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "PAGES":
                    rows: list[tuple[str, str]] = []
                    for elt in node.value.elts:  # type: ignore[union-attr]
                        stem = _ast_str(elt.elts[0])
                        path = _ast_str(elt.elts[1])
                        if stem is None or path is None:
                            raise AssertionError(f"bad PAGES row: {ast.dump(elt)}")
                        rows.append((stem, path))
                    return rows
    raise AssertionError("PAGES list not found")


def test_capture_pages_spa_only_root_and_chat():
    """ADR-001: real SPA destinations are only `/` and `/chat`; other spa-* are redirects."""
    rows = _capture_pages_rows()
    by_stem = dict(rows)
    assert by_stem.get("landing") == "/"
    assert by_stem.get("spa-chat") == "/chat"
    # Deleted SPA operator pages must not be remounted as capture targets.
    for banned in ("spa-builder", "builder", "spa-agent-creator-page"):
        assert banned not in by_stem
    redirect_stems = {
        "spa-teams": "/teams",
        "spa-blueprints": "/blueprints",
        "spa-settings": "/settings",
        "spa-agent-creator": "/agent-creator",
    }
    for stem, path in redirect_stems.items():
        assert by_stem.get(stem) == path, f"{stem} must capture bare redirect entry {path}"
    # No other spa-* stems beyond chat + redirect documentation.
    spa_stems = [s for s, _ in rows if s.startswith("spa-")]
    assert set(spa_stems) == {"spa-chat", *redirect_stems}


def test_capture_script_waits_for_connected_or_unavailable():
    """spa-chat must wait for a terminal WS state (not Connecting…)."""
    src = CAPTURE_SCRIPT.read_text()
    assert 'aria-label="Chat message"' in src
    assert "Websocket not connected" in src
    assert "SPA_CHAT_STATUS_TIMEOUT_MS" in src
    assert "20_000" in src or "20000" in src
    assert "connection_status" in src
    # Hard-fail Connecting… unless --allow-connecting (docs must not claim ready).
    assert "_spa_chat_status_is_terminal" in src
    assert "--allow-connecting" in src
    assert "allow_connecting" in src
    assert "spa-chat not terminal" in src


def test_capture_script_seeds_session_detail_after_sessions_list():
    """Empty sessions.png then seed resp_journey_seed before session-detail."""
    src = CAPTURE_SCRIPT.read_text()
    assert "seed_session_detail_fixture" in src
    assert "resp_journey_seed" in src
    assert "sessions_captured" in src
    stems = _capture_script_stems()
    assert stems.index("sessions") < stems.index("session-detail")
    assert "SESSION_DETAIL_ID" in src
    assert "SWARM_RESPONSES_DIR" in src
    # Isolated XDG user data so My Blueprints ignores host custom agents.
    assert "SWARM_USER_DATA_DIR" in src
    assert "reset_capture_user_data_dir" in src


def test_capture_script_requires_frontend_dist():
    """Without dist/, ADR-001 `/` + `/chat` cannot be captured honestly."""
    src = CAPTURE_SCRIPT.read_text()
    assert "require_frontend_dist" in src
    assert "webui/frontend/dist" in src or "FRONTEND_DIST_INDEX" in src


def test_user_journey_embeds_sessions_and_profiles_when_captured():
    """If PAGES captures exist on disk, USER_JOURNEY must embed them (not link-only)."""
    text = USER_JOURNEY.read_text()
    embeds = _png_embeds(text)
    for stem in ("sessions", "session-detail", "profiles"):
        if (SCREENSHOTS_DIR / f"{stem}.png").is_file():
            assert f"{stem}.png" in embeds, (
                f"USER_JOURNEY.md must embed screenshots/{stem}.png when the "
                "capture exists (do not leave a GUIDED_TOUR-only pointer)"
            )


def test_guided_tour_embeds_session_detail_when_captured():
    """GUIDED_TOUR must embed session-detail.png when the journey capture exists."""
    if not (SCREENSHOTS_DIR / "session-detail.png").is_file():
        pytest.skip("session-detail.png not captured yet")
    text = GUIDED_TOUR.read_text()
    embeds = _png_embeds(text)
    assert "session-detail.png" in embeds, (
        "GUIDED_TOUR.md must embed screenshots/session-detail.png when captured"
    )


def test_session_detail_caption_is_seeded_fixture_not_live_run():
    """Tour captions must not claim session-detail.png is a live hybrid_team run."""
    for path in (GUIDED_TOUR, USER_JOURNEY):
        text = path.read_text().lower()
        # Require honest seeded-fixture language near the embed.
        assert "session-detail.png" in path.read_text()
        assert "seeded" in text
        assert "resp_journey_seed" in path.read_text()
        # Must not claim the PNG is evidence of a live multi-model / hybrid_team run.
        for banned in (
            "live hybrid_team run",
            "from a live hybrid_team",
            "live post /v1/responses run",
        ):
            assert banned not in text, f"{path.name} must not claim: {banned!r}"


def test_user_journey_launcher_caption_matches_fs_introspect_default():
    """teams-launch capture defaults to first option fs_introspect (not hybrid_team)."""
    for path in (USER_JOURNEY, GUIDED_TOUR, SCREENSHOTS_MD):
        text = path.read_text()
        # Near the launcher capture, docs must name the selected blueprint honestly.
        assert "**`fs_introspect`** selected" in text or "`fs_introspect`** selected" in text
        # Must not claim a different blueprint is pre-selected in the PNG.
        assert "django_chat` is pre-selected" not in text
        assert "django_chat is pre-selected" not in text
        assert "**`hybrid_team`** selected (first" not in text
        assert "**`hybrid_team`** selected (first bundled" not in text
        assert "hybrid_team` selected (first" not in text
        # teams-launch.png itself is not the seeded hybrid_team session fixture.
        assert "teams-launch.png` shows hybrid_team" not in text
        assert "teams-launch.png shows **`hybrid_team`**" not in text


def test_tour_docs_bridge_cli_list_vs_library_vs_landing_counts():
    """Captions must not equate swarm-cli list dirs with library/SPA totals."""
    journey = USER_JOURNEY.read_text()
    guided = GUIDED_TOUR.read_text()
    registry = SCREENSHOTS_MD.read_text()

    # Stale deleted husks must not appear in the journey CLI list transcript.
    for banned in ("family_ties", "whinge_surf", "digitalbutlers", "flock"):
        assert f"- {banned} " not in journey and f"- {banned} (" not in journey, (
            f"USER_JOURNEY.md swarm-cli list must not list deleted husk {banned!r}"
        )

    # PNG-honest regen numbers stay named.
    assert "12 of 49" in journey and "12 of 49" in guided
    assert "12 of 49" in registry or "**12 of 49**" in registry

    # Explicit bridge: CLI dirs ≠ library discovery (landing is no longer a count dashboard).
    for path, text in (
        (USER_JOURNEY, journey),
        (GUIDED_TOUR, guided),
        (SCREENSHOTS_MD, registry),
    ):
        flat = " ".join(text.split())
        assert "31" in flat and "49" in flat, (
            f"{path.name} must mention CLI 31 / library 49 count bridge"
        )
        assert "os-cli list" in flat or "`os-cli list`" in text or "swarm-cli list" in flat


def test_settings_caption_matches_empty_meter_not_populated_local_config():
    """settings.png meter is 40 of 47 / 85% (defaults), not the old empty 0 of 0."""
    banned = (
        "Values shown are this dev machine's local configuration",
        "Values shown are this machine's local configuration",
    )
    for path in (USER_JOURNEY, GUIDED_TOUR, SCREENSHOTS_MD):
        text = path.read_text()
        for phrase in banned:
            assert phrase not in text, f"{path.name} must not claim: {phrase!r}"
        assert "40 of 47" in text, f"{path.name} must name the 40 of 47 Settings meter"
        assert "0 of 0" in text, f"{path.name} must still name the old empty fixture as not this PNG"
        assert "settings.png" in text


def test_session_detail_remains_seeded_hybrid_team_distinct_from_launcher():
    """session-detail may be hybrid_team-shaped seed; teams-launch is fs_introspect."""
    for path in (USER_JOURNEY, GUIDED_TOUR, SCREENSHOTS_MD):
        text = path.read_text()
        assert "resp_journey_seed" in text
        assert "hybrid_team" in text
        assert "seeded" in text.lower()
        # Launcher default and session seed must stay distinct in captions.
        assert "**`fs_introspect`** selected" in text or "`fs_introspect`** selected" in text
        # Must not say the launcher PNG is the hybrid_team seed.
        assert not re.search(
            r"(?i)teams-launch\.png[^\n]{0,80}hybrid_team[^\n]{0,40}selected",
            text,
        ), f"{path.name}: teams-launch must not claim hybrid_team selected"


def test_user_journey_screenshot_date_is_current_regeneration():
    text = USER_JOURNEY.read_text()
    assert "2026-09-16" in text
    assert "2026-06-11 with a fresh development database" not in text
    assert "2026-07-21" not in text


def test_tour_captions_claim_sticky_banner_in_checked_in_spa_pngs():
    """Checked-in spa-*.png include the capture-injected Redirected banner."""
    for path in (GUIDED_TOUR, SCREENSHOTS_MD):
        text = path.read_text()
        assert "Redirected:" in text or "“Redirected:" in text or '"Redirected:' in text
        # Must not claim the banner is missing from on-disk PNGs.
        assert "banner on regeneration" not in text
        assert "regenerate to inject" not in text.lower()


def test_spa_app_mobile_dock_omits_settings_tab():
    """SPA product chrome is left rail + chat; Settings is the gear sheet, not a nav eject."""
    app = (REPO / "webui" / "frontend" / "src" / "App.tsx").read_text()
    chat = (
        (REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx").read_text()
        # #856 slice J: the settings affordance mounts from ChatHeader.
        + (REPO / "webui" / "frontend" / "src" / "features" / "chat" / "ChatHeader.tsx").read_text()
    )
    assert 'MobileTab href="/settings/"' not in app
    assert 'NavLink to="/"' not in app
    assert "MobileTab" not in app
    assert 'href="/settings/"' not in app
    assert "Open settings" in chat
    sheet = (
        (REPO / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx").read_text()
        + (
            REPO
            / "webui"
            / "frontend"
            / "src"
            / "components"
            / "settings"
            / "panes"
            / "RemotesCatalogPane.tsx"
        ).read_text()
    )
    assert "modal-end" in sheet or 'placement="end"' in sheet
    # REQ-59: Remotes is an opt-in catalog, not a menu-dropdown of unused kinds.
    assert "Add remote" in sheet
    assert "menu-dropdown" not in sheet


def test_feature_status_mobile_dock_omits_settings():
    """FEATURE_STATUS must describe Grok rail + sheet Settings, not a catalog dock."""
    text = (REPO / "FEATURE_STATUS.md").read_text()
    # Stale claim paired Settings into the five-tab dock list.
    assert "mobile dock Home·Chat + Django hrefs (Blueprints·Teams·Sessions·Settings)" not in text
    assert "no mobile five-tab dock" in text
    assert "Settings is desktop top-nav" not in text


def test_auth_summary_csp_has_no_style_residual():
    """AUTH.md overview must match prod CSP (no style-src unsafe-inline)."""
    text = (REPO / "docs" / "AUTH.md").read_text()
    assert "style residual" not in text
    assert "style-src self; no unsafe-inline" in text or (
        "script-src/style-src self" in text and "no unsafe-inline" in text
    )


def test_every_non_archive_png_listed_in_registry():
    """Every PNG under docs/screenshots/ (except archive/) must appear in SCREENSHOTS.md."""
    registry = SCREENSHOTS_MD.read_text()
    missing = []
    for path in _non_archive_screenshot_pngs():
        rel = _registry_rel(path)
        # Accept `skills/foo.png`, `webui/foo.png`, `mobile/foo.png`, or bare basename.
        if rel not in registry and path.name not in registry:
            missing.append(rel)
    assert not missing, f"PNGs missing from SCREENSHOTS.md registry: {missing}"


def test_skills_glob_not_a_substitute_for_per_file_rows():
    """Do not lump skills stills as skills/* — each file needs its own Used-in row."""
    registry = SCREENSHOTS_MD.read_text()
    assert "`docs/screenshots/skills/*`" not in registry
    assert "`skills/*`" not in registry
    for path in sorted((SCREENSHOTS_DIR / "skills").glob("*.png")):
        assert f"`skills/{path.name}`" in registry, f"missing skills row for {path.name}"


def test_webui_pngs_have_per_file_registry_rows():
    registry = SCREENSHOTS_MD.read_text()
    for path in sorted((SCREENSHOTS_DIR / "webui").glob("*.png")):
        assert f"`webui/{path.name}`" in registry, f"missing webui row for {path.name}"


def test_non_archive_pngs_embedded_or_marked_registry_only():
    """Orphans must be honest: embedded in docs, or Used-in none/registry-only."""
    registry = SCREENSHOTS_MD.read_text()
    embeds = _docs_png_embed_targets()
    dishonest = []
    for path in _non_archive_screenshot_pngs():
        rel = _registry_rel(path)
        if rel in embeds:
            continue
        # Find the registry table row that mentions this file.
        row = None
        for line in registry.splitlines():
            if f"`{rel}`" in line or (
                "/" not in rel and f"`{path.name}`" in line and line.strip().startswith("|")
            ):
                row = line
                break
        if row is None:
            dishonest.append(f"{rel}: no registry row")
            continue
        used_ok = any(m in row.lower() for m in ("none", "registry-only", "unused"))
        # Light twins / historical orphans are allowed; claiming a live Used-in without embed is not.
        if not used_ok:
            dishonest.append(f"{rel}: not embedded and Used-in is not registry-only/none ({row})")
    assert not dishonest, "registry honesty gaps:\n" + "\n".join(dishonest)


def test_skills_and_webui_doc_embeds_resolve_on_disk():
    """Captions in skills/webui docs must point at real files (no broken paths)."""
    embed_re = re.compile(r"!\[[^\]]*\]\(([^)]+\.png)\)")
    docs = [
        REPO / "docs" / "SKILLS_AND_CONSENSUS_WALKTHROUGH.md",
        REPO / "docs" / "examples" / "webui-config-panels.md",
        REPO / "docs" / "examples" / "inference-profile-routing.md",
        REPO / "docs" / "examples" / "tool-capabilities.md",
    ]
    missing = []
    for path in docs:
        text = path.read_text()
        for m in embed_re.finditer(text):
            rel = m.group(1)
            if rel.startswith("http"):
                continue
            target = (path.parent / rel).resolve()
            if not target.is_file():
                missing.append(f"{path.name}: {rel}")
    assert not missing, f"broken screenshot embeds: {missing}"


def test_guided_tour_embeds_mobile_spa_chat_when_captured():
    """High-value mobile spa-chat orphan must be embedded once the PNG exists."""
    if not (SCREENSHOTS_DIR / "mobile" / "spa-chat.png").is_file():
        pytest.skip("mobile/spa-chat.png not captured yet")
    text = GUIDED_TOUR.read_text()
    assert "mobile/spa-chat.png" in text, (
        "GUIDED_TOUR.md must embed screenshots/mobile/spa-chat.png when captured"
    )


def test_blueprint_library_caption_matches_ready_mcp_badges():
    """blueprint-library.png shows ready MCP checkmarks, not a checking spinner."""
    banned = (
        "still shows the checking spinner",
        "checking spinner labeled **MCP** on each card)",
        "MCP badges (checking spinner)",
    )
    for path in (GUIDED_TOUR, USER_JOURNEY, SCREENSHOTS_MD):
        text = path.read_text()
        for phrase in banned:
            assert phrase not in text, f"{path.name} must not claim: {phrase!r}"
        assert "ready green checkmarks" in text or "MCP badges (ready green checkmarks)" in text, (
            f"{path.name} must name ready MCP checkmarks on the library PNG"
        )


def test_my_blueprints_caption_matches_three_custom_agents():
    """my-blueprints.png shows Custom Created 20 (Lib Agent / First Team), not empty CTAs."""
    banned = (
        "empty on a fresh library",
        "empty personal library",
        "Empty-state CTAs",
        "nothing added to the library yet",
        "often empty on fresh db",
    )
    for path in (GUIDED_TOUR, USER_JOURNEY, SCREENSHOTS_MD):
        text = path.read_text()
        for phrase in banned:
            assert phrase not in text, f"{path.name} must not claim: {phrase!r}"
        assert "First Team" in text or "Lib Agent" in text, (
            f"{path.name} must name custom cards in my-blueprints.png"
        )
        assert "Custom Created" in text and "**20**" in text, (
            f"{path.name} must name Custom Created **20**"
        )


def test_agent_creator_caption_names_identity_progressive_disclosure():
    """agent-creator.png shows 1 Identity open; optional Persona/Tags collapsed."""
    for path in (GUIDED_TOUR, USER_JOURNEY, SCREENSHOTS_MD):
        text = path.read_text()
        assert "**1 Identity**" in text, f"{path.name} must name **1 Identity**"
        assert "Generate Blueprint" in text, f"{path.name} must name Generate Blueprint"

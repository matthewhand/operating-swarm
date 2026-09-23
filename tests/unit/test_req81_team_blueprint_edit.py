from pathlib import Path


def test_team_editor_has_edit_blueprint_control():
    src = Path("webui/frontend/src/components/TeamEditor.tsx").read_text(encoding="utf-8")
    assert "Edit blueprint…" in src
    assert "section: 'blueprint'" in src
    assert "OPEN_TEAM_COMPOSER_EVENT" not in src
    assert "os-team-editor" in src


def test_rail_edit_profile_opens_team_editor_not_drop_zone():
    src = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (
            Path("webui/frontend/src/components/AgentSidebar.tsx"),
            # #856 slices 14/J: row edit ops live in the useRailRowOps hook.
            Path("webui/frontend/src/features/sidebar/useRailRowOps.ts"),
        )
    )
    assert "openTeamEditor" in src
    assert "declaredRosterForTeam" in src


def test_persona_parse_is_ast_only():
    src = Path("src/swarm/core/persona_parse.py").read_text(encoding="utf-8")
    assert "ast.parse" in src
    assert "exec(" not in src
    assert "eval(" not in src
    assert "compile(" not in src

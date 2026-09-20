"""REQ-107 chrome contracts: optional CoS picker + team-scoped brief."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSER = REPO / "webui" / "frontend" / "src" / "components" / "TeamComposer.tsx"
TEAM_ROSTER = REPO / "webui" / "frontend" / "src" / "lib" / "teamRoster.ts"
APP = REPO / "webui" / "frontend" / "src" / "App.tsx"
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
PKG = REPO / "webui" / "frontend" / "package.json"
COS = REPO / "src" / "swarm" / "core" / "team_cos.py"
TEAM_ROSTER_LIB = REPO / "webui" / "frontend" / "src" / "lib" / "teamRoster.ts"


def test_designer_has_optional_cos_control_and_instructions():
    src = COMPOSER.read_text(encoding="utf-8")
    starter = TEAM_ROSTER_LIB.read_text(encoding="utf-8")
    assert 'aria-label="Chief of Staff"' in src
    assert "No Chief of Staff" in src
    assert "COS_EMPTY_ROSTER_HINT" in src
    assert "team-cos-instructions" in src
    assert "How to use this team" in src
    assert "COS_INSTRUCTIONS_HELPER" in src
    # The starter brief is the honest instruction set (lib/teamRoster.ts);
    # an earlier "Do not auto-assign" copy was folded into it.
    assert "Do not duplicate work" in starter
    helpers = TEAM_ROSTER.read_text(encoding="utf-8")
    assert "same agent can sit on multiple teams" in helpers


def test_chat_stays_mounted_under_team_composer():
    app = APP.read_text(encoding="utf-8")
    rail = SIDEBAR.read_text(encoding="utf-8")
    assert "import TeamComposer" in app
    assert "<TeamComposer" in app
    assert "OPEN_TEAM_COMPOSER_EVENT" in app
    # #182/#907: the Compose-team dispatch lives in the rail footer button.
    assert "OPEN_TEAM_COMPOSER_EVENT" in rail
    assert "os-teams-button" in rail
    # Overlay, never a route that unmounts Chat. (/teams/* is the deep-link
    # redirect into chat, not a composer route.)
    assert 'element={<TeamComposer' not in app


def test_daisyui5_react18_lock():
    pkg = json.loads(PKG.read_text(encoding="utf-8"))
    assert pkg["dependencies"]["react"].startswith("^18")
    assert pkg["dependencies"]["daisyui"].startswith("^5")


def test_runtime_brief_is_team_scoped_not_global():
    src = COS.read_text(encoding="utf-8")
    assert "team-scoped" in src.lower() or "team_scoped" in src or "Team-scoped" in src
    assert "COS_ELIGIBLE_KINDS" in src
    assert '"api"' in src and '"cli"' in src
    assert "remote" in src
    assert "developer" in src
    assert "Do not invent a CoS" in src or "Never invents a CoS" in src


def test_frontend_helpers_omit_ineligible_kinds():
    src = TEAM_ROSTER.read_text(encoding="utf-8")
    assert "COS_ELIGIBLE_KINDS" in src
    assert "COS_REMOTE_REASON" in src
    assert "DEFAULT_COS_STARTER" in src
    assert "runtimeBriefForTarget" in src
    assert "restoreCosId" in src

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
    """The composer exposes the optional CoS picker and the brief it writes.

    Read as the *structure* of the surfaces, not as prose. The previous form
    asserted the literal ``"How to use this rig"`` inside ``TeamComposer.tsx``;
    #1362 relabelled that field to "How to use this group chat" (it is a group
    chat, not a rig) and the test went red on correct copy, with the control
    fully intact.

    What the old assertion could not catch: a CoS control that had been deleted
    outright would still leave ``COS_INSTRUCTIONS_HELPER`` imported and
    ``team-cos-instructions`` in the file, so only the one drifted string
    distinguished "present" from "renamed".

    The *behaviour* -- that the picker is optional, that selecting a CoS
    enables the brief, that it seeds from the starter and saves what was typed
    -- is asserted by rendering in
    ``webui/frontend/src/components/__tests__/TeamComposer.test.tsx``
    ("selects a CoS, saves team-scoped instructions, and can clear CoS",
    "omits remotes from the CoS picker").
    """
    composer = COMPOSER.read_text(encoding="utf-8")
    lib = TEAM_ROSTER_LIB.read_text(encoding="utf-8")

    # The control: a labelled, addressable brief field on the composer.
    assert 'data-testid="team-cos-instructions"' in composer, (
        "the CoS brief field is gone from the composer"
    )
    assert 'aria-label="Chief of Staff instructions"' in composer
    # Its hint text comes from the lib, not from a copy in the component.
    assert "COS_INSTRUCTIONS_HELPER" in composer
    # The empty-roster and sentinel copy the #979 retune introduced.
    assert "COS_EMPTY_ROSTER_HINT" in composer
    assert "NO_COS_VALUE" in lib and "FIRST_AGENT_VALUE" in lib

    # The starter brief is the honest instruction set, and it still says the
    # one thing a CoS must not do.
    assert "Do not duplicate work" in lib
    assert "The same agent can sit on multiple rigs" in lib


def test_chat_stays_mounted_under_team_composer():
    """The composer is an overlay: it must not unmount Chat.

    #1676 made the composer ``lazy()``, so the previous ``"import TeamComposer"
    in app`` needle rotted on a correct code-split. The property being pinned
    is the *mount shape*, not the import spelling: the composer is rendered as
    an element (overlay) and never as a route ``element={...}``, which is what
    would unmount Chat.
    """
    app = APP.read_text(encoding="utf-8")
    rail = SIDEBAR.read_text(encoding="utf-8")

    # Loaded by any mechanism, mounted as an element.
    assert "TeamComposer" in app, "App no longer mounts the team composer at all"
    assert "<TeamComposer" in app
    # Overlay, never a route that unmounts Chat. (/teams/* is the deep-link
    # redirect into chat, not a composer route.)
    assert 'element={<TeamComposer' not in app
    # #182/#907: the Compose-team dispatch lives in the rail footer button.
    assert "OPEN_TEAM_COMPOSER_EVENT" in app
    assert "OPEN_TEAM_COMPOSER_EVENT" in rail
    assert "os-teams-button" in rail


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

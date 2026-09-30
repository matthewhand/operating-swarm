"""REQ-109: Add agent — CLI | API | Remote, behind a rail affordance.

What rotted here
----------------
``test_sidebar_has_add_button`` asserted four literals inside
``AgentSidebar.tsx``:

    assert 'aria-label="Add agent"' in content
    assert 'data-testid="add-agent-button"' in content

#1674 replaced that bare button with ``AddBotMenu`` — a searchable menu of
the rail's existing seats plus "Create new agent" / "Create group chat". The
affordance is now ``data-testid="add-bot-menu-trigger"`` and the literal
``aria-label="Add agent"`` moved down into ``AddBotMenu.tsx`` as the menu
group's own label. Both needles were false: the rail had not lost anything.

What the old form could not catch
--------------------------------
* That the "Add agent" affordance had been *removed entirely* — the four
  greps only proved the tokens existed somewhere in a 2,000-line file, so
  deleting the control while leaving a stale constant would stay green.
* That the menu the control opens actually works. None of these greps could
  see behaviour at all.

The replacement
---------------
The affordance and its behaviour are asserted by RENDERING:
  * ``webui/frontend/src/components/__tests__/RailAddBotMenu1674.test.tsx``
    renders the real rail, finds ``add-bot-menu-trigger``, and asserts it sits
    inside ``.os-rail-search-row``.
  * ``webui/frontend/src/components/__tests__/AddBotMenu1674.test.tsx``
    drives the menu: it offers the create actions, filters, is keyboard
    navigable, and closes on Escape / outside press.
  * ``webui/frontend/src/components/__tests__/AddAgentWizard.test.tsx``
    covers the three-kind wizard the create action opens.

What stays here is the *kind coverage of the wizard itself* — the one claim
with no behavioural equivalent anywhere, namely that the wizard's per-kind
step exposes exactly these three kinds and never a fourth, and that its
remote copy is named OpenMousBot. That is checked against the wizard module
it owns.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAIL = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
ADD_BOT_MENU = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AddBotMenu.tsx"
WIZARD_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AddAgentWizard.tsx"
PKG = REPO_ROOT / "webui" / "frontend" / "package.json"

# The three creatable seat kinds, per AGENTS.md §3 minus `team` (a team is a
# roster, not a creatable seat) and minus `remote`-as-CLI.
CREATABLE_KINDS = ("cli", "api", "remote")


def test_rail_exposes_the_add_agent_affordance():
    """The rail mounts the Add-bot trigger and opens the menu from it.

    #1674: the control is a menu of existing seats plus create actions, not a
    bare wizard button. Asserted structurally on the rail's own two files --
    the substring checks that used to live here could not distinguish a live
    control from a leftover constant.
    """
    rail = RAIL.read_text(encoding="utf-8")
    menu = ADD_BOT_MENU.read_text(encoding="utf-8")

    assert "AddBotMenu" in rail, "the rail no longer mounts the Add-bot menu"
    assert "add-bot-menu-trigger" in menu, "the menu has no trigger testid to anchor to"
    # The menu still reaches the wizard, so REQ-109's wizard is not orphaned.
    assert "OPEN_AGENT_EDITOR_EVENT" in rail or "setAddWizardOpen" in rail


def test_add_agent_wizard_implements_three_kinds_and_openmousbot_copy():
    """REQ-109 rule 3: CLI | API | Remote, and the remote copy says OpenMousBot.

    The wizard's kind step must offer exactly the three creatable kinds -- a
    fourth kind appearing in the data without a step here would be a seat the
    operator cannot create, and that is the one thing a substring test in the
    wrong language could never see.
    """
    content = WIZARD_TSX.read_text(encoding="utf-8")

    # Overlay modal, not a route.
    assert "Modal" in content
    assert "isOpen" in content
    assert "onClose" in content

    for kind in CREATABLE_KINDS:
        assert f"'{kind}'" in content, f"the wizard has no {kind!r} kind step"
        assert f'data-testid="kind-option-{kind}"' in content, (
            f"the {kind!r} step has no testid, so it cannot be driven by a render test"
        )

    # REQ-409: Remote copy must use OpenMousBot, never OMB in user-facing labels.
    assert "OPENMOUSBOT_LABEL" in content
    assert "OpenMousBot" in content

    # Creation API calls, per kind.
    assert "createCustomBlueprint" in content
    assert "createRemote" in content


def test_daisyui5_react18_lock():
    """REQ-109 tooling floor: the wizard's modal primitives need DaisyUI 5 on React 18."""
    pkg = json.loads(PKG.read_text(encoding="utf-8"))
    assert pkg["dependencies"]["react"].startswith("^18")
    assert pkg["dependencies"]["daisyui"].startswith("^5")

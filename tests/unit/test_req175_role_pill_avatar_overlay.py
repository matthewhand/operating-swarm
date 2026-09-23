"""REQ-175: Role badges/pills overlay the rail avatar (not beside name or on second row)."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"

# #856 slice G: the row markup moved verbatim into sidebar/rowsRender.tsx;
# these pins read the union so the doctrine spans both homes.
_ROWS_RENDER = SIDEBAR_TSX.parent / "sidebar" / "rowsRender.tsx"


def _sidebar_text():
    return "\n".join(x.read_text(encoding="utf-8") for x in (SIDEBAR_TSX, _ROWS_RENDER))




def test_sidebar_role_badge_overlays_avatar():
    content = _sidebar_text()

    # REQ-175 contract. Updated twice by later deliberate redesigns: the Sep-2026
    # UI parity sweep moved the agent role badge OFF the avatar overlay onto the
    # name row's timestamp slot (behavioral spec: AgentRolePillOverlay.test.tsx);
    # #849 then aligned the Team/Remote pills right in that same slot too. No
    # avatar-overlay badges remain in the sidebar.
    assert 'data-avatar-overlay="true"' not in content
    assert "roleBadgeNode" in content
    assert 'data-avatar-overlay="true"' not in "".join(
        line for line in content.splitlines() if "roleBadgeNode" in line or "roleCssClass(role)" in line
    )

    # REQ-67 contract: badge className carries roleCssClass (shrink-0 for the
    # name-row pill). #500 moved the slot render into RailRowSlot: the badge
    # is passed as a prop alongside the timestamp (no inline ternary anymore).
    assert re.search(
        r"className=\{`os-agent-role-badge shrink-0 \$\{roleCssClass\(role\)\}`\}",
        content,
    )
    assert re.search(r"badge=\{roleBadgeNode\}", content)


def test_second_row_does_not_contain_role_badge_chip():
    content = _sidebar_text()

    # In single agent row, second row has snippet and optional taskCount, but NOT badge ? <span ...>
    # #446 lets that snippet slot show the awaiting-approval label instead, so the
    # pinned shape is the conditional, not the bare snippet expression.
    agent_second_row = re.search(
        r'\{needsApproval \? NEEDS_APPROVAL_LABEL : snippet \|\| agent\.description\}'
        r'\s*</span>\s*\{taskCount > 1',
        content,
    )
    assert agent_second_row is not None, "Second row should not reserve role badge chip beside snippet"

    # In team row, second row only has team snippet
    team_second_row = re.search(
        r'\{teamNeedsApproval\s*\?\s*NEEDS_APPROVAL_LABEL\s*:\s*teamSnippet \|\| team\.description\}'
        r'\s*</span>\s*</span>\s*</span>\s*</Link>',
        content,
    )
    assert team_second_row is not None, "Team second row should not contain Team badge"

    # In remote row, second row only has remote snippet
    remote_second_row = re.search(
        r'\{remoteNeedsApproval\s*\?\s*NEEDS_APPROVAL_LABEL\s*:\s*remoteSnippet'
        r" \|\| \(remote as any\)\.description \|\| 'Remote team'\}"
        r'\s*</span>\s*</span>\s*</span>\s*</Link>',
        content,
    )
    assert remote_second_row is not None, "Remote second row should not contain Remote badge"

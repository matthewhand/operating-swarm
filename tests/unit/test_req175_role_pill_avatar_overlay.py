"""REQ-175: Role badges/pills overlay the rail avatar (not beside name or on second row)."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"


def test_sidebar_role_badge_overlays_avatar():
    content = SIDEBAR_TSX.read_text(encoding="utf-8")

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
    # name-row pill) and the badge competes with unread/timestamp, not the avatar.
    assert re.search(
        r"className=\{`os-agent-role-badge shrink-0 \$\{roleCssClass\(role\)\}`\}",
        content,
    )
    assert re.search(
        r"roleBadgeNode\s*\)\s*:\s*timestampLabel", content
    ) or re.search(r"\) : roleBadgeNode \? \(\s*roleBadgeNode\s*\) : timestampLabel", content)


def test_second_row_does_not_contain_role_badge_chip():
    content = SIDEBAR_TSX.read_text(encoding="utf-8")

    # In single agent row, second row has snippet and optional taskCount, but NOT badge ? <span ...>
    agent_second_row = re.search(
        r'\{snippet \|\| agent\.description\}\s*</span>\s*\{taskCount > 1',
        content,
    )
    assert agent_second_row is not None, "Second row should not reserve role badge chip beside snippet"

    # In team row, second row only has team snippet
    team_second_row = re.search(
        r'\{teamSnippet \|\| team\.description\}\s*</span>\s*</span>\s*</span>\s*</Link>',
        content,
    )
    assert team_second_row is not None, "Team second row should not contain Team badge"

    # In remote row, second row only has remote snippet
    remote_second_row = re.search(
        r'\{remoteSnippet \|\| \(remote as any\)\.description \|\| \'Remote team\'\}\s*</span>\s*</span>\s*</span>\s*</Link>',
        content,
    )
    assert remote_second_row is not None, "Remote second row should not contain Remote badge"

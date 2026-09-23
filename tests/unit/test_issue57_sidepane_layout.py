"""#57: revised sidepane layout — role pill, team stack, hover-only hints."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
AVATAR_STACK = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "avatarStack.ts"
SIDEBAR = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
SUMMARY_CARD = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "CompactSummaryCard.tsx"
CONCEAL = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SidepaneConceal.tsx"


def test_role_badge_sits_on_the_name_row_not_bottom_centered():
    # #856 slice G: the row markup moved verbatim into sidebar/rowsRender.tsx.
    sidebar = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (SIDEBAR, SIDEBAR.parent / "sidebar" / "rowsRender.tsx")
    )
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert "os-agent-row__label-col" in sidebar
    assert "roleBadgeNode" in sidebar
    assert "justify-between" in sidebar
    # List-row badges are in the name-row right slot, not avatar overlay.
    assert "data-avatar-overlay" not in sidebar
    # Absolute centering is the fav-tile badge, not `.os-agent-role-badge` itself.
    badge_rule = css.split(".os-agent-role-badge {", 1)[1].split("}", 1)[0]
    assert "left:" not in badge_rule
    assert "translateX(-50%)" not in badge_rule


def test_team_stack_shows_all_up_to_three_then_two_plus_n():
    """REQ-891 (#485) redesigned the team sidepane stack: at most
    STACK_FACE_LIMIT (3) faces, no +N chip, recency-ordered while any member
    works, stable roster order when idle. The old "all ≤3 then 2 + N" rule
    survives only in the rail constants (TEAM_STACK_*), kept for #398."""
    src = AVATAR_STACK.read_text(encoding="utf-8")
    assert "TEAM_STACK_ALL_MAX = 3" in src
    assert "TEAM_STACK_FACE_LIMIT = 2" in src
    assert "export function teamSidepaneStack" in src
    assert "faces: ordered.slice(0, STACK_FACE_LIMIT)" in src
    assert "remainder: 0" in src
    assert "b.startedAt - a.startedAt" in src


def test_alt_n_and_ctrl_k_hints_are_hover_only():
    css = INDEX_CSS.read_text(encoding="utf-8")
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert ".os-fav-tile:hover .os-fav-tile__shortcut" in css
    assert ".os-fav-tile:focus-within .os-fav-tile__shortcut" not in css
    # #500 moved the hover/row swap out of the sidebar (RailRowSlot owns the
    # slot now; the Alt-swap class was retired outright).
    assert "group-hover/row" not in sidebar
    assert "event.currentTarget.blur()" in sidebar
    assert ".os-rail-search:hover .os-rail-search__kbd" in css
    assert ".os-rail-search:focus-within .os-rail-search__kbd" not in css


def test_summary_cards_offer_the_same_edit_controls_as_chat_bubbles():
    src = SUMMARY_CARD.read_text(encoding="utf-8")
    assert "canEdit" in src
    assert "onSaveEdit" in src
    assert 'aria-label="Edit message"' in src
    assert "data-testid=\"summary-edit-button\"" in src


def test_conceal_buttons_from_issue_251_remain():
    conceal = CONCEAL.read_text(encoding="utf-8")
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert 'aria-label="Collapse sidebar"' in conceal
    assert 'aria-label="Conceal sidepane"' in conceal
    assert "SidebarConcealButton" in sidebar
    # #767 (PR #876): pane icons replaced the BrandMarkMono toggle.
    assert "PanelLeftClose" in conceal

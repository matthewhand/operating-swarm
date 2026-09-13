"""REQ-67: role chrome is the badge only — no row fill/border."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA_CSS = REPO / "webui" / "frontend" / "src" / "index.css"
DJANGO_CSS = REPO / "src" / "swarm" / "static" / "css" / "rest_mode_style.css"
SIDEBAR_JS = REPO / "src" / "swarm" / "static" / "js" / "agent_sidebar.js"
SIDEBAR_TSX = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"

ROLE_ROW_CLASS = re.compile(
    r"os-agent-row--(?:support|gate|skeptic|cos|chief_of_staff)|"
    r"os-agent-role-(?:support|gate|skeptic|chief_of_staff)"
)


def test_css_has_no_role_row_fill_or_border():
    for css in (SPA_CSS.read_text(encoding="utf-8"), DJANGO_CSS.read_text(encoding="utf-8")):
        assert ".os-agent-row--support" not in css
        assert ".os-agent-row--gate" not in css
        assert ".os-agent-row--skeptic" not in css
        assert ".os-agent-row--cos" not in css
        assert ".os-agent-row.os-agent-role-" not in css
        assert ".os-agent-item.os-agent-role-" not in css
        assert '.os-agent-item[data-role=' not in css
        assert ".os-agent-dot[data-role=" not in css
        assert ".os-agent-role-badge[data-role=\"support\"]" in css
        assert ".os-agent-role-badge[data-role=\"gate\"]" in css
        assert ".os-agent-role-badge[data-role=\"skeptic\"]" in css
        assert ".os-agent-role-badge[data-role=\"chief_of_staff\"]" in css
        assert ".os-agent-role-badge[data-role=\"suggestions\"]" in css
        assert ".os-agent-role-badge[data-role=\"engineer\"]" in css
        assert ".os-agent-row--engineer" not in css
        # Selected / hover / hidden / working stay — those are not role colours.
        assert ".os-agent-row:hover" in css or ".os-agent-item:hover" in css


def test_spa_rows_do_not_apply_role_fill_classes():
    tsx = SIDEBAR_TSX.read_text(encoding="utf-8")
    assert "os-agent-row--${role}" not in tsx
    assert "os-agent-row--cos" not in tsx
    assert "roleCssClass(role)" in tsx
    assert "os-agent-role-badge" in tsx
    # Badge still carries the role class (shrink-0 was added for the name-row
    # pill); the row className does not.
    badge = re.search(
        r"className=\{`os-agent-role-badge([^`]*)\$\{roleCssClass\(role\)\}`\}",
        tsx,
    )
    assert badge, "expected role badge className template with roleCssClass"
    assert badge.group(1).strip() == "shrink-0"
    row_class = re.search(r"const className = `os-agent-row[^`]+`", tsx)
    assert row_class, "expected agent row className template"
    assert not ROLE_ROW_CLASS.search(row_class.group(0))


def test_django_sidebar_does_not_stamp_role_class_on_the_row():
    js = SIDEBAR_JS.read_text(encoding="utf-8")
    assert 'link.className += " os-agent-role-"' not in js
    assert 'badge.className = "os-agent-role-badge"' in js
    assert 'badge.setAttribute("data-role", role)' in js
    assert 'dot.setAttribute("data-role"' not in js

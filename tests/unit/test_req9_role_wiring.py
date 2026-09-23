"""REQ-9 contracts: codegen wiring, sidepane class names, API role fields."""

from pathlib import Path

import pytest

from swarm.core.agent_roles import ROLE_CSS_CLASSES

REPO = Path(__file__).resolve().parents[2]
DJANGO_CSS = REPO / "src" / "swarm" / "static" / "css" / "rest_mode_style.css"
SPA_CSS = REPO / "webui" / "frontend" / "src" / "index.css"
SIDEBAR_JS = REPO / "src" / "swarm" / "static" / "js" / "agent_sidebar.js"
SIDEBAR_TS = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
SIDEBAR_TS_ROWS = SIDEBAR_TS.parent / "sidebar" / "RailSections.tsx"
TEAM_JS = REPO / "src" / "swarm" / "static" / "js" / "team_creator.js"


def _team(*, gate=False, skeptic=False):
    agents = [
        {"name": "Writer", "system_prompt": "You write files.", "role": "default"},
        {"name": "Editor", "system_prompt": "You edit.", "role": "default"},
    ]
    if gate:
        agents.append({
            "name": "ToolGate",
            "role": "gate",
            "system_prompt": "Classify tool calls.",
        })
    if skeptic:
        agents.append({
            "name": "Skeptic",
            "role": "skeptic",
            "system_prompt": "Review whether work landed.",
        })
    return {
        "name": "Role Team",
        "description": "REQ-9 wiring fixture",
        "coordinator_name": "Writer",
        "agents": agents,
    }


def test_team_codegen_source_wires_gate_and_skeptic():
    """Generated teams must call the fail-open gate + bounded skeptic helpers."""
    src = (REPO / "src" / "swarm" / "views" / "agent_creator_views.py").read_text(
        encoding="utf-8"
    )
    for needle in (
        "from swarm.core.agent_roles import",
        "from swarm.core.skeptic import",
        "from swarm.core.tool_gate import",
        "wrap_tools_with_gate",
        "run_with_skeptic",
        "attach_gate_as_tool",
        "attach_skeptic_as_tool",
        "attach_suggestions_as_tool",
        "find_role_agent(self._agents",
        "normalize_agent_role",
        '\\"role\\": \\"default\\"',
        "gate_agent",
        "skeptic_agent",
    ):
        assert needle in src, f"missing {needle!r} in team codegen"


def test_sidepane_css_class_names_exist_django_and_spa():
    django_css = DJANGO_CSS.read_text(encoding="utf-8")
    spa_css = SPA_CSS.read_text(encoding="utf-8")
    js = SIDEBAR_JS.read_text(encoding="utf-8")
    ts = "\n".join(x.read_text(encoding="utf-8") for x in (SIDEBAR_TS, SIDEBAR_TS_ROWS))
    team = TEAM_JS.read_text(encoding="utf-8")
    # REQ-67: role colour lives on .os-agent-role-badge[data-role=...], not row classes.
    assert "os-agent-role-badge" in django_css
    assert "os-agent-role-badge" in spa_css
    for role, css_class in ROLE_CSS_CLASSES.items():
        if role == "default":
            continue
        assert f'data-role="{role}"' in django_css
        assert f'data-role="{role}"' in spa_css
        assert css_class.startswith("os-agent-role-")
    assert "data-role" in js
    assert "os-agent-role-" in js
    assert "os-agent-role-" in ts
    assert "member-agent-role" in team
    assert 'value="gate"' in team
    assert 'value="skeptic"' in team
    assert 'value="support"' in team
    assert 'value="suggestions"' in team


def test_codegen_unwired_still_calls_wrap_but_gate_is_none():
    try:
        from swarm.views.agent_creator_views import _render_swarm_blueprint_code
    except Exception as exc:
        pytest.skip(f"django stack unavailable: {exc}")

    code = _render_swarm_blueprint_code(_team())
    assert "wrap_tools_with_gate" in code
    assert "run_with_skeptic" in code
    assert "find_role_agent(self._agents, \"gate\")" in code
    assert "find_role_agent(self._agents, \"skeptic\")" in code
    assert "'role': 'default'" in code or '"role": "default"' in code


def test_codegen_wires_gate_and_skeptic_roles():
    try:
        from swarm.views.agent_creator_views import _render_swarm_blueprint_code
    except Exception as exc:
        pytest.skip(f"django stack unavailable: {exc}")

    code = _render_swarm_blueprint_code(_team(gate=True, skeptic=True))
    assert "attach_gate_as_tool" in code
    assert "attach_skeptic_as_tool" in code
    assert "attach_suggestions_as_tool" in code
    # AGENT_SPECS is emitted via repr(), so keys/values are single-quoted.
    assert "'role': 'gate'" in code or '"role": "gate"' in code
    assert "'role': 'skeptic'" in code or '"role": "skeptic"' in code
    assert "gate_agent" in code
    assert "skeptic_agent" in code
    assert "submit_gate_verdict" in code or "attach_classifier_tools" in code
    assert "Classify" in code or "submit_gate_verdict" in code


def test_api_views_serialize_role_fields():
    src = (REPO / "src" / "swarm" / "views" / "api_views.py").read_text(encoding="utf-8")
    assert "from swarm.core.agent_roles import blueprint_role_fields" in src
    assert "**blueprint_role_fields(meta)" in src

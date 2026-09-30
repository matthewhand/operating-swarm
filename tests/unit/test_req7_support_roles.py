"""REQ-7: Support/gate/skeptic role looks + Support registration."""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIDEBAR_JS = REPO / "src" / "swarm" / "static" / "js" / "agent_sidebar.js"
SHELL_CSS = REPO / "src" / "swarm" / "static" / "css" / "rest_mode_style.css"
SPA_CSS = REPO / "webui" / "frontend" / "src" / "index.css"
SUPPORT_BP = REPO / "src" / "swarm" / "blueprints" / "support" / "blueprint_support.py"
GATE_BP = REPO / "src" / "swarm" / "blueprints" / "gate" / "blueprint_gate.py"
SKEPTIC_BP = REPO / "src" / "swarm" / "blueprints" / "skeptic" / "blueprint_skeptic.py"


def test_support_is_a_blueprint_with_role():
    text = SUPPORT_BP.read_text(encoding="utf-8")
    assert '"role": "support"' in text
    assert "as_tool" in text
    assert "grok" not in text.lower() or "Do not shell out to grok" in text


def _prose(path: Path) -> str:
    """Every string literal in a module, with implicit concatenation resolved.

    Reading the raw source does not work: these descriptions are written as
    wrapped, implicitly-concatenated literals, so the source text between two
    fragments is a quote and whitespace ("...this seat does " "not answer"),
    never the sentence a reader sees. ``ast`` gives the real string values.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return " ".join(
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    )


def _registered_role(path: Path) -> str | None:
    """The role a blueprint's metadata declares, read from the AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "role":
                return value.value if isinstance(value, ast.Constant) else None
    return None


def test_gate_and_skeptic_are_role_stubs():
    """Both register a role and neither pretends to have an engine.

    #1670: this used to substring-match prose ("Until wired, all approved",
    "findings go back to retry"). That is a rotted assertion twice over. Both
    blueprints were rewritten to return the shared honest refusal instead of
    their own instruction banner — so the gate phrase now only survives inside
    a docstring *describing the banner that was removed*, and the skeptic
    phrase was reworded out from under it. Matching prose asserted a changelog,
    not a contract.

    What actually has to hold is structural: the role is declared, the seat is
    built on the shared unavailable-seat helper, it refuses rather than faking
    an answer, and it says the engine does not exist.
    """
    for label, path, role, subject in (
        ("gate", GATE_BP, "gate", "approval classifier"),
        ("skeptic", SKEPTIC_BP, "skeptic", "skeptic retry loop"),
    ):
        text = path.read_text(encoding="utf-8")
        prose = _prose(path)
        assert _registered_role(path) == role, f"{label} must declare role={role}"
        assert "unavailable.placeholder_metadata()" in text, (
            f"{label} must be built on the shared unavailable-seat placeholder"
        )
        assert "cannot_answer_chunk" in text, (
            f"{label} must refuse honestly instead of inventing an answer"
        )
        assert "is not implemented" in prose, (
            f"{label} must state that its {subject} does not exist"
        )
        assert "does not answer" in prose, (
            f"{label} must say the seat does not answer"
        )


def test_django_sidebar_styles_roles_not_diamonds():
    js = SIDEBAR_JS.read_text(encoding="utf-8")
    css = SHELL_CSS.read_text(encoding="utf-8")
    assert "data-role" in js
    assert 'os-agent-item--"' in js or "os-agent-item--" in js
    assert 'role === "support"' in js
    assert 'role === "gate"' in js
    assert 'role === "skeptic"' in js
    assert "os-agent-item--support" in css
    assert "os-agent-item--gate" in css
    assert "os-agent-item--skeptic" in css
    assert "os-role-pill--support" in css


def test_spa_role_looks_are_distinct():
    """REQ-67: role colour lives on the badge; briefing chips live on the pill."""
    css = SPA_CSS.read_text(encoding="utf-8")
    assert ".os-agent-role-badge" in css
    assert ".os-code-python" in css
    pill = (REPO / "webui" / "frontend" / "src" / "components" / "SupportBriefingPill.tsx").read_text(
        encoding="utf-8"
    )
    assert "os-handoff-chip" in pill
    assert "os-handoff-chip--system" in pill

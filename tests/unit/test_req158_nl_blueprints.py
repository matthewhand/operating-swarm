"""REQ-158 / #567 — source-lock: NL create, hidden code, no :8001, no secrets."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "skills" / "support-session-ownership" / "SKILL.md"
BLUEPRINT = REPO / "src" / "swarm" / "blueprints" / "support" / "blueprint_support.py"
CORE = REPO / "src" / "swarm" / "core" / "support_nl_blueprint.py"
STARTER = REPO / "src" / "swarm" / "core" / "support_agent.py"
JOURNEY = REPO / "src" / "swarm" / "core" / "support_journey.py"
README = REPO / "README.md"
DOCS = REPO / "docs" / "SUPPORT_NL_BLUEPRINTS.md"
REQ = REPO / "docs" / "requirements" / "REQ-158.md"
FRONT_JOURNEY = REPO / "webui" / "frontend" / "src" / "lib" / "supportJourney.ts"
FRONT_CARD = REPO / "webui" / "frontend" / "src" / "lib" / "supportNlBlueprint.ts"
CI = REPO / ".github" / "workflows" / "req158-nl-blueprints.yml"


def _read(*paths: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_happy_path_and_under_the_hood_are_documented():
    readme = README.read_text(encoding="utf-8")
    docs = DOCS.read_text(encoding="utf-8")
    blob = f"{readme}\n{docs}"
    assert "under the hood" in blob.lower()
    assert "Python" in blob
    assert "ApiKindBase" in blob or "blueprint class" in blob.lower()
    assert "ask **Support**" in blob or "ask Support" in blob
    assert "View / edit code" in blob
    assert "Add as agent" in docs
    assert "Save as blueprint" in docs
    assert "Socratic" in docs or "socratic" in docs.lower()
    assert "Open in chat" not in docs
    # Guided path is GitHub-only; README may still mention the REQ-156 seed host.
    assert ":8001" not in docs
    assert "WAVE" not in docs
    assert "ghp_" not in docs
    assert "sk-" not in docs


def test_support_nl_create_does_not_require_user_python():
    blob = _read(SKILL, BLUEPRINT, CORE, STARTER)
    assert "SUPPORT_NL_BLUEPRINT_NO_USER_PYTHON" in blob
    assert "create_blueprint_from_nl" in blob
    lowered = blob.lower()
    assert "write python" in lowered
    assert "not" in lowered and "python" in lowered
    assert "View / edit code" in blob
    assert "ApiKindBase" in blob
    assert ":8001" not in blob


def test_kickstart_includes_handoff_example():
    journey = JOURNEY.read_text(encoding="utf-8")
    front = FRONT_JOURNEY.read_text(encoding="utf-8")
    assert "Create a BA → Engineer → Tester workflow" in journey
    assert "Create a BA → Engineer → Tester workflow" in front
    assert "View / edit code" in FRONT_CARD.read_text(encoding="utf-8")


def test_req_pointer_and_own_diff_ci():
    assert "github.com/matthewhand/open-swarm/issues/567" in REQ.read_text(encoding="utf-8")
    text = CI.read_text(encoding="utf-8")
    assert "REQ-158" in text or "req158" in text.lower()
    assert "pytest" in text
    assert "vitest" in text
    assert ":8001" not in text

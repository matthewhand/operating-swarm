"""REQ-137 / #530 — Support is the first-run journey onboarder.

Source-lock so we extend Support skill/instructions (no second bot), keep
#367 honesty, and never ship secrets or a live ``:8001`` host.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "skills" / "support-session-ownership" / "SKILL.md"
BLUEPRINT = REPO / "src" / "swarm" / "blueprints" / "support" / "blueprint_support.py"
STARTER = REPO / "src" / "swarm" / "core" / "support_agent.py"
JOURNEY = REPO / "src" / "swarm" / "core" / "support_journey.py"
SUGGESTIONS = REPO / "src" / "swarm" / "core" / "suggestions.py"
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
BRIEFING = REPO / "webui" / "frontend" / "src" / "lib" / "support-briefing.ts"
FRONT_JOURNEY = REPO / "webui" / "frontend" / "src" / "lib" / "supportJourney.ts"
CI = REPO / ".github" / "workflows" / "req137-support-onboard.yml"

JOURNEY_NEEDLES = (
    "create a team",
    "add a remote",
    "wire a CLI",
    "ONBOARD_JOURNEY_CLI_API_REMOTE",
)


def _read(*paths: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def test_support_skill_covers_the_journey_and_stays_honest():
    skill = SKILL.read_text(encoding="utf-8")
    for needle in JOURNEY_NEEDLES:
        assert needle.lower() in skill.lower() or needle in skill
    assert "SESSION_OWNERSHIP_API_CLI_REMOTE" in skill
    assert "Chief of Staff" in skill
    assert "Hermes" in skill
    assert "OpenMousBot" in skill
    assert "Herdr" in skill
    assert "one pane" in skill.lower()
    assert "click the bubble to edit" in skill.lower()
    assert ":8001" not in skill
    assert "WAVE" not in skill
    assert "ghp_" not in skill
    assert "sk-" not in skill


def test_both_support_instruction_sets_cover_the_journey():
    blob = _read(BLUEPRINT, STARTER)
    for needle in ("Create a team", "Add a remote", "Wire a CLI", "ONBOARD_JOURNEY_CLI_API_REMOTE"):
        assert needle in blob
    assert "ApiKindBase" in blob
    assert "CliKindBase" in blob
    assert "RemoteKindBase" in blob
    assert ":8001" not in blob
    assert "WAVE" not in blob


def test_kickstart_and_chat_empty_state_share_journey_chips():
    journey = JOURNEY.read_text(encoding="utf-8")
    suggestions = SUGGESTIONS.read_text(encoding="utf-8")
    chat = CHAT.read_text(encoding="utf-8")
    front = FRONT_JOURNEY.read_text(encoding="utf-8")
    briefing = BRIEFING.read_text(encoding="utf-8")
    assert "SUPPORT_KICKSTART_CANNED" in journey
    assert "is_support_consumer" in suggestions
    # Slice-20/#856: the kickstart chip wiring moved into useSlashLifecycle.
    assert "supportJourneyKickstart" in (
        REPO / "webui" / "frontend" / "src" / "features" / "chat" / "useSlashLifecycle.ts"
    ).read_text(encoding="utf-8")
    assert "Create a team" in front
    assert "Add a remote" in front
    assert "Wire a CLI" in front
    assert "Create a team" in briefing
    assert "no second bot" in journey.lower()
    assert ":8001" not in journey
    assert ":8001" not in front


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "REQ-137" in text or "req137" in text.lower()
    assert "pytest" in text
    assert "vitest" in text
    assert ":8001" not in text

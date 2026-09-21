"""REQ-137: first-run Support journey onboarder (no second bot).

Shared fixture + kickstart phrases so the Support skill, canned chips,
and Chat empty-state stay aligned. No secrets. GitHub-only — no live host.
"""

from __future__ import annotations

SUPPORT_JOURNEY_FIXTURE = "ONBOARD_JOURNEY_CLI_API_REMOTE"

SUPPORT_CONSUMER_IDS = frozenset({"support", "starter-support"})

#: Admin/bootstrap seat IDs (#893)
ADMIN_CONSUMER_IDS = frozenset({"admin", "starter-admin"})

# First-run chips — keep these short; they are sent as the user message.
SUPPORT_KICKSTART_CANNED = (
    "Create a team",
    "Create a BA → Engineer → Tester workflow",
    "Add a remote",
    "Wire a CLI",
)

ADMIN_KICKSTART_CANNED = (
    "Configure API Provider",
    "What is Open Swarm?",
    "Local Models (Ollama)",
    "Upgrade to LLM",
)

SUPPORT_JOURNEY_PHRASES = (
    "create a team",
    "Create a BA → Engineer → Tester workflow",
    "add a remote",
    "wire a CLI",
    "blueprint",
    "Chief of Staff",
    "Hermes",
    "OpenMousBot",
    "Herdr",
    "CLI",
    "API",
    "remote",
    "one pane",
    "list models",
    "View / edit code",
)


def is_support_consumer(agent_id: str | None) -> bool:
    """True for the default Support seats (blueprint + router starter)."""
    ident = (agent_id or "").strip().lower()
    return ident in SUPPORT_CONSUMER_IDS


def is_admin_consumer(agent_id: str | None) -> bool:
    """True for the default Admin seats (#893)."""
    ident = (agent_id or "").strip().lower()
    return ident in ADMIN_CONSUMER_IDS


def support_kickstart() -> list[str]:
    return list(SUPPORT_KICKSTART_CANNED)


def admin_kickstart() -> list[str]:
    return list(ADMIN_KICKSTART_CANNED)

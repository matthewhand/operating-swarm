"""Shared copy: what a blueprint is, the Python contract, and how it is consumed.

Used by the library creator UI and by agent instructions so humans and agents
see the same interface spec.
"""

from __future__ import annotations

# Short product sentence for headers / library lead.
BLUEPRINT_ONE_LINER = (
    "A blueprint is a coded agent team: a Python kind-base subclass "
    "(ApiKindBase / CliKindBase / RemoteKindBase) the framework discovers and runs."
)

# What authors (and coding agents) must implement.
BLUEPRINT_INTERFACE = """\
from swarm.core.kind_bases import ApiKindBase

class MyTeamBlueprint(ApiKindBase):
    metadata = {
        "name": "my_team",           # id used as the API model name
        "title": "My Team",
        "description": "What this team does",
        "version": "1.0.0",
    }

    async def run(self, messages, **kwargs):
        # messages: OpenAI-style [{role, content}, ...]
        # yield chunks the web Chat UI and /v1/chat/completions stream
        yield {"messages": [{"role": "assistant", "content": "..."}]}
"""

BLUEPRINT_CONSUMPTION = """\
Web
  • Blueprint Library — browse, install, create
  • Agents sidebar — listed as a coded team (click to talk, no dropdown)
  • Chat — same list in the side pane; POST model=<id> still works
  • POST /v1/chat/completions  {"model": "<blueprint id>", "messages": [...]}

CLI
  • swarm-cli list
  • swarm-cli launch <blueprint id> --message "..."
"""

# Compact prompt injected into coding agents that author blueprints.
BLUEPRINT_AGENT_BRIEF = (
    "Blueprints are coded agent teams. Prefer subclassing a kind base from "
    "swarm.core.kind_bases: ApiKindBase (openai-agents handoff / as-tool graphs), "
    "CliKindBase (native grok/agy session), or RemoteKindBase (Hermes / "
    "OpenMousBot / Herdr). BlueprintBase is the low-level parent — do not "
    "invent a fourth harness from the raw base in the common case. Required: "
    "class-level metadata (name/title/description/version) and "
    "`async def run(self, messages, **kwargs)` yielding "
    '`{"messages": [{"role": "assistant", "content": "..."}]}` chunks. '
    "The framework discovers them and serves them as the API `model` id "
    "on /v1/chat/completions, in the web Chat/Library UI, and via "
    "`swarm-cli launch <id> --message ...`. ADR-005 / REQ-159."
)


# Shipped preset bots (#1311). Recipes only: provider, model, and plugins.
# Presets stay undeletable catalog rows; create_agent(preset_id=...) materializes one rail seat.
PRESET_BOTS = (
    {
        "id": "preset-support",
        "name": "Support",
        "description": "First-run onboarder. Create a team, add a remote, wire a CLI.",
        "kind": "api",
        "role": "support",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "plugins": ["support-tools"],
        "instructions": (
            "Help the operator stand up a working roster. Never ask for raw "
            "secrets; collect env-var names only."
        ),
    },
    {
        "id": "preset-researcher",
        "name": "Researcher",
        "description": "Gather sources, cite claims, and hand off a linked brief.",
        "kind": "api",
        "role": "default",
        "provider": "openai",
        "model": "gpt-4o",
        "plugins": ["web-search"],
        "instructions": (
            "Research the assigned question. Link every claim. Do not publish "
            "or contact anyone."
        ),
    },
    {
        "id": "preset-reviewer",
        "name": "Reviewer",
        "description": "Check a draft against sources and list only blocking issues.",
        "kind": "api",
        "role": "skeptic",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "plugins": ["repo-reader"],
        "instructions": (
            "Review the draft against the cited sources. List only blocking "
            "issues. Do not rewrite unless asked."
        ),
    },
)


def _copy_preset(row: dict) -> dict:
    """Detach nested lists so callers cannot mutate the catalog."""
    copied = dict(row)
    copied["plugins"] = list(row.get("plugins") or [])
    return copied


def get_preset_bot(preset_id: str) -> dict | None:
    """Return a copy of one shipped preset, or None."""
    ident = str(preset_id or "").strip()
    if not ident:
        return None
    for row in PRESET_BOTS:
        if row["id"] == ident:
            return _copy_preset(row)
    return None


def list_preset_bots() -> list[dict]:
    """Shipped presets in catalog order."""
    return [_copy_preset(row) for row in PRESET_BOTS]

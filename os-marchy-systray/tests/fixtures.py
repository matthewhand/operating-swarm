"""Fixtures mirroring the real OS API payload shapes.

Shapes are copied from the Django/DRF serializers, not invented:

* ``/v1/agents/``        — ``agent_router_views.list_agents``
* ``/v1/team-rosters/``  — ``team_rosters_api`` + ``serialize_roster``
* ``/v1/cli-agents/``    — ``cli_catalog.cli_agents_catalog_payload``
* ``/v1/remotes/``       — ``remotes_api.RemotesListView``
* ``/health``            — ``HealthCheckView``
"""

from __future__ import annotations

AGENTS_PAYLOAD: dict = {
    "status": "success",
    "blueprint_name": "agent_router",
    "data": {
        "router": "router",
        "handoff_rules": [],
        "agents": [
            {
                "agent_id": "cos",
                "name": "Chief of Staff",
                "specialty": "Talks to any available team.",
                "color": "#6366f1",
                "icon": "🧑",
                "type": "specialist",
                "agent_type": "api",
                "kind": "api",
                "chat_model": "cos",
            },
            {
                "agent_id": "research",
                "name": "Research",
                "specialty": "Coded agent team",
                "color": "#3b82f6",
                "icon": "📦",
                "type": "team",
                "agent_type": "api",
                "kind": "blueprint",
                "chat_model": "research",
            },
            {
                "agent_id": "lonely",
                "name": "Lonely Seat",
                "specialty": "No rig claims me.",
                "color": "#f59e0b",
                "icon": "🤖",
                "type": "specialist",
                "agent_type": "api",
                "kind": "blueprint",
                "chat_model": "lonely",
            },
        ],
    },
}

ROSTERS_PAYLOAD: dict = {
    "object": "list",
    "data": [
        {
            "id": "newsroom",
            "object": "team_roster",
            "name": "Newsroom",
            "members": [
                {
                    "id": "cos",
                    "name": "Chief of Staff",
                    "kind": "api",
                    "role": "chief_of_staff",
                    "source": "blueprint:cos",
                },
                {
                    "id": "research",
                    "name": "Research",
                    "kind": "api",
                    "role": "default",
                    "source": "blueprint:research",
                },
                {
                    "id": "newsroom-desk",
                    "name": "Newsroom Desk",
                    "kind": "team",
                    "role": "default",
                    "source": "team:newsroom-desk",
                    "team_id": "newsroom-desk",
                },
            ],
            "tools": [],
            "wires": {"handoff": True, "as_tool": True},
            "chief_of_staff_id": "cos",
            "chief_of_staff_instructions": "",
        }
    ],
}

CLI_PAYLOAD: dict = {
    "clis": ["grok", "agy"],
    "known": ["grok", "agy"],
    "configured": [{"name": "grok"}],
    "discovered": ["agy"],
    "installed": ["grok"],
    "suggestions": [],
    "catalog": [],
    "native_consensus": [],
    "list_models": [],
    "list_sessions": [],
    "rail": [
        {
            "id": "cli_agent",
            "object": "cli.agent",
            "name": "cli_agent",
            "cli": "grok",
            "kind": "cli",
            "description": "Host CLI — pick a discovered catalog CLI in the header.",
            "installed": True,
        },
        {
            "id": "api_agent",
            "object": "cli.agent",
            "name": "api_agent",
            "cli": "",
            "kind": "api",
            "description": "LiteLLM — pick a profile.",
            "installed": True,
        },
    ],
    "modes": {"cli": True, "api": True},
}

REMOTES_PAYLOAD: dict = {
    "object": "list",
    "kinds": ["hermes", "omb", "herdr"],
    "data": [
        {
            "id": "hermes",
            "kind": "hermes",
            "title": "Hermes",
            "source": "default",
            "added": False,
            "agents": [],
        },
        {
            "id": "omb",
            "kind": "omb",
            "title": "OpenMousBot",
            "source": "config",
            "added": True,
            "capabilities": {"list": True, "send": True, "sessions": False},
            "agents": [
                {"id": "bot-a", "name": "Bot A", "role": "worker", "status": "running"},
                {"id": "bot-b", "name": "Bot B", "role": "worker", "status": "finished"},
            ],
        },
        {
            "id": "herdr-x",
            "kind": "herdr",
            "title": "Herdr X",
            "source": "config",
            "added": True,
            "agents": [],
        },
    ],
    "configured": [
        {
            "id": "omb",
            "kind": "omb",
            "title": "OpenMousBot",
            "source": "config",
            "added": True,
            "capabilities": {"list": True, "send": True, "sessions": False},
            "agents": [
                {"id": "bot-a", "name": "Bot A", "role": "worker", "status": "running"},
                {"id": "bot-b", "name": "Bot B", "role": "worker", "status": "finished"},
            ],
        },
        {
            "id": "herdr-x",
            "kind": "herdr",
            "title": "Herdr X",
            "source": "config",
            "added": True,
            "agents": [],
        },
    ],
    "team_members": [],
}

TEAMS_PAYLOAD: dict = {
    "object": "list",
    "data": [
        {"id": "fast", "object": "team", "description": "Fast profile", "llm_profile": "default"}
    ],
}

HEALTH_PAYLOAD: dict = {"status": "ok", "version": "0.5.4"}

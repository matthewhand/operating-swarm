"""Agent Router types: how a sidebar agent is run.

Three types:

* **api** — LiteLLM / OpenAI-compatible chat, implemented as openai-agents
  ``Agent``s. One instruction block is a single persona. Two or more
  ``personas`` make an in-app openai-agents swarm (coordinator + specialists).
  Built-in specialists, personality designs, swarm designs, and coded
  blueprints are all API agents.
* **cli** — a host executable (grok, agy, claude, …) via ``CliAdapter``.
* **remote** — another agentic framework over HTTP (or Herdr), e.g. OpenMausBot.

``kind`` is the finer stored record (``builtin`` / ``personality`` / ``swarm`` /
``blueprint`` / ``cli`` / ``remote``). ``agent_type`` is the user-facing type.
"""

from __future__ import annotations

from typing import Any

AGENT_TYPES = ("api", "cli", "remote")

KIND_TO_TYPE: dict[str, str] = {
    "api": "api",
    "builtin": "api",
    "personality": "api",
    "swarm": "api",  # persona/swarm *design* — not the nested open-swarm remote
    "blueprint": "api",
    "cli": "cli",
    "remote": "remote",
    # REQ-203: remotes impl ids are Remote, not a fifth user-facing kind.
    "herdr": "remote",
    "hermes": "remote",
    "omb": "remote",
    "rakazo": "remote",
    "open-swarm": "remote",
    "trueforge": "remote",
    "true_forge": "remote",
}

AGENT_TYPE_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "api",
        "label": "API",
        "description": (
            "LiteLLM / OpenAI-compatible. One openai-agents Agent by default; "
            "add personas for a multi-agent swarm."
        ),
    },
    {
        "id": "cli",
        "label": "CLI",
        "description": "Host executable in one-shot print mode (grok, agy, claude, …).",
    },
    {
        "id": "remote",
        "label": "Remote",
        "description": "Another agentic framework — OpenMausBot, Hermes, Rakazo, Herdr.",
    },
)


def agent_type_for_kind(kind: str | None) -> str:
    """Map a stored ``kind`` to ``api``, ``cli``, or ``remote``."""
    key = (kind or "builtin").strip().lower()
    return KIND_TO_TYPE.get(key, "api")


def public_personas(raw: Any) -> list[dict[str, str]]:
    """Normalize persona records for API list/inspector payloads."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        out.append({
            "name": name[:60],
            "instructions": str(item.get("instructions") or "").strip()[:4000],
        })
    return out

"""Nested Operating Swarm (OS-peer) remote — point one instance at another.

Catalog id is ``swarm``. User-facing copy is **Operating Swarm** / **OS-peer**.
Aliases: ``open-swarm``, ``operating-swarm``, ``os-peer``. Bare stored-design
``swarm`` (persona recipe) stays API — this module is the Remote *impl*.

Named instances (``swarm-2``, ``swarm_gpu``) share the impl and get their own
env slugs through ``swarm.core.remotes`` (``SWARM_2_BASE_URL`` /
``SWARM_2_API_KEY``). A child is not required to nest the parent. Never
persist this process' listen URL as a remote.
"""

from __future__ import annotations

import re
from typing import Any

KIND_ID = "swarm"
KIND_LABEL = "Operating Swarm"
PEER_NICK = "OS-peer"
APP_NAME = "operating-swarm"

HEALTH_PATH = "/health"
VERSION_PATH = "/v1/models"

LIST_AGENT_PATHS: tuple[str, ...] = (
    "/v1/blueprints/",
    "/v1/blueprints",
    "/v1/models/",
    "/v1/models",
)
LIST_SESSION_PATHS: tuple[str, ...] = (
    "/api/sessions/",
    "/api/sessions",
    "/v1/sessions/",
    "/v1/sessions",
)
LIST_TEAM_PATHS: tuple[str, ...] = (
    "/v1/agent-team/",
    "/v1/agent-team",
    "/v1/teams/",
    "/v1/teams",
)
SEND_PATHS: tuple[str, ...] = (
    "/v1/chat/completions/",
    "/v1/chat/completions",
)

_SEMVER = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?")


def version_string(payload: Any) -> str:
    """Best-effort version from a /health (or version-path) body."""
    if isinstance(payload, str):
        text = payload.strip()
        return text if text and _SEMVER.match(text) else ""
    if not isinstance(payload, dict):
        return ""
    for key in ("version", "app_version", "swarm_version"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, (int, float)):
            return str(raw)
        if isinstance(raw, dict):
            nested = version_string(raw)
            if nested:
                return nested
    return ""


def _major(version: str) -> int | None:
    match = _SEMVER.match((version or "").strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def peer_version_warning(peer: str, local: str) -> str:
    """Warn when the child OS-peer looks incompatible. Empty = no warning.

    Missing version is a warning, not a hard fail. Major-version mismatch is
    incompatible. Same major (including unknown/0.0.0 local) stays quiet.
    """
    peer_v = (peer or "").strip()
    local_v = (local or "").strip()
    if not peer_v:
        return "peer did not advertise a version; treat the OS-peer as unverified"
    peer_major = _major(peer_v)
    local_major = _major(local_v)
    if peer_major is None:
        return f"peer version {peer_v!r} is not semver; compatibility unverified"
    if local_major is None:
        return ""
    if peer_major != local_major:
        return (
            f"incompatible OS-peer version {peer_v} (this instance is {local_v}); "
            "list/send may fail"
        )
    return ""


def items_from_body(body: Any, *keys: str) -> list[Any]:
    """Pull a list out of common OpenAI / OS list envelopes."""
    if isinstance(body, list):
        return list(body)
    if not isinstance(body, dict):
        return []
    for key in keys or ("data", "items", "results"):
        raw = body.get(key)
        if isinstance(raw, list):
            return list(raw)
    for key in ("agents", "blueprints", "models", "sessions", "teams", "members"):
        raw = body.get(key)
        if isinstance(raw, list):
            return list(raw)
    return []


def agent_id(row: Any) -> str:
    if isinstance(row, str):
        return row.strip()
    if not isinstance(row, dict):
        return ""
    for key in ("id", "name", "blueprint_id", "model", "slug"):
        raw = row.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def members_from_agents(
    agents: list[Any],
    *,
    remote: str = KIND_ID,
) -> list[dict[str, Any]]:
    """Sidepane-shaped members so a nested OS-peer lists like other remotes."""
    members: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in agents:
        ident = agent_id(row)
        if not ident or ident in seen:
            continue
        seen.add(ident)
        title = ident
        if isinstance(row, dict):
            title = str(row.get("name") or row.get("title") or ident)
        members.append(
            {
                "id": ident,
                "name": ident,
                "title": title,
                "kind": KIND_ID,
                "remote": remote,
            }
        )
    return members


def extract_completion_text(body: Any) -> str:
    """Assistant text from a non-streaming /v1/chat/completions body."""
    if isinstance(body, str):
        return body.strip()
    if not isinstance(body, dict):
        return ""
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    for key in ("output_text", "content", "text", "reply"):
        raw = body.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def health_payload(version: str) -> dict[str, str]:
    """JSON body this process advertises on GET /health for OS-peer probes."""
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": version or "0.0.0",
        "peer": PEER_NICK,
    }

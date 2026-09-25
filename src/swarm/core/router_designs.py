"""Persist custom Agent Router designs (personality, openai-agents swarm, CLI).

Stored as JSON under the user config dir. Built-in router ids cannot be
overwritten. These records are metadata for the live router, not executed
Python blueprints.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from swarm.core.paths import get_user_config_dir_for_swarm

KINDS = ("personality", "swarm", "cli", "remote", "api")
RESERVED_IDS = frozenset({"researcher", "writer", "analyst", "coder", "router", "consensus"})

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def designs_path() -> Path:
    override = os.environ.get("SWARM_ROUTER_DESIGNS")
    if override:
        return Path(override)
    return get_user_config_dir_for_swarm() / "router_designs.json"


def slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")
    return slug or "agent"


def load_designs() -> list[dict[str, Any]]:
    path = designs_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, list):
        return []
    return [a for a in agents if isinstance(a, dict) and a.get("agent_id")]


# #1157: seat→design lookups run per turn; designs change rarely and only via
# upsert/delete, so a tiny (path, mtime)-keyed cache keeps the resolver cheap
# without ever serving a stale design after a write or an env reroute.
_designs_cache: tuple[str, float, list[dict[str, Any]]] | None = None


def _designs_cached() -> list[dict[str, Any]]:
    global _designs_cache
    path = designs_path()
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        return []
    if _designs_cache is None or _designs_cache[:2] != key:
        _designs_cache = (*key, load_designs())
    return _designs_cache[2]


def _find_design(agent_id: str) -> dict[str, Any] | None:
    """The design row for ``agent_id`` (mtime-cached), or None."""
    raw = (agent_id or "").strip()
    if not raw:
        return None
    for spec in _designs_cached():
        if spec.get("agent_id") == raw:
            return spec
    return None


def designed_agent_kind(agent_id: str) -> str | None:
    """Kind of the designed agent ``agent_id`` ('personality'/'cli'/…), or None.

    #1157: the chat-turn resolver needs to know whether an incoming seat id
    is a designer-created agent without a full designs load per request.
    """
    spec = _find_design(agent_id)
    kind = str(spec.get("kind") or "").strip().lower() if spec else ""
    return kind or None


def designed_seat_params(agent_id: str) -> dict[str, str]:
    """Params routing a turn at a designed (non-CLI) seat to its runner.

    Personality/swarm designs run through the ``agent_router`` blueprint with
    a direct target (their real Agent objects are bound there by
    ``_attach_designed``). CLI designs are remapped by the CLI catalog
    instead and need no params. Non-designs get ``{}``.
    """
    kind = designed_agent_kind(agent_id)
    if kind in ("personality", "swarm"):
        return {"target_agent": agent_id.strip(), "routing_strategy": "direct"}
    return {}


def save_designs(agents: list[dict[str, Any]]) -> None:
    path = designs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"agents": agents}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_design(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize and validate a design payload. Raises ValueError on bad input."""
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in KINDS:
        raise ValueError(
            "kind must be 'api' (LiteLLM / openai-agents; add personas for a swarm), "
            "'personality' (one openai-agents voice), "
            "'swarm' (openai-agents coordinator + specialists), "
            "'cli' (installed agentic CLI), "
            "or 'remote' (Hermes / OpenMausBot / Rakazo / OpenAI-compatible team)."
        )
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    agent_id = str(raw.get("agent_id") or slugify(name)).strip().lower()
    agent_id = slugify(agent_id)
    if agent_id in RESERVED_IDS:
        raise ValueError(f"agent_id {agent_id!r} is reserved")
    if len(agent_id) > 48:
        raise ValueError("agent_id is too long")

    personas = _normalize_personas(raw.get("personas"))
    if kind in ("api", "personality", "swarm"):
        if kind == "swarm" or len(personas) >= 2:
            if len(personas) < 2:
                raise ValueError("swarm agents need at least two personas")
            kind = "swarm"
        else:
            kind = "personality"

    spec: dict[str, Any] = {
        "agent_id": agent_id,
        "name": name[:80],
        "kind": kind,
        "agent_type": _agent_type_for(kind),
        "specialty": str(raw.get("specialty") or "").strip()[:160],
        "description": str(raw.get("description") or "").strip()[:400],
        "instructions": str(raw.get("instructions") or "").strip()[:8000],
        "color": _safe_color(raw.get("color")),
        "icon": (str(raw.get("icon") or "🤖").strip() or "🤖")[:4],
        "group": _group_for(kind, raw.get("group")),
        "type": "specialist" if kind != "swarm" else "orchestrator",
    }
    if kind == "remote":
        from swarm.core.remote_teams import FRAMEWORKS, normalize_framework

        framework = normalize_framework(str(raw.get("framework") or spec["agent_id"])) or ""
        base_url = str(raw.get("base_url") or "").strip()
        model = str(raw.get("model") or "default").strip() or "default"
        if not framework and not base_url:
            raise ValueError(
                "remote teams need a framework (hermes, openmausbot, rakazo, herdr, dsh) or a base_url"
            )
        if framework and framework in FRAMEWORKS:
            meta = FRAMEWORKS[framework]
            spec["name"] = spec["name"] or meta["name"]
            spec["color"] = spec["color"] if raw.get("color") else meta["color"]
            spec["icon"] = spec["icon"] if raw.get("icon") else meta["icon"]
            if not spec["specialty"]:
                spec["specialty"] = meta["specialty"]
            if not spec["description"]:
                spec["description"] = meta["description"]
            spec["agent_id"] = spec["agent_id"] if raw.get("agent_id") else framework
        spec["framework"] = framework or spec["agent_id"]
        spec["base_url"] = base_url
        spec["model"] = model[:80]
        spec["target"] = str(raw.get("target") or "").strip()[:64]
        spec["transport"] = "herdr" if spec["framework"] == "herdr" else "http"
        if spec["framework"] == "dsh" and not spec.get("base_url"):
            spec["base_url"] = "http://127.0.0.1:3080/v1"
        spec["group"] = "remote"
        spec["type"] = "specialist"
        if not spec["specialty"]:
            spec["specialty"] = "Remote agentic team"
    elif kind == "cli":
        from swarm.core.cli_catalog import catalog_entry, catalog_names

        cli = str(raw.get("cli") or "").strip().lower()
        if not cli:
            raise ValueError("cli agents need a CLI name (grok, claude, gemini, …)")
        if not catalog_entry(cli):
            known = ", ".join(catalog_names())
            raise ValueError(
                f"cli must be a catalog CLI ({known}). "
                "OpenMausBot / Rakazo / Hermes are remote teams, not CLIs."
            )
        spec["cli"] = cli
        if not spec["specialty"]:
            spec["specialty"] = f"{cli} CLI"
    elif kind == "swarm":
        spec["personas"] = personas
        if not spec["specialty"]:
            spec["specialty"] = "openai-agents swarm"
        if not spec["instructions"]:
            names = ", ".join(p["name"] for p in personas)
            spec["instructions"] = (
                f"You coordinate a swarm of openai-agents personas: {names}. "
                "Delegate to the specialist who should own each part of the task, "
                "then return one combined answer."
            )
    else:
        if not spec["instructions"]:
            raise ValueError("personality agents need instructions")
        if not spec["specialty"]:
            spec["specialty"] = "single personality"
    if not spec["description"]:
        spec["description"] = spec["specialty"]
    from swarm.core.agent_mcp import mcp_fields_from_raw

    mcp = mcp_fields_from_raw(raw, kind=kind)
    if mcp:
        spec.update(mcp)
    return spec


def upsert_design(raw: dict[str, Any]) -> dict[str, Any]:
    spec = validate_design(raw)
    agents = load_designs()
    agents = [a for a in agents if a.get("agent_id") != spec["agent_id"]]
    agents.append(spec)
    save_designs(agents)
    if spec.get("mcp_mode"):
        from swarm.core.agent_mcp import register_mcp

        register_mcp(
            spec["agent_id"],
            mode=spec.get("mcp_mode"),
            mcp_servers=spec.get("mcp_servers"),
        )
    if spec.get("kind") == "remote" and (spec.get("base_url") or spec.get("target")):
        try:
            from swarm.core.remote_teams import persist_remote_overlay

            persist_remote_overlay(spec)
        except Exception:
            pass
    return spec


def delete_design(agent_id: str) -> bool:
    agents = load_designs()
    kept = [a for a in agents if a.get("agent_id") != agent_id]
    if len(kept) == len(agents):
        return False
    save_designs(kept)
    return True


def _safe_color(value: Any) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return text.lower()
    return "#6366f1"


def _agent_type_for(kind: str) -> str:
    from swarm.core.agent_types import agent_type_for_kind

    return agent_type_for_kind(kind)


def _group_for(kind: str, group: Any) -> str:
    allowed = {"specialists", "tools", "orchestration", "remote"}
    g = str(group or "").strip().lower()
    if g in allowed:
        return g
    if kind == "cli":
        return "tools"
    if kind == "swarm":
        return "orchestration"
    if kind == "remote":
        return "remote"
    return "specialists"


def _normalize_personas(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        instructions = str(item.get("instructions") or "").strip()
        if not name or not instructions:
            continue
        out.append({"name": name[:60], "instructions": instructions[:4000]})
    return out

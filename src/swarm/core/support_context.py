"""Live context for the Support agent (role=support).

Assembles the current agent list, whether inference is actually usable, and
in-product / quickstart paths so the System → Support briefing pill and
Support tools stay honest. Does not call any LLM.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# In-product paths. Settings is the SPA sheet (#1442), not the Django dump.
SPA_SETTINGS_INFERENCE_HREF = "/chat?settings=llm-profiles"
CREATE_PATHS = {
    "agent": "/agent-creator/",
    "blueprint": "/blueprint-library/",
    "team": "/teams/launch/",
    "teams": "/teams/",
    "settings": SPA_SETTINGS_INFERENCE_HREF,
    "profiles": "/profiles/",
}

INFERENCE_QUICKSTART_ANCHOR = "#4-configure-your-llm-provider"
TEAM_QUICKSTART_ANCHOR = "#2b-create-your-own-team-wizard"

# Repo-relative docs used when present; never invent a second quickstart.
_QUICKSTART_RELATIVE = Path("docs") / "QUICKSTART.md"


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent / "docs" / "QUICKSTART.md").is_file() or (parent / "pyproject.toml").is_file():
            return parent
    return here.parents[3] if len(here.parents) > 3 else (here.parents[-1] if here.parents else here.parent)


def quickstart_path() -> Path | None:
    candidate = _repo_root() / _QUICKSTART_RELATIVE
    return candidate if candidate.is_file() else None


def quickstart_href(anchor: str = "") -> str:
    """Path operators can open; not a hosted docs site."""
    href = f"/docs/QUICKSTART.md{anchor}"
    return href


_ROLE_RANK = {"support": 0, "gate": 1, "skeptic": 2}


def agent_role(agent: dict[str, Any] | None) -> str:
    if not isinstance(agent, dict):
        return ""
    role = str(agent.get("role") or "").strip().lower()
    if role:
        return role
    ident = str(agent.get("id") or agent.get("name") or "").strip().lower()
    if ident in _ROLE_RANK:
        return ident
    return ""


def is_support_agent(agent: dict[str, Any] | None) -> bool:
    return agent_role(agent) == "support"


def _unresolved(value: Any) -> bool:
    text = str(value or "").strip()
    return not text or text.startswith("${")


def _profile_ready(profile: Any) -> bool:
    """True when a profile can actually talk to a model (no leftover ${ENV})."""
    if not isinstance(profile, dict):
        return False
    if _unresolved(profile.get("model")):
        return False
    api_key = profile.get("api_key")
    base_url = profile.get("base_url")
    if not _unresolved(api_key):
        return True
    # Local / keyless OpenAI-compatible gateways (Ollama, LiteLLM placeholder).
    return not _unresolved(base_url)


def _env_inference_ready() -> list[str]:
    """Env vars that make inference usable even without a resolved profile."""
    signals: list[str] = []
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "LITELLM_API_KEY",
        "LITELLM_BASE_URL",
        "OLLAMA_BASE_URL",
        "OPENAI_BASE_URL",
    ):
        if str(os.environ.get(name) or "").strip():
            signals.append(name)
    return signals


def _load_swarm_config() -> dict[str, Any]:
    try:
        from swarm.core.config_loader import find_config_file, load_config

        path = find_config_file()
        if path is None:
            return {}
        loaded = load_config(path)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def inference_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Whether a usable LLM profile / env credential is present. No secrets."""
    cfg = config if isinstance(config, dict) else _load_swarm_config()
    llm_section = cfg.get("llm") if isinstance(cfg.get("llm"), dict) else {}
    ready_profiles: list[str] = []
    for name, profile in llm_section.items():
        if name == "profiles" and isinstance(profile, dict):
            for inner_name, inner in profile.items():
                if _profile_ready(inner):
                    ready_profiles.append(str(inner_name))
            continue
        if _profile_ready(profile):
            ready_profiles.append(str(name))

    env_signals = _env_inference_ready()
    configured = bool(ready_profiles or env_signals)
    return {
        "configured": configured,
        "profiles": ready_profiles,
        "env_signals": env_signals,
        "quickstart": {
            "doc": str(_QUICKSTART_RELATIVE),
            "anchor": INFERENCE_QUICKSTART_ANCHOR,
            "settings": CREATE_PATHS["settings"],
            "profiles": CREATE_PATHS["profiles"],
            "cli": (
                "swarm-cli config add --section llm --name default --json "
                '\'{"provider":"openai","model":"gpt-4o-mini",'
                '"api_key":"${OPENAI_API_KEY}"}\''
            ),
        },
    }


def _agent_entries_from_discovery() -> list[dict[str, str]]:
    try:
        from swarm.views.utils import _load_all_blueprint_metadata_sync

        available = _load_all_blueprint_metadata_sync()
    except Exception:
        return []
    if not isinstance(available, dict):
        return []
    entries: list[dict[str, str]] = []
    for blueprint_id, info in available.items():
        meta = info.get("metadata", {}) if isinstance(info, dict) else {}
        entries.append(
            {
                "id": str(blueprint_id),
                "name": str(meta.get("name") or blueprint_id),
                "description": str(meta.get("description") or ""),
                "role": str(meta.get("role") or ""),
            }
        )
    return entries


def sort_support_first(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(agents))
    indexed.sort(key=lambda item: (_ROLE_RANK.get(agent_role(item[1]), 10), item[0]))
    return [agent for _, agent in indexed]


def live_context(*, agents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Snapshot used by the System → Support briefing pill and Support tools."""
    agent_list = agents if agents is not None else _agent_entries_from_discovery()
    inference = inference_status()
    return {
        "agents": sort_support_first(list(agent_list)),
        "agent_count": len(agent_list),
        "inference": inference,
        "create": dict(CREATE_PATHS),
        "quickstarts": {
            "inference": {
                "title": "Set inference",
                "doc": str(_QUICKSTART_RELATIVE) + INFERENCE_QUICKSTART_ANCHOR,
                "settings": CREATE_PATHS["settings"],
                "profiles": CREATE_PATHS["profiles"],
            },
            "team": {
                "title": "New team",
                "doc": str(_QUICKSTART_RELATIVE) + TEAM_QUICKSTART_ANCHOR,
                "launch": CREATE_PATHS["team"],
                "cli": "swarm-cli wizard",
            },
            "blueprint": {
                "title": "Write blueprint",
                "library": CREATE_PATHS["blueprint"],
                "creator": CREATE_PATHS["agent"],
            },
        },
        "chips": {
            "new_team": {"label": "New team", "href": CREATE_PATHS["team"]},
            "write_blueprint": {"label": "Write blueprint", "href": CREATE_PATHS["agent"]},
            "blueprints": {"label": "Blueprints", "href": CREATE_PATHS["blueprint"]},
            "set_inference": {"label": "Set inference", "href": CREATE_PATHS["settings"]},
            "profiles": {"label": "Profiles", "href": CREATE_PATHS["profiles"]},
            "quickstart": {
                "label": "Quickstart",
                "href": str(_QUICKSTART_RELATIVE) + INFERENCE_QUICKSTART_ANCHOR,
            },
        },
    }


def _quickstart_excerpt(heading_prefix: str, *, max_chars: int = 1800) -> str:
    path = quickstart_path()
    if path is None:
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith(heading_prefix):
            start = i
            break
    if start is None:
        return ""
    collected = [lines[start]]
    for line in lines[start + 1 :]:
        if line.startswith("## ") and not line.startswith(heading_prefix):
            break
        collected.append(line)
    excerpt = "\n".join(collected).strip()
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 1].rstrip() + "…"
    return excerpt


def quickstart_section(name: str) -> str:
    """Return an existing QUICKSTART.md section. Empty when the file is missing."""
    mapping = {
        "inference": "## 4. Configure Your LLM Provider",
        "team": "## 2b. Create Your Own Team (Wizard)",
        "blueprint": "## 2. Install a Blueprint",
        "run": "## 5. Run a Blueprint",
    }
    heading = mapping.get((name or "").strip().lower())
    if not heading:
        return ""
    return _quickstart_excerpt(heading)


def _chip(label: str, href: str) -> str:
    return f"[{label}]({href})"


def briefing_markdown(context: dict[str, Any] | None = None) -> str:
    """Compressed intel for the System → Support pill popover. Not transcript copy."""
    ctx = context or live_context()
    inference = ctx.get("inference") or {}
    agents = ctx.get("agents") or []

    lines = ["**Agents**"]
    if agents:
        for agent in agents:
            name = agent.get("name") or agent.get("id") or "untitled"
            role = agent.get("role") or ""
            lines.append(f"- {name}" + (f" · {role}" if role else ""))
    else:
        lines.append("- none")

    lines.append("")
    if inference.get("configured"):
        profiles = ", ".join(inference.get("profiles") or []) or "on"
        lines.append(f"**Inference** on · {profiles}")
    else:
        lines.append("**Inference** off")

    lines.extend(
        [
            "",
            "**Gate** — dangerous tool call? yes/no. Until wired, all approved.",
            "**Skeptic** — prompt done? If not, findings go back to retry.",
        ]
    )
    return "\n".join(lines)


def welcome_markdown(context: dict[str, Any] | None = None) -> str:
    """Back-compat alias: briefing only. Action chips are separate UI."""
    return briefing_markdown(context)


def model_context_block(context: dict[str, Any] | None = None) -> str:
    """Laconic snapshot injected on Support load."""
    ctx = context or live_context()
    inference = ctx.get("inference") or {}
    agents = ctx.get("agents") or []
    names = [str(a.get("id") or a.get("name") or "") for a in agents]
    status = "on" if inference.get("configured") else "off"
    profiles = ", ".join(inference.get("profiles") or []) or "—"
    return (
        f"Agents: {', '.join(names) or 'none'}\n"
        f"Inference: {status} · {profiles}\n"
        f"New team: {CREATE_PATHS['team']}\n"
        f"Set inference: {CREATE_PATHS['settings']}\n"
        f"Write blueprint: {CREATE_PATHS['agent']}\n"
        "Gate: stub. All approved until wired.\n"
        "Skeptic: stub. Retry loop later."
    )


def create_paths_markdown() -> str:
    return " ".join(
        [
            _chip("New team", CREATE_PATHS["team"]),
            _chip("Set inference", CREATE_PATHS["settings"]),
            _chip("Write blueprint", CREATE_PATHS["agent"]),
        ]
    )

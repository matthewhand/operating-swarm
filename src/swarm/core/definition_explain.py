"""REQ-42 — role / blueprint / team definition briefs + default-LLM summarise.

Assembles the real source plus injected runtime context (system prompt, tools,
metadata, handoff/as-tool wiring, extra notes) and, when a default LLM is
configured, summarises it through the same OpenAI/LiteLLM client used by
``DjangoChatConsumer.respond_with_default_model``. No second inference stack.
"""

from __future__ import annotations

import json
import os
from typing import Any

# Distinctive fixture string for tests (never a secret / token / personal dump).
REQ42_INJECTED_FIXTURE = "REQ42_INJECTED_FIXTURE_MARKER"

DEFINITION_KINDS = ("role", "blueprint", "team")

ROLE_BRIEFS: dict[str, str] = {
    "support": (
        "Support is Socratic: it talks about the other agents and how this "
        "team is wired. It asks one clarifying question at a time, offers a "
        "short multiple-choice when you are stuck, and never takes over the work."
    ),
    "gate": (
        "Gate is a YES/NO classifier for a pending tool call. It finishes by "
        "calling submit_gate_verdict (verdict yes = dangerous / elicit the "
        "operator; no = safe / proceed). Prose is never parsed as the verdict. "
        "If no gate is wired on the roster, the gate is fail-open — every tool "
        "call is approved and you are never asked."
    ),
    "skeptic": (
        "Skeptic is a bounded retry reviewer. It sees the original prompt plus "
        "the agent's output and finishes by calling submit_skeptic_verdict "
        "(pass or fail). On fail it hands concise findings back (max 2 retries). "
        "On pass it stops. It does not nag. Prose is never parsed as the verdict."
    ),
    "cos": (
        "Chief of Staff (CoS) talks to any team. It routes the operator to the "
        "right roster and coordinates across teams-of-teams instead of doing "
        "the specialist work itself."
    ),
    "suggestions": (
        "Suggestions prepares a short list of quick-select prompts. A consumer "
        "with Use suggestions on shows those as chips after each turn, including "
        "before the first message. Clicking a chip sends that exact string. "
        "Chips are chrome, not extra LLM context."
    ),
    "engineer": (
        "Engineer implements the quoted work. It writes only after a gate or "
        "CoS has unblocked it. It is a specialist seat (as_tool / handoff), "
        "not an extra Grok chrome row."
    ),
    "default": (
        "This is a worker blueprint: it runs its own system prompt, tools, and "
        "handoffs. It is not a gate, skeptic, Support, Chief of Staff, "
        "engineer, or suggestions seat."
    ),
}

TEAM_BRIEF = (
    "A team is a roster of members that can hand off or be invoked as tools. "
    "The operator can talk to the whole team or a single member. Role seats "
    "(Support, gate, skeptic, CoS) change how work is approved, reviewed, or routed."
)

BLUEPRINT_BRIEF = (
    "A blueprint is the Python/API recipe for an agent: instructions, tools, "
    "metadata, and as-tool / handoff wiring. The runtime injects extra context "
    "on top of this source when the agent runs."
)

ROLE_ALIASES = {
    "default": "default",
    "worker": "default",
    "agent": "default",
    "coordinator": "default",
    "support": "support",
    "helper": "support",
    "gate": "gate",
    "tool_gate": "gate",
    "tool-gate": "gate",
    "toolgate": "gate",
    "skeptic": "skeptic",
    "reviewer": "skeptic",
    "cos": "cos",
    "chief_of_staff": "cos",
    "chief-of-staff": "cos",
    "chiefofstaff": "cos",
    "engineer": "engineer",
    "eng": "engineer",
    "none": "default",
    "suggestions": "suggestions",
    "suggestion": "suggestions",
    "suggest": "suggestions",
}

ROLE_FALLBACK_SOURCE = {
    "support": (
        "# Blueprint recipe — Support (Socratic)\n"
        "SUPPORT_INSTRUCTIONS = (\n"
        '    "You are Support. Talk about the other agents and how this team is wired. "\n'
        '    "Stay Socratic: ask one clarifying question at a time."\n'
        ")\n"
    ),
    "gate": (
        "# Blueprint recipe — Gate (YES/NO via submit_gate_verdict)\n"
        "# Unwired gate is fail-open: every tool call is approved.\n"
        "GATE_INSTRUCTIONS = (\n"
        '    "You are a tool-call gate. When done, call submit_gate_verdict "\n'
        '    "with verdict=\\"yes\\" if dangerous or verdict=\\"no\\" if not."\n'
        ")\n"
        "def submit_gate_verdict(verdict: str, reason: str = \"\") -> str:\n"
        '    """Finish the gate determination. Example: submit_gate_verdict(\\"yes\\", \\"rm -rf\\")."""\n'
        "    return verdict\n"
    ),
    "skeptic": (
        "# Blueprint recipe — Skeptic (bounded retry via submit_skeptic_verdict)\n"
        "SKEPTIC_MAX_RETRIES = 2\n"
        "SKEPTIC_INSTRUCTIONS = (\n"
        '    "When done, call submit_skeptic_verdict with verdict=\\"pass\\" or \\"fail\\". "\n'
        '    "Max 2 retries. Prose is not a verdict."\n'
        ")\n"
        "def submit_skeptic_verdict(verdict: str, reason: str = \"\") -> str:\n"
        '    """Finish the skeptic determination. Example: submit_skeptic_verdict(\\"fail\\", \\"missing file\\")."""\n'
        "    return verdict\n"
    ),
    "cos": (
        "# Blueprint recipe — Chief of Staff (talk-to-any-team)\n"
        "COS_INSTRUCTIONS = (\n"
        '    "You are Chief of Staff. Route the operator to the right team. "\n'
        '    "Talk to any roster; do not do the specialist work yourself."\n'
        ")\n"
    ),
    "suggestions": (
        "# Blueprint recipe — Suggestions (quick-select chips)\n"
        "SUGGESTIONS_INSTRUCTIONS = (\n"
        '    "Return JSON {\\"suggestions\\": [2-5 short strings]} the operator can click."\n'
        ")\n"
    ),
    "engineer": (
        "# Blueprint recipe — Engineer (implementer)\n"
        "ENGINEER_INSTRUCTIONS = (\n"
        '    "You are the engineer. Implement the quoted issue after the gate. "\n'
        '    "Do not start without a quoted Intent/Success and feasibility."\n'
        ")\n"
    ),
}

SUMMARIZER_SYSTEM = (
    "You summarise an Operating Swarm role, blueprint, or team definition for an operator. "
    "Use only the provided source and injected context. Do not invent secrets, tokens, "
    "credentials, or personal data. Write 3-6 short sentences explaining how it works "
    "at runtime (tools, handoffs, approvals, retries). No raw file dump."
)


def normalize_role(value: object) -> str:
    if value is None:
        return "default"
    key = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if not key:
        return "default"
    return ROLE_ALIASES.get(key, "default")


def role_from_identity(definition_id: str, role: str | None = None) -> str:
    explicit = normalize_role(role)
    if explicit != "default":
        return explicit
    key = (definition_id or "").strip().lower()
    if key in ROLE_ALIASES:
        return ROLE_ALIASES[key]
    if key in {"chief-of-staff", "chief_of_staff", "chiefofstaff"}:
        return "cos"
    return normalize_role(key)


def static_explanation(kind: str, role: str) -> str:
    if kind == "team":
        return TEAM_BRIEF
    if kind == "blueprint" and role == "default":
        return BLUEPRINT_BRIEF
    return ROLE_BRIEFS.get(role, ROLE_BRIEFS["default"])


def default_llm_status() -> dict[str, Any]:
    """Whether the same default model consumers.py would call is configured."""
    model = (
        os.environ.get("LITELLM_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or os.environ.get("DEFAULT_LLM")
    )
    model_name = str(model).strip() if model else ""
    return {"configured": bool(model_name), "model": model_name or None}


def _blueprint_source_from_disk(blueprint_id: str) -> str:
    from pathlib import Path

    from swarm.settings import BLUEPRINT_DIRECTORY

    base = Path(BLUEPRINT_DIRECTORY).resolve()
    bp_dir = (base / blueprint_id).resolve()
    if base not in bp_dir.parents or not bp_dir.is_dir():
        return ""
    files = sorted(
        p for p in bp_dir.iterdir()
        if p.is_file() and p.suffix in {".py", ".md", ".json", ".txt"}
    )
    if not files:
        return ""
    primary = next((p for p in files if p.name.startswith("blueprint_")), files[0])
    try:
        return primary.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return ""


def _custom_blueprint_code(blueprint_id: str) -> str:
    try:
        from swarm.views.api_views import get_user_blueprint_library

        lib = get_user_blueprint_library()
        for item in lib.get("custom") or []:
            if item.get("id") == blueprint_id:
                return str(item.get("code") or "")
    except Exception:
        return ""
    return ""


def _team_roster(team_id: str) -> dict[str, Any] | None:
    from pathlib import Path

    candidates = [
        Path("webui/frontend/public/team_rosters.json"),
        Path("src/swarm/static/team_rosters.json"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict) and row.get("id") == team_id:
                return row
    return {
        "id": team_id,
        "name": team_id,
        "description": "Example multi-agent roster",
        "members": [],
    }


def load_source(kind: str, definition_id: str, role: str) -> str:
    if kind == "team":
        roster = _team_roster(definition_id) or {}
        return json.dumps(roster, indent=2, sort_keys=True)
    live = _blueprint_source_from_disk(definition_id) or _custom_blueprint_code(definition_id)
    if live.strip():
        return live
    return ROLE_FALLBACK_SOURCE.get(role, f"# Blueprint {definition_id}\n# No source published yet.\n")


def _blueprint_metadata(blueprint_id: str) -> dict[str, Any]:
    try:
        from asgiref.sync import async_to_sync
        from swarm.views.utils import get_available_blueprints

        blueprints = async_to_sync(get_available_blueprints)()
        info = blueprints.get(blueprint_id) if isinstance(blueprints, dict) else None
        if isinstance(info, dict):
            meta = info.get("metadata") if isinstance(info.get("metadata"), dict) else {}
            return dict(meta)
    except Exception:
        return {}
    return {}


def _blueprint_tools(blueprint_id: str) -> dict[str, Any]:
    try:
        from swarm.core import tool_capabilities
        from swarm.core.config_loader import find_config_file, load_config
        from asgiref.sync import async_to_sync
        from swarm.views.utils import get_available_blueprints

        blueprints = async_to_sync(get_available_blueprints)()
        info = blueprints.get(blueprint_id) if isinstance(blueprints, dict) else None
        if info is None:
            return {}
        meta = info.get("metadata", {}) if isinstance(info, dict) else {}
        requirements = meta.get("tool_requirements") or {}
        cfg_file = find_config_file()
        config = load_config(cfg_file) if cfg_file else {}
        servers, res = tool_capabilities.resolve_mcp_servers(requirements, config)
        return {
            "requirements": tool_capabilities.normalize_requirements(requirements),
            "servers": list((servers or {}).keys()),
            "satisfied": getattr(res, "satisfied", {}),
            "missing_mandatory": getattr(res, "missing_mandatory", []),
        }
    except Exception:
        return {}


def _handoff_notes(kind: str, role: str, meta: dict[str, Any], roster: dict[str, Any] | None) -> str:
    parts: list[str] = []
    if role == "gate":
        parts.append(
            "Gate is invoked as_tool on a pending tool call and finishes via "
            "submit_gate_verdict (yes/no). Unwired gate is fail-open. "
            "Missing tool call nudges then fail-closes (needs-human / block)."
        )
    elif role == "skeptic":
        parts.append(
            "Skeptic is invoked as_tool after a run and finishes via "
            "submit_skeptic_verdict (pass/fail); findings feed a bounded retry (max 2)."
        )
    elif role == "support":
        parts.append("Support talks about other agents; it does not take over their tools.")
    elif role == "cos":
        parts.append("CoS can address any team roster (talk-to-any-team).")
    elif role == "suggestions":
        parts.append(
            "Suggestions is invoked as_tool after a consumer turn "
            "(and on an empty thread for kickstart)."
        )
    gate_agent = meta.get("gate_agent")
    skeptic_agent = meta.get("skeptic_agent")
    if gate_agent:
        parts.append(f"Roster gate_agent={gate_agent}.")
    if skeptic_agent:
        parts.append(f"Roster skeptic_agent={skeptic_agent}.")
    agents = meta.get("agents")
    if isinstance(agents, list) and agents:
        seats = ", ".join(
            f"{a.get('name', '?')}:{a.get('role', 'default')}" if isinstance(a, dict) else str(a)
            for a in agents
        )
        parts.append(f"AGENT_SPECS seats: {seats}.")
    if kind == "team" and roster:
        members = roster.get("members") or []
        names = [
            f"{m.get('name') or m.get('id')} ({m.get('role') or m.get('kind') or 'member'})"
            for m in members
            if isinstance(m, dict)
        ]
        if names:
            parts.append("Members: " + ", ".join(names) + ".")
    if not parts:
        parts.append("No extra as-tool / handoff seats declared.")
    return " ".join(parts)


def _system_prompt_from_source(source: str, role: str) -> str:
    for marker in (
        "SUPPORT_INSTRUCTIONS",
        "GATE_INSTRUCTIONS",
        "SKEPTIC_INSTRUCTIONS",
        "COS_INSTRUCTIONS",
        "SUGGESTIONS_INSTRUCTIONS",
        "INSTRUCTIONS",
    ):
        if marker in source:
            start = source.find(marker)
            return source[start : start + 400]
    return ROLE_BRIEFS.get(role, ROLE_BRIEFS["default"])


def collect_injected(
    kind: str,
    definition_id: str,
    role: str,
    source: str,
    *,
    extra: str | None = None,
) -> dict[str, Any]:
    meta = _blueprint_metadata(definition_id) if kind != "team" else {}
    tools = _blueprint_tools(definition_id) if kind != "team" else {}
    roster = _team_roster(definition_id) if kind == "team" else None
    extra_text = extra if extra is not None else _default_extra(kind, role)
    return {
        "system_prompt": _system_prompt_from_source(source, role),
        "tools": tools,
        "metadata": {
            "id": definition_id,
            "kind": kind,
            "role": role,
            "gate_agent": meta.get("gate_agent"),
            "skeptic_agent": meta.get("skeptic_agent"),
            "agents": meta.get("agents"),
            "title": (roster or {}).get("name") if roster else definition_id,
        },
        "handoff": _handoff_notes(kind, role, meta, roster),
        "extra": extra_text,
    }


def _default_extra(kind: str, role: str) -> str:
    # Tests may opt into the distinctive fixture marker without secrets.
    if os.environ.get("SWARM_DEFINITION_TEST_FIXTURE") == "1":
        return REQ42_INJECTED_FIXTURE
    if role == "gate":
        return "Runtime injects the pending tool name and arguments before classify."
    if role == "skeptic":
        return "Runtime injects the original prompt plus the latest agent output."
    if role == "support":
        return "Runtime injects the visible agent/team roster so Support can talk about them."
    if role == "cos":
        return "Runtime injects the list of teams CoS may address."
    if kind == "team":
        return "Runtime injects member as-tool / handoff handles for this roster."
    return "Runtime may inject MCP tool schemas and memory snippets on top of this source."


def build_summarize_prompt(
    kind: str,
    definition_id: str,
    explanation: str,
    source: str,
    injected: dict[str, Any],
) -> str:
    extra = injected.get("extra") or ""
    tools = injected.get("tools") or {}
    metadata = injected.get("metadata") or {}
    return (
        f"Kind: {kind}\n"
        f"Id: {definition_id}\n\n"
        f"## Human brief\n{explanation}\n\n"
        f"## Source\n{source[:12_000]}\n\n"
        f"## Injected system prompt\n{injected.get('system_prompt')}\n\n"
        f"## Injected tools\n{json.dumps(tools, default=str)[:4_000]}\n\n"
        f"## Injected metadata\n{json.dumps(metadata, default=str)[:2_000]}\n\n"
        f"## Injected handoff / as-tool wiring\n{injected.get('handoff')}\n\n"
        f"## Extra runtime context\n{extra}\n"
    )


def summarize_with_default_llm(prompt: str) -> tuple[bool, str | None, str | None]:
    """Call the existing default-model client. Returns (configured, model, text)."""
    status = default_llm_status()
    if not status["configured"]:
        return False, None, None
    from swarm.utils.env_utils import openai_client_kwargs

    try:
        from openai import OpenAI
    except Exception:
        return True, status["model"], None

    try:
        client = OpenAI(**openai_client_kwargs())
        response = client.chat.completions.create(
            model=status["model"],
            messages=[
                {"role": "system", "content": SUMMARIZER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=400,
        )
    except Exception:
        # Network / auth / rate-limit / provider errors: stay on the default-LLM
        # path (configured=True) without crashing the Settings pane request.
        return True, status["model"], None

    choice = (response.choices or [None])[0]
    message = getattr(choice, "message", None) if choice is not None else None
    text = getattr(message, "content", None) if message is not None else None
    if isinstance(choice, dict):
        text = (choice.get("message") or {}).get("content")
    return True, status["model"], (text or "").strip() or None


def build_definition(
    kind: str,
    definition_id: str,
    *,
    source_override: str | None = None,
    extra: str | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    kind = (kind or "blueprint").strip().lower()
    if kind not in DEFINITION_KINDS:
        kind = "blueprint"
    definition_id = (definition_id or "").strip()
    resolved_role = role_from_identity(definition_id, role)
    if kind == "role" and resolved_role == "default":
        resolved_role = role_from_identity(definition_id)
    explanation = static_explanation(kind, resolved_role)
    source = source_override if source_override is not None else load_source(kind, definition_id, resolved_role)
    injected = collect_injected(kind, definition_id, resolved_role, source, extra=extra)
    llm = default_llm_status()
    title = definition_id
    if kind == "team":
        roster = _team_roster(definition_id) or {}
        title = str(roster.get("name") or definition_id)
    elif resolved_role != "default":
        title = resolved_role.capitalize() if definition_id == resolved_role else definition_id
    return {
        "kind": kind,
        "id": definition_id,
        "title": title,
        "role": resolved_role,
        "explanation": explanation,
        "source": source,
        "injected": injected,
        "default_llm": llm,
    }


def summarise_definition(
    kind: str,
    definition_id: str,
    *,
    source_override: str | None = None,
    extra: str | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    payload = build_definition(
        kind,
        definition_id,
        source_override=source_override,
        extra=extra,
        role=role,
    )
    prompt = build_summarize_prompt(
        payload["kind"],
        payload["id"],
        payload["explanation"],
        payload["source"],
        payload["injected"],
    )
    configured, model, summary = summarize_with_default_llm(prompt)
    return {
        "kind": payload["kind"],
        "id": payload["id"],
        "configured": configured,
        "model": model,
        "summary": summary,
        "injected_extra": payload["injected"].get("extra"),
    }

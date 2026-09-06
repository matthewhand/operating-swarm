"""First-class agent roles for rail look and team wiring.

Canonical roles:

* ``default`` / ``none`` — ordinary worker (no badge)
* ``support`` — Support seat (REQ-7). Teal badge.
* ``gate`` — tool-call classifier (alias ``tool_gate``). Amber badge.
* ``skeptic`` — post-run reviewer. Violet badge.
* ``chief_of_staff`` — talks to any team (aliases ``cos``, ``chief``). Ice-steel badge.
* ``engineer`` — implementer seat (software-dev / Chatty). Slate badge.
* ``suggestions`` — quick-select chips after a turn (REQ-85). Sage badge.

Sidepane class names (reuse these; do not invent a parallel set):

* ``os-agent-role-badge`` is the only role colour (chip + ``os-agent-role-<role>``)
* ``data-role="<role>"`` may appear on the row for identification
* Rows have no role fill, left-border accent, or outline (REQ-67)

REQ-75: a blueprint may declare ``metadata.role`` (applied on create / re-pick)
and an optional ``metadata.workflow`` hint (``handoff`` / ``as_tool``). The
agent editor role wins once the operator explicitly overrides it.

REQ-28: Chief of Staff keeps a distinct **badge** colour — not support / gate /
skeptic. REQ-67 removed role row chrome. Hover-edit (REQ-25) can later target
this role's blueprint; this module at least names the badge contract.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

ROLE_DEFAULT = "default"
ROLE_SUPPORT = "support"
ROLE_GATE = "gate"
ROLE_SKEPTIC = "skeptic"
ROLE_CHIEF_OF_STAFF = "chief_of_staff"
ROLE_ENGINEER = "engineer"
ROLE_SUGGESTIONS = "suggestions"

# User-facing / config aliases → canonical role.
ROLE_ALIASES: dict[str, str] = {
    "default": ROLE_DEFAULT,
    "none": ROLE_DEFAULT,
    "worker": ROLE_DEFAULT,
    "agent": ROLE_DEFAULT,
    "coordinator": ROLE_DEFAULT,
    "support": ROLE_SUPPORT,
    "helper": ROLE_SUPPORT,
    "gate": ROLE_GATE,
    "tool_gate": ROLE_GATE,
    "tool-gate": ROLE_GATE,
    "toolgate": ROLE_GATE,
    "skeptic": ROLE_SKEPTIC,
    "reviewer": ROLE_SKEPTIC,
    "chief_of_staff": ROLE_CHIEF_OF_STAFF,
    "chief-of-staff": ROLE_CHIEF_OF_STAFF,
    "chiefofstaff": ROLE_CHIEF_OF_STAFF,
    "cos": ROLE_CHIEF_OF_STAFF,
    "chief": ROLE_CHIEF_OF_STAFF,
    "engineer": ROLE_ENGINEER,
    "eng": ROLE_ENGINEER,
    "suggestions": ROLE_SUGGESTIONS,
    "suggestion": ROLE_SUGGESTIONS,
    "suggest": ROLE_SUGGESTIONS,
}

CANONICAL_ROLES: tuple[str, ...] = (
    ROLE_DEFAULT,
    ROLE_SUPPORT,
    ROLE_GATE,
    ROLE_SKEPTIC,
    ROLE_CHIEF_OF_STAFF,
    ROLE_ENGINEER,
    ROLE_SUGGESTIONS,
)

ROLE_BADGE_LABELS: dict[str, str] = {
    ROLE_DEFAULT: "",
    ROLE_SUPPORT: "Support",
    ROLE_GATE: "Gate",
    ROLE_SKEPTIC: "Skeptic",
    ROLE_CHIEF_OF_STAFF: "CoS",
    ROLE_ENGINEER: "Engineer",
    ROLE_SUGGESTIONS: "Suggest",
}

WORKFLOW_HANDOFF = "handoff"
WORKFLOW_AS_TOOL = "as_tool"
WORKFLOW_ALIASES: dict[str, str] = {
    "handoff": WORKFLOW_HANDOFF,
    "handoffs": WORKFLOW_HANDOFF,
    "as_tool": WORKFLOW_AS_TOOL,
    "as-tool": WORKFLOW_AS_TOOL,
    "astool": WORKFLOW_AS_TOOL,
}
CANONICAL_WORKFLOWS: tuple[str, ...] = (WORKFLOW_HANDOFF, WORKFLOW_AS_TOOL)

# WebUI-as-blueprint leftovers (#419 deleted django_chat). REQ-75 pickers
# still refuse a webui kind if a leftover row appears.
WEBUI_BLUEPRINT_IDS = frozenset({"django_chat"})
WEBUI_KINDS = frozenset({"webui", "django_chat", "webpage", "django-chat"})

# CSS contract for the AGENTS sidepane badge (Django + SPA). REQ-67: not on the row.
ROLE_CSS_CLASS_PREFIX = "os-agent-role-"
ROLE_CSS_CLASSES: dict[str, str] = {
    role: f"{ROLE_CSS_CLASS_PREFIX}{role}" for role in CANONICAL_ROLES
}


def normalize_agent_role(value: Any) -> str:
    """Map a free-text / alias role to a canonical visual/wiring role.

    Unknown values become ``default`` so they never accidentally enable
    gate, skeptic, or chief-of-staff wiring. ``none`` is an alias of
    ``default`` (no badge).
    """
    if value is None:
        return ROLE_DEFAULT
    key = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if not key:
        return ROLE_DEFAULT
    return ROLE_ALIASES.get(key, ROLE_DEFAULT)


def normalize_workflow(value: Any) -> str | None:
    """Map a blueprint workflow hint to ``handoff`` / ``as_tool``, or ``None``.

    v1 is metadata only — not a new orchestration engine.
    """
    if value is None:
        return None
    key = str(value).strip().lower().replace(" ", "_")
    if not key:
        return None
    return WORKFLOW_ALIASES.get(key)


def is_webui_blueprint(blueprint_id: Any = None, meta: dict[str, Any] | None = None) -> bool:
    """True when a catalog row is a leftover webui/django-chat recipe.

    Pickers must not offer a webui kind (REQ-75). ``django_chat`` is
    already gone (#419); this helper still classifies leftovers.
    """
    bid = str(blueprint_id or "").strip().lower().replace("-", "_")
    if bid in WEBUI_BLUEPRINT_IDS:
        return True
    meta = meta or {}
    kind = str(meta.get("kind") or "").strip().lower().replace("-", "_")
    if kind in WEBUI_KINDS:
        return True
    if meta.get("urls_module") or meta.get("url_prefix"):
        return True
    return False


def apply_blueprint_role(
    blueprint_role: Any,
    *,
    current_role: Any = None,
    role_overridden: bool = False,
) -> str:
    """Apply a blueprint default role unless the agent editor overrode it.

    Re-picking a blueprint re-applies ``blueprint_role`` when
    ``role_overridden`` is False. An explicit editor change wins.
    """
    if role_overridden:
        return normalize_agent_role(current_role)
    return normalize_agent_role(blueprint_role)


def is_chief_of_staff(role: Any) -> bool:
    """True when *role* is ``chief_of_staff`` (including ``cos`` / ``chief``)."""
    return normalize_agent_role(role) == ROLE_CHIEF_OF_STAFF


def can_manage_agent_lifecycle(role: Any) -> bool:
    """True for Support / CoS — the only roles that get create/archive tools (REQ-154)."""
    canonical = normalize_agent_role(role)
    return canonical == ROLE_SUPPORT or canonical == ROLE_CHIEF_OF_STAFF or is_chief_of_staff(role)


def role_css_class(role: Any) -> str:
    """Return ``os-agent-role-<canonical>`` for a role value."""
    return ROLE_CSS_CLASSES[normalize_agent_role(role)]


def role_badge_label(role: Any) -> str:
    """Short chip label (``CoS``, ``Gate``, …). Empty for ``default``."""
    return ROLE_BADGE_LABELS.get(normalize_agent_role(role), "")


def role_from_agent(agent: Any) -> str:
    """Read ``role`` from an openai-agents Agent, spec dict, or attribute bag."""
    if agent is None:
        return ROLE_DEFAULT
    if isinstance(agent, dict):
        return normalize_agent_role(agent.get("role"))
    return normalize_agent_role(getattr(agent, "role", None))


def attach_role(agent: Any, role: Any) -> Any:
    """Stamp a canonical ``role`` attribute on an Agent (or any object)."""
    canonical = normalize_agent_role(role)
    try:
        agent.role = canonical
    except Exception:
        pass
    return agent


def _agent_name(agent: Any, fallback: str | None = None) -> str | None:
    if isinstance(agent, dict):
        name = agent.get("name") or agent.get("id")
    else:
        name = getattr(agent, "name", None) or getattr(agent, "id", None)
    if name:
        return str(name)
    return fallback


def find_role_agent(agents: Any, role: str) -> Any | None:
    """Return the first agent/spec whose role matches *role*, or ``None``."""
    want = normalize_agent_role(role)
    if want == ROLE_DEFAULT:
        return None
    if agents is None:
        return None
    items: Iterable[tuple[str | None, Any]]
    if isinstance(agents, dict):
        items = agents.items()
    else:
        items = ((_agent_name(a), a) for a in agents)
    for _name, agent in items:
        if role_from_agent(agent) == want:
            return agent
    return None


def find_role_name(agents: Any, role: str) -> str | None:
    """Name of the first agent wired as *role*, or ``None`` if unwired."""
    agent = find_role_agent(agents, role)
    if agent is None:
        return None
    return _agent_name(agent)


def normalize_roster(agents: Any) -> list[dict[str, str]]:
    """``[{name, role}, ...]`` for API / sidepane consumers."""
    roster: list[dict[str, str]] = []
    if agents is None:
        return roster
    if isinstance(agents, dict):
        iterable = agents.items()
    else:
        pairs: list[tuple[str | None, Any]] = []
        for i, item in enumerate(agents):
            if isinstance(item, str):
                pairs.append((item, {"name": item, "role": ROLE_DEFAULT}))
            else:
                pairs.append((_agent_name(item, str(i)), item))
        iterable = pairs
    for name, agent in iterable:
        if not name or str(name).startswith("_"):
            continue
        roster.append({
            "name": str(name),
            "role": role_from_agent(agent),
        })
    return roster


def blueprint_role_fields(meta: dict[str, Any] | None) -> dict[str, Any]:
    """Serialize role + roster + wiring names for ``/v1/blueprints/``.

    Blueprint-level ``role`` is explicit metadata (Support / gate / CoS /
    engineer). ``none`` / missing becomes ``default`` (no badge). Member
    wiring lives on ``agents[]`` plus ``gate_agent`` / ``skeptic_agent``
    / ``suggestions_agent``. ``workflow`` is an optional handoff / as_tool
    hint (apply-on-create metadata, not a new engine).
    """
    meta = meta or {}
    raw_agents = meta.get("agents")
    roster = normalize_roster(raw_agents) if raw_agents else []
    if raw_agents and not roster and isinstance(raw_agents, list):
        roster = [
            {"name": str(item), "role": ROLE_DEFAULT}
            for item in raw_agents
            if item
        ]
    role = normalize_agent_role(meta.get("role"))
    gate = meta.get("gate_agent") or find_role_name(roster, ROLE_GATE)
    skeptic = meta.get("skeptic_agent") or find_role_name(roster, ROLE_SKEPTIC)
    cos = meta.get("chief_of_staff_agent") or find_role_name(roster, ROLE_CHIEF_OF_STAFF)
    suggestions = meta.get("suggestions_agent") or find_role_name(roster, ROLE_SUGGESTIONS)
    return {
        "role": role,
        "agents": roster,
        "gate_agent": gate,
        "skeptic_agent": skeptic,
        "chief_of_staff_agent": cos,
        "suggestions_agent": suggestions,
        "workflow": normalize_workflow(meta.get("workflow")),
    }


@dataclass
class ModeBPayload:
    """Mode B role-invocation payload per ADR-010 (REQ-191/REQ-191b).

    Mode B is used when other agents invoke a role agent via as_tool or handoff.
    Unlike Mode A (human chat with full private configure thread), Mode B uses
    strictly caller_context + latest_message.
    """

    invocation: str  # "as_tool" | "handoff"
    caller_id: str
    role: str
    latest_message: str
    caller_context: str | list[dict[str, Any]]
    callee_thread_id: str | None = None

    def __post_init__(self) -> None:
        if self.invocation not in CANONICAL_WORKFLOWS:
            norm_inv = normalize_workflow(self.invocation)
            if norm_inv:
                self.invocation = norm_inv
            else:
                raise ValueError(
                    f"Invalid invocation '{self.invocation}': must be 'as_tool' or 'handoff'"
                )
        if not self.caller_id:
            raise ValueError("caller_id is required for Mode B invocation")
        self.role = normalize_agent_role(self.role)
        if not self.latest_message:
            raise ValueError("latest_message is required for Mode B invocation")
        if self.caller_context is None:
            raise ValueError("caller_context is required for Mode B invocation")

    def build_model_messages(self, system_prompt: str | None = None) -> list[dict[str, str]]:
        """Construct model context window for Mode B execution.

        Strictly per ADR-010:
        Model messages = execution prompt + caller_context + latest_message only.
        callee_thread_id is explicitly NOT loaded as model context.
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if isinstance(self.caller_context, str):
            messages.append({
                "role": "user",
                "content": f"[Caller Context from {self.caller_id}]:\n{self.caller_context}",
            })
        elif isinstance(self.caller_context, list):
            for item in self.caller_context:
                if isinstance(item, dict) and "role" in item and "content" in item:
                    messages.append({"role": str(item["role"]), "content": str(item["content"])})
                else:
                    messages.append({"role": "user", "content": str(item)})

        messages.append({"role": "user", "content": self.latest_message})
        return messages


def is_mode_b_payload(data: Any) -> bool:
    """True when data matches the Mode B invocation payload contract."""
    if not isinstance(data, dict):
        return False
    inv = data.get("invocation")
    norm_inv = normalize_workflow(inv) if inv else None
    return (
        norm_inv in CANONICAL_WORKFLOWS
        and bool(data.get("caller_id"))
        and bool(data.get("role"))
        and bool(data.get("latest_message"))
        and "caller_context" in data
    )


def parse_mode_b_payload(data: dict[str, Any]) -> ModeBPayload:
    """Parse and validate Mode B invocation payload dict."""
    return ModeBPayload(
        invocation=data["invocation"],
        caller_id=str(data["caller_id"]),
        role=data["role"],
        latest_message=str(data["latest_message"]),
        caller_context=data["caller_context"],
        callee_thread_id=data.get("callee_thread_id"),
    )

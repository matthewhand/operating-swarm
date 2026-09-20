"""REQ-158: Support builds a blueprint/team from natural language.

Happy path: underspecified asks get one Socratic question; specified asks
draft an ``ApiKindBase`` card. Persist happens when the user clicks
**Add as agent** or **Save as blueprint**. They do **not** write Python.

Under the hood the seat is still an ``ApiKindBase`` Python class (ADR-005).
Code stays hidden unless they ask to view / edit it.

Deviation vs #562 / REQ-154: this is Support-only **blueprint/team create**
via the existing custom-library + rail seat path. Full Support/CoS
create/archive (soft-delete, ~30d purge) stays on #562.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from swarm.core.decision_question import format_decision_question

logger = logging.getLogger(__name__)

SUPPORT_NL_FIXTURE = "SUPPORT_NL_BLUEPRINT_NO_USER_PYTHON"
SUPPORT_NL_SOURCE = "support-nl"
SUPPORT_NL_FENCE = "swarm-nl-blueprint"
TEAM_PURPOSE_QUESTION_ID = "team-purpose"
ADD_AS_AGENT_LABEL = "Add as agent"
SAVE_AS_BLUEPRINT_LABEL = "Save as blueprint"
TEAM_PURPOSE_CHOICES = [
    "Software delivery (BA → Engineer → Tester)",
    "Review loop with a skeptic",
    "Coordinator + specialist",
]

TEMPLATE_PIPELINE = "pipeline"
TEMPLATE_SKEPTIC = "skeptic_loop"
TEMPLATE_TEAM = "first_team"

PIPELINE_EDGES: tuple[tuple[str, str], ...] = (("ba", "engineer"), ("engineer", "tester"))
SKEPTIC_EDGES: tuple[tuple[str, str], ...] = (
    ("ba", "engineer"),
    ("engineer", "tester"),
    ("tester", "skeptic"),
    ("skeptic", "engineer"),
)
TEAM_EDGES: tuple[tuple[str, str], ...] = (("coordinator", "specialist"),)

_ID_SAFE = re.compile(r"[^a-z0-9_]+")


@dataclass(frozen=True)
class NlBlueprintSpec:
    """Interpreted NL request — no user-authored Python."""

    template: str
    blueprint_id: str
    title: str
    description: str
    graph_label: str
    edges: tuple[tuple[str, str], ...]
    class_name: str


@dataclass
class CreatedNlBlueprint:
    """Result of Support NL create. ``code`` is optional-reveal only."""

    spec: NlBlueprintSpec
    code: str
    usable: bool
    chat_href: str
    persisted: bool
    item: dict[str, Any] = field(default_factory=dict)

    def card_payload(self) -> dict[str, Any]:
        return {
            "id": self.spec.blueprint_id,
            "title": self.spec.title,
            "usable": self.usable,
            "persisted": self.persisted,
            "chatHref": self.chat_href,
            "graphLabel": self.spec.graph_label,
            "edges": [list(edge) for edge in self.spec.edges],
            "template": self.spec.template,
            "source": SUPPORT_NL_SOURCE,
            "fixture": SUPPORT_NL_FIXTURE,
            "userWrotePython": False,
            "description": self.spec.description,
            "kind": "api",
            "code": self.code,
        }

    def user_reply(self, *, include_code_fence: bool = False) -> str:
        """Transcript copy: draft first; Python hidden unless asked."""
        if self.persisted:
            lead = (
                f"Created **{self.spec.title}**. The team is usable in chat — "
                "you did not write Python."
            )
            cta = f"Open: {self.chat_href}"
        else:
            lead = (
                f"Drafted **{self.spec.title}** from your answers and our team "
                "docs (ADR-005 `ApiKindBase`). You did not write Python."
            )
            cta = (
                f"**{ADD_AS_AGENT_LABEL}** puts it on the rail. "
                f"**{SAVE_AS_BLUEPRINT_LABEL}** keeps it in the library."
            )
        lines = [
            lead,
            "",
            cta,
            f"Graph: {self.spec.graph_label}",
            "",
            "Under the hood this is a Python `ApiKindBase` blueprint class. "
            "Code stays hidden unless you choose **View / edit code**.",
            "",
            f"```{SUPPORT_NL_FENCE}",
            json.dumps(self.card_payload(), indent=2),
            "```",
        ]
        if include_code_fence:
            lines.extend(["", "```python", self.code.rstrip(), "```"])
        return "\n".join(lines)


def slugify_blueprint_id(raw: str, *, fallback: str = "support_team") -> str:
    text = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    text = _ID_SAFE.sub("_", text).strip("_")
    if not text or text[0].isdigit():
        text = f"{fallback}_{text}".strip("_") or fallback
    return text[:48]


def class_name_for_id(blueprint_id: str) -> str:
    parts = [p for p in blueprint_id.split("_") if p]
    if not parts:
        return "SupportTeamBlueprint"
    return "".join(p[:1].upper() + p[1:] for p in parts) + "Blueprint"


def interpret_nl(prompt: str) -> str:
    """Map a natural-language ask to a small template. Ignores any pasted Python."""
    text = (prompt or "").lower()
    if "```" in (prompt or "") or ("class " in (prompt or "") and "def " in (prompt or "")):
        # User pasted code — still treat as NL intent, never require they author it.
        text = re.sub(r"```.*?```", " ", prompt or "", flags=re.S).lower()
    if any(word in text for word in ("skeptic", "circular", "punt-back", "punt back")):
        return TEMPLATE_SKEPTIC
    if any(
        word in text
        for word in (
            "ba",
            "engineer",
            "tester",
            "handoff",
            "sdlc",
            "pipeline",
            "workflow",
        )
    ):
        return TEMPLATE_PIPELINE
    return TEMPLATE_TEAM


def _spec_for_template(template: str, *, blueprint_id: str | None = None) -> NlBlueprintSpec:
    if template == TEMPLATE_SKEPTIC:
        ident = slugify_blueprint_id(blueprint_id or "ba_eng_tester_skeptic")
        return NlBlueprintSpec(
            template=template,
            blueprint_id=ident,
            title="BA → Engineer → Tester → Skeptic",
            description=(
                "Circular skeptic handoff. Built by Support from natural language. "
                "API/blueprint only — CLI and remote stay native."
            ),
            graph_label="BA → Engineer → Tester → Skeptic → Engineer",
            edges=SKEPTIC_EDGES,
            class_name=class_name_for_id(ident),
        )
    if template == TEMPLATE_PIPELINE:
        ident = slugify_blueprint_id(blueprint_id or "ba_eng_tester")
        return NlBlueprintSpec(
            template=template,
            blueprint_id=ident,
            title="BA → Engineer → Tester",
            description=(
                "Forced BA → Engineer → Tester handoff. Built by Support from "
                "natural language (REQ-158 / #564). API/blueprint only."
            ),
            graph_label="BA → Engineer → Tester",
            edges=PIPELINE_EDGES,
            class_name=class_name_for_id(ident),
        )
    ident = slugify_blueprint_id(blueprint_id or "first_team")
    return NlBlueprintSpec(
        template=TEMPLATE_TEAM,
        blueprint_id=ident,
        title="First Team",
        description=(
            "Coordinator + specialist team. Built by Support from natural language. "
            "You did not write Python."
        ),
        graph_label="Coordinator → Specialist",
        edges=TEAM_EDGES,
        class_name=class_name_for_id(ident),
    )


def render_apikind_python(spec: NlBlueprintSpec) -> str:
    """Generate the hidden-by-default Python class. User never types this."""
    edge_pairs = ", ".join(f"({src!r}, {dst!r})" for src, dst in spec.edges)
    if spec.template == TEMPLATE_TEAM:
        body = _TEAM_CLASS_BODY
    elif spec.template == TEMPLATE_SKEPTIC:
        body = _SKEPTIC_CLASS_BODY
    else:
        body = _PIPELINE_CLASS_BODY
    return body.format(
        class_name=spec.class_name,
        blueprint_id=spec.blueprint_id,
        title=spec.title,
        description=spec.description,
        edge_pairs=edge_pairs,
    )


def existing_custom_ids() -> set[str]:
    ids: set[str] = set()
    try:
        from swarm.views.blueprint_library_views import get_user_blueprint_library

        lib = get_user_blueprint_library()
        for item in lib.get("custom") or []:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
    except Exception:
        logger.debug("NL blueprint library id scan skipped", exc_info=True)
    try:
        from swarm.views import api_views

        for item in getattr(api_views, "_custom_blueprints_registry", []) or []:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
    except Exception:
        logger.debug("NL blueprint registry id scan skipped", exc_info=True)
    return ids


def unique_blueprint_id(base: str, existing: set[str] | None = None) -> str:
    known = existing if existing is not None else existing_custom_ids()
    if base not in known:
        return base
    n = 2
    while f"{base}_{n}" in known:
        n += 1
    return f"{base}_{n}"


def _test_mode() -> bool:
    return os.environ.get("SWARM_TEST_MODE", "").lower() in ("1", "true", "yes")


def persist_custom_item(item: dict[str, Any], *, disk: bool | None = None) -> dict[str, Any]:
    """Stamp a rail-visible custom seat and persist (disk + in-memory registry).

    ``SWARM_TEST_MODE`` skips disk so pytest does not write the host XDG library.
    Pass ``disk=True`` to force the custom-library write in those tests.
    """
    from swarm.core.rail_seats import build_custom_rail_item
    from swarm.views import api_views

    stamped = build_custom_rail_item(item)
    write_disk = (not _test_mode()) if disk is None else disk
    if write_disk:
        try:
            from swarm.views.blueprint_library_views import (
                get_user_blueprint_library,
                save_user_blueprint_library,
            )

            lib = get_user_blueprint_library()
            custom = [row for row in (lib.get("custom") or []) if isinstance(row, dict)]
            custom = [row for row in custom if row.get("id") != stamped.get("id")]
            custom.append(stamped)
            lib["custom"] = custom
            if not save_user_blueprint_library(lib):
                logger.warning("NL blueprint disk persist returned false for %s", stamped.get("id"))
        except Exception:
            logger.warning("NL blueprint disk persist failed for %s", stamped.get("id"), exc_info=True)
    try:
        registry = api_views._custom_blueprints_registry
        kept = [row for row in list(registry) if isinstance(row, dict) and row.get("id") != stamped.get("id")]
        registry.clear()
        registry.extend(kept)
        registry.append(stamped)
    except Exception:
        logger.warning("NL blueprint registry persist failed for %s", stamped.get("id"), exc_info=True)

    # Invalidate blueprint discovery cache so get_available_blueprints sees the
    # new seat immediately (#723 shared helper).
    try:
        from swarm.views.utils import invalidate_blueprint_meta_cache

        invalidate_blueprint_meta_cache()
    except Exception:
        pass

    return stamped


def create_nl_blueprint(prompt: str, *, persist: bool = False) -> CreatedNlBlueprint:
    """Draft (default) or persist a team/workflow from NL. No user-written Python."""
    template = interpret_nl(prompt)
    draft = _spec_for_template(template)
    blueprint_id = unique_blueprint_id(draft.blueprint_id)
    spec = _spec_for_template(template, blueprint_id=blueprint_id)
    code = render_apikind_python(spec)
    item = {
        "id": spec.blueprint_id,
        "name": spec.title,
        "description": spec.description,
        "category": "api",
        "tags": ["support-nl", "handoff", spec.template, "team"],
        "code": code,
        "kind": "api",
        "rail": True,
        "source": SUPPORT_NL_SOURCE,
        "requirements": "",
        "required_mcp_servers": [],
        "env_vars": [],
    }
    persisted = False
    stored = item
    if persist:
        stored = persist_custom_item(item)
        persisted = True
    return CreatedNlBlueprint(
        spec=spec,
        code=code,
        usable=persisted,
        chat_href=f"/chat?blueprint={spec.blueprint_id}",
        persisted=persisted,
        item=stored,
    )


def wants_nl_create(user_text: str) -> bool:
    """True when the user asked Support to *build* a team, not to show Python."""
    lowered = (user_text or "").strip().lower()
    if not lowered:
        return False
    if any(
        phrase in lowered
        for phrase in (
            "write a blueprint",
            "show the code",
            "show me the code",
            "view / edit",
            "view code",
            "edit code",
        )
    ):
        return False
    return any(
        phrase in lowered
        for phrase in (
            "create a team",
            "create a workflow",
            "create a ba",
            "build me a",
            "build a team",
            "handoff",
            "first team",
        )
    ) or ("engineer" in lowered and "tester" in lowered)


def wants_code_reveal(user_text: str) -> bool:
    lowered = (user_text or "").strip().lower()
    return any(
        phrase in lowered
        for phrase in (
            "write a blueprint",
            "show the code",
            "show me the code",
            "view / edit",
            "view code",
            "edit code",
            "python",
        )
    )


def nl_design_is_specified(user_text: str) -> bool:
    """True when the ask already names a topology we can draft."""
    text = (user_text or "").strip().lower()
    if not text:
        return False
    if any(word in text for word in ("skeptic", "circular", "punt-back", "punt back")):
        return True
    if any(
        word in text
        for word in ("ba", "engineer", "tester", "handoff", "sdlc", "pipeline")
    ):
        return True
    if "coordinator" in text and "specialist" in text:
        return True
    return False


def socratic_team_design_question() -> str:
    """One purpose/shape question. Docs-informed design happens after the answer."""
    prose = (
        "A local team is an `ApiKindBase` roster (ADR-005). "
        "I will use our team docs to pick the graph — one question first."
    )
    question = format_decision_question(
        ask="What should this team do?",
        choices=list(TEAM_PURPOSE_CHOICES),
        other="Describe the team",
        question_id=TEAM_PURPOSE_QUESTION_ID,
    )
    return f"{prose}\n\n{question}"


def map_team_purpose_answer(answer: str) -> str | None:
    """Map a Socratic purpose choice to an NL create prompt."""
    lowered = (answer or "").strip().lower()
    if not lowered:
        return None
    if lowered.startswith("software delivery"):
        return "Create a BA → Engineer → Tester workflow"
    if lowered.startswith("review loop"):
        return "Create a BA engineer tester skeptic workflow"
    if lowered.startswith("coordinator"):
        return "Create a first team"
    return None


def _assistant_asked_team_purpose(messages: list[dict[str, Any]] | None) -> bool:
    """True only if the immediately preceding assistant turn asked for team purpose."""
    for msg in reversed(messages or []):
        if str(msg.get("role") or "").lower() == "assistant":
            return TEAM_PURPOSE_QUESTION_ID in str(msg.get("content") or "")
    return False


def nl_create_or_socratic(
    user_text: str,
    messages: list[dict[str, Any]] | None = None,
    *,
    include_code_fence: bool = False,
) -> str | None:
    """Socratic first; draft card when specified. None if this turn is not team-create."""
    text = (user_text or "").strip()
    if not text:
        return None
    if wants_code_reveal(text) and not wants_nl_create(text):
        return None
    mapped = map_team_purpose_answer(text)
    if mapped:
        return create_nl_blueprint(mapped, persist=False).user_reply(
            include_code_fence=include_code_fence
        )
    if _assistant_asked_team_purpose(messages):
        return create_nl_blueprint(text, persist=False).user_reply(
            include_code_fence=include_code_fence
        )
    if wants_nl_create(text):
        if nl_design_is_specified(text):
            return create_nl_blueprint(text, persist=False).user_reply(
                include_code_fence=include_code_fence
            )
        return socratic_team_design_question()
    return None


_PIPELINE_CLASS_BODY = '''\
"""Support-created handoff graph — generated, user did not write this."""

from typing import Any, ClassVar

from agents import Agent

from swarm.core.kind_bases import ApiKindBase


class {class_name}(ApiKindBase):
    """Forced BA → Engineer → Tester. Built by Support from NL (REQ-158)."""

    metadata: ClassVar[dict[str, Any]] = {{
        "name": "{blueprint_id}",
        "title": "{title}",
        "description": "{description}",
        "version": "0.1.0",
        "tags": ["support-nl", "handoff", "team"],
        "rail": True,
        "workflow": "handoff",
        "required_mcp_servers": [],
        "env_vars": [],
    }}

    DECLARED_EDGES: ClassVar[tuple[tuple[str, str], ...]] = ({edge_pairs},)

    def create_starting_agent(self, mcp_servers):  # noqa: ARG002
        tester = Agent(
            name="Tester",
            instructions=(
                "You are Tester. Verify Engineer work against Success. "
                "No further programmatic handoff. Finish and stop."
            ),
            handoffs=[],
        )
        engineer = Agent(
            name="Engineer",
            instructions=(
                "You are Engineer. Implement from the BA brief. "
                "When ready, hand off only to Tester. Do not skip back to BA."
            ),
            handoffs=[tester],
        )
        ba = Agent(
            name="BA",
            instructions=(
                "You are BA. Capture Intent, Success, Constraints, Owner. "
                "When the brief is ready, hand off only to Engineer. Do not skip to Tester."
            ),
            handoffs=[engineer],
        )
        return ba

    async def run(self, messages, **kwargs):
        async for chunk in super().run(messages, **kwargs):
            yield chunk
'''

_SKEPTIC_CLASS_BODY = '''\
"""Support-created circular skeptic graph — generated, user did not write this."""

from typing import Any, ClassVar

from agents import Agent

from swarm.core.kind_bases import ApiKindBase


class {class_name}(ApiKindBase):
    """BA → Engineer → Tester → Skeptic (punt-back). Built by Support from NL."""

    metadata: ClassVar[dict[str, Any]] = {{
        "name": "{blueprint_id}",
        "title": "{title}",
        "description": "{description}",
        "version": "0.1.0",
        "tags": ["support-nl", "handoff", "skeptic", "team"],
        "rail": True,
        "workflow": "handoff",
        "required_mcp_servers": [],
        "env_vars": [],
    }}

    DECLARED_EDGES: ClassVar[tuple[tuple[str, str], ...]] = ({edge_pairs},)

    def create_starting_agent(self, mcp_servers):  # noqa: ARG002
        skeptic = Agent(
            name="Skeptic",
            instructions=(
                "You are Skeptic. If the work is not done, punt back to Engineer. "
                "Do not invent a skip to BA."
            ),
        )
        tester = Agent(
            name="Tester",
            instructions="You are Tester. Verify, then hand off only to Skeptic.",
        )
        engineer = Agent(
            name="Engineer",
            instructions="You are Engineer. Implement, then hand off only to Tester.",
        )
        ba = Agent(
            name="BA",
            instructions="You are BA. Brief the work, then hand off only to Engineer.",
            handoffs=[engineer],
        )
        engineer.handoffs = [tester]
        tester.handoffs = [skeptic]
        skeptic.handoffs = [engineer]
        return ba

    async def run(self, messages, **kwargs):
        async for chunk in super().run(messages, **kwargs):
            yield chunk
'''

_TEAM_CLASS_BODY = '''\
"""Support-created first team — generated, user did not write this."""

from typing import Any, ClassVar

from agents import Agent

from swarm.core.kind_bases import ApiKindBase


class {class_name}(ApiKindBase):
    """Coordinator + specialist. Built by Support from NL (REQ-158)."""

    metadata: ClassVar[dict[str, Any]] = {{
        "name": "{blueprint_id}",
        "title": "{title}",
        "description": "{description}",
        "version": "0.1.0",
        "tags": ["support-nl", "team", "starter"],
        "rail": True,
        "workflow": "as_tool",
        "required_mcp_servers": [],
        "env_vars": [],
    }}

    DECLARED_EDGES: ClassVar[tuple[tuple[str, str], ...]] = ({edge_pairs},)

    def create_starting_agent(self, mcp_servers):  # noqa: ARG002
        specialist = Agent(
            name="Specialist",
            instructions="Do the concrete work the coordinator delegates.",
        )
        coordinator = Agent(
            name="Coordinator",
            instructions="Plan the work, then call consult_specialist.",
            tools=[],
        )
        if hasattr(specialist, "as_tool"):
            coordinator.tools.append(
                specialist.as_tool(
                    tool_name="consult_specialist",
                    tool_description="Delegate implementation to the specialist.",
                )
            )
        return coordinator

    async def run(self, messages, **kwargs):
        async for chunk in super().run(messages, **kwargs):
            yield chunk
'''

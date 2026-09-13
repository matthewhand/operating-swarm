"""software_dev — CoS / engineer / skeptic via openai-agents as-tool.

Custom team/blueprint (spirit of REQ-4 ``cos_team`` folder/config), not extra
Grok Bot seats and not a concurrent Grok/OMB/Rakazo trio.

Talk-to seat is CoS (coding-requirements-gate). Engineer and skeptic are
specialists the CoS uses via ``as_tool()`` and optional ``handoff()``.

Deterministic grammar (no LLM — same idea as ``remote_harness``)::

    status              list seats + wiring
    quote <issue text>  CoS extracts Intent/Success/Constraints/Owner
    implement ...       engineer (blocked without quoted Issue + feasibility)
    review ...          skeptic text-only PASS/FAIL (look-only; no writes)

Structured params: ``seat``, ``action``, ``issue``, ``feasibility``,
``path``, ``content``, ``work``, ``tests``, ``visual``, ``deviations``.

Workspace/context params (``workdir``, ``cwd``, ``remote_workdir``,
``ssh_host`` / ``ssh_user`` / ``ssh_port`` / ``ssh_identity_env``,
``issue``, ``feasibility``, …) do **not** force the deterministic seat
router. Only ``seat`` / ``action`` (or an explicit grammar verb /
``SWARM_TEST_MODE``) select that path. Freeform and Issue-first user
text go to ``Runner.run(coordinator)`` so CoS can call
``consult_engineer`` / ``consult_skeptic`` (as_tool) and handoffs.
Structured multi-turn (``quote`` then a later freeform turn) remains
supported.

Tip quirk (Issue #150): ``bool(self._params)`` treated any non-empty
params — including workdir-only — as deterministic and skipped Runner.
Chatty Commander #854 worked around that by omitting ``params.workdir``.
That workaround is no longer required.

**FS-locality (Issue #148):** ``read_file`` / ``list_files`` /
``write_file`` default to the **API-host filesystem**. A local
``params.workdir`` on dev-worker-max (:8002) cannot see dev-worker-gpu paths
such as ``~/chatty-commander``. Point ``params.workdir`` at
``user@host:path`` / ``ssh://user@host/path``, or set
``params.remote_workdir`` (plus ``ssh_host`` / ``ssh_user`` when the
path is bare). Identity is an env-var *name* for a key *path* — never
a private key. Local ``..`` / absolute escapes out of the workspace
root are still refused.

Config block ``software_dev`` (optional)::

    {"software_dev": {"talk_to": "cos"}}
"""

from __future__ import annotations

import logging
import os
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.blueprints.software_dev.workspace import (
    WORKDIR_CONTEXT_KEYS,
    WorkspaceBackend,
    resolve_workspace,
)
from swarm.blueprints.software_dev.roles import (
    COS_INSTRUCTIONS,
    ENGINEER_INSTRUCTIONS,
    SEAT_COS,
    SEAT_ENGINEER,
    SEAT_SKEPTIC,
    SEATS,
    SKEPTIC_INSTRUCTIONS,
    SKEPTIC_LOOK_ONLY,
    SKEPTIC_NO_WRITE,
    SoftwareDevContext,
    engineer_may_start,
    extract_quoted_issue,
    hygiene_ok,
    pr_fixes_clause,
    seat_tool_policy,
    skeptic_verdict,
)
from swarm.core.blueprint_base import BlueprintBase
from swarm.core.classifier_verdict import attach_classifier_tools

logger = logging.getLogger(__name__)

# Params that select the deterministic seat/action router (Issue 136 e2e).
# Workspace/context keys must not appear here — workdir-only used to skip
# Runner via ``bool(self._params)`` (Issue #150 / Chatty Commander #854).
_ROUTING_PARAM_KEYS: frozenset[str] = frozenset({"seat", "action"})

# Grammar verbs that stay on the deterministic seat router (no LLM).
_DETERMINISTIC_ACTIONS: frozenset[str] = frozenset(
    ("status", "quote", "implement", "write", "review", "unblock", "verdict")
)

# Freeform / Issue-first: live CoS Runner (consult_engineer / consult_skeptic).
ACTION_CHAT = "chat"


def params_select_router(params: dict[str, Any] | None) -> bool:
    """True only when params explicitly select seat/action routing.

    ``workdir`` / ``remote_workdir`` / other non-empty context params
    do not trip this gate.
    """
    blob = params or {}
    return any(str(blob.get(key) or "").strip() for key in _ROUTING_PARAM_KEYS)


class SoftwareDevBlueprint(BlueprintBase):
    """CoS talk-to + engineer + skeptic, wired as openai-agents as-tool."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "software_dev",
        "title": "Software-dev team (CoS / engineer / skeptic)",
        "description": (
            "Custom software-dev team: CoS (coding-requirements-gate) talks; "
            "engineer and skeptic are openai-agents as-tool / handoff seats. "
            "Not extra Grok Bot seats. Issue-first REQ; engineer blocked "
            "without a quoted Issue; skeptic is look-only text PASS/FAIL."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["software-dev", "team", "cos", "engineer", "skeptic", "as-tool"],
        "aliases": ["software-dev", "software_dev_team"],
        "workflow": "as_tool",
        "required_mcp_servers": [],
        "env_vars": [
            "SWARM_SOFTWARE_DEV_WORKDIR",
            "SWARM_SOFTWARE_DEV_REMOTE_WORKDIR",
            "SWARM_SOFTWARE_DEV_SSH_HOST",
            "SWARM_SOFTWARE_DEV_SSH_USER",
            "SWARM_SOFTWARE_DEV_SSH_PORT",
            "SWARM_SOFTWARE_DEV_SSH_IDENTITY",
        ],
        "agents": [
            {"name": "coding-requirements-gate", "role": "chief_of_staff", "seat": "cos"},
            {"name": "engineer", "role": "engineer", "seat": "engineer"},
            {"name": "skeptic", "role": "skeptic", "seat": "skeptic"},
        ],
        "gate_agent": "coding-requirements-gate",
        "skeptic_agent": "skeptic",
    }

    def __init__(self, blueprint_id: str = "software_dev", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}
        self._agents: dict[str, Any] = {}
        self.context = SoftwareDevContext()
        self._workspace_cache: WorkspaceBackend | None = None
        # Tests inject a stub SSH runner (never from client params).
        self._workspace_runner = None

    def set_params(self, params: dict[str, Any] | None) -> None:
        new = dict(params or {})
        old = self._params
        self._params = new
        if any(old.get(key) != new.get(key) for key in WORKDIR_CONTEXT_KEYS):
            self._workspace_cache = None
            self._agents = {}

    def _cfg(self) -> dict[str, Any]:
        block = (self._config or {}).get("software_dev") or {}
        return block if isinstance(block, dict) else {}

    def _workspace(self) -> WorkspaceBackend:
        if self._workspace_cache is not None:
            return self._workspace_cache
        self._workspace_cache = resolve_workspace(
            self._params,
            self._cfg(),
            runner=self._workspace_runner,
        )
        return self._workspace_cache

    def _make_agent(self, name: str, instructions: str, tools: list[Any], **kwargs: Any):
        try:
            return self.make_agent(name, instructions, tools, **kwargs)
        except Exception as exc:
            logger.debug("make_agent(%s) fell back to bare Agent: %s", name, exc)
            from agents import Agent

            return Agent(name=name, instructions=instructions, tools=tools, **kwargs)

    def _build_tools(self) -> dict[str, Any]:
        """Seat-isolated callables. Skeptic never writes; engineer is gated."""
        ctx = self.context
        workspace = self._workspace()

        def read_file(path: str) -> str:
            rel = path.strip() or "."
            text = workspace.read_file(rel)
            if not text.startswith("ERROR:"):
                ctx.reads.append(rel)
            return text

        def list_files(directory: str = ".") -> str:
            text = workspace.list_files(directory)
            if not text.startswith("ERROR:"):
                ctx.reads.append(directory)
            return text

        def write_file(path: str, content: str) -> str:
            ok, reason = ctx.engineer_gate(payload=f"{path}\n{content}")
            if not ok:
                return reason
            rel = path.strip()
            result = workspace.write_file(rel, content)
            if result.startswith("OK:"):
                ctx.writes.append(rel)
            return result

        def implement(task: str) -> str:
            ok, reason = ctx.engineer_gate(payload=task)
            if not ok:
                return reason
            quoted = ctx.quoted_issue
            clause = pr_fixes_clause(quoted)
            return (
                f"ENGINEER implementing to Success.\n"
                f"Quoted Issue #{quoted.number if quoted else '?'}.\n"
                f"Feasibility: {ctx.feasibility or 'stated in prompt'}.\n"
                f"Task: {task}\n"
                f"PR: {clause}"
            )

        def quote_issue(text: str) -> str:
            ctx.refresh_from_text(text)
            quoted = ctx.quoted_issue
            if quoted is None or not quoted.is_complete():
                return (
                    "CoS: Issue is not quoted. Need Intent, Success, "
                    "Constraints, Owner before the engineer may start."
                )
            ok, reason = hygiene_ok(text)
            if not ok:
                return reason
            return (
                f"CoS quoted Issue #{quoted.number or '?'}:\n"
                f"Intent: {quoted.intent}\n"
                f"Success: {quoted.success}\n"
                f"Constraints: {quoted.constraints}\n"
                f"Owner: {quoted.owner}\n"
                f"PR: {pr_fixes_clause(quoted)}"
            )

        def unblock_skeptic() -> str:
            ctx.skeptic_unblocked = True
            return "CoS unblocked skeptic for look-only review (still no writes)."

        def review(
            work: str,
            tests: str = "",
            visual: str = "",
            deviations: str = "",
            payload: str = "",
        ) -> str:
            if not ctx.skeptic_unblocked:
                return SKEPTIC_LOOK_ONLY
            return skeptic_verdict(
                quoted=ctx.quoted_issue,
                work=work,
                tests_note=tests,
                visual_note=visual,
                deviations=deviations,
                payload=payload,
            )

        def skeptic_write(_path: str = "", _content: str = "") -> str:
            return SKEPTIC_NO_WRITE

        return {
            "read_file": read_file,
            "list_files": list_files,
            "write_file": write_file,
            "implement": implement,
            "quote_issue": quote_issue,
            "unblock_skeptic": unblock_skeptic,
            "review": review,
            "skeptic_write": skeptic_write,
        }

    def _as_function_tools(self, raw: dict[str, Any]) -> dict[str, Any]:
        try:
            from agents import function_tool
        except ImportError:
            return raw

        wrapped: dict[str, Any] = {}

        @function_tool
        def read_file(path: str) -> str:
            """Read a workspace file (look-only)."""
            return raw["read_file"](path)

        @function_tool
        def list_files(directory: str = ".") -> str:
            """List workspace files (look-only)."""
            return raw["list_files"](directory)

        @function_tool
        def write_file(path: str, content: str) -> str:
            """Engineer write. Blocked without a quoted Issue + feasibility."""
            return raw["write_file"](path, content)

        @function_tool
        def implement(task: str) -> str:
            """Engineer implement-to-Success. Blocked without a quoted Issue."""
            return raw["implement"](task)

        @function_tool
        def quote_issue(text: str) -> str:
            """CoS: extract Intent/Success/Constraints/Owner from an Issue."""
            return raw["quote_issue"](text)

        @function_tool
        def unblock_skeptic() -> str:
            """CoS: allow the skeptic to issue a look-only verdict."""
            return raw["unblock_skeptic"]()

        @function_tool
        def review(
            work: str,
            tests: str = "",
            visual: str = "",
            deviations: str = "",
            payload: str = "",
        ) -> str:
            """Skeptic: four checks + tests + hygiene. FAIL on a leak. Text-only."""
            return raw["review"](work, tests, visual, deviations, payload)

        wrapped.update(
            {
                "read_file": read_file,
                "list_files": list_files,
                "write_file": write_file,
                "implement": implement,
                "quote_issue": quote_issue,
                "unblock_skeptic": unblock_skeptic,
                "review": review,
            }
        )
        return wrapped

    def _build_agents(self) -> dict[str, Any]:
        """CoS coordinator + engineer/skeptic as_tool (and handoff when available)."""
        if self._agents:
            return self._agents
        raw = self._build_tools()
        tools = self._as_function_tools(raw)

        def _tools(*names: str) -> list[Any]:
            return [tools[n] for n in names if n in tools]

        try:
            engineer = self._make_agent(
                "engineer",
                ENGINEER_INSTRUCTIONS,
                _tools("read_file", "list_files", "write_file", "implement"),
            )
            skeptic = self._make_agent(
                "skeptic",
                SKEPTIC_INSTRUCTIONS,
                _tools("read_file", "list_files", "review"),
            )
            attach_classifier_tools(skeptic, "skeptic")
            talk_to = self._cfg().get("talk_to") or SEAT_COS
            cos = self._make_agent(
                "coding-requirements-gate",
                COS_INSTRUCTIONS,
                _tools("quote_issue", "unblock_skeptic"),
            )
            cos.tools = list(getattr(cos, "tools", None) or [])
            if hasattr(engineer, "as_tool"):
                for tool_name in ("consult_engineer", "engineer"):
                    cos.tools.append(
                        engineer.as_tool(
                            tool_name=tool_name,
                            tool_description=(
                                "Use the engineer seat as a tool. Engineer is blocked "
                                "without a quoted Issue + feasibility."
                            ),
                        )
                    )
            if hasattr(skeptic, "as_tool"):
                for tool_name in ("consult_skeptic", "skeptic"):
                    cos.tools.append(
                        skeptic.as_tool(
                            tool_name=tool_name,
                            tool_description=(
                                "Use the skeptic seat as a tool for look-only "
                                "PASS/FAIL review. Skeptic does not write code."
                            ),
                        )
                    )
            try:
                from agents import handoff

                existing = list(getattr(cos, "handoffs", None) or [])
                existing.extend(
                    [
                        handoff(engineer),
                        handoff(skeptic),
                    ]
                )
                cos.handoffs = existing
            except Exception as exc:
                logger.debug("software_dev handoff wiring skipped: %s", exc)

            self._agents = {
                SEAT_COS: cos,
                "coding-requirements-gate": cos,
                SEAT_ENGINEER: engineer,
                SEAT_SKEPTIC: skeptic,
                "talk_to": talk_to,
                "_raw_tools": raw,
            }
        except Exception as exc:
            logger.debug("software_dev agent wiring skipped: %s", exc)
            self._agents = {"_raw_tools": raw}
        return self._agents

    def _last_user_text(self, messages: list[dict[str, Any]]) -> str:
        for m in reversed(messages or []):
            if (m.get("role") or "user") == "user" and m.get("content"):
                return str(m["content"]).strip()
        return support.render_prompt(messages).strip()

    def _parse(self, messages: list[dict[str, Any]]) -> tuple[str, str, str]:
        """Return (seat, action, remainder)."""
        params = dict(self._params)
        seat = str(params.get("seat") or "").strip().lower()
        action = str(params.get("action") or "").strip().lower()
        text = self._last_user_text(messages)
        if params.get("issue"):
            self.context.refresh_from_text(str(params["issue"]), params.get("feasibility"))
        elif text:
            self.context.refresh_from_text(text, params.get("feasibility"))
        if params.get("feasibility"):
            self.context.feasibility = str(params["feasibility"])
        if params.get("unblock_skeptic") or params.get("skeptic_unblocked"):
            self.context.skeptic_unblocked = True

        if seat or action:
            if not seat:
                if action in ("implement", "write"):
                    seat = SEAT_ENGINEER
                elif action in ("review", "verdict"):
                    seat = SEAT_SKEPTIC
                else:
                    seat = SEAT_COS
            if not action:
                action = "status"
            return seat, action, text

        parts = text.split(None, 1)
        head = (parts[0].lower() if parts else "status").rstrip(":")
        rest = parts[1] if len(parts) > 1 else ""
        if head in ("status", "seats", "who"):
            return SEAT_COS, "status", rest
        if head in ("quote", "gate"):
            return SEAT_COS, "quote", rest or text
        if head in ("implement", "write"):
            return SEAT_ENGINEER, "implement", rest
        if head in ("review", "verdict"):
            return SEAT_SKEPTIC, "review", rest
        # Issue-first bodies and other non-grammar prompts are live CoS turns.
        # Mapping them to quote/status used to skip Runner.run (Issue #150).
        return SEAT_COS, ACTION_CHAT, text

    def _status_text(self) -> str:
        agents = self._build_agents()
        coord = agents.get(SEAT_COS)
        tool_names = []
        for tool in getattr(coord, "tools", []) or []:
            tool_names.append(getattr(tool, "name", None) or getattr(tool, "__name__", ""))
        handoffs = getattr(coord, "handoffs", None) or []
        workspace = self._workspace()
        return (
            "software_dev team (custom blueprint, not extra Grok seats)\n"
            f"talk-to: CoS / coding-requirements-gate\n"
            f"seats: {', '.join(SEATS)}\n"
            f"wiring: openai-agents as_tool ({', '.join(str(n) for n in tool_names) or 'none'})\n"
            f"handoffs: {len(handoffs)}\n"
            f"workspace: {workspace.label()}\n"
            f"{workspace.locality_note()}\n"
            "engineer blocked without quoted Issue + feasibility\n"
            "skeptic look-only; text-only PASS/FAIL; does not write code\n"
            "hygiene: placeholders only; skeptic FAILs on a leak"
        )

    def _run_seat(self, seat: str, action: str, text: str) -> str:
        agents = self._build_agents()
        raw = agents.get("_raw_tools") or self._build_tools()
        params = dict(self._params)

        if seat == SEAT_ENGINEER and action in ("implement", "write"):
            ok, reason = engineer_may_start(
                self.context.source_text or text,
                feasibility=self.context.feasibility or params.get("feasibility"),
            )
            if not ok:
                return reason
            path = str(params.get("path") or "").strip()
            content = params.get("content")
            if path and content is not None:
                return raw["write_file"](path, str(content))
            return raw["implement"](text or str(params.get("task") or "implement Success"))

        if seat == SEAT_SKEPTIC:
            if action in ("write", "implement", "write_file") or params.get("path"):
                return raw["skeptic_write"]()
            return raw["review"](
                params.get("work") or text,
                str(params.get("tests") or ""),
                str(params.get("visual") or ""),
                str(params.get("deviations") or ""),
                str(params.get("payload") or params.get("diff") or ""),
            )

        if action == "quote":
            return raw["quote_issue"](params.get("issue") or text)
        if action == "unblock":
            return raw["unblock_skeptic"]()
        return self._status_text()

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        agents = self._build_agents()
        seat, action, text = self._parse(messages)
        test_mode = os.environ.get("SWARM_TEST_MODE", "").lower() in ("1", "true", "yes")
        deterministic = (
            test_mode
            or params_select_router(self._params)
            or action in _DETERMINISTIC_ACTIONS
        )

        if deterministic:
            body = self._run_seat(seat, action, text)
            yield support.message_chunk(
                body,
                final=True,
                meta=support.backend_meta(["software_dev", seat]),
            )
            return

        coordinator = agents.get(SEAT_COS)
        if coordinator is None:
            yield support.message_chunk(
                self._status_text(),
                final=True,
                meta=support.backend_meta(["software_dev"]),
            )
            return

        try:
            from agents import Runner

            result = await Runner.run(coordinator, text)
            content = getattr(result, "final_output", None) or str(result)
        except Exception as exc:
            logger.warning("software_dev Runner failed; falling back to CoS status: %s", exc)
            content = self._status_text() + f"\n(coordinator unavailable: {exc})"
        yield support.message_chunk(
            str(content),
            final=True,
            meta=support.backend_meta(["software_dev"]),
        )


# Re-export for tests that import policy helpers via the blueprint package.
__all__ = [
    "ACTION_CHAT",
    "SoftwareDevBlueprint",
    "engineer_may_start",
    "extract_quoted_issue",
    "params_select_router",
    "seat_tool_policy",
]

"""Gate role: classify a pending tool call as dangerous or not.

Wiring is **default-open** (fail-open when unwired):

* No gate agent on the team → every tool call is approved and the user is
  **never** elicited.
* A ``gate`` / ``tool_gate`` role actually wired → the agent investigates,
  then **must** call ``submit_gate_verdict`` (REQ-108). Prose is never a
  verdict. Missing tool → continue nudges, then fail closed (dangerous /
  needs-human / block). Dangerous calls elicit user approval.

This is openai-agents handoff / agent-as-tool — not an extra Grok/OMB/Rakazo
seat. The Support agent (REQ-7) may *talk* about the gate; this module is the
runtime wiring.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from swarm.core.agent_roles import (
    ROLE_GATE,
    attach_role,
    find_role_agent,
    normalize_agent_role,
)
from swarm.core.classifier_verdict import (
    GATE_INSTRUCTIONS,
    GATE_VERDICT_TOOL,
    attach_classifier_tools,
    run_classifier_until_verdict,
)

logger = logging.getLogger(__name__)

GATE_ROLE = ROLE_GATE
BELAY_ROLE = ROLE_GATE

_DANGEROUS_TOKENS = frozenset({"YES", "Y", "DANGEROUS", "TRUE", "1"})
_SAFE_TOKENS = frozenset({"NO", "N", "SAFE", "FALSE", "0"})

ClassifyFn = Callable[[str, dict[str, Any]], bool]
ElicitFn = Callable[[str, dict[str, Any]], bool]
InvokeFn = Callable[[Any, str], Any]


@dataclass
class GateVerdict:
    """Structured danger classification from ``submit_gate_verdict`` (or fail-closed)."""

    dangerous: bool
    raw: str = ""
    elicited: bool = False
    approved: bool = True
    prompted: bool = False
    failed_closed: bool = False
    needs_human: bool = False
    nudges: int = 0
    reason: str = ""
    tool_name: str = GATE_VERDICT_TOOL


@dataclass
class ToolGate:
    """Optional gate agent bound to a team. ``agent is None`` means unwired."""

    agent: Any = None
    classify_fn: ClassifyFn | None = None
    invoke_fn: InvokeFn | None = None
    elicit_fn: ElicitFn | None = None
    consultations: list[dict[str, Any]] = field(default_factory=list)

    @property
    def wired(self) -> bool:
        return self.agent is not None or self.classify_fn is not None

    def classify(self, tool_name: str, arguments: dict[str, Any] | None = None) -> GateVerdict:
        return classify_pending_tool_call(
            gate=self.agent,
            tool_name=tool_name,
            arguments=arguments,
            classify_fn=self.classify_fn,
            invoke_fn=self.invoke_fn,
            trace=self.consultations,
        )

    def approve(self, tool_name: str, arguments: dict[str, Any] | None = None) -> GateVerdict:
        return approve_pending_tool_call(
            gate=self.agent,
            tool_name=tool_name,
            arguments=arguments,
            classify_fn=self.classify_fn,
            invoke_fn=self.invoke_fn,
            elicit_fn=self.elicit_fn,
            trace=self.consultations,
        )


def parse_gate_token(text: Any) -> bool:
    """Parse a structured yes/no as *dangerous*.

    Kept for programmatic ``classify_fn`` / fixture dicts. The live classifier
    path (REQ-108) does **not** scrape the last assistant message.
    """
    if isinstance(text, bool):
        return text
    if isinstance(text, dict):
        for key in ("dangerous", "is_dangerous", "yes", "deny"):
            if key in text:
                return bool(text[key])
        if "approved" in text:
            return not bool(text["approved"])
        text = text.get("token") or text.get("answer") or text.get("content") or ""
    raw = str(text or "").strip()
    parts = raw.split()
    if not parts:
        return False
    token = parts[0].upper().strip(".,!?;:\"'")
    if token in _DANGEROUS_TOKENS:
        return True
    if token in _SAFE_TOKENS:
        return False
    # Ambiguous prose from a live model: not dangerous (do not fail closed).
    return False


def _gate_prompt(tool_name: str, arguments: dict[str, Any] | None) -> str:
    return (
        "Is this pending tool call dangerous?\n"
        f"Tool: {tool_name}\n"
        f"Arguments: {arguments or {}}\n"
        f"When finished, call `{GATE_VERDICT_TOOL}` "
        '(verdict="yes" if dangerous, verdict="no" if not). '
        "Do not finish with prose."
    )


def _invoke_gate_agent(
    gate: Any,
    prompt: str,
    *,
    invoke_fn: InvokeFn | None = None,
) -> Any:
    """Consult the gate until ``submit_gate_verdict`` or fail closed."""
    return run_classifier_until_verdict(
        agent=gate,
        prompt=prompt,
        role="gate",
        invoke_fn=invoke_fn,
    )


def classify_pending_tool_call(
    *,
    gate: Any = None,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    classify_fn: ClassifyFn | None = None,
    invoke_fn: InvokeFn | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> GateVerdict:
    """Return whether *tool_name* is dangerous. Unwired → not dangerous."""
    args = arguments or {}
    if classify_fn is None and gate is None:
        verdict = GateVerdict(dangerous=False, raw="UNWIRED", approved=True)
        if trace is not None:
            trace.append({"tool": tool_name, "wired": False, "dangerous": False})
        return verdict
    raw = ""
    failed_closed = False
    needs_human = False
    nudges = 0
    reason = ""
    try:
        if classify_fn is not None:
            dangerous = bool(classify_fn(tool_name, args))
            raw = "YES" if dangerous else "NO"
        else:
            turn = _invoke_gate_agent(gate, _gate_prompt(tool_name, args), invoke_fn=invoke_fn)
            payload = getattr(turn, "payload", None) or {}
            dangerous = bool(payload.get("dangerous", True))
            raw = getattr(turn, "raw", None) or str(payload)
            failed_closed = bool(getattr(turn, "failed_closed", False))
            needs_human = bool(payload.get("needs_human") or failed_closed)
            nudges = int(getattr(turn, "nudges", 0) or 0)
            reason = str(payload.get("reason") or "")
            if failed_closed:
                # Fail closed: treat as dangerous / needs-human. Never parse prose.
                dangerous = True
    except Exception as exc:
        logger.info("wired gate failed to classify %s (%s); treating as dangerous", tool_name, exc)
        dangerous = True
        raw = f"ERROR: {exc}"
        failed_closed = True
        needs_human = True
    verdict = GateVerdict(
        dangerous=dangerous,
        raw=str(raw),
        failed_closed=failed_closed,
        needs_human=needs_human,
        nudges=nudges,
        reason=reason,
    )
    if trace is not None:
        trace.append({
            "tool": tool_name,
            "wired": True,
            "dangerous": dangerous,
            "raw": verdict.raw,
            "failed_closed": failed_closed,
            "nudges": nudges,
        })
    return verdict


def approve_pending_tool_call(
    *,
    gate: Any = None,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    classify_fn: ClassifyFn | None = None,
    invoke_fn: InvokeFn | None = None,
    elicit_fn: ElicitFn | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> GateVerdict:
    """Approve a pending tool call.

    Unwired (no gate and no classify_fn): approved, **elicit_fn is not called**.
    Wired + not dangerous: approved, no prompt.
    Wired + dangerous: ``elicit_fn`` is called; missing elicit → denied.
    """
    args = arguments or {}
    unwired = gate is None and classify_fn is None
    if unwired:
        # Default-open: never prompt when no gate is wired to the team.
        verdict = GateVerdict(dangerous=False, raw="UNWIRED", approved=True, prompted=False)
        if trace is not None:
            trace.append({
                "tool": tool_name,
                "wired": False,
                "prompted": False,
                "approved": True,
            })
        return verdict

    classified = classify_pending_tool_call(
        gate=gate,
        tool_name=tool_name,
        arguments=args,
        classify_fn=classify_fn,
        invoke_fn=invoke_fn,
        trace=None,
    )
    if not classified.dangerous:
        classified.approved = True
        classified.prompted = False
        if trace is not None:
            trace.append({
                "tool": tool_name,
                "wired": True,
                "dangerous": False,
                "prompted": False,
                "approved": True,
                "raw": classified.raw,
            })
        return classified

    prompted = False
    approved = False
    if elicit_fn is not None:
        prompted = True
        approved = bool(elicit_fn(tool_name, args))
    classified.prompted = prompted
    classified.elicited = prompted
    classified.approved = approved
    if trace is not None:
        trace.append({
            "tool": tool_name,
            "wired": True,
            "dangerous": True,
            "prompted": prompted,
            "approved": approved,
            "raw": classified.raw,
        })
    return classified


def tool_gate_from_team(
    agents: Any,
    *,
    classify_fn: ClassifyFn | None = None,
    invoke_fn: InvokeFn | None = None,
    elicit_fn: ElicitFn | None = None,
) -> ToolGate:
    """Build a ``ToolGate`` from a team roster. Missing gate → unwired."""
    return ToolGate(
        agent=find_role_agent(agents, ROLE_GATE),
        classify_fn=classify_fn,
        invoke_fn=invoke_fn,
        elicit_fn=elicit_fn,
    )


def attach_gate_as_tool(coordinator: Any, gate: Any) -> Any:
    """Expose the gate on the coordinator via openai-agents ``as_tool``.

    Classification still goes through :func:`approve_pending_tool_call` so a
    coordinator that forgets to call the tool cannot bypass the wrapper path.
    """
    if coordinator is None or gate is None:
        return coordinator
    attach_role(gate, ROLE_GATE)
    attach_classifier_tools(gate, "gate")
    as_tool = getattr(gate, "as_tool", None)
    if not callable(as_tool):
        return coordinator
    try:
        tool = as_tool(
            tool_name=getattr(gate, "name", None) or "gate",
            tool_description=(
                "Classify a pending tool call as dangerous or not. "
                f"The gate finishes by calling {GATE_VERDICT_TOOL}."
            ),
        )
        tools = list(getattr(coordinator, "tools", None) or [])
        tools.append(tool)
        coordinator.tools = tools
    except Exception as exc:
        logger.debug("gate as_tool wiring skipped: %s", exc)
    return coordinator


def gate_wrap_callable(
    fn: Callable[..., Any],
    *,
    tool_name: str,
    gate: Any = None,
    classify_fn: ClassifyFn | None = None,
    invoke_fn: InvokeFn | None = None,
    elicit_fn: ElicitFn | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> Callable[..., Any]:
    """Wrap a callable so a wired gate classifies it before it runs.

    Unwired gate: the wrapper is a no-op passthrough (still no elicit).
    """
    if gate is None and classify_fn is None:
        return fn

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        verdict = approve_pending_tool_call(
            gate=gate,
            tool_name=tool_name,
            arguments={"args": args, "kwargs": kwargs},
            classify_fn=classify_fn,
            invoke_fn=invoke_fn,
            elicit_fn=elicit_fn,
            trace=trace,
        )
        if not verdict.approved:
            return f"DENIED: tool call {tool_name!r} was not approved"
        return fn(*args, **kwargs)

    wrapped.__name__ = getattr(fn, "__name__", tool_name)
    wrapped.__doc__ = getattr(fn, "__doc__", None)
    return wrapped


def wrap_tools_with_gate(
    tools: list[Any] | None,
    *,
    gate: Any = None,
    classify_fn: ClassifyFn | None = None,
    invoke_fn: InvokeFn | None = None,
    elicit_fn: ElicitFn | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> list[Any]:
    """Wrap a list of callables. Unwired → returned unchanged (no prompt)."""
    if not tools:
        return list(tools or [])
    if gate is None and classify_fn is None:
        return list(tools)
    wrapped: list[Any] = []
    for tool in tools:
        name = (
            getattr(tool, "name", None)
            or getattr(tool, "__name__", None)
            or type(tool).__name__
        )
        if callable(tool) and not hasattr(tool, "on_invoke_tool"):
            wrapped.append(
                gate_wrap_callable(
                    tool,
                    tool_name=str(name),
                    gate=gate,
                    classify_fn=classify_fn,
                    invoke_fn=invoke_fn,
                    elicit_fn=elicit_fn,
                    trace=trace,
                )
            )
        else:
            wrapped.append(tool)
    return wrapped


def is_gate_role(role: Any) -> bool:
    return normalize_agent_role(role) == ROLE_GATE


is_belay_role = is_gate_role

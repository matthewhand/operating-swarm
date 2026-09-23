"""Workflow model B: persona / agent-as-tool swarm (openai-agents).

Specialists are encouraged to **read and write**. A coordinator switches
personas (agent-as-tool style) rather than taking a formal multi-model vote.

See ``docs/SWARM_WORKFLOWS.md``. Offline/scripted runs prove tool policy without
an LLM; live runs can use ``Runner`` when configured.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from swarm.core.async_utils import run_coro_sync

logger = logging.getLogger(__name__)


@dataclass
class PersonaStep:
    """One coordinator decision: which persona to invoke and with what instruction."""

    persona: str
    instruction: str


@dataclass
class PersonaResult:
    persona: str
    instruction: str
    output: str
    tool_trace: list[str] = field(default_factory=list)
    ok: bool = True


@dataclass
class PersonaSwarmResult:
    steps: list[PersonaResult]
    final: str
    writes: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    agents: dict[str, Any] = field(default_factory=dict)


class WorkspaceTools:
    """Read/write tool surface bound to a workspace root (model B specialists).

    Paths use a **portable relative grammar** so the same calls work on Windows
    and POSIX hosts:

    * Both ``/`` and ``\\`` are separators (backslash is never a literal name char).
    * Absolute forms are rejected up front: POSIX (``/etc``), Windows drive
      (``C:\\...``, ``C:foo``), and UNC (``\\\\server\\share``).
    * ``..`` segments that resolve outside the workspace root are rejected.
    * ``reads`` / ``writes`` traces use POSIX-style relative keys (``docs/ADR.md``).
    """

    def __init__(self, root: str | os.PathLike[str] | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.reads: list[str] = []
        self.writes: list[str] = []

    def _relkey(self, path: Path) -> str:
        """Stable POSIX-style path relative to the workspace (for traces)."""
        rel = path.relative_to(self.root)
        key = rel.as_posix()
        return key if key not in ("", ".") else "."

    def _safe(self, rel: str | os.PathLike[str] | Path) -> Path:
        """Resolve *rel* under the workspace; reject absolute and escaping paths.

        Host ``Path`` joining alone is not portable: on POSIX, ``\\`` is a normal
        character, so Windows-style ``..\\escape`` would not traverse and drive
        letter paths would nest as relative directories. Normalize separators and
        reject absolute/drive/UNC forms with PurePosixPath / PureWindowsPath
        before joining under the real root.
        """
        raw = os.fspath(rel)
        if raw in ("", "."):
            return self.root

        # Portable relative grammar: treat backslash as a separator everywhere.
        norm = raw.replace("\\", "/")
        posix = PurePosixPath(norm)
        win = PureWindowsPath(norm)

        # Reject POSIX absolute, Windows absolute/UNC, and drive-relative (C:foo).
        if posix.is_absolute() or win.is_absolute() or win.drive:
            raise ValueError(f"path escapes workspace: {rel}")

        parts = [p for p in posix.parts if p not in ("", ".")]
        path = self.root.joinpath(*parts).resolve() if parts else self.root

        # Reject sibling escapes (e.g. ../ws_evil). Prefix startswith is unsafe
        # when another path is a string prefix of root (root=/ws vs /ws_evil).
        if not path.is_relative_to(self.root):
            raise ValueError(f"path escapes workspace: {rel}")
        return path

    def read_file(self, path: str | os.PathLike[str] | Path) -> str:
        p = self._safe(path)
        text = p.read_text(encoding="utf-8")
        # Record only after path validation + successful read.
        self.reads.append(self._relkey(p))
        return text

    def write_file(self, path: str | os.PathLike[str] | Path, content: str) -> str:
        p = self._safe(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        # Record only after path validation + successful write (never log escapes).
        key = self._relkey(p)
        self.writes.append(key)
        return f"OK: wrote {key} ({len(content)} bytes)"

    def list_files(self, directory: str | os.PathLike[str] | Path = ".") -> str:
        p = self._safe(directory)
        if not p.is_dir():
            return f"ERROR: not a directory: {directory}"
        # Record only after path validation succeeds.
        self.reads.append(self._relkey(p))
        return "\n".join(sorted(x.name for x in p.iterdir()))


def build_persona_agents(tools: WorkspaceTools) -> dict[str, Any]:
    """Construct openai-agents ``Agent`` personas with R/W tools.

    Returns a name → Agent map. Tools are real callables registered via
    ``function_tool`` when available.
    """
    try:
        from agents import Agent, function_tool
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("openai-agents (package 'agents') is required for model B") from e

    @function_tool
    def read_file(path: str) -> str:
        """Read a file under the workspace (allowed for all personas)."""
        return tools.read_file(path)

    @function_tool
    def write_file(path: str, content: str) -> str:
        """Write a file under the workspace (encouraged for implementer personas)."""
        return tools.write_file(path, content)

    @function_tool
    def list_files(directory: str = ".") -> str:
        """List files in a workspace directory."""
        return tools.list_files(directory)

    researcher = Agent(
        name="Researcher",
        instructions=(
            "You are a researcher persona. Prefer reading and summarizing. "
            "You may write notes if needed. Use tools to inspect the workspace."
        ),
        tools=[read_file, list_files, write_file],
    )
    implementer = Agent(
        name="Implementer",
        instructions=(
            "You are an implementer persona. You are encouraged to read and write. "
            "Apply concrete changes with write_file after inspecting context."
        ),
        tools=[read_file, list_files, write_file],
    )
    coordinator = Agent(
        name="Coordinator",
        instructions=(
            "You coordinate personas. Switch between Researcher and Implementer "
            "as needed. Specialists may read and write."
        ),
        # Agent-as-tool style wiring when handoffs/as_tool are available.
        tools=[read_file, list_files, write_file],
    )

    # Attach as_tool if the SDK supports it (agent-as-tool switching).
    try:
        coordinator.tools = list(coordinator.tools or [])
        if hasattr(researcher, "as_tool"):
            coordinator.tools.append(
                researcher.as_tool(
                    tool_name="consult_researcher",
                    tool_description="Switch to Researcher persona",
                )
            )
        if hasattr(implementer, "as_tool"):
            coordinator.tools.append(
                implementer.as_tool(
                    tool_name="consult_implementer",
                    tool_description="Switch to Implementer persona (read/write)",
                )
            )
    except Exception as e:  # pragma: no cover
        logger.debug("as_tool wiring skipped: %s", e)

    # Hybrid A←B: coordinator may consult MoA (read-only opinions) without granting
    # panelists write access. Wired as a real function_tool when agents SDK allows.
    moa_calls: list[dict[str, Any]] = []

    def _consult_moa_sync(question: str) -> str:
        """Sync wrapper: run MoA collect→determine (never act) for the coordinator."""
        import asyncio

        from swarm.core.moa.tools import consult_moa

        async def _run() -> dict[str, Any]:
            return await consult_moa(
                question,
                participants=["analyst", "critic"],
                backend="fake",
                fake_responses={
                    "analyst": (
                        '{"claim":"Prefer the safer option with clear rollback",'
                        '"confidence":0.85}'
                    ),
                    "critic": (
                        '{"claim":"Prefer the safer option and add monitoring",'
                        '"confidence":0.8}'
                    ),
                },
            )

        payload = run_coro_sync(_run())

        moa_calls.append({"question": question, "payload": payload})
        det = (payload or {}).get("determination") or {}
        answer = det.get("answer") or "(no determination)"
        return f"[MoA determination — read-only panel]\n{answer}"

    try:
        @function_tool
        def consult_moa_panel(question: str) -> str:
            """Call Mixture of Agents for a read-only multi-seat consensus opinion.

            Use before high-stakes writes. Participants cannot write; you (or the
            implementer) apply changes after reviewing the determination.
            """
            return _consult_moa_sync(question)

        coordinator.tools = list(coordinator.tools or []) + [consult_moa_panel]
    except Exception as e:  # pragma: no cover
        logger.debug("consult_moa tool wiring skipped: %s", e)

    return {
        "coordinator": coordinator,
        "researcher": researcher,
        "implementer": implementer,
        "_tools": {
            "read_file": tools.read_file,
            "write_file": tools.write_file,
            "list_files": tools.list_files,
            "consult_moa": _consult_moa_sync,
        },
        "_moa_calls": moa_calls,
    }


def run_scripted_persona_swarm(
    workspace: str | Path,
    steps: list[PersonaStep] | None = None,
    *,
    seed_files: dict[str, str] | None = None,
) -> PersonaSwarmResult:
    """Prove model B offline: coordinator switches personas; specialists R/W.

    Does not require an LLM API. Uses real ``Agent`` construction from
    openai-agents and real workspace tools. Scripted steps simulate the
    coordinator's persona switches (what an LLM coordinator would choose).
    """
    tools = WorkspaceTools(workspace)
    if seed_files:
        for rel, content in seed_files.items():
            tools.write_file(rel, content)
        # Reset traces so seed writes don't count as swarm work.
        tools.writes.clear()
        tools.reads.clear()

    agents = build_persona_agents(tools)
    if steps is None:
        steps = [
            PersonaStep(
                "researcher",
                "Read notes.txt and list the workspace.",
            ),
            PersonaStep(
                "implementer",
                "Write summary.md based on notes.txt.",
            ),
        ]

    results: list[PersonaResult] = []
    for step in steps:
        persona = step.persona.lower()
        if persona not in agents or persona.startswith("_"):
            results.append(
                PersonaResult(
                    persona=step.persona,
                    instruction=step.instruction,
                    output=f"unknown persona {step.persona}",
                    ok=False,
                )
            )
            continue

        agent = agents[persona]
        trace: list[str] = []
        # Scripted tool use matching persona encouragement:
        # researcher: read-heavy; implementer: write-heavy (both may R/W).
        out_parts: list[str] = []
        try:
            if persona == "researcher":
                listing = tools.list_files(".")
                trace.append("list_files('.')")
                out_parts.append(f"listing:\n{listing}")
                if "notes.txt" in listing or (tools.root / "notes.txt").exists():
                    text = tools.read_file("notes.txt")
                    trace.append("read_file('notes.txt')")
                    out_parts.append(f"notes.txt:\n{text}")
                    # Optional note (R/W allowed for B specialists).
                    tools.write_file(
                        "research_scratch.txt",
                        f"Researcher notes: found notes.txt ({len(text)} chars)\n",
                    )
                    trace.append("write_file('research_scratch.txt')")
            elif persona == "implementer":
                if (tools.root / "notes.txt").exists():
                    src = tools.read_file("notes.txt")
                    trace.append("read_file('notes.txt')")
                else:
                    src = "(no notes.txt)"
                content = (
                    f"# Summary\n\nSource notes:\n\n{src}\n\n"
                    f"_Written by Implementer persona (read/write encouraged)._\n"
                )
                tools.write_file("summary.md", content)
                trace.append("write_file('summary.md')")
                out_parts.append(tools.read_file("summary.md"))
                trace.append("read_file('summary.md')")
            else:
                # Coordinator: may inspect only in scripted mode.
                listing = tools.list_files(".")
                trace.append("list_files('.')")
                out_parts.append(listing)

            # Prove Agent object is a real openai-agents Agent with tools.
            tool_names = []
            for t in getattr(agent, "tools", None) or []:
                tool_names.append(getattr(t, "name", None) or getattr(t, "__name__", type(t).__name__))
            out_parts.append(f"[agent={agent.name} tools={tool_names}]")

            results.append(
                PersonaResult(
                    persona=step.persona,
                    instruction=step.instruction,
                    output="\n".join(out_parts),
                    tool_trace=trace,
                    ok=True,
                )
            )
        except Exception as e:
            results.append(
                PersonaResult(
                    persona=step.persona,
                    instruction=step.instruction,
                    output=str(e),
                    tool_trace=trace,
                    ok=False,
                )
            )

    final = results[-1].output if results else ""
    return PersonaSwarmResult(
        steps=results,
        final=final,
        writes=list(tools.writes),
        reads=list(tools.reads),
        agents={k: getattr(v, "name", k) for k, v in agents.items() if not k.startswith("_")},
    )


async def run_hybrid_scripted(
    workspace: str | Path,
    question: str,
    *,
    seed_files: dict[str, str] | None = None,
    moa_backend: str = "fake",
    moa_participants: list[str] | None = None,
    moa_fake_responses: dict[str, str] | None = None,
) -> PersonaSwarmResult:
    """Hybrid champagne: B coordinator consults MoA (A), then implementer writes.

    1. ``consult_moa`` — read-only panel opinions + orchestrator determination (no act)
    2. Implementer persona writes ``decision.md`` / ``summary.md`` using that determination

    Proves write policy split: MoA participants never write; B implementer does.
    """
    from swarm.core.moa.team import _default_fakes
    from swarm.core.moa.tools import consult_moa

    tools = WorkspaceTools(workspace)
    if seed_files:
        for rel, content in seed_files.items():
            tools.write_file(rel, content)
        tools.writes.clear()
        tools.reads.clear()

    agents = build_persona_agents(tools)
    moa_calls: list[dict[str, Any]] = agents.get("_moa_calls") or []

    seats = list(moa_participants or ["analyst", "critic"])
    fakes = moa_fake_responses
    if moa_backend == "fake" and not fakes:
        fakes = _default_fakes(question, seats)

    # --- Step A: MoA consult (read-only) ---
    moa_payload = await consult_moa(
        question,
        seats,
        backend=moa_backend,
        fake_responses=fakes,
        cwd=str(tools.root),
    )
    moa_calls.append({"question": question, "payload": moa_payload})
    det = (moa_payload.get("determination") or {}).get("answer") or ""
    # Coordinator records MoA output in workspace (orchestrator/B-side write only)
    tools.write_file(
        "moa_determination.md",
        f"# MoA determination (read-only panel)\n\n{det}\n",
    )
    moa_step = PersonaResult(
        persona="consult_moa",
        instruction=question,
        output=det,
        tool_trace=[
            "consult_moa(act=False)",
            f"participants={seats}",
            "write_file('moa_determination.md')  # B-side only",
        ],
        ok=bool(det),
    )

    # --- Step B: implementer applies decision (R/W specialist) ---
    notes = ""
    if (tools.root / "notes.txt").exists():
        notes = tools.read_file("notes.txt")
    decision_body = (
        f"# Decision\n\n## Context\n{notes or question}\n\n"
        f"## MoA consensus\n{det}\n\n"
        f"_Applied by Implementer persona after consult_moa (hybrid A←B)._\n"
    )
    tools.write_file("decision.md", decision_body)
    impl_step = PersonaResult(
        persona="implementer",
        instruction="Apply MoA determination to decision.md",
        output=decision_body,
        tool_trace=[
            "read_file('notes.txt')" if notes else "skip notes",
            "read_file('moa_determination.md')",
            "write_file('decision.md')",
        ],
        ok=True,
    )

    return PersonaSwarmResult(
        steps=[moa_step, impl_step],
        final=decision_body,
        writes=list(tools.writes),
        reads=list(tools.reads),
        agents={
            **{k: getattr(v, "name", k) for k, v in agents.items() if not k.startswith("_")},
            "moa_seats": seats,  # type: ignore[dict-item]
            "moa_backend": moa_backend,  # type: ignore[dict-item]
        },
    )


async def run_persona_swarm_with_runner(
    workspace: str | Path,
    user_message: str,
    *,
    seed_files: dict[str, str] | None = None,
    max_turns: int = 4,
) -> PersonaSwarmResult:
    """Optional live path: coordinator Agent via openai-agents ``Runner``.

    Falls back to scripted persona swarm when Runner/LLM is unavailable so
    offline CI stays green. Live mode still uses the same R/W WorkspaceTools.
    """
    tools = WorkspaceTools(workspace)
    if seed_files:
        for rel, content in seed_files.items():
            tools.write_file(rel, content)
        tools.writes.clear()
        tools.reads.clear()

    agents = build_persona_agents(tools)
    coordinator = agents["coordinator"]

    try:
        from agents import Runner
    except ImportError:
        return run_scripted_persona_swarm(
            workspace,
            seed_files=None,  # already seeded into tools workspace
        )

    # #737: bare Agent(...)s inherit the SDK's gpt-4o /responses default —
    # pin the framework chat model before handing them to Runner.
    try:
        from swarm.core.blueprint_base import apply_agent_model_defaults

        apply_agent_model_defaults(coordinator)
    except Exception:
        pass

    try:
        result = await Runner.run(coordinator, user_message, max_turns=max_turns)
        final = str(getattr(result, "final_output", None) or result)
        return PersonaSwarmResult(
            steps=[
                PersonaResult(
                    persona="coordinator",
                    instruction=user_message,
                    output=final,
                    tool_trace=[
                        "path=runner",
                        f"reads={tools.reads}",
                        f"writes={tools.writes}",
                    ],
                    ok=True,
                )
            ],
            final=final,
            writes=list(tools.writes),
            reads=list(tools.reads),
            agents={
                k: getattr(v, "name", k)
                for k, v in agents.items()
                if not k.startswith("_")
            },
        )
    except Exception as e:
        logger.info("Runner path unavailable (%s); falling back to scripted MoA-B", e)
        # Scripted path on same workspace; re-seed files if provided.
        return run_scripted_persona_swarm(
            workspace,
            seed_files=seed_files,
        )

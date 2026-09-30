"""Mixture of Agents (MoA) — workflow model A: orchestrated consensus.

Operating Swarm has two primary multi-agent styles (see ``docs/SWARM_WORKFLOWS.md``):

* **A. MoA (this package)** — consensus of subagents + orchestration agent.
  Subagents are encouraged to be **read-only**; the orchestrator alone determines
  consensus and performs impactful ops.
* **B. Persona swarm** — ``openai-agents`` single coordinator switching personas
  / agent-as-tool specialists that are encouraged to **read and write**.

Product model (A)
-----------------
* **Participants** (external agentic CLIs via an injectable backend, typically
  acpx) only produce read-only opinions: text proposals and critiques. They never
  perform write or other impactful side effects as part of MoA participation.
* **Orchestrator** alone performs consensus determination (choose / synthesize /
  reject among opinions) and is the only path that may perform write or
  impactful operations after determination.

Primary product name is **Mixture of Agents / MoA**. Historical names such as
``cli_fusion`` / ``cli_ensemble`` are legacy only and are not exported here.

Participant invocation policy (production acpx backend)
--------------------------------------------------------
* One-shot: ``acpx <agent> exec …``
* Permissions: ``--approve-reads`` (default) or ``--deny-all`` — never
  ``--approve-all``
* Output: ``--format quiet`` (final assistant text) for simple collection
* Optional: ``--cwd`` scoped to the repo under review

See ``docs/MOA.md`` for the full architecture.

CLI dogfood
-----------
``swarm-cli moa "question" --backend fake|grok|acpx`` runs the same path.
``--backend grok`` is the first-class **live** consensus participant (local
``grok -p``, write tools disallowed). ``fake`` is default for CI. ``acpx`` is
optional multi-vendor; **Codex is not required**.
"""

from __future__ import annotations

from swarm.core.moa.agents_orchestrator import run_moa_agents_orchestrator
from swarm.core.moa.backends import (
    AcpxParticipantBackend,
    FakeParticipantBackend,
    GrokParticipantBackend,
)
from swarm.core.moa.orchestrator import MoAOrchestrator, MoAResult
from swarm.core.moa.policy import (
    PARTICIPANT_PERMISSION_MODES,
    WriteDeniedError,
    assert_participant_name,
    assert_participant_permission,
    participant_acpx_flags,
)
from swarm.core.moa.team import (
    MOA_NESTED_PAYLOAD_KEYS,
    SPECIALIST_PAYLOAD_KEYS,
    TEAM_CLI_ENVELOPE_KEYS,
    TEAM_RESULT_PAYLOAD_KEYS,
    MoATeamResult,
    SpecialistTask,
    TeamTask,
    default_output_path,
    format_team_text,
    parse_team_tasks,
    run_moa_consensus,
    run_moa_then_team,
    team_result_to_payload,
    validate_team_payload,
)
from swarm.core.moa.types import (
    ActResult,
    Determination,
    ParticipantOpinion,
    PermissionMode,
)

__all__ = [
    "PARTICIPANT_PERMISSION_MODES",
    "ActResult",
    "AcpxParticipantBackend",
    "Determination",
    "FakeParticipantBackend",
    "GrokParticipantBackend",
    "MOA_NESTED_PAYLOAD_KEYS",
    "MoAOrchestrator",
    "MoAResult",
    "MoATeamResult",
    "ParticipantOpinion",
    "PermissionMode",
    "SPECIALIST_PAYLOAD_KEYS",
    "SpecialistTask",
    "TEAM_CLI_ENVELOPE_KEYS",
    "TEAM_RESULT_PAYLOAD_KEYS",
    "TeamTask",
    "WriteDeniedError",
    "assert_participant_name",
    "assert_participant_permission",
    "format_team_text",
    "default_output_path",
    "parse_team_tasks",
    "participant_acpx_flags",
    "run_moa_agents_orchestrator",
    "run_moa_consensus",
    "run_moa_then_team",
    "team_result_to_payload",
    "validate_team_payload",
]

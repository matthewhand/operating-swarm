# Orchestration Patterns

Operating Swarm exposes each multi-agent orchestration pattern as a **blueprint** — a
`model` id you select from any OpenAI client. This page gives a sequence diagram
for each, its status, and the field-standard pattern it mirrors (the same set
Microsoft's Agent Framework names: sequential, concurrent, handoff, group-chat,
Magentic-One).

All diagrams are GitHub-rendered Mermaid. Backends shown (`gemini`, `claude`,
`grok`) are illustrative — any configured CLI fills any role.

> **The bundled blueprints are *examples*, not the product.** Operating Swarm is a
> **composition system**: you define your own personas and teams (via config or
> Django [`/agent-creator/`](../FEATURE_STATUS.md); the SPA Builder route is
> unmounted) and choose *how* consensus is invoked. The patterns below are
> the architectural primitives you compose from — see
> [Composing your own](#composing-your-own) and
> [Consensus invocation: always vs gated](#consensus-invocation--always-vs-gated).

| Blueprint | Pattern | Status |
|---|---|---|
| [`cli_agent`](#cli_agent--single-backend) | single agent + failover | ✅ built |
| [`cli_fusion`](#cli_fusion--concurrent-panel--judge) | concurrent (always consensus) | ✅ built |
| [`cli_orchestrator`](#cli_orchestrator--handoff--escalation) | handoff / **gated** consensus | ✅ built |
| [`cli_map`](#cli_map--map-reduce) | map-reduce | ✅ built |
| [`cli_pipeline`](#cli_pipeline--sequential-refinement) | sequential | ✅ built |
| [`cli_roundtable`](#cli_roundtable--group-chat-debate) | group chat | ✅ built |
| [`cli_planner`](#cli_planner--magentic-one-ledger) | Magentic-One | ✅ built |
| [`hybrid_team` / `hybrid_swarm`](#hybrid--rest-coordinator--cli-consensus) | REST + CLI mixed | ✅ built |
| [`persona_council`](#persona-council--diverse-lens-consensus) | diverse-lens consensus | ✅ built |

---

## Composing your own

The blueprints ship as worked examples; the framework's intent is that **you
assemble teams**. A team is three choices:

```mermaid
flowchart LR
    U[You — config or Django /agent-creator/] --> P[Pick personas]
    P --> B[Pick backends per persona]
    B --> S{Pick a consensus strategy}
    S --> A1[single — cli_agent]
    S --> A2[always consensus — cli_fusion]
    S --> A3[gated consensus — cli_orchestrator]
    S --> A4[debate — cli_roundtable]
    S --> A5[sequential — cli_pipeline]
    S --> A6[plan and delegate — cli_planner]
    S --> A7[REST plus CLI — hybrid_team]
```

A **persona** is just a backend plus a system-prompt lens. The same machinery
that runs a joke-named team runs a council of real expert lenses — only the
prompts change.

---

## Consensus invocation: always vs gated

The architectural fork that matters most: **is consensus always paid, or does a
router decide it's worth it?** Operating Swarm supports both, because the underlying
openai-agents framework lets a routing/orchestration agent *decide whether to
hand off* to a consensus panel.

```mermaid
flowchart TB
    Q[Request] --> MODE{Consensus strategy}

    MODE -->|always — cli_fusion| F[Run full panel every time]
    F --> FJ[Judge synthesizes]
    FJ --> FO[Answer]

    MODE -->|gated — cli_orchestrator| R[Cheap router answers and decides]
    R --> D{High stakes?}
    D -->|no| RO[Return router answer — 1 inference]
    D -->|yes| ESC[Escalate to consensus panel]
    ESC --> EJ[Judge synthesizes]
    EJ --> EO[Answer]
```

**Always** (`cli_fusion`) maximizes confidence on every call. **Gated**
(`cli_orchestrator`) is the agentic-handoff model: spend one cheap inference,
and only pay for consensus when the question is correctness-critical or
contested. Same panel, different *trigger*.

---

## `cli_agent` — single backend ✅

Expose one CLI over the API, with an ordered failover chain so a dead or
unauthenticated backend hands off to the next.

```mermaid
sequenceDiagram
    participant Client
    participant BP as cli_agent
    participant P as Primary CLI
    participant F as Fallback CLI
    Client->>BP: prompt
    BP->>P: run prompt
    alt primary ok
        P-->>BP: answer
    else primary fails
        P-->>BP: error
        BP->>F: run prompt
        F-->>BP: answer
    end
    BP-->>Client: final answer
```

---

## `cli_fusion` — concurrent panel + judge ✅

Fan one prompt to a panel of CLIs **in parallel**, then a judge compares (not
concatenates) their answers and synthesizes one, optionally iterating a bounded
master-plan loop. Survivors carry the round if a panelist dies.

```mermaid
sequenceDiagram
    participant Client
    participant BP as cli_fusion
    participant G as gemini
    participant C as claude
    participant K as grok
    participant J as judge claude
    Client->>BP: prompt
    par concurrent panel
        BP->>G: prompt
        BP->>C: prompt
        BP->>K: prompt
    end
    G-->>BP: answer A
    C-->>BP: answer B
    K-->>BP: answer C
    BP->>J: compare A B C and synthesize
    J-->>BP: synthesis plus analysis
    Note over BP,J: analysis lists consensus, contradictions, gaps, unique insights
    BP-->>Client: synthesized answer
```

Live proof: [`docs/proofs/tri_cli_fusion_run.txt`](./proofs/tri_cli_fusion_run.txt).

---

## `cli_orchestrator` — handoff / escalation ✅

A cheap router CLI answers directly and decides whether the question is
high-stakes. Routine questions cost a single inference; only contested ones
escalate to a full consensus panel.

```mermaid
sequenceDiagram
    participant Client
    participant BP as cli_orchestrator
    participant R as router gemini
    participant Panel as panel plus judge
    Client->>BP: prompt
    BP->>R: answer and decide escalate
    R-->>BP: answer plus escalate flag
    alt escalate is false
        BP-->>Client: router answer
    else escalate is true
        BP->>Panel: run consensus
        Panel-->>BP: synthesized answer
        BP-->>Client: escalated answer
    end
```

Live proof: [`docs/proofs/orchestrator_escalation_run.txt`](./proofs/orchestrator_escalation_run.txt).

---

## `cli_map` — map-reduce ✅

Split one task into independent subtasks, distribute them across worker CLIs in
parallel (round-robin), and reduce the results into one answer.

```mermaid
sequenceDiagram
    participant Client
    participant BP as cli_map
    participant PL as planner
    participant W1 as worker A
    participant W2 as worker B
    participant RD as reducer
    Client->>BP: task
    BP->>PL: decompose into subtasks
    PL-->>BP: subtask list
    par distribute round robin
        BP->>W1: subtask 1
        BP->>W2: subtask 2
    end
    W1-->>BP: result 1
    W2-->>BP: result 2
    BP->>RD: combine results
    RD-->>BP: merged answer
    BP-->>Client: final answer
```

---

## `cli_pipeline` — sequential refinement ✅

A staged chain where each CLI refines the previous stage's output. Different
backends play to their strengths in order — for example a fast model drafts, a
strong model reviews, a third polishes. Distinct from `cli_fusion`: stages are
**sequential and dependent**, not a parallel panel.

```mermaid
sequenceDiagram
    participant Client
    participant BP as cli_pipeline
    participant S1 as stage 1 draft
    participant S2 as stage 2 review
    participant S3 as stage 3 polish
    Client->>BP: prompt
    BP->>S1: prompt
    S1-->>BP: draft
    BP->>S2: refine the draft
    S2-->>BP: reviewed draft
    BP->>S3: polish the reviewed draft
    S3-->>BP: final
    BP-->>Client: final answer
    Note over BP,S3: each stage sees the running output, not the original only
```

---

## `cli_roundtable` — group-chat debate ✅

Several CLIs **debate in a shared transcript** across bounded rounds. Each round
every debater sees the others' latest positions; a moderator decides whether to
run another round or conclude, then synthesizes. Distinct from `cli_fusion`:
debaters react to each other across rounds, not just answer once.

```mermaid
sequenceDiagram
    participant Client
    participant BP as cli_roundtable
    participant D1 as debater gemini
    participant D2 as debater claude
    participant M as moderator
    Client->>BP: question
    loop bounded rounds
        par debaters respond to shared transcript
            BP->>D1: respond given transcript
            BP->>D2: respond given transcript
        end
        D1-->>BP: position 1
        D2-->>BP: position 2
        BP->>M: continue or conclude
        alt conclude
            M-->>BP: final synthesis
        else continue
            M-->>BP: next prompt for the table
        end
    end
    BP-->>Client: synthesized conclusion
```

---

## `cli_planner` — Magentic-One ledger ✅

A planner maintains a **task ledger**, delegates subtasks to specialist CLIs,
inspects results, and **re-plans on stall** up to a bound before synthesizing.
Distinct from `cli_map`: planning is iterative and reactive, not a single
decompose-then-reduce.

```mermaid
sequenceDiagram
    participant Client
    participant BP as cli_planner
    participant PL as planner
    participant Led as task ledger
    participant Spec as specialist CLI
    Client->>BP: goal
    BP->>PL: build initial plan
    PL-->>Led: ledger of subtasks
    loop until done or max rounds
        BP->>Led: next open subtask
        Led-->>BP: subtask
        BP->>Spec: do subtask
        Spec-->>BP: result
        BP->>PL: progress check given result
        alt stalled
            PL-->>Led: revise plan
        else progressing
            PL-->>Led: mark done and continue
        end
    end
    BP->>PL: synthesize final from ledger
    PL-->>BP: final answer
    BP-->>Client: final answer
```

---

## Hybrid — REST coordinator + CLI consensus ✅

`hybrid_team` / `hybrid_swarm` mix the two worlds: a **REST/LLM coordinator** (an
openai-agents `Agent`) reasons, then **delegates mid-run** to CLI personas and a
consensus panel — both exposed to it as *function tools*. This is the agentic
handoff in its fullest form: the model itself decides to reach for a CLI persona
or to call for consensus.

```mermaid
sequenceDiagram
    participant Client
    participant Co as REST coordinator LLM
    participant Persona as grok CLI persona
    participant Panel as consensus panel
    participant J as judge
    Client->>Co: prompt
    Co->>Co: reason and plan
    Co->>Persona: delegate sub-question via tool call
    Persona-->>Co: persona answer
    Co->>Panel: call for consensus via tool call
    Panel->>J: compare answers
    J-->>Panel: synthesis
    Panel-->>Co: consensus answer
    Co-->>Client: REST plan plus persona plus consensus, combined
```

Verified live — one response carried all three: `REST plan: … / grok persona:
Berlin / Consensus: Berlin`.

---

## Persona council — diverse-lens consensus ✅

`persona_council` is a panel where each member is the same backend wearing a
different **expert lens** (a system-prompt persona), fanned out in parallel, then
reconciled. Consensus comes from *perspective diversity*, not redundancy — the
judge reports agreement, genuine disagreement, and a synthesized position with
the trade-offs named. Built-in councils (`ethics`, `science`, `psych`,
`decision`, `red_team`) need no config; pick one with `params.council`, pass an
explicit `personas` roster, or add your own in a `persona_council` config block.

Verified live (`council: ethics` on claude): the judge reported *"four of the
five lenses converge… Kantian, Virtue, Rawlsian, and Care all reject
pre-programmed sacrifice"* — agreement and the utilitarian tension, both named.

```mermaid
sequenceDiagram
    participant Client
    participant BP as persona council
    participant L1 as lens A — e.g. Utilitarian
    participant L2 as lens B — e.g. Kantian
    participant L3 as lens C — e.g. Virtue ethics
    participant J as judge or moderator
    Client->>BP: question
    par each lens answers through its framework
        BP->>L1: question framed as lens A
        BP->>L2: question framed as lens B
        BP->>L3: question framed as lens C
    end
    L1-->>BP: view A
    L2-->>BP: view B
    L3-->>BP: view C
    BP->>J: reconcile the views
    J-->>BP: consensus, tensions, synthesized position
    BP-->>Client: multi-lens answer
```

Swap the roster for any domain: philosophers, scientists, psychologists,
economists, a security red-team. The lenses are **data** (config presets), not
code.

---

## Choosing a pattern

| If you want | Use |
|---|---|
| One CLI, with a backup if it is down | `cli_agent` |
| The best single answer from several models | `cli_fusion` |
| Cheap by default, rigorous only when it matters | `cli_orchestrator` |
| To split a big task across workers and merge | `cli_map` |
| Staged refinement, draft then review then polish | `cli_pipeline` |
| Models to argue toward a conclusion | `cli_roundtable` |
| A planner to drive specialists toward a goal | `cli_planner` |
| An LLM that reasons, then reaches for CLI personas + consensus | `hybrid_team` / `hybrid_swarm` |
| Consensus from diverse expert lenses, not redundant runs | `persona_council` (`params.council`) |
| Your own personas + your own consensus rule | config preset / Django `/agent-creator/` (SPA Builder unmounted) |

See [VISION.md](./VISION.md) for how these fit the larger picture, and
[CLI_FUSION.md](./CLI_FUSION.md) for configuration of the built blueprints.

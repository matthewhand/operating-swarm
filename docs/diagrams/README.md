# Open Swarm Visual Architecture Diagrams

This directory contains visual architecture diagrams for the Open Swarm platform. Each diagram is available as both an interactive, typography-tuned standalone HTML/SVG document and an inlined GitHub-rendered Mermaid diagram below.

## Index of Diagrams

| Diagram | Type | Standalone Interactive Document |
|---|---|---|
| **High-Level Architecture Stack** | Layered System Flow | [architecture-diagram.html](./architecture-diagram.html) |
| **Four Agent Seats Architecture** | Taxonomy Tree | [agent-taxonomy-tree-diagram.html](./agent-taxonomy-tree-diagram.html) |
| **Agent Execution Lifecycle** | State Machine | [agent-lifecycle-state-diagram.html](./agent-lifecycle-state-diagram.html) |
| **Multi-Agent Handoff & Delegation** | Sequence Flow | [handoff-sequence-diagram.html](./handoff-sequence-diagram.html) |
| **Protocol Evolution Roadmap** | Milestone Timeline | [protocol-evolution-timeline-diagram.html](./protocol-evolution-timeline-diagram.html) |

---

## 1. High-Level Architecture Stack

Overview of client interfaces, edge API gateway, four agent execution seats, and persistence layers.

*Interactive Standalone:* [architecture-diagram.html](./architecture-diagram.html)

```mermaid
flowchart TB
    subgraph clients ["Client & Consumer Interfaces"]
        direction LR
        WebUI["Grok-like React WebUI<br/><em>Left rail & agent workspace</em>"]
        CLI["Swarm CLI Terminal<br/><em>Interactive terminal sessions</em>"]
        External["External API Clients<br/><em>Open WebUI, SDK & cURL</em>"]
    end

    subgraph edge ["Edge API & Protocol Gateway"]
        direction LR
        REST["OpenAI REST Gateway<br/><em>/v1/chat/completions & /v1/responses</em>"]
        WS["Django Channels WebSocket<br/><em>Token streaming & async events</em>"]
        Auth["Egress Governance & Auth<br/><em>Bearer token & LLM routing</em>"]
    end

    subgraph services ["Services & Agent Execution Seats"]
        direction LR
        Router["Four Agent Seats Router<br/><em>CLI | API | Blueprint | Remote</em>"]
        Handoff["Handoff & Agent-as-Tool<br/><em>openai-agents orchestration</em>"]
        Team["Team Blueprint Engine<br/><em>Roster delegation & MoA</em>"]
    end

    subgraph data ["Data & State Persistence"]
        direction LR
        DB["Django ORM & Database<br/><em>db.sqlite3 agent configs & state</em>"]
        YAML["Agent & Blueprint YAML<br/><em>Rosters & prompt manifests</em>"]
        Memory["Swarm Memory & Audit<br/><em>Conversation turns & tool logs</em>"]
    end

    WebUI ==> REST
    REST ==> Router
    Router ==> Handoff
    Router ==> DB

    CLI -.-> WS
    External -.-> Auth
    Handoff -.-> Team
    WS -.-> YAML
    Auth -.-> Memory
```

---

## 2. Four Agent Seats Architecture (Taxonomy)

Decomposition of Open Swarm's canonical execution seats (CLI, API, Blueprint, and Remote) and concrete adapter targets.

*Interactive Standalone:* [agent-taxonomy-tree-diagram.html](./agent-taxonomy-tree-diagram.html)

```mermaid
flowchart TD
    Root["Open Swarm Seats<br/><em>4 Canonical Kinds</em>"]

    Root --> CLI["CLI Seat<br/><em>Host native binary runtime</em>"]
    Root --> API["API Seat<br/><em>True inference chat completions</em>"]
    Root ==> BP["Blueprint Seat (Focal)<br/><em>Programmatic recipes & teams</em>"]
    Root --> Remote["Remote Seat<br/><em>External autonomous harnesses</em>"]

    CLI -.-> CLI_A["Adapters:<br/>• grok / agy CLI (Native PTY)<br/>• claude / gemini (Subprocess)<br/>• opencode / codex (Local context)"]
    API -.-> API_A["Adapters:<br/>• LiteLLM Proxy (Aliasing & fallback)<br/>• Ollama / vLLM (Local weights)<br/>• OpenAI / Groq (Direct cloud)"]
    BP ==> BP_A["Composition:<br/>• Team Blueprint Subtype (Roster + handoff)<br/>• Mixture of Agents (MoA layers)<br/>• openai-agents SDK (Handoff & tool)"]
    Remote -.-> Remote_A["Harnesses:<br/>• Hermes Agent (OpenShell sandbox)<br/>• OpenMousBot / Rakazo (HTTP agent)<br/>• Herdr SSH Cluster (SSH harness)"]
```

---

## 3. Agent Execution Lifecycle

State machine detailing agent turn progression from `Idle` through `Routing`, `Running`, `Tool Execution`, and `Handoff` to final resolution.

*Interactive Standalone:* [agent-lifecycle-state-diagram.html](./agent-lifecycle-state-diagram.html)

```mermaid
stateDiagram-v2
    [*] --> Idle: Initialize
    Idle --> Routing: User Request
    Routing --> Running: Resolve Seat & Model
    Running --> Tool_Execution: Agent-as-tool Call
    Tool_Execution --> Running: Tool Result Loop
    Running --> Handoff: Delegate (Team Swarm)
    Handoff --> Completed: Resolve Turn
    Running --> Completed: Stream Finished
    Running --> Failed: Exception / Timeout
    Failed --> [*]: Error Event
    Completed --> [*]: Session Stored
```

---

## 4. Multi-Agent Handoff & Delegation Flow

End-to-end request sequence showing an edge request handed off from the orchestrator to a specialist blueprint, invoking a remote containerized agent as a tool, and streaming response tokens back.

*Interactive Standalone:* [handoff-sequence-diagram.html](./handoff-sequence-diagram.html)

```mermaid
sequenceDiagram
    autonumber
    actor User as Client / WebUI
    participant Router as Swarm Router (API Gateway)
    participant Specialist as Specialist Agent (Blueprint)
    participant Remote as Remote Agent (Hermes / OpenMousBot)

    User->>Router: POST /v1/chat/completions
    activate Router
    Router->>Specialist: handoff_to_agent(code)
    activate Specialist
    Specialist->>Specialist: synthesize plan
    Specialist->>Remote: agent_as_tool: exec
    activate Remote
    Remote-->>Specialist: sandbox execution ok
    deactivate Remote
    Specialist-->>Router: handoff response
    deactivate Specialist
    Router-->>User: SSE token stream (200 OK)
    deactivate Router
```

---

## 5. Autonomous Coordination Protocol Roadmap

Timeline of Open Swarm protocol evolution from early static socket meshes through decentralized discovery, task bidding auctions, and polyglot runtimes.

*Interactive Standalone:* [protocol-evolution-timeline-diagram.html](./protocol-evolution-timeline-diagram.html)

```mermaid
timeline
    title Open Swarm Protocol Evolution Roadmap
    2024
        OCT 2024 : v0.1 Static Mesh (hardcoded socket pipes)
        DEC 2024 : v0.4 Peer Discovery (mDNS heartbeats)
    2025
        APR 2025 : v1.0 Task Bidding (utility & capacity auctions)
        AUG 2025 : v1.8 Autonomous Consensus (byzantine fault election & self-healing)
        NOV 2025 : v2.0 Polyglot Runtimes (unified cross-model orchestration)
```

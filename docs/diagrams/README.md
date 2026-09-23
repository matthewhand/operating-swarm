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
| **CLI PTY Execution & Streaming** | Cross-Functional Swimlane | [cli-pty-execution-swimlane-diagram.html](./cli-pty-execution-swimlane-diagram.html) |
| **Domain Entity & Persistence Model** | ER Data Model | [domain-entity-er-diagram.html](./domain-entity-er-diagram.html) |
| **Safety & Sandbox Isolation Stack** | Compensating Layer Stack | [safety-sandbox-layer-stack-diagram.html](./safety-sandbox-layer-stack-diagram.html) |

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
    Running --> Tool_Execution: Call Function Tool
    Tool_Execution --> Running: Return Tool Result
    Running --> Handoff: Delegate / Transfer
    Handoff --> Running: Target Agent Turn
    Running --> Completed: Final Response (Stream End)
    Running --> Failed: Exception / Timeout
    Completed --> Idle: Await Next Turn
    Failed --> Idle: Honest Error Toast
```

---

## 4. Multi-Agent Handoff & Delegation

Sequence diagram tracing the flow of a multi-turn delegation query from the WebUI through the Router to specialized API and Remote harness agents.

*Interactive Standalone:* [handoff-sequence-diagram.html](./handoff-sequence-diagram.html)

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Router as Seat Router
    participant Specialist as Code Specialist
    participant Remote as TrueForge / OMB

    User->>Router: POST /v1/chat/completions
    activate Router
    Router->>Specialist: transfer_to_agent("specialist")
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

---

## 6. CLI PTY Execution & Bidirectional Stream Transport

Cross-functional swimlane tracking keystroke IO, pty fork lifecycle, asynchronous worker ring-buffers, and output rendering between React and host runtimes.

*Interactive Standalone:* [cli-pty-execution-swimlane-diagram.html](./cli-pty-execution-swimlane-diagram.html)

```mermaid
flowchart LR
    subgraph UI ["WebUI Frontend"]
        Mount["Mount Seat / Connect"]
        Key["Keystroke / Resize"]
        Render["Render Terminal (xterm)"]
    end
    subgraph ASGI ["ASGI & WebSocket"]
        WS["Route /ws/cli-sessions"]
        Frame["Validate IO Chunk"]
        Push["Push stdout Event"]
    end
    subgraph PTY ["PTY Session Manager"]
        Fork["pty.fork() Master FD"]
        Write["os.write(master_fd)"]
        Read["Async select() & Buffer"]
    end
    subgraph CLI ["Host Binary Runtime"]
        Exec["execvp(grok / agy)"]
        ANSI["stdout / ANSI Stream"]
    end

    Mount --> WS --> Fork --> Exec
    Key --> Frame --> Write --> Exec
    ANSI --> Read --> Push --> Render
```

---

## 7. Core Domain Entity & Persistence Relationships

Entity-relationship diagram mapping agent profiles, team rosters, persisted conversation sessions, turn records, tool execution audit events, and routine schedules.

*Interactive Standalone:* [domain-entity-er-diagram.html](./domain-entity-er-diagram.html)

```mermaid
erDiagram
    AgentProfile ||--o{ ConversationSession : owns
    AgentProfile ||--o{ TeamMember : participates
    TeamRoster ||--|{ TeamMember : contains
    ConversationSession ||--|{ TurnRecord : contains
    TurnRecord ||--o{ ToolCallEvent : emits
    AgentProfile ||--o{ RoutineSchedule : runs

    AgentProfile {
        string id PK
        string name
        string kind
        string system_prompt
        json tools_allowlist
    }
    TeamRoster {
        string id PK
        string name
        string routing_mode
        string chief_of_staff_id FK
    }
    TeamMember {
        string roster_id PK,FK
        string agent_id PK,FK
        string role_label
    }
    ConversationSession {
        uuid id PK
        string agent_id FK
        string seat_kind
        string title
    }
    TurnRecord {
        uuid id PK
        uuid session_id FK
        int turn_index
        string role
        text content
    }
    ToolCallEvent {
        uuid id PK
        uuid turn_id FK
        string tool_name
        string status
    }
    RoutineSchedule {
        string id PK
        string agent_id FK
        string cron_expression
    }
```

---

## 8. Multi-Tier Safety & Sandbox Isolation Stack

Compensating layer stack illustrating defense-in-depth from per-agent tool allowlists down through destructive command safety gates, LangChain sandbox harnesses, and egress controls.

*Interactive Standalone:* [safety-sandbox-layer-stack-diagram.html](./safety-sandbox-layer-stack-diagram.html)

```mermaid
flowchart TD
    subgraph T1 ["Tier 1: Policy & Surface"]
        direction LR
        Allowlist["Per-Agent Tool Allowlist"]
        Schema["Strict Function Schema"]
        Approval["Interactive Modal Prompt"]
    end
    subgraph T2 ["Tier 2: Safety Gate (Focal)"]
        direction LR
        Classifier["Destructive Command Scanner"]
        Confirm["Ask-User Confirmation Gate"]
        Cache["Always-Allow Session Memory"]
    end
    subgraph T3 ["Tier 3: Sandbox & Harness"]
        direction LR
        LangChain["LangChain Sandbox Wrapper"]
        Docker["Rootless Container Isolation"]
        OpenShell["OpenShell / E2B microVM"]
    end
    subgraph T4 ["Tier 4: Egress & Audit"]
        direction LR
        Redact["Token & Secret Redaction"]
        Firewall["Private LAN / Egress Guard"]
        Audit["Immutable ToolCall Audit Log"]
    end

    T1 ==> T2 ==> T3 ==> T4
```
